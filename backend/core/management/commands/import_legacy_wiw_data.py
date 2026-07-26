import json
from datetime import datetime
from pathlib import Path
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import (
    ClientCompany,
    ShiftImportPackage,
    ShiftImportRevision,
    WorkerProfile,
    WorkingTimeAccountRecord,
    WorkingTimeSetting,
    WorkingTimeSyncLog,
)


def aware(value):
    parsed = parse_datetime(str(value or ''))
    if not parsed:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


class Command(BaseCommand):
    help = 'Importiert einen privaten JSON-Export der beiden früheren WIW-WordPress-Plugins.'

    def add_arguments(self, parser):
        parser.add_argument('file', help='Pfad zur privaten JSON-Datei')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        path = Path(options['file'])
        if not path.exists():
            raise CommandError(f'Datei nicht gefunden: {path}')
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except Exception as exc:
            raise CommandError(f'Ungültiges JSON: {exc}') from exc
        if not isinstance(payload, dict):
            raise CommandError('Die Wurzel der Importdatei muss ein JSON-Objekt sein.')

        counts = {'packages': 0, 'revisions': 0, 'settings': 0, 'records': 0, 'logs': 0, 'skipped': 0}
        dry = options['dry_run']

        for row in payload.get('contracts', []):
            request_id = str(row.get('request_id') or '').strip()
            first = aware(row.get('first_shift_time'))
            if not request_id or not first:
                counts['skipped'] += 1
                continue
            raw = row.get('raw_shifts_data') or row.get('payload') or {}
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except ValueError:
                    raw = {'legacy_raw': raw}
            client = None
            site_name = str(row.get('site_name') or raw.get('site_name') or 'Legacy Client')
            client_number = str(row.get('customer_number') or '').strip()
            if client_number:
                client = ClientCompany.objects.filter(customer_number=client_number).first()
            if not client:
                client = ClientCompany.objects.filter(name__iexact=site_name).first()
            if dry:
                counts['packages'] += 1
                continue
            package, _ = ShiftImportPackage.objects.update_or_create(
                request_id=request_id,
                defaults={
                    'client': client,
                    'site_name': site_name,
                    'site_address': str(row.get('site_address') or raw.get('site_address') or ''),
                    'first_shift_time': first,
                    'first_shift_end_time': aware(row.get('first_shift_end_time')),
                    'payload': raw if isinstance(raw, dict) else {},
                    'source_hash': str(row.get('source_hash') or raw.get('source_hash') or ''),
                    'status': str(row.get('status') or 'pending'),
                },
            )
            counts['packages'] += 1

        for row in payload.get('revisions', []):
            package = ShiftImportPackage.objects.filter(request_id=row.get('request_id')).first()
            if not package:
                counts['skipped'] += 1
                continue
            if dry:
                counts['revisions'] += 1
                continue
            ShiftImportRevision.objects.update_or_create(
                package=package,
                version=int(row.get('version') or 1),
                defaults={
                    'action': str(row.get('action') or 'legacy'),
                    'old_shift_ids': row.get('old_shift_ids') or [],
                    'new_shift_ids': row.get('new_shift_ids') or [],
                    'old_payload': row.get('old_payload') or {},
                    'new_payload': row.get('new_payload') or {},
                },
            )
            counts['revisions'] += 1

        for row in payload.get('settings', []):
            worker = WorkerProfile.objects.filter(wiw_user_id=str(row.get('user_id') or '')).first()
            if not worker:
                counts['skipped'] += 1
                continue
            if dry:
                counts['settings'] += 1
                continue
            WorkingTimeSetting.objects.update_or_create(
                worker=worker,
                defaults={
                    'monthly_limit': Decimal(str(row.get('monthly_limit') or 0)),
                    'hourly_rate': Decimal(str(row.get('hourly_rate') or 0)),
                    'active': bool(int(row.get('active', 1))),
                    'excluded': bool(row.get('excluded', False)),
                    'notes': str(row.get('notes') or ''),
                },
            )
            counts['settings'] += 1

        for row in payload.get('records', []):
            worker = WorkerProfile.objects.filter(wiw_user_id=str(row.get('user_id') or '')).first()
            month = str(row.get('year_month') or '')
            if not worker or len(month) < 7:
                counts['skipped'] += 1
                continue
            if dry:
                counts['records'] += 1
                continue
            WorkingTimeAccountRecord.objects.update_or_create(
                worker=worker,
                year_month=datetime.strptime(month[:7], '%Y-%m').date(),
                defaults={
                    key: Decimal(str(row.get(key) or 0))
                    for key in ('ist_hours', 'soll_hours', 'difference_hours', 'carryover_previous', 'paid_hours', 'manual_adjustment', 'saldo_cumulative', 'hourly_rate', 'gross_amount')
                } | {
                    'raw_entries': row.get('raw_entries') or [],
                    'source': str(row.get('source') or 'legacy_wordpress'),
                    'synced_at': aware(row.get('synced_at')),
                },
            )
            counts['records'] += 1

        for row in payload.get('logs', []):
            if dry:
                counts['logs'] += 1
                continue
            WorkingTimeSyncLog.objects.create(
                range_start=row.get('range_start') or None,
                range_end=row.get('range_end') or None,
                status=str(row.get('status') or 'ok'),
                message=str(row.get('message') or ''),
                records_count=int(row.get('records_count') or 0),
                metadata={'legacy': True},
            )
            counts['logs'] += 1

        prefix = 'DRY RUN – ' if dry else ''
        self.stdout.write(self.style.SUCCESS(prefix + json.dumps(counts, ensure_ascii=False)))
