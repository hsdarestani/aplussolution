"""Auto approve legacy *routine* completed A+ work time reports.

The previous release approved new self-reported shifts on submission and
backfilled imported WIW times, but did not approve previously submitted native
A+ entries. Those historical rows continued to populate "Offene Freigaben".

Preserve genuinely exceptional cases for administrators: offsite checkout,
admin-closed timers, open correction requests, invalid/oversized durations,
unassigned rows, and cancelled shifts. Nothing in the payroll/lexware ledger
is recalculated or altered by this migration.
"""
from datetime import timedelta

from django.db import migrations
from django.utils import timezone


SELF_REPORTED_REASON = 'SELF_REPORTED_AFTER_SHIFT'
BACKFILL_ACTION = 'time.auto_approved_legacy_completed'


def backfill_completed_native_times(apps, schema_editor):
    TimeEntry = apps.get_model('core', 'TimeEntry')
    TimeEntryCorrection = apps.get_model('core', 'TimeEntryCorrection')
    AuditLog = apps.get_model('core', 'AuditLog')

    db_alias = schema_editor.connection.alias
    all_pending = (
        TimeEntry.objects.using(db_alias)
        .filter(wiw_time_id__isnull=True, clock_out__isnull=False, approved=False)
        .exclude(worker__user__email__iendswith='@sync.invalid')
    )
    initial_count = all_pending.count()
    pending_corrections = (
        TimeEntryCorrection.objects.using(db_alias)
        .filter(status='pending')
        .values_list('entry_id', flat=True)
    )
    cutoff = timezone.now() + timedelta(minutes=15)
    approved_count = 0

    # Run against the historical app state, not imported runtime models.
    # Keep the original timestamps, shift, notes and breaks unchanged.
    for entry in (
        all_pending.select_related('shift')
        .exclude(pk__in=pending_corrections)
        .iterator(chunk_size=200)
    ):
        if not entry.shift_id or entry.shift.status in {'cancelled', 'draft'}:
            continue
        reason = (entry.edit_reason or '').strip()
        # Blank reasons came from ordinary clock-in/clock-out flows on older
        # builds. All other notes may indicate a manual close or safety issue.
        if reason and not reason.startswith(SELF_REPORTED_REASON):
            continue
        if 'OUTSIDE_GEOFENCE:' in reason or 'ADMIN_REVIEW:' in reason:
            continue
        if entry.clock_out <= entry.clock_in or entry.clock_out > cutoff:
            continue
        gross_minutes = int((entry.clock_out - entry.clock_in).total_seconds() // 60)
        # Keep overnight clock-out dating anomalies and long-running timers in
        # the genuine review queue.
        if gross_minutes <= 0 or gross_minutes > 18 * 60:
            continue
        break_minutes = (
            entry.break_minutes if entry.break_minutes is not None
            else entry.shift.break_minutes
        ) or 0
        if int(break_minutes) >= gross_minutes:
            continue

        changed = (
            TimeEntry.objects.using(db_alias)
            .filter(pk=entry.pk, approved=False)
            .update(approved=True, approved_by_id=None)
        )
        if changed:
            AuditLog.objects.using(db_alias).create(
                actor_id=None,
                action=BACKFILL_ACTION,
                object_type='TimeEntry',
                object_id=str(entry.pk),
                metadata={
                    'source': 'native_aplus',
                    'original_reason': reason,
                    'automatic': True,
                    'preserved_payroll_history': True,
                },
                ip_address=None,
            )
            approved_count += 1

    remaining_count = all_pending.count()
    print(
        'ATTENDANCE_NATIVE_AUTO_APPROVAL '
        f'before={initial_count} approved={approved_count} '
        f'pending_manual_review={remaining_count}'
    )


class Migration(migrations.Migration):
    dependencies = [('core', '0056_backfill_2026_holiday_hours_and_wiw_approvals')]
    operations = [
        migrations.RunPython(backfill_completed_native_times, migrations.RunPython.noop),
    ]
