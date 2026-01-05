import logging
import time

from django.core.management.base import BaseCommand

from core.models import Recipe
from core.services.embeddings import VectorStore, generate_recipe_embedding

logger = logging.getLogger(__name__)

REGENERATE_ALL = False
BATCH_SIZE = 50
DELAY_SECONDS = 0.2


class Command(BaseCommand):
    help = "Backfill embeddings for all existing recipes that don't have embeddings yet"

    def handle(self, *args, **options):
        store = VectorStore()

        total_recipes = Recipe.objects.count()
        self.stdout.write(f"Total recipes in database: {total_recipes}\n")

        if REGENERATE_ALL:
            self.stdout.write("Re-embedding ALL recipes...\n")
            recipes = Recipe.objects.select_related("book").prefetch_related("keywords").all()
        else:
            self.stdout.write("Embedding recipes without existing embeddings...\n")
            conn = store._get_connection()
            try:
                cursor = conn.execute("SELECT recipe_id FROM recipe_embeddings")
                embedded_ids = {row[0] for row in cursor.fetchall()}
            finally:
                conn.close()

            recipes = (
                Recipe.objects.exclude(id__in=embedded_ids)
                .select_related("book")
                .prefetch_related("keywords")
            )

        recipes_to_process = recipes.count()
        self.stdout.write(f"Recipes to process: {recipes_to_process}\n")
        self.stdout.write("-" * 80 + "\n")

        if recipes_to_process == 0:
            self.stdout.write(self.style.SUCCESS("No recipes need embedding!\n"))
            return

        processed = 0
        failed = 0
        start_time = time.time()

        for recipe in recipes.iterator(chunk_size=BATCH_SIZE):
            try:
                generate_recipe_embedding(recipe)
                processed += 1

                if processed % 10 == 0:
                    elapsed = time.time() - start_time
                    rate = processed / elapsed if elapsed > 0 else 0
                    remaining = recipes_to_process - processed
                    eta = remaining / rate if rate > 0 else 0
                    self.stdout.write(
                        f"Processed {processed}/{recipes_to_process} "
                        f"({processed * 100 / recipes_to_process:.1f}%) - "
                        f"ETA: {eta:.0f}s\n"
                    )

                if DELAY_SECONDS > 0:
                    time.sleep(DELAY_SECONDS)

            except Exception as e:
                failed += 1
                logger.warning(f"Failed to embed recipe {recipe.id} ({recipe.name}): {e}")
                if failed <= 5:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Failed to generate embedding: {recipe.name[:50]} - {e}\n"
                        )
                    )

        elapsed = time.time() - start_time
        self.stdout.write("\n" + "=" * 80 + "\n")
        self.stdout.write("SUMMARY\n")
        self.stdout.write("-" * 80 + "\n")
        self.stdout.write(f"Total processed: {processed}\n")
        self.stdout.write(f"Failed: {failed}\n")
        self.stdout.write(f"Time elapsed: {elapsed:.1f}s\n")

        self.stdout.write(
            self.style.SUCCESS(f"\nSuccessfully generated embeddings for {processed} recipes\n")
        )
