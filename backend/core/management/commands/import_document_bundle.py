from django.core.management.base import BaseCommand, CommandError

from core.document_engine import import_template_bundle, seed_document_catalog


class Command(BaseCommand):
    help = 'Importiert das private ZIP-Paket der acht Dokumentvorlagen.'

    def add_arguments(self, parser):
        parser.add_argument('bundle')

    def handle(self, *args, **options):
        seed_document_catalog()
        try:
            with open(options['bundle'], 'rb') as handle:
                result = import_template_bundle(handle)
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(str(result)))
