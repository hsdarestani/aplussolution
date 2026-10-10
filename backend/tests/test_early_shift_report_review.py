"""Workers can report in the last shift hour; extensions require review."""
from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import Shift, TimeEntry
from core.time_views import outside_planned_shift


@pytest.mark.django_db
def test_can_report_early_in_last_hour_without_approval(auth_worker, shift):
    now = timezone.now()
    shift.starts_at = now - timedelta(hours=3)
    shift.ends_at = now + timedelta(minutes=35)
    shift.status = Shift.Status.CONFIRMED
    shift.save(update_fields=['starts_at', 'ends_at', 'status', 'updated_at'])

    reply = auth_worker.post('/api/time-entries/report_shift/', {
        'shift': str(shift.id),
        'clock_in': (shift.starts_at + timedelta(minutes=5)).isoformat(),
        'clock_out': (now - timedelta(minutes=2)).isoformat(),
        'legal_acknowledged': True,
    }, format='json')
    assert reply.status_code == 201, reply.data
    assert reply.data['review_required'] is False
    entry = TimeEntry.objects.get(shift=shift)
    assert entry.approved is True


@pytest.mark.django_db
def test_cannot_report_earlier_than_one_hour_before_end(auth_worker, shift):
    now = timezone.now()
    shift.starts_at = now - timedelta(hours=3)
    shift.ends_at = now + timedelta(hours=1, minutes=5)
    shift.status = Shift.Status.CONFIRMED
    shift.save(update_fields=['starts_at', 'ends_at', 'status', 'updated_at'])

    reply = auth_worker.post('/api/time-entries/report_shift/', {
        'shift': str(shift.id),
        'clock_in': (shift.starts_at + timedelta(minutes=10)).isoformat(),
        'clock_out': now.isoformat(),
        'legal_acknowledged': True,
    }, format='json')
    assert reply.status_code == 400
    assert not TimeEntry.objects.filter(shift=shift).exists()


@pytest.mark.django_db
@pytest.mark.parametrize('kind', ['earlier_start', 'later_finish'])
def test_outside_planned_hours_go_to_admin_queue(auth_worker, auth_admin, shift, kind):
    now = timezone.now()
    shift.starts_at = now - timedelta(hours=4)
    shift.ends_at = now - timedelta(minutes=35)
    shift.status = Shift.Status.CONFIRMED
    shift.save(update_fields=['starts_at', 'ends_at', 'status', 'updated_at'])

    start = shift.starts_at + timedelta(minutes=10)
    finish = shift.ends_at - timedelta(minutes=5)
    if kind == 'earlier_start':
        start = shift.starts_at - timedelta(minutes=15)
    else:
        finish = shift.ends_at + timedelta(minutes=15)

    reply = auth_worker.post('/api/time-entries/report_shift/', {
        'shift': str(shift.id),
        'clock_in': start.isoformat(),
        'clock_out': finish.isoformat(),
        'legal_acknowledged': True,
    }, format='json')
    assert reply.status_code == 201, reply.data
    assert reply.data['review_required'] is True
    entry = TimeEntry.objects.get(shift=shift)
    assert entry.approved is False
    assert 'OUTSIDE_SHIFT_PLAN:' in entry.edit_reason
    exceptions = auth_admin.get('/api/attendance/exceptions/')
    assert exceptions.status_code == 200
    assert any(str(row['id']) == str(entry.id) for row in exceptions.data['unapproved_entries'])


@pytest.mark.django_db
def test_shorter_shift_within_planned_window_needs_no_review(auth_worker, shift):
    now = timezone.now()
    shift.starts_at = now - timedelta(hours=5)
    shift.ends_at = now - timedelta(minutes=10)
    shift.save(update_fields=['starts_at', 'ends_at', 'updated_at'])
    reply = auth_worker.post('/api/time-entries/report_shift/', {
        'shift': str(shift.id),
        'clock_in': (shift.starts_at + timedelta(minutes=30)).isoformat(),
        'clock_out': (shift.ends_at - timedelta(minutes=25)).isoformat(),
        'legal_acknowledged': True,
    }, format='json')
    assert reply.status_code == 201, reply.data
    assert reply.data['review_required'] is False


@pytest.mark.django_db
def test_report_cannot_claim_future_clock_out_during_early_entry(auth_worker, shift):
    now = timezone.now()
    shift.starts_at = now - timedelta(hours=3)
    shift.ends_at = now + timedelta(minutes=45)
    shift.save(update_fields=['starts_at', 'ends_at', 'updated_at'])
    reply = auth_worker.post('/api/time-entries/report_shift/', {
        'shift': str(shift.id),
        'clock_in': shift.starts_at.isoformat(),
        'clock_out': shift.ends_at.isoformat(),
        'legal_acknowledged': True,
    }, format='json')
    assert reply.status_code == 400


def test_overnight_boundary_recognition():
    start = timezone.now()
    shift = Shift(starts_at=start, ends_at=start + timedelta(hours=6))
    assert not outside_planned_shift(shift, start + timedelta(minutes=10), start + timedelta(hours=5))
    assert outside_planned_shift(shift, start - timedelta(minutes=1), start + timedelta(hours=5))
    assert outside_planned_shift(shift, start + timedelta(minutes=10), shift.ends_at + timedelta(minutes=1))


@pytest.mark.django_db
def test_live_clock_out_beyond_plan_needs_review(auth_worker, shift):
    now = timezone.now()
    shift.starts_at = now - timedelta(hours=2)
    shift.ends_at = now - timedelta(minutes=10)
    shift.save(update_fields=['starts_at', 'ends_at', 'updated_at'])
    entry = TimeEntry.objects.create(
        worker=shift.worker,
        shift=shift,
        clock_in=shift.starts_at + timedelta(minutes=5),
        clock_out=None,
        approved=False,
    )
    reply = auth_worker.post('/api/time-entries/clock_out/', {}, format='json')
    assert reply.status_code == 200, reply.data
    assert reply.data['review_required'] is True
    entry.refresh_from_db()
    assert entry.approved is False


@pytest.mark.django_db
def test_admin_can_approve_outside_plan_after_review(auth_worker, auth_admin, shift):
    now = timezone.now()
    shift.starts_at = now - timedelta(hours=5)
    shift.ends_at = now - timedelta(hours=1)
    shift.save(update_fields=['starts_at', 'ends_at', 'updated_at'])
    report = auth_worker.post('/api/time-entries/report_shift/', {
        'shift': str(shift.id),
        'clock_in': (shift.starts_at - timedelta(minutes=15)).isoformat(),
        'clock_out': (shift.ends_at + timedelta(minutes=15)).isoformat(),
        'legal_acknowledged': True,
    }, format='json')
    assert report.status_code == 201
    entry = TimeEntry.objects.get(shift=shift)
    decision = auth_admin.post(f'/api/time-entries/{entry.id}/approve/', {
        'reason': 'Mehrarbeit geprüft und genehmigt',
    }, format='json')
    assert decision.status_code == 200, decision.data
    entry.refresh_from_db()
    assert entry.approved is True
    assert entry.approved_by is not None
    assert 'ADMIN_REVIEW:' in entry.edit_reason
