import json
import logging
from pathlib import Path

import pytest
from django.conf import settings
from django.forms.models import model_to_dict

from core.models import Book, Config
from core.services.extract import extract_recipe_data_from_book

logger = logging.getLogger(__name__)

BOOKS_DIR = settings.BASE_DIR / '_books'

def get_book_directories():
    return sorted([d for d in BOOKS_DIR.iterdir() if d.is_dir() and not d.name.startswith('.')])

@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('book_path', get_book_directories())
# @pytest.mark.skip
def test_extract_recipes(book_path: Path):

    
    book = Book.objects.create(
        title=book_path.name,
        author="Test Author",
        path=str(book_path),
        calibre_id="99999"
    )
    
    recipes, report = extract_recipe_data_from_book(book)

    with open(book.get_recipes_json_path(), 'w') as f:
        json.dump([r.model_dump() for r in recipes], f, indent=2, ensure_ascii=False)

    with open(book.get_report_path(), 'w') as f:
        json.dump(model_to_dict(report), f, indent=2, ensure_ascii=False, default=str)

    logger.info(f'Extracted {len(recipes)} recipes from {book.title}')
    assert recipes is not None
