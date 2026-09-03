from django.core.management.base import BaseCommand, CommandError

from core.wiw_schedule_sync import WhenIWorkSynchronizer


class Command(BaseCommand):
    help = 'Synchronisiert operative Daten aus When I Work.'

    def add_arguments(self, parser):
        parser.add_argument('--full', action='store_true')

    def handle(self, *args, **options):
        try:
            run = WhenIWorkSynchronizer().sync('full' if options['full'] else 'incremental')
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f'{run.status}: {run.counts}'))
