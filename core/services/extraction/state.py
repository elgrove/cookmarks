from typing import Literal, TypedDict


class ExtractionState(TypedDict, total=False):
    book_id: str
    epub_path: str
    report_id: str

    chapter_files: list[str]
    extraction_type: Literal["file", "block"]
    images_in_separate_chapters: bool | None
    images_can_be_matched: bool | None

    raw_recipes: list[dict]
    already_tried: list[str]

    human_response: str | None
