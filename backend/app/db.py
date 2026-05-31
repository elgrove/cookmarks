from collections.abc import Iterator
from typing import Annotated, Any

import sqlite_vec
from fastapi import Depends
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _configure_connection(dbapi_conn: Any, _record: Any) -> None:
    dbapi_conn.enable_load_extension(True)
    sqlite_vec.load(dbapi_conn)
    dbapi_conn.enable_load_extension(False)
    # SQLite ignores foreign keys (and ON DELETE) unless enabled per connection.
    dbapi_conn.execute("PRAGMA foreign_keys=ON")


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


# Shared FastAPI dependency alias for an ORM session.
SessionDep = Annotated[Session, Depends(get_session)]
