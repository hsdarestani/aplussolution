from datetime import timedelta
from io import BytesIO

import pytest
from django.utils import timezone
from pypdf import PdfReader
from rest_framework.test import APIClient

from core.models import AuditLog, Shift, TimeEntry


@pytest.mark.django_db
def test_attendance_pdf_includes_unapproved_wiw_import(auth_admin, worker_user, shift):
    start = timezone.now() - timedelta(days=2, hours=7)
    shift.starts_at = start
    shift.ends_at = start + timedelta(hours=7)
    shift.save(update_fields=['starts_at', 'ends_at', 'updated_at'])
    TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        shift=shift,
        clock_in=start,
        clock_out=start + timedelta(hours=7),
        break_minutes=30,
        approved=False,
        wiw_time_id='wiw-pdf-history-1',
        wiw_payload={'source': 'test'},
    )

    day = timezone.localtime(start).date().isoformat()
    response = auth_admin.get('/api/reports/attendance.pdf', {
        'date_from': day,
        'date_to': day,
        'workers': str(worker_user.worker_profile.id),
    })

    assert response.status_code == 200
    text = '\n'.join(page.extract_text() or '' for page in PdfReader(BytesIO(response.content)).pages)
    assert worker_user.get_full_name() in text
    assert '6:30 Std.' in text


@pytest.mark.django_db
def test_admin_can_create_and_edit_time_from_shift_card(auth_admin, admin_user, manager_user, worker_user, shift):
    start = shift.starts_at
    end = shift.ends_at
    created = auth_admin.post('/api/time-entries/set-for-shift/', {
        'shift': str(shift.id),
        'worker': str(worker_user.worker_profile.id),
        'clock_in': start.isoformat(),
        'clock_out': end.isoformat(),
        'break_minutes': 30,
        'reason': 'Schichtkarte erfasst',
    }, format='json')
    assert created.status_code == 201
    entry = TimeEntry.objects.get(id=created.data['id'])
    assert entry.approved is True
    assert entry.approved_by == admin_user
    assert AuditLog.objects.filter(
        object_type='TimeEntry',
        object_id=str(entry.id),
        action='time.admin_shift_created',
    ).exists()

    edited = auth_admin.post('/api/time-entries/set-for-shift/', {
        'shift': str(shift.id),
        'worker': str(worker_user.worker_profile.id),
        'clock_in': (start + timedelta(minutes=15)).isoformat(),
        'clock_out': (end - timedelta(minutes=15)).isoformat(),
        'break_minutes': 30,
        'reason': 'Korrektur laut Einsatzleitung',
    }, format='json')
    assert edited.status_code == 200
    assert TimeEntry.objects.filter(shift=shift, worker=worker_user.worker_profile).count() == 1

    detail = auth_admin.get(f'/api/shifts/{shift.id}/')
    assert detail.status_code == 200
    rows = detail.data['admin_time_entries']
    assert len(rows) == 1
    assert rows[0]['worker'] == str(worker_user.worker_profile.id)
    assert rows[0]['source'] == 'admin'
    assert any(log['action'] == 'time.admin_shift_updated' for log in rows[0]['logs'])

    manager = APIClient()
    manager.force_authenticate(manager_user)
    denied = manager.post('/api/time-entries/set-for-shift/', {
        'shift': str(shift.id),
        'worker': str(worker_user.worker_profile.id),
        'clock_in': start.isoformat(),
        'clock_out': end.isoformat(),
        'break_minutes': 0,
    }, format='json')
    assert denied.status_code == 403

    manager_detail = manager.get(f'/api/shifts/{shift.id}/')
    assert manager_detail.status_code == 200
    assert manager_detail.data['admin_time_entries'] == []


@pytest.mark.django_db
def test_attendance_home_prefers_latest_completed_shift_for_manual_report(auth_worker, worker_user, company, location, position):
    now = timezone.now()
    older = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        worker=worker_user.worker_profile,
        starts_at=now - timedelta(hours=8),
        ends_at=now - timedelta(hours=6),
        status=Shift.Status.CONFIRMED,
    )
    latest = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        worker=worker_user.worker_profile,
        starts_at=now - timedelta(hours=4),
        ends_at=now - timedelta(hours=2),
        status=Shift.Status.CONFIRMED,
    )

    response = auth_worker.get('/api/attendance/home/')

    assert response.status_code == 200
    assert response.data['pending_shift_report']['id'] == str(latest.id)
    assert response.data['pending_shift_report']['id'] != str(older.id)
