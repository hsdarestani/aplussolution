import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.wiw_migration import build_wiw_migration_report
from core.wiw_scope_reconciliation import reconcile_wiw_history_scope


class Command(BaseCommand):
    help = 'Synchronisiert die vollständige WIW-Historie erneut und ordnet Legacy-Stammdaten dem Phase-1-Scope zu.'

    def add_arguments(self, parser):
        parser.add_argument('--compact', action='store_true')

    def handle(self, *args, **options):
        try:
            with transaction.atomic():
                migration = build_wiw_migration_report(apply_full_sync=True)
                sync_status = (migration.get('sync') or {}).get('status')
                if sync_status != 'success':
                    raise RuntimeError(f'WIW final history import status is {sync_status or "missing"}, expected success.')
                if not migration.get('cutover_ready'):
                    incomplete = [name for name, row in migration.get('resources', {}).items() if not row.get('complete')]
                    raise RuntimeError('WIW history is incomplete: ' + ', '.join(incomplete))

                scope = reconcile_wiw_history_scope()
                if not scope.get('valid'):
                    raise RuntimeError('WIW scope reconciliation did not produce the expected active client/position scope.')
        except Exception as exc:
            raise CommandError(f'WIW Phase 2 reconciliation failed: {exc}') from exc

        report = {
            'source': 'when_i_work',
            'target': 'aplus_workforce',
            'history_sync': migration,
            'scope_reconciliation': scope,
            'success': True,
        }
        self.stdout.write(json.dumps(report, ensure_ascii=False, default=str, indent=None if options['compact'] else 2, sort_keys=True))
        self.stdout.write(self.style.SUCCESS('WIW history synchronized and canonical workforce scope verified.'))
