from django.core.management.base import BaseCommand

from core.models import Recipe
from core.services.ai import count_tokens
from core.services.embeddings import recipe_to_text


class Command(BaseCommand):
    help = "Count tokens for 10 random recipes"

    def handle(self, *args, **options):
        recipes = Recipe.objects.order_by("?")[:10]

        total_tokens = 0
        for recipe in recipes:
            text = recipe_to_text(recipe)
            tokens = count_tokens(text)
            total_tokens += tokens
            self.stdout.write(f"{recipe.name[:50]}: {tokens} tokens ({len(text)} chars)\n")

        self.stdout.write(f"\nTotal: {total_tokens} tokens for 10 recipes\n")
        self.stdout.write(f"Average: {total_tokens / 10:.0f} tokens per recipe\n")
