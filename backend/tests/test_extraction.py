import uuid
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlite_vec
from langgraph.checkpoint.sqlite import SqliteSaver
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings as app_settings
from app.models import Base
from app.models.book import Book
from app.models.enums import AIProvider as AIProviderEnum
from app.models.enums import ExtractionMethod, ExtractionStatus
from app.models.extraction import ExtractionRun
from app.models.recipe import Recipe
from app.schemas.extraction import RecipeData
from app.services.ai import ModelRole, StubProvider, Usage, get_ai_provider, get_config
from app.services.extraction import graph
from app.services.extraction.graph import get_extraction_graph
from app.services.extraction.state import ExtractionState
from app.tasks.extraction import (
    extract_recipes_from_book,
    resume_extraction,
    save_recipes_from_graph_state,
)

# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #


def _make_engine(db_file: Path) -> Any:
    engine = create_engine(
        f"sqlite:///{db_file}", connect_args={"check_same_thread": False, "timeout": 30}
    )

    @event.listens_for(engine, "connect")
    def _configure(dbapi_conn: Any, _record: Any) -> None:
        dbapi_conn.enable_load_extension(True)
        sqlite_vec.load(dbapi_conn)
        dbapi_conn.enable_load_extension(False)
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[sessionmaker[Session]]:
    """A throwaway DB with the graph/task `SessionLocal` patched onto it, so nodes
    that open their own session read and write the test database."""
    engine = _make_engine(tmp_path / "test.sqlite3")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr("app.services.extraction.graph.SessionLocal", factory)
    monkeypatch.setattr("app.tasks.extraction.SessionLocal", factory)
    yield factory
    engine.dispose()


def _make_book(session: Session, calibre_id: int = 999) -> Book:
    book = Book(
        calibre_id=calibre_id,
        title="Test Cookbook",
        author="Test Author",
        path="Test Author/Test Cookbook (999)",
    )
    session.add(book)
    session.commit()
    return book


def _make_run(session: Session, book: Book) -> ExtractionRun:
    run = ExtractionRun(book_id=book.id, status=ExtractionStatus.RUNNING)
    session.add(run)
    session.commit()
    return run


_CONTAINER_XML = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

_OPF_XML = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>E2E</dc:title></metadata>
  <manifest>
    <item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="c2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="c1"/>
    <itemref idref="c2"/>
  </spine>
</package>"""


def _write_epub(path: Path) -> None:
    chapter = "<html><body><h1>Recipe</h1><p>Some cooking text {}</p></body></html>"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", _CONTAINER_XML)
        z.writestr("content.opf", _OPF_XML)
        z.writestr("chapter1.xhtml", chapter.format("one"))
        z.writestr("chapter2.xhtml", chapter.format("two"))


# --------------------------------------------------------------------------- #
# Pure: routing
# --------------------------------------------------------------------------- #


def test_route_post_analyse() -> None:
    assert graph.route_post_analyse({"extraction_type": "block"}) == "extract_block"
    assert graph.route_post_analyse({"extraction_type": "file"}) == "extract_file"


def test_route_post_validate_with_images() -> None:
    state: ExtractionState = {"raw_recipes": [{"name": "R", "image": "img.jpg"}], "already_tried": []}
    assert graph.route_post_validate(state) == "resolve_images"


def test_route_post_validate_no_images_first_try() -> None:
    state: ExtractionState = {"raw_recipes": [{"name": "R", "image": None}], "already_tried": []}
    assert graph.route_post_validate(state) == "await_human"


def test_route_post_validate_no_images_already_tried_block() -> None:
    state: ExtractionState = {"raw_recipes": [{"name": "R", "image": None}], "already_tried": ["block"]}
    assert graph.route_post_validate(state) == "resolve_images"


def test_route_post_human() -> None:
    assert graph.route_post_human({"human_response": "has_images"}) == "extract_block"
    assert graph.route_post_human({"human_response": "no_images"}) == "resolve_images"


def test_route_post_resolve_with_images() -> None:
    state: ExtractionState = {"raw_recipes": [{"name": "R", "image": "resolved.jpg"}], "already_tried": []}
    assert graph.route_post_resolve(state) == "finalise"


def test_route_post_resolve_no_images_with_human_response() -> None:
    state: ExtractionState = {"raw_recipes": [{"name": "R", "image": None}], "human_response": "no_images"}
    assert graph.route_post_resolve(state) == "finalise"


def test_route_post_resolve_no_images_no_human_response() -> None:
    state: ExtractionState = {"raw_recipes": [{"name": "R", "image": None}], "already_tried": []}
    assert graph.route_post_resolve(state) == "await_human"


def test_route_post_resolve_no_images_already_tried_block() -> None:
    state: ExtractionState = {"raw_recipes": [{"name": "R", "image": None}], "already_tried": ["block"]}
    assert graph.route_post_resolve(state) == "finalise"


# --------------------------------------------------------------------------- #
# Pure: RecipeData / Usage / provider
# --------------------------------------------------------------------------- #


def test_recipe_data_normalises_and_aliases() -> None:
    r = RecipeData(
        name="PASTA alla NORMA",
        recipeIngredients=["x"],
        recipeInstructions=["y"],
        recipeYield="serves 4",
    )
    assert r.name == "Pasta Alla Norma"
    assert r.yields == "Serves 4"
    assert r.ingredients == ["x"]
    dumped = r.model_dump(by_alias=True)
    assert "recipeIngredients" in dumped and "bookOrder" in dumped


def test_recipe_data_rejects_empty_ingredients() -> None:
    with pytest.raises(ValueError):
        RecipeData(name="x", recipeIngredients=[], recipeInstructions=["y"])


def test_usage_accumulation_preserves_none() -> None:
    from decimal import Decimal

    total = Usage() + Usage(cost_usd=Decimal("0.01"), input_tokens=100)
    total = total + Usage(cost_usd=Decimal("0.02"), output_tokens=5)
    assert total.cost_usd == Decimal("0.03")
    assert total.input_tokens == 100
    assert total.output_tokens == 5
    assert (Usage() + Usage()).cost_usd is None


def test_provider_registry(db: sessionmaker[Session]) -> None:
    with db() as s:
        assert get_ai_provider(s) is None  # unconfigured

    with db() as s:
        c = get_config(s)
        c.ai_provider = AIProviderEnum.GEMINI
        c.api_key = None
        s.commit()
        assert get_ai_provider(s) is None  # network provider needs a key

    with db() as s:
        c = get_config(s)
        c.ai_provider = AIProviderEnum.STUB
        s.commit()
        provider = get_ai_provider(s)
        assert isinstance(provider, StubProvider)
        assert provider.model_for(ModelRole.BLOCKS_OF_FILES) == "stub-extract"


def test_stub_extract_unique_names_and_image_match() -> None:
    provider = StubProvider(api_key="")
    ok, _ = provider.check_if_can_match_images("sample")
    assert ok is True
    r1, _ = provider.extract_recipes("chapter one", model="stub-extract")
    r2, _ = provider.extract_recipes("chapter two", model="stub-extract")
    assert len(r1) == len(r2) == 1
    assert r1[0].name != r2[0].name


def test_check_if_can_match_images_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit model overrides the provider's IMAGE_MATCH default; omitting it
    falls back to that default. This is what lets the eval pin one model end-to-end."""
    provider = StubProvider(api_key="")
    seen: list[str] = []
    real = provider._complete

    def spy(prompt: str, model: str, *, schema: dict | None = None, temp: float = 0) -> Any:
        seen.append(model)
        return real(prompt, model, schema=schema, temp=temp)

    monkeypatch.setattr(provider, "_complete", spy)
    provider.check_if_can_match_images("sample", model="custom-vision")
    provider.check_if_can_match_images("sample")
    assert seen == ["custom-vision", provider.model_for(ModelRole.IMAGE_MATCH)]


def test_model_for_respects_per_role_overrides() -> None:
    """A per-role override replaces only that role's model; the rest keep defaults."""
    provider = StubProvider(api_key="", model_overrides={"one_recipe_per_file": "custom-model"})
    assert provider.model_for(ModelRole.ONE_RECIPE_PER_FILE) == "custom-model"
    assert provider.model_for(ModelRole.MANY_RECIPES_PER_FILE) == "stub-extract"

    plain = StubProvider(api_key="")
    assert plain.model_for(ModelRole.ONE_RECIPE_PER_FILE) == "stub-extract"


# --------------------------------------------------------------------------- #
# Nodes (DB-backed, mocked EPUB/provider)
# --------------------------------------------------------------------------- #


def test_analyse_epub_file_path(db: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch) -> None:
    with db() as s:
        book = _make_book(s)
        run = _make_run(s, book)
        run_id, book_id = str(run.id), str(book.id)

    monkeypatch.setattr(
        graph, "get_chapterlike_files_from_epub", lambda _p: ["c1.xhtml", "c2.xhtml"]
    )
    monkeypatch.setattr(graph, "has_separate_image_chapters", lambda _f: False)

    result = graph.analyse_epub({"report_id": run_id, "book_id": book_id, "epub_path": "/x/y.epub"})
    assert result["extraction_type"] == "file"
    assert len(result["chapter_files"]) == 2

    with db() as s:
        run = s.get(ExtractionRun, uuid.UUID(run_id))
        assert run is not None
        assert run.total_chapters == 2
        assert run.extraction_method == ExtractionMethod.FILE
        assert run.images_in_separate_chapters is False


def test_analyse_epub_block_path(
    db: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    with db() as s:
        c = get_config(s)
        c.ai_provider = AIProviderEnum.STUB
        s.commit()
        book = _make_book(s)
        run = _make_run(s, book)
        run_id, book_id = str(run.id), str(book.id)

    monkeypatch.setattr(
        graph, "get_chapterlike_files_from_epub", lambda _p: [f"c{i}.xhtml" for i in range(200)]
    )
    monkeypatch.setattr(graph, "has_separate_image_chapters", lambda _f: True)
    monkeypatch.setattr(graph, "get_sample_chapters_content", lambda _p, _f: "sample")

    result = graph.analyse_epub({"report_id": run_id, "book_id": book_id, "epub_path": "/x/y.epub"})
    assert result["extraction_type"] == "block"  # stub image-match answers "yes"

    with db() as s:
        run = s.get(ExtractionRun, uuid.UUID(run_id))
        assert run is not None
        assert run.extraction_method == ExtractionMethod.BLOCK
        assert run.images_can_be_matched is True


def test_analyse_epub_respects_preset_image_match(
    db: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-set images_can_be_matched short-circuits the (fallible) model check: the
    eval uses this to force the block path for a book the check misjudges."""
    with db() as s:
        book = _make_book(s)
        run = _make_run(s, book)
        run.images_can_be_matched = True  # forced
        s.commit()
        run_id, book_id = str(run.id), str(book.id)

    monkeypatch.setattr(
        graph, "get_chapterlike_files_from_epub", lambda _p: [f"c{i}.xhtml" for i in range(200)]
    )
    monkeypatch.setattr(graph, "has_separate_image_chapters", lambda _f: True)

    def _should_not_run(*_a: object, **_k: object) -> str:
        raise AssertionError("image-match check must be skipped when pre-set")

    monkeypatch.setattr(graph, "get_sample_chapters_content", _should_not_run)

    result = graph.analyse_epub({"report_id": run_id, "book_id": book_id, "epub_path": "/x/y.epub"})
    assert result["extraction_type"] == "block"

    with db() as s:
        run = s.get(ExtractionRun, uuid.UUID(run_id))
        assert run is not None
        assert run.extraction_method == ExtractionMethod.BLOCK


def test_resolve_images_sets_book_fields(
    db: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    with db() as s:
        book = _make_book(s)
        run = _make_run(s, book)
        run_id, book_id = str(run.id), str(book.id)

    monkeypatch.setattr(graph, "build_image_path_lookup", lambda _p: {})
    monkeypatch.setattr(graph, "resolve_image_path_in_epub", lambda _img, _lookup: None)

    state: ExtractionState = {
        "report_id": run_id,
        "book_id": book_id,
        "epub_path": "/x.epub",
        "raw_recipes": [
            {"name": "R1", "recipeIngredients": ["a"], "recipeInstructions": ["b"]},
        ],
    }
    result = graph.resolve_images(state)
    recipe = result["raw_recipes"][0]
    assert recipe["bookOrder"] == 1
    assert recipe["author"] == "Test Author"
    assert recipe["bookTitle"] == "Test Cookbook"
    assert recipe["image"] is None


def test_finalise_marks_done(db: sessionmaker[Session]) -> None:
    with db() as s:
        book = _make_book(s)
        run = _make_run(s, book)
        run_id, book_id = str(run.id), str(book.id)

    graph.finalise(
        {
            "report_id": run_id,
            "book_id": book_id,
            "epub_path": "/x",
            "raw_recipes": [{"name": "a"}, {"name": "b"}],
        }
    )

    with db() as s:
        run = s.get(ExtractionRun, uuid.UUID(run_id))
        assert run is not None
        assert run.recipes_found == 2
        assert run.status == ExtractionStatus.DONE
        assert run.completed_at is not None


# --------------------------------------------------------------------------- #
# Save / reconcile
# --------------------------------------------------------------------------- #


def test_save_creates_recipes_with_keywords(db: sessionmaker[Session]) -> None:
    raw = [
        {
            "name": "Pasta",
            "recipeIngredients": ["x"],
            "recipeInstructions": ["y"],
            "keywords": ["Italian", "Quick"],
            "bookOrder": 1,
        }
    ]
    with db() as s:
        book = _make_book(s)
        run = _make_run(s, book)
        count = save_recipes_from_graph_state(s, book, run, raw)
        assert count == 1
        recipes = s.scalars(select(Recipe)).all()
        assert len(recipes) == 1
        assert {k.name for k in recipes[0].keywords} == {"Italian", "Quick"}
        assert recipes[0].order == 1


def test_save_reconciles_by_name_in_place(db: sessionmaker[Session]) -> None:
    first = [
        {"name": "Pasta", "recipeIngredients": ["x"], "recipeInstructions": ["y"], "bookOrder": 1}
    ]
    with db() as s:
        book = _make_book(s)
        run = _make_run(s, book)
        save_recipes_from_graph_state(s, book, run, first)
        recipe_id = s.scalars(select(Recipe)).one().id

    second = [
        {
            "name": "Pasta",
            "description": "updated",
            "recipeIngredients": ["x2"],
            "recipeInstructions": ["y2"],
            "keywords": ["Italian"],
            "bookOrder": 5,
        }
    ]
    with db() as s:
        book = s.scalars(select(Book)).one()
        run2 = _make_run(s, book)
        save_recipes_from_graph_state(s, book, run2, second)
        recipes = s.scalars(select(Recipe)).all()
        assert len(recipes) == 1  # reconciled in place, not duplicated
        assert recipes[0].id == recipe_id  # stable identity across re-extraction
        assert recipes[0].description == "updated"
        assert recipes[0].order == 5
        assert {k.name for k in recipes[0].keywords} == {"Italian"}


# --------------------------------------------------------------------------- #
# Graph compilation + end-to-end (Stub, review pause, resume)
# --------------------------------------------------------------------------- #


def test_graph_compiles_with_checkpointer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "db_path", tmp_path / "graph.sqlite3")
    get_extraction_graph.cache_clear()
    compiled = get_extraction_graph()
    assert isinstance(compiled.checkpointer, SqliteSaver)
    get_extraction_graph.cache_clear()


@pytest.fixture
def e2e(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[sessionmaker[Session], Path]]:
    db_file = tmp_path / "app.sqlite3"
    library = tmp_path / "library"
    library.mkdir()
    monkeypatch.setattr(app_settings, "db_path", db_file)
    monkeypatch.setattr(app_settings, "calibre_library_path", library)

    engine = _make_engine(db_file)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr("app.services.extraction.graph.SessionLocal", factory)
    monkeypatch.setattr("app.tasks.extraction.SessionLocal", factory)
    get_extraction_graph.cache_clear()
    yield factory, library
    get_extraction_graph.cache_clear()
    engine.dispose()


def test_end_to_end_stub_review_then_resume(e2e: tuple[sessionmaker[Session], Path]) -> None:
    factory, library = e2e

    with factory() as s:
        c = get_config(s)
        c.ai_provider = AIProviderEnum.STUB
        s.commit()
        book = Book(
            calibre_id=1,
            title="E2E Cookbook",
            author="Stub Author",
            path="Stub Author/E2E (1)",
        )
        s.add(book)
        s.commit()
        book_id = str(book.id)

    book_dir = library / "Stub Author" / "E2E (1)"
    book_dir.mkdir(parents=True)
    _write_epub(book_dir / "book.epub")

    # First pass: zero images -> pauses for human review, nothing saved yet.
    message = extract_recipes_from_book(book_id)
    assert "paused for review" in message.lower()
    with factory() as s:
        run = s.scalars(select(ExtractionRun)).one()
        assert run.status == ExtractionStatus.REVIEW
        run_id = str(run.id)
        assert s.scalars(select(Recipe)).all() == []

    # Resume answering "no_images" -> resolves, finalises, saves two recipes.
    message = resume_extraction(run_id, "no_images")
    assert "Extracted 2 recipes" in message
    with factory() as s:
        recipes = s.scalars(select(Recipe)).all()
        assert len(recipes) == 2
        assert all(r.book_id == uuid.UUID(book_id) for r in recipes)
        assert all("Stub" in {k.name for k in r.keywords} for r in recipes)
        run = s.scalars(select(ExtractionRun)).one()
        assert run.status == ExtractionStatus.DONE
        assert run.recipes_found == 2


def test_resume_rejects_invalid_response() -> None:
    with pytest.raises(ValueError):
        resume_extraction(str(uuid.uuid4()), "maybe")
