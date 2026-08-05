from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CalibreExclusion(Base):
    """A Calibre book id deliberately kept out of Cookmarks. Deleting a book that is still
    in the library would otherwise be undone by the next sync, which upserts by
    `calibre_id`; an exclusion makes the sync skip it for good. The title is kept only so
    the sync report can name what it skipped."""

    __tablename__ = "calibre_exclusions"

    calibre_id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500), default="")
