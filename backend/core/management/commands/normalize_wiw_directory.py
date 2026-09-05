from django.core.management.base import BaseCommand

from core.wiw_directory import ACTIVE_CLIENT_NAMES, MARTHA_LOCATION_NAMES, normalize_wiw_directory


class Command(BaseCommand):
    help = 'Normalize WIW-created customers/locations into the canonical A+ directory without losing external aliases.'

    def handle(self, *args, **options):
        stats = normalize_wiw_directory()
        self.stdout.write(self.style.SUCCESS('A+ / WIW directory normalized.'))
        self.stdout.write('Active customers: ' + ', '.join(ACTIVE_CLIENT_NAMES))
        self.stdout.write('Martha locations: ' + ', '.join(MARTHA_LOCATION_NAMES))
        for key, value in stats.items():
            self.stdout.write(f'{key}={value}')
