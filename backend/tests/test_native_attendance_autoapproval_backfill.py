"""Regression checks for old A+ time reports stranded in Offene Freigaben."""
import importlib
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.db import connection
from django.utils import timezone

from core.attendance_models import TimeEntryCorrection
from core.models import AuditLog, Shift, TimeEntry


@pytest.mark.django_db
def test_backfill_auto_approves_old_clean_native_records_but_keeps_exceptions(
    worker_user, shift, capsys
):
    worker = worker_user.worker_profile
    now = timezone.now()
    shift.status = Shift.Status.CONFIRMED
    shift.starts_at = now - timedelta(days=3)
    shift.ends_at = shift.starts_at + timedelta(hours=8)
    shift.save(update_fields=['status', 'starts_at', 'ends_at', 'updated_at'])

    def add_entry(*, reason='', clock_in=None, clock_out=None, shift_override=None, wiw_id=None):
        start = clock_in or shift.starts_at
        end = clock_out or start + timedelta(hours=8)
        return TimeEntry.objects.create(
            worker=worker,
            shift=shift if shift_override is None else shift_override,
            clock_in=start,
            clock_out=end,
            approved=False,
            edit_reason=reason,
            wiw_time_id=wiw_id,
            break_minutes=30,
        )

    old_report = add_entry(reason='SELF_REPORTED_AFTER_SHIFT\nLEGAL_ACKNOWLEDGED')
    old_clock = add_entry()
    offsite = add_entry(reason='OUTSIDE_GEOFENCE: außerhalb des Einsatzortes')
    admin_closed = add_entry(reason='Admin geschlossen: Korrektur erforderlich')
    correction = add_entry()
    TimeEntryCorrection.objects.create(
        entry=correction,
        requested_by=worker,
        requested_clock_out=correction.clock_out - timedelta(minutes=15),
        reason='Bitte Arbeitsende korrigieren',
        status=TimeEntryCorrection.Status.PENDING,
    )
    suspicious = add_entry(clock_out=shift.starts_at + timedelta(hours=25))
    imported_wiw = add_entry(wiw_id='historical-wiw-42')

    mod = importlib.import_module('core.migrations.0057_backfill_completed_native_time_approvals')
    mod.backfill_completed_native_times(apps, SimpleNamespace(connection=connection))
    for item in (old_report, old_clock, offsite, admin_closed, correction, suspicious, imported_wiw):
        item.refresh_from_db()

    assert old_report.approved is True
    assert old_clock.approved is True
    assert old_report.approved_by_id is None
    assert old_clock.approved_by_id is None
    for item in (offsite, admin_closed, correction, suspicious, imported_wiw):
        assert item.approved is False
    assert AuditLog.objects.filter(action=mod.BACKFILL_ACTION).count() == 2

    output = capsys.readouterr().out
    assert 'before=6 approved=2 pending_manual_review=4' in output
    # Idempotent, so a retry cannot duplicate approvals/audit evidence.
    mod.backfill_completed_native_times(apps, SimpleNamespace(connection=connection))
    assert AuditLog.objects.filter(action=mod.BACKFILL_ACTION).count() == 2
