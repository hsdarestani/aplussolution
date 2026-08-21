import json

from django.core.management.base import BaseCommand, CommandError

from core.document_catalog_service import ensure_document_catalog
from core.document_source_recovery import recover_document_sources


class Command(BaseCommand):
    help = 'Reconnect private contract template source files that survived a database reset on the persistent media volume.'

    def add_arguments(self, parser):
        parser.add_argument('--strict', action='store_true', help='Exit non-zero unless all eight catalog sources are available.')
        parser.add_argument('--slug', action='append', dest='slugs', help='Recover only the selected catalog slug. May be repeated.')

    def handle(self, *args, **options):
        slugs = options.get('slugs') or None
        ensure_document_catalog(recover_sources=False)
        result = recover_document_sources(slugs=slugs)
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
        if options.get('strict') and not result.get('complete'):
            raise CommandError(
                'Private Vertragsvorlagen konnten nicht vollständig wiederhergestellt werden. '
                f"Fehlend: {result.get('missing')}; mehrdeutig: {result.get('ambiguous')}; ungültig: {result.get('invalid')}"
            )
        if result.get('complete'):
            self.stdout.write(self.style.SUCCESS('Private Vertragsvorlagen sind vollständig verbunden.'))
        else:
            self.stdout.write(self.style.WARNING('Mindestens eine private Vertragsvorlage benötigt weiterhin Aufmerksamkeit.'))
