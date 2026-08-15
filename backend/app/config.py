from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COOKMARKS_", env_file=".env", extra="ignore")

    version: str = "0.2.0"
    env: str = "dev"

    # "session" (username + password, cookie sessions) or "none" (no accounts: every
    # request resolves to a single implicit user). Defaults to session so a deployment
    # that forgets the variable locks people out rather than letting them in.
    auth_mode: Literal["session", "none"] = "session"

    db_path: Path = BACKEND_ROOT / "db.sqlite3"

    # Absolute root of the Calibre library on this machine. Book.path is stored
    # relative to it, so the library can be relocated without touching the data.
    calibre_library_path: Path = Path.home() / "books" / "calibre-all"

    # Which Calibre books the live re-sync mirrors: those carrying this tag and
    # having this format. Defaults match v1's proven filter ("Food" + EPUB).
    calibre_sync_tag: str = "Food"
    calibre_sync_format: str = "EPUB"

    # Where an uploaded or downloaded book waits between staging and ingestion. In prod
    # this sits on the data volume (COOKMARKS_INGEST_STAGING_PATH=/data/ingest), so a
    # staged file survives a restart between the confirm and the worker picking it up.
    ingest_staging_path: Path = BACKEND_ROOT / "ingest-staging"
    ingest_max_bytes: int = 500_000_000

    # SvelteKit adapter-static output, served by FastAPI in production.
    frontend_dist: Path = BACKEND_ROOT.parent / "frontend" / "build"

    # Worker threads per extraction node (chapters/blocks extracted concurrently).
    # The per-minute request budget is a user-tunable Config column, not a setting.
    extraction_threads: int = 16

    # How long a run may sit QUEUED or RUNNING before startup treats it as abandoned.
    # Well above the slowest real extraction, so a genuinely in-flight run is never
    # reaped by an API restart that leaves the worker running.
    stale_run_after_hours: int = 6

    # Celery broker + result backend. Redis in dev/prod (a separate worker process
    # runs extraction off the request thread, surviving restarts); overridable via
    # COOKMARKS_CELERY_BROKER_URL / _RESULT_BACKEND. Construction never connects, so
    # importing this stays cheap; tests stub the task dispatch and never reach Redis.
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Linear "Submit a ticket" integration — all supplied via the environment
    # (COOKMARKS_LINEAR_*). The footer link stays hidden until both an API key and a
    # team are set; the project is optional. See .env.example for the values.
    linear_api_key: str = ""
    linear_team_id: str = ""
    linear_project_id: str = ""


settings = Settings()
