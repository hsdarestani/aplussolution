"""Safely complete missing historical Lexware worker-month statements."""
import json
from django.core.management.base import BaseCommand
from core.lexware_missing_months import complete_historical_months


class Command(BaseCommand):
    help = "Add only absent, verified Lexware historical payroll months. Dry run by default."

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, default=2025)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        report = complete_historical_months(
            year=options['year'], apply=options['apply'],
        )
        self.stdout.write('LEXWARE_MISSING_MONTHS ' + json.dumps(report, sort_keys=True))
