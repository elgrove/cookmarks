from unittest.mock import patch

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from core.models import Book, ExtractionReport
from core.services.extraction.graph import (
    analyse_epub,
    app,
    finalise,
    resolve_images,
    route_post_analyse,
    route_post_human,
    route_post_resolve,
    route_post_validate,
    validate,
)


@pytest.fixture
def mock_book():
    book = Book.objects.create(
        calibre_id=999,
        title="Test Cookbook",
        author="Test Author",
        path="/fake/path/to/book",
    )
    return book


@pytest.fixture
def mock_report(mock_book):
    report = ExtractionReport.objects.create(
        book=mock_book,
        provider_name="GEMINI",
        total_chapters=0,
        chapters_processed=[],
        recipes_found=0,
        errors=[],
        status="running",
    )
    return report


@pytest.fixture
def initial_state(mock_book, mock_report):
    return {
        "book_id": str(mock_book.id),
        "epub_path": "/fake/path/to/book/test.epub",
        "report_id": str(mock_report.id),
        "already_tried": [],
    }


@pytest.mark.django_db
class TestExtractionGraph:
    def test_graph_compilation(self):
        assert app is not None
        assert app.checkpointer is not None
        assert isinstance(app.checkpointer, SqliteSaver)

    @patch("core.services.extraction.graph.get_chapterlike_files_from_epub")
    @patch("core.services.extraction.graph.has_separate_image_chapters")
    def test_analyse_epub_node(
        self, mock_has_separate, mock_get_files, mock_book, mock_report, initial_state
    ):
        mock_get_files.return_value = ["chapter1.xhtml", "chapter2.xhtml"]
        mock_has_separate.return_value = False

        result = analyse_epub(initial_state)

        assert "chapter_files" in result
        assert "extraction_type" in result
        assert result["extraction_type"] == "file"
        assert len(result["chapter_files"]) == 2

        mock_report.refresh_from_db()
        assert mock_report.total_chapters == 2
        assert mock_report.extraction_method == "file"

    @patch("core.services.extraction.graph.get_config")
    @patch("core.services.extraction.graph.get_chapterlike_files_from_epub")
    @patch("core.services.extraction.graph.has_separate_image_chapters")
    @patch("core.services.extraction.graph.get_sample_chapters_content")
    def test_analyse_epub_with_separate_images(
        self,
        mock_sample_content,
        mock_has_separate,
        mock_get_files,
        mock_get_config,
        mock_book,
        mock_report,
        initial_state,
    ):
        mock_get_files.return_value = ["chapter1.xhtml", "chapter2.xhtml"]
        mock_has_separate.return_value = True
        mock_sample_content.return_value = "sample content"

        mock_config = mock_get_config.return_value
        mock_config.ai_provider = "GEMINI"

        with patch("core.services.extraction.graph.GeminiProvider") as mock_provider:
            provider_instance = mock_provider.return_value
            provider_instance.check_if_can_match_images.return_value = (
                True,
                {"cost_usd": 0.001, "input_tokens": 100, "output_tokens": 10},
            )

            result = analyse_epub(initial_state)

            assert result["extraction_type"] == "block"
            assert result["images_in_separate_chapters"] is True

            mock_report.refresh_from_db()
            assert mock_report.extraction_method == "block"
            assert mock_report.images_can_be_matched is True

    def test_validate_node_with_images(self, initial_state):
        state_with_recipes = {
            **initial_state,
            "raw_recipes": [
                {"name": "Recipe 1", "image": "image1.jpg"},
                {"name": "Recipe 2", "image": None},
            ],
        }

        result = validate(state_with_recipes)
        assert result == {}

    def test_route_post_analyse_file(self, initial_state):
        state = {**initial_state, "extraction_type": "file"}
        assert route_post_analyse(state) == "extract_file"

    def test_route_post_analyse_block(self, initial_state):
        state = {**initial_state, "extraction_type": "block"}
        assert route_post_analyse(state) == "extract_block"

    def test_route_post_validate_with_images(self, initial_state):
        state = {
            **initial_state,
            "raw_recipes": [{"name": "Recipe", "image": "image.jpg"}],
            "already_tried": [],
        }
        assert route_post_validate(state) == "resolve_images"

    def test_route_post_validate_no_images_first_try(self, initial_state):
        state = {
            **initial_state,
            "raw_recipes": [{"name": "Recipe", "image": None}],
            "already_tried": [],
        }
        assert route_post_validate(state) == "await_human"

    def test_route_post_validate_no_images_already_tried_block(self, initial_state):
        state = {
            **initial_state,
            "raw_recipes": [{"name": "Recipe", "image": None}],
            "already_tried": ["block"],
        }
        assert route_post_validate(state) == "resolve_images"

    def test_route_post_human_has_images(self, initial_state):
        state = {**initial_state, "human_response": "has_images"}
        assert route_post_human(state) == "extract_block"

    def test_route_post_human_no_images(self, initial_state):
        state = {**initial_state, "human_response": "no_images"}
        assert route_post_human(state) == "resolve_images"

    @patch("core.services.extraction.utils.build_image_path_lookup")
    @patch("core.services.extraction.utils.resolve_image_path_in_epub")
    def test_resolve_images_node(
        self, mock_resolve, mock_build_lookup, mock_book, mock_report, initial_state
    ):
        mock_build_lookup.return_value = {"image1.jpg": ["OEBPS/images/image1.jpg"]}
        mock_resolve.return_value = "OEBPS/images/image1.jpg"

        state = {
            **initial_state,
            "raw_recipes": [
                {"name": "Recipe 1", "image": "image1.jpg"},
            ],
        }

        result = resolve_images(state)

        recipes = result["raw_recipes"]
        assert recipes[0]["bookOrder"] == 1
        assert recipes[0]["author"] == "Test Author"
        assert recipes[0]["bookTitle"] == "Test Cookbook"

    def test_finalise_node(self, mock_book, mock_report, initial_state):
        state = {
            **initial_state,
            "raw_recipes": [
                {"name": "Recipe 1"},
                {"name": "Recipe 2"},
            ],
        }

        finalise(state)

        mock_report.refresh_from_db()
        assert mock_report.recipes_found == 2
        assert mock_report.status == "done"
        assert mock_report.completed_at is not None

    def test_route_post_resolve_with_images(self, initial_state):
        state = {
            **initial_state,
            "raw_recipes": [{"name": "Recipe", "image": "resolved_image.jpg"}],
            "already_tried": [],
        }
        assert route_post_resolve(state) == "finalise"

    def test_route_post_resolve_no_images_with_human_response(self, initial_state):
        state = {
            **initial_state,
            "raw_recipes": [{"name": "Recipe", "image": None}],
            "already_tried": [],
            "human_response": "no_images",
        }
        assert route_post_resolve(state) == "finalise"

    def test_route_post_resolve_no_images_no_human_response(self, initial_state):
        state = {
            **initial_state,
            "raw_recipes": [{"name": "Recipe", "image": None}],
            "already_tried": [],
        }
        assert route_post_resolve(state) == "await_human"

    def test_route_post_resolve_no_images_already_tried_block(self, initial_state):
        state = {
            **initial_state,
            "raw_recipes": [{"name": "Recipe", "image": None}],
            "already_tried": ["block"],
        }
        assert route_post_resolve(state) == "finalise"
