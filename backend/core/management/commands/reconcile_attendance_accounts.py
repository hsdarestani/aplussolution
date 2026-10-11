"""Audit and optionally reconcile stale A+ attendance account snapshots.

Usage:
  python manage.py reconcile_attendance_accounts --year 2026
  python manage.py reconcile_attendance_accounts --year 2026 --apply

Dry run by default. Never overwrites imported legacy ledgers or Lexware docs.
"""
from collections import defaultdict
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from core.attendance_account_sync import reconcile_worker_month
from core.models import TimeEntry, WorkingTimeAccountRecord, WorkerProfile
from core.working_time import _monthly_pdf_verified_entries


def find_mismatches(year, worker_id=None):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime(year, 1, 1), tz)
    end = timezone.make_aware(datetime(year + 1, 1, 1), tz)
    accounts = WorkingTimeAccountRecord.objects.filter(year_month__year=year).select_related('worker__user')
    times = TimeEntry.objects.filter(
        clock_in__gte=start, clock_in__lt=end, clock_out__isnull=False,
    ).filter(Q(approved=True) | Q(wiw_time_id__isnull=False)).values_list(
        'worker_id', 'clock_in'
    )
    if worker_id:
        accounts = accounts.filter(worker_id=worker_id)
        times = times.filter(worker_id=worker_id)
    account_map = {(str(a.worker_id), a.year_month): a for a in accounts}
    candidate = set(account_map)
    for employee_id, start_time in times.iterator():
        month = timezone.localtime(start_time, tz).date().replace(day=1)
        candidate.add((str(employee_id), month))

    mismatches = defaultdict(set)
    protected_legacy = 0
    missing = 0
    for (employee_id, month) in sorted(candidate):
        account = account_map.get((employee_id, month))
        if account and account.source != 'aplus_time_entries':
            protected_legacy += 1
            continue
        if account is None:
            missing += 1
            mismatches[employee_id].add(month)
            continue
        _, stale = _monthly_pdf_verified_entries(account.worker, account)
        if stale:
            mismatches[employee_id].add(month)
    return mismatches, missing, protected_legacy, len(candidate)


class Command(BaseCommand):
    help = 'Safely check A+ monthly attendance against approved TimeEntry evidence.'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, default=timezone.localdate().year)
        parser.add_argument('--worker-id', type=str)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        year = options['year']
        if not 2000 <= year <= 2100:
            raise ValueError('Year out of range')
        worker_id = options['worker_id']
        if worker_id and not WorkerProfile.objects.filter(pk=worker_id).exists():
            raise ValueError('Worker not found')

        mismatch, missing, protected, checked = find_mismatches(year, worker_id)
        count = sum(len(months) for months in mismatch.values())
        self.stdout.write(
            f'ATTENDANCE_AUDIT year={year} checked_months={checked} '
            f'stale_months={count} workers={len(mismatch)} '
            f'missing_accounts={missing} protected_legacy={protected} '
            f'mode={"apply" if options["apply"] else "dry_run"}'
        )
        if not options['apply']:
            return
        for employee_id, months in mismatch.items():
            reconcile_worker_month(employee_id, min(months))
        after, missing_after, protected_after, checked_after = find_mismatches(year, worker_id)
        remaining = sum(len(months) for months in after.values())
        self.stdout.write(
            f'ATTENDANCE_RESULT year={year} checked_months={checked_after} '
            f'remaining_stale={remaining} remaining_missing={missing_after} '
            f'protected_legacy={protected_after}'
        )
        if remaining:
            raise RuntimeError(f'{remaining} A+ account months still need review')
