from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.wiw_schedule_sync import WhenIWorkSynchronizer


class Command(BaseCommand):
    help = 'Historischer WIW-Import (seit Cutover deaktiviert).'

    def add_arguments(self, parser):
        parser.add_argument('--full', action='store_true')

    def handle(self, *args, **options):
        if not settings.WIW_SYNC_ENABLED:
            self.stdout.write(
                self.style.WARNING(
                    'WIW-Synchronisierung ist dauerhaft deaktiviert. '
                    'Vorhandene importierte Daten bleiben unverändert in A+ erhalten.'
                )
            )
            return
        try:
            run = WhenIWorkSynchronizer().sync('full' if options['full'] else 'incremental')
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f'{run.status}: {run.counts}'))
