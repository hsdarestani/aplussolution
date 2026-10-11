"""Reconcile missing historical Lexware payroll identities, dry run by default."""
import json
from django.core.management.base import BaseCommand, CommandError

from core.lexware_historical import reconcile_archive


class Command(BaseCommand):
    help = "Recover inactive historical employees and unmatched archive payroll rows. Dry run unless --apply."

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, default=2025)
        parser.add_argument('--month', type=int, default=12)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        year, month = options['year'], options['month']
        if not 2000 <= year <= 2100 or not 1 <= month <= 12:
            raise CommandError('Invalid payroll year/month')
        report = reconcile_archive(year, month, apply=options['apply'])
        # Only summary counts go to public GitHub CI, never payroll identities.
        self.stdout.write('LEXWARE_HISTORICAL_RECONCILE ' + json.dumps(report, sort_keys=True))
