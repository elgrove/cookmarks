from enum import StrEnum, auto


class BookLayoutType(StrEnum):
    CHAPTER_PER_FILE = 'chapter_per_file' # 1
    RECIPE_AND_PHOTO_PER_FILE = 'recipe_and_photo_per_file' # 2
    SEPERATE_PHOTO_FILES = 'seperate_photo_files' # 3


def classify_book_layout(chapter_files: int) -> BookLayoutType:
    if chapter_files < 30:
        return BookLayoutType.CHAPTER_PER_FILE

    if 30 <= chapter_files <= 180:
        return BookLayoutType.RECIPE_AND_PHOTO_PER_FILE

    return BookLayoutType.SEPERATE_PHOTO_FILES
