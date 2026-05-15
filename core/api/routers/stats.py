import random
from datetime import date

from django.db.models import Count
from ninja import Router

from core.api.schemas import HomeStats
from core.models import Book, Config, Recipe

router = Router()


@router.get("/home", response=HomeStats)
def home_stats(request):
    books = list(Book.objects.all())
    has_books = len(books) > 0
    has_recipes = Recipe.objects.exists()
    is_configured = Config.is_configured()

    book_of_the_day = None
    if has_books:
        today = date.today()
        random.seed(int(today.strftime("%Y%m%d")))
        chosen = random.choice(books)
        recipe_count = (
            Book.objects.filter(id=chosen.id)
            .annotate(rc=Count("recipes"))
            .values_list("rc", flat=True)
            .first()
            or 0
        )
        book_of_the_day = {
            "id": chosen.id,
            "calibre_id": chosen.calibre_id,
            "title": chosen.title,
            "clean_title": chosen.clean_title,
            "author": chosen.author,
            "pubdate": chosen.pubdate,
            "isbn": chosen.isbn or "",
            "description": chosen.description or "",
            "recipe_count": recipe_count,
        }

    return {
        "has_books": has_books,
        "has_recipes": has_recipes,
        "is_configured": is_configured,
        "books_count": len(books),
        "book_of_the_day": book_of_the_day,
    }
