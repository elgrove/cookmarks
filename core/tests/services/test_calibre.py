import pytest

from core.models import Book
from core.services.calibre import load_books_from_calibre
from core.tests.conftest import TEST_CALIBRE_BOOK, TEST_CALIBRE_DIR


@pytest.mark.django_db(transaction=True)
class TestLoadBooksFromCalibre:
    def test_load_books_creates_book_record(self, db):
        if not TEST_CALIBRE_DIR.exists():
            pytest.skip(f"Test calibre directory not found: {TEST_CALIBRE_DIR}")

        # Ensure no books exist before loading
        assert Book.objects.count() == 0

        created_count, updated_count = load_books_from_calibre(TEST_CALIBRE_DIR)

        # Should have created at least one book
        assert created_count >= 1
        assert Book.objects.count() >= 1

        # Verify the test book was loaded correctly
        book = Book.objects.filter(title=TEST_CALIBRE_BOOK["title"]).first()
        assert book is not None, f"Expected book '{TEST_CALIBRE_BOOK['title']}' not found"
        assert book.author == TEST_CALIBRE_BOOK["author"]
        assert book.calibre_id is not None
        assert book.path is not None

    def test_loaded_book_has_valid_epub_path(self, db):
        if not TEST_CALIBRE_DIR.exists():
            pytest.skip(f"Test calibre directory not found: {TEST_CALIBRE_DIR}")

        load_books_from_calibre(TEST_CALIBRE_DIR)

        book = Book.objects.filter(title=TEST_CALIBRE_BOOK["title"]).first()
        assert book is not None

        # The book's get_epub_path method should return a valid path
        epub_path = book.get_epub_path()
        assert epub_path is not None
        assert epub_path.exists(), f"EPUB file not found at {epub_path}"
        assert epub_path.suffix == ".epub"

    def test_load_books_updates_existing_records(self, db):
        if not TEST_CALIBRE_DIR.exists():
            pytest.skip(f"Test calibre directory not found: {TEST_CALIBRE_DIR}")

        # First load
        created_count_1, updated_count_1 = load_books_from_calibre(TEST_CALIBRE_DIR)
        book_count_after_first = Book.objects.count()

        # Second load should update, not create
        created_count_2, updated_count_2 = load_books_from_calibre(TEST_CALIBRE_DIR)

        # No new books should be created
        assert created_count_2 == 0
        assert updated_count_2 == created_count_1
        assert Book.objects.count() == book_count_after_first
