"""The isolated database the eval runs against.

The extraction pipeline is database-coupled: its nodes read Book/Config and write
TaskRun through a module-level session factory, and the LangGraph checkpointer
opens ``settings.db_path``. So the eval stands up its own throwaway SQLite, seeds just
the Config and Book rows it needs (copied from the real app DB), and rebinds the
pipeline onto it. Prod data is never read for recipes nor written at all.

Rebinding mirrors what the test fixtures do; it is deliberate and contained to this
module so the rest of the suite stays free of global state.
"""

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

import sqlite_vec
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models import Base, Book
from app.models.enums import AIProvider
from app.services.ai import get_config, provider_requires_api_key
from app.services.extraction import graph
from app.services.extraction.graph import get_extraction_graph
from evals.config import EVALS_DIR

logger = logging.getLogger(__name__)

EVAL_DB_PATH = EVALS_DIR / "eval.sqlite3"

# The app DB to read the provider key from when the environment doesn't supply one,
# captured before any rebind. Books are resolved from the Calibre library, not here.
_CONFIG_DB_PATH = settings.db_path

_KEY_ENV_VAR = {
    "ANTHROPIC": "ANTHROPIC_API_KEY",
    "GEMINI": "GEMINI_API_KEY",
    "OPENROUTER": "OPENROUTER_API_KEY",
}


def make_engine(db_path: Path) -> Any:
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False, "timeout": 30}
    )

    @event.listens_for(engine, "connect")
    def _configure(dbapi_conn: Any, _record: Any) -> None:
        dbapi_conn.enable_load_extension(True)
        sqlite_vec.load(dbapi_conn)
        dbapi_conn.enable_load_extension(False)
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def _resolve_book_in_calibre(calibre_id: int) -> dict[str, Any]:
    """Find a book by its Calibre id in the library on disk. Calibre lays books out as
    ``<author>/<title> (<id>)/``, so the directory gives path, title and author with no
    dependency on a seeded app database."""
    library = settings.calibre_library_path
    matches = sorted(library.glob(f"*/*({calibre_id})"))
    if not matches:
        raise RuntimeError(f"No book directory for calibre_id {calibre_id} under {library}")
    book_dir = matches[0]
    return {
        "calibre_id": calibre_id,
        "title": book_dir.name,
        "author": book_dir.parent.name,
        "path": str(book_dir.relative_to(library)),
    }


_PROD_DB_PATH = Path("/home/aaron/docker/cookmarks/data/db.sqlite3")


def _read_config_keys() -> dict[str, str]:
    for db_path in (_CONFIG_DB_PATH, _PROD_DB_PATH):
        if not db_path.exists():
            continue
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                row = conn.execute(
                    "SELECT ai_provider, api_key, assistant_provider, assistant_api_key FROM config WHERE id = 1"
                ).fetchone()
            finally:
                conn.close()
        except sqlite3.OperationalError:
            continue
        if not row:
            continue
        keys: dict[str, str] = {}
        if row[0] and row[1]:
            keys[str(row[0])] = str(row[1])
            keys[str(row[0]).lower()] = str(row[1])
        if len(row) > 3 and row[2] and row[3]:
            keys[str(row[2])] = str(row[3])
            keys[str(row[2]).lower()] = str(row[3])
        if keys:
            return keys
    return {}


def resolve_api_key(provider: str) -> str:
    """Find the provider's key: environment first (ANTHROPIC_API_KEY / GEMINI_API_KEY / OPENROUTER_API_KEY),
    then the app DB's Config if it holds a key for this same provider. Keyless providers
    (e.g. the offline stub) need nothing, so return an empty string."""
    if not provider_requires_api_key(provider):
        return ""

    env_var = _KEY_ENV_VAR.get(provider)
    if env_var and os.environ.get(env_var):
        return os.environ[env_var]

    keys = _read_config_keys()
    if provider in keys:
        return keys[provider]

    hint = f"set {env_var}" if env_var else "configure it in the app DB"
    raise RuntimeError(f"No API key for provider {provider!r}; {hint} (or {_CONFIG_DB_PATH}).")


def build_eval_database(calibre_ids: list[int], *, reset: bool = True) -> sessionmaker[Session]:
    """Create a fresh eval DB (current ORM schema) seeded with the requested books."""
    if reset and EVAL_DB_PATH.exists():
        EVAL_DB_PATH.unlink()
    EVAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    engine = make_engine(EVAL_DB_PATH)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with factory() as session:
        for calibre_id in calibre_ids:
            book = _resolve_book_in_calibre(calibre_id)
            session.add(
                Book(
                    calibre_id=book["calibre_id"],
                    title=book["title"],
                    author=book["author"],
                    path=book["path"],
                )
            )
        session.commit()

    logger.info(f"Built eval DB at {EVAL_DB_PATH} with {len(calibre_ids)} book(s)")
    return factory


def set_provider(
    factory: sessionmaker[Session],
    provider: str,
    api_key: str,
    model_overrides: dict[str, str] | None = None,
) -> None:
    """Point the eval DB's singleton Config at a provider + key (and optional per-role
    model overrides) for the next book run."""
    with factory() as session:
        config = get_config(session)
        config.ai_provider = AIProvider(provider)
        config.api_key = api_key
        config.model_overrides = model_overrides
        session.commit()


def set_assistant_provider(
    factory: sessionmaker[Session], provider: str, api_key: str, model: str
) -> None:
    with factory() as session:
        config = get_config(session)
        config.assistant_provider = AIProvider(provider)
        config.assistant_api_key = api_key
        config.model_overrides = {"assistant": model}
        session.commit()


def bind_pipeline(factory: sessionmaker[Session]) -> None:
    """Rebind the extraction pipeline (graph nodes + LangGraph checkpointer) onto the
    eval DB. Call once, after building the DB, before invoking the graph."""
    graph.SessionLocal = factory
    settings.db_path = EVAL_DB_PATH
    get_extraction_graph.cache_clear()
