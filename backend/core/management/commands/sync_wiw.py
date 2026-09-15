from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Historischer WIW-Import (seit Cutover dauerhaft deaktiviert).'

    def add_arguments(self, parser):
        # Keep the legacy flag accepted so old operational commands fail safe
        # instead of surprising automation with an unknown argument error.
        parser.add_argument('--full', action='store_true')

    def handle(self, *args, **options):
        # WIW -> A+ migration is complete. This command deliberately performs
        # no network access and no database writes, even if a stale environment
        # or test fixture still exposes an old WIW_SYNC_ENABLED value.
        self.stdout.write(
            self.style.WARNING(
                'WIW-Synchronisierung ist dauerhaft deaktiviert. '
                'Vorhandene importierte Daten bleiben unverändert in A+ erhalten.'
            )
        )
