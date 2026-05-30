from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COOKMARKS_", env_file=".env", extra="ignore")

    version: str = "0.2.0"
    env: str = "dev"

    db_path: Path = BACKEND_ROOT / "db.sqlite3"

    # SvelteKit adapter-static output, served by FastAPI in production.
    frontend_dist: Path = BACKEND_ROOT.parent / "frontend" / "build"

    # Broker is deferred until the real worker is ported; defaults keep imports cheap.
    celery_broker_url: str = "memory://"
    celery_result_backend: str = "cache+memory://"


settings = Settings()
