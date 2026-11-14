from django.core.management.base import BaseCommand
from django.utils.text import slugify

from marketplace.models import ActivityTag


class Command(BaseCommand):
    help = "Create the standard companion activity categories."

    def handle(self, *args, **options):
        names = [
            "Date",
            "Event partner",
            "Movie partner",
            "Shopping",
            "Dining",
            "Travel buddy",
            "Sports partner",
            "Other",
        ]
        for name in names:
            ActivityTag.objects.get_or_create(name=name, defaults={"slug": slugify(name)})
        self.stdout.write(self.style.SUCCESS("Activity categories are ready."))