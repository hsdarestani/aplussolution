import json

from django.core.management.base import BaseCommand, CommandError

from core.wiw_migration import build_wiw_migration_report


class Command(BaseCommand):
    help = 'Run the one-time final When I Work import/reconciliation before decommissioning WIW.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Run one final full WIW import before reconciliation.',
        )
        parser.add_argument(
            '--strict',
            action='store_true',
            help='Exit with an error unless every supported WIW resource is fully present locally.',
        )
        parser.add_argument(
            '--compact',
            action='store_true',
            help='Print compact JSON instead of pretty JSON.',
        )

    def handle(self, *args, **options):
        try:
            report = build_wiw_migration_report(apply_full_sync=options['apply'])
        except Exception as exc:
            raise CommandError(f'WIW final migration failed: {exc}') from exc

        payload = json.dumps(
            report,
            ensure_ascii=False,
            default=str,
            indent=None if options['compact'] else 2,
            sort_keys=True,
        )
        self.stdout.write(payload)

        if options['strict'] and not report['cutover_ready']:
            missing = [
                name
                for name, row in report['resources'].items()
                if not row['complete']
            ]
            raise CommandError(
                'Cutover is not safe yet. Incomplete resources: ' + ', '.join(missing)
            )

        if report['cutover_ready']:
            self.stdout.write(self.style.SUCCESS('WIW reconciliation complete. A+ Workforce is cutover-ready.'))
        else:
            self.stdout.write(self.style.WARNING('WIW reconciliation found gaps; keep WIW available for another migration pass.'))
