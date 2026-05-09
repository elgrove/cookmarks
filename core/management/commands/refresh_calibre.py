from django.conf import settings
from django.core.management.base import BaseCommand

from core.services.calibre import load_books_from_calibre


class Command(BaseCommand):
    help = (
        "Sync Book rows from the Calibre library at settings.CALIBRE_ROOT. "
        "Idempotent (update_or_create by calibre_id); also rewrites Book.path "
        "if CALIBRE_ROOT differs from when rows were last loaded."
    )

    def handle(self, *args, **options):
        path = settings.CALIBRE_ROOT
        self.stdout.write(f"Loading from {path}")
        created, updated = load_books_from_calibre(path)
        self.stdout.write(self.style.SUCCESS(f"{created} created, {updated} updated."))
