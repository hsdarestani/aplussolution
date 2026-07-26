import os

from django.core.management.base import BaseCommand

from core.document_engine import seed_document_catalog
from core.models import Position, User


class Command(BaseCommand):
    help = 'Erstellt Grunddaten, Dokumentkatalog und den ersten Administrator.'

    def handle(self, *args, **kwargs):
        email = os.getenv('DJANGO_SUPERUSER_EMAIL')
        if email and not User.objects.filter(email=email).exists():
            User.objects.create_superuser(
                email=email,
                password=os.getenv('DJANGO_SUPERUSER_PASSWORD'),
                first_name=os.getenv('DJANGO_SUPERUSER_FIRST_NAME', 'A+'),
                last_name=os.getenv('DJANGO_SUPERUSER_LAST_NAME', 'Admin'),
            )
        for name in ['Servicekraft', 'Hostess', 'Eventhelfer', 'Lagerhelfer', 'Inventurhelfer', 'Promoter', 'Logistiker']:
            Position.objects.get_or_create(name=name)
        result = seed_document_catalog()
        self.stdout.write(self.style.SUCCESS(f'Grunddaten sind bereit. Dokumentkatalog: {result}'))
