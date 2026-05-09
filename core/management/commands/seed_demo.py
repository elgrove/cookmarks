import json
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import (
    Book,
    Config,
    ExtractionReport,
    Recipe,
    RecipeList,
    RecipeListItem,
)
from core.services.calibre import load_books_from_calibre
from core.tasks import save_recipes_from_graph_state

logger = logging.getLogger(__name__)

FIXTURE_DIR_NAME = "_test_calibre"
WEEKNIGHT_LIST_NAME = "Weeknight"
FAVOURITES_PICK_COUNT = 3
WEEKNIGHT_PICK_COUNT = 5


class Command(BaseCommand):
    help = (
        "Idempotently populate the local DB with a representative demo dataset "
        "from _test_calibre/. Sets Config to STUB AI provider so the app runs offline."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--if-empty",
            action="store_true",
            help="No-op if any Books already exist (used by `make dev` auto-seed).",
        )
        parser.add_argument(
            "--force-config",
            action="store_true",
            help="Overwrite Config to STUB even if a real provider/api_key is set.",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        if options["if_empty"] and Book.objects.exists():
            self.stdout.write("Books already present — skipping seed.")
            return

        fixture_path = settings.BASE_DIR / FIXTURE_DIR_NAME
        if not (fixture_path / "metadata.db").exists():
            self.stderr.write(
                self.style.ERROR(
                    f"No Calibre fixture at {fixture_path}/metadata.db. "
                    "Make sure _test_calibre/ is synced to this machine."
                )
            )
            return

        self._seed_config(force=options["force_config"])
        book = self._load_book(fixture_path)
        if not book:
            return
        self._seed_recipes(book)
        self._seed_lists(book)
        self._seed_review_report(book)

        self.stdout.write(self.style.SUCCESS("seed_demo complete."))

    def _seed_config(self, *, force: bool):
        config = Config.get_solo()
        if config.ai_provider and not force:
            self.stdout.write(
                f"Config already set to {config.ai_provider}; leaving alone "
                "(use --force-config to overwrite)."
            )
            return
        config.ai_provider = "STUB"
        config.api_key = "stub"
        config.save()
        self.stdout.write(self.style.SUCCESS("Config set to STUB provider."))

    def _load_book(self, fixture_path) -> Book | None:
        created, updated = load_books_from_calibre(fixture_path)
        self.stdout.write(f"Calibre load: {created} created, {updated} updated.")
        book = Book.objects.filter(path__startswith=str(fixture_path)).first()
        if not book:
            self.stderr.write(self.style.ERROR("No Books loaded from fixture."))
        return book

    def _seed_recipes(self, book: Book):
        recipes_path = book.get_recipes_json_path()
        if not recipes_path.exists():
            self.stderr.write(
                self.style.WARNING(f"No gold recipes.json at {recipes_path}; skipping recipe seed.")
            )
            return

        with open(recipes_path) as f:
            raw_recipes = json.load(f)

        report, _ = ExtractionReport.objects.update_or_create(
            book=book,
            provider_name="STUB",
            status="done",
            defaults={
                "model_name": "stub-extract",
                "started_at": timezone.now() - timedelta(minutes=5),
                "completed_at": timezone.now(),
                "total_chapters": 1,
                "chapters_processed": [],
                "extraction_method": "block",
                "images_in_separate_chapters": False,
                "images_can_be_matched": True,
                "recipes_found": len(raw_recipes),
                "errors": [],
                "cost_usd": 0,
                "input_tokens": 0,
                "output_tokens": 0,
            },
        )

        save_recipes_from_graph_state(book, report, raw_recipes)
        self.stdout.write(
            self.style.SUCCESS(f"Seeded {Recipe.objects.filter(book=book).count()} recipes.")
        )

    def _seed_lists(self, book: Book):
        recipes = list(Recipe.objects.filter(book=book).order_by("order")[:WEEKNIGHT_PICK_COUNT])
        if not recipes:
            return

        weeknight, _ = RecipeList.objects.get_or_create(
            name=WEEKNIGHT_LIST_NAME, defaults={"is_default": False}
        )
        for r in recipes:
            RecipeListItem.objects.get_or_create(recipe_list=weeknight, recipe=r)

        favourites = RecipeList.get_favourites()
        for r in recipes[:FAVOURITES_PICK_COUNT]:
            RecipeListItem.objects.get_or_create(recipe_list=favourites, recipe=r)

        self.stdout.write(
            f"Lists: '{WEEKNIGHT_LIST_NAME}' ({weeknight.recipes.count()}), "
            f"'Favourites' ({favourites.recipes.count()})."
        )

    def _seed_review_report(self, book: Book):
        ExtractionReport.objects.update_or_create(
            book=book,
            provider_name="STUB",
            status="review",
            defaults={
                "model_name": "stub-extract",
                "started_at": timezone.now() - timedelta(minutes=2),
                "total_chapters": 3,
                "chapters_processed": [],
                "extraction_method": "block",
                "images_in_separate_chapters": True,
                "recipes_found": 0,
                "errors": [],
                "cost_usd": 0,
                "input_tokens": 0,
                "output_tokens": 0,
            },
        )
        self.stdout.write("Review-status ExtractionReport seeded.")
