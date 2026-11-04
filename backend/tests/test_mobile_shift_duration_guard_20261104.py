"""Manual 08:00–13:00 must never persist as tomorrow 13:00 (29h)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from core.models import Shift


@pytest.mark.django_db
def test_manual_create_rejects_29_hour_shift_and_does_not_save(auth_admin, company, location, position):
    start = datetime(2026, 11, 19, 8, 0, tzinfo=ZoneInfo('Europe/Berlin'))
    before = Shift.objects.count()
    response = auth_admin.post('/api/shifts/', {
        'client': str(company.pk),
        'location': str(location.pk),
        'position': str(position.pk),
        'starts_at': start.isoformat(),
        'ends_at': (start + timedelta(hours=29)).isoformat(),
        'required_count': 1,
        'status': 'published',
    }, format='json')
    assert response.status_code == 400, response.data
    assert '24 Stunden' in str(response.data)
    assert Shift.objects.count() == before


@pytest.mark.django_db
def test_manual_edit_rejects_29_hours_and_keeps_original_end(auth_admin, company, location, position):
    start = datetime(2026, 11, 17, 8, 0, tzinfo=ZoneInfo('Europe/Berlin'))
    original_end = start + timedelta(hours=5)
    created = auth_admin.post('/api/shifts/', {
        'client': str(company.pk),
        'location': str(location.pk),
        'position': str(position.pk),
        'starts_at': start.isoformat(),
        'ends_at': original_end.isoformat(),
        'required_count': 1,
        'status': 'published',
    }, format='json')
    assert created.status_code == 201, created.data
    slot_id = created.data['slot_cards'][0]['id']
    response = auth_admin.patch(f"/api/shifts/{created.data['id']}/cards/{slot_id}/", {
        'ends_at': (start + timedelta(hours=29)).isoformat(),
    }, format='json')
    assert response.status_code == 400, response.data
    assert '24 Stunden' in str(response.data)
    shift = Shift.objects.get(pk=created.data['id'])
    assert shift.ends_at == original_end


@pytest.mark.django_db
def test_legitimate_night_shift_still_allowed(auth_admin, company, location, position):
    start = datetime(2026, 11, 17, 22, 0, tzinfo=ZoneInfo('Europe/Berlin'))
    response = auth_admin.post('/api/shifts/', {
        'client': str(company.pk),
        'location': str(location.pk),
        'position': str(position.pk),
        'starts_at': start.isoformat(),
        'ends_at': (start + timedelta(hours=8)).isoformat(),
        'required_count': 1,
        'status': 'published',
    }, format='json')
    assert response.status_code == 201, response.data
