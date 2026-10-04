from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import ClientCompany, Location, Notification, Position, Shift, User, WorkerProfile
from core.shift_slots import ShiftSlot


pytestmark = pytest.mark.django_db


def test_admin_shift_change_notifies_worker_with_before_after_and_history():
    admin = User.objects.create_user(email='admin-change@example.com', password='pw', role=User.Role.ADMIN)
    worker_user = User.objects.create_user(email='worker-change@example.com', password='pw', role=User.Role.WORKER)
    worker = WorkerProfile.objects.create(user=worker_user, employee_number='CHANGE-1')
    client = ClientCompany.objects.create(name='Change Kunde', customer_number='CHANGE')
    location = Location.objects.create(client=client, name='Alter Ort', address='Alt 1')
    position = Position.objects.create(name='Servicekraft Change')

    start = timezone.now() + timedelta(days=4)
    shift = Shift.objects.create(
        client=client,
        location=location,
        position=position,
        starts_at=start,
        ends_at=start + timedelta(hours=6),
        notes='Alte Notiz',
        status=Shift.Status.CONFIRMED,
    )
    ShiftSlot.objects.create(
        shift=shift,
        worker=worker,
        status=ShiftSlot.Status.CLAIMED,
        source='admin_assignment',
    )

    admin_api = APIClient()
    admin_api.force_authenticate(admin)
    next_start = start + timedelta(hours=1)
    response = admin_api.patch(
        f'/api/shifts/{shift.id}/',
        {
            'starts_at': next_start.isoformat(),
            'ends_at': (next_start + timedelta(hours=6)).isoformat(),
            'notes': 'Neue Notiz',
        },
        format='json',
    )
    assert response.status_code == 200

    notice = Notification.objects.filter(user=worker_user, title='Schicht geändert').latest('created_at')
    assert 'Beginn:' in notice.body
    assert '→' in notice.body
    assert 'Notiz: Alte Notiz → Neue Notiz' in notice.body

    worker_api = APIClient()
    worker_api.force_authenticate(worker_user)
    history = worker_api.get(f'/api/shifts/{shift.id}/changes/')
    assert history.status_code == 200
    assert len(history.data) == 1
    fields = {item['field']: item for item in history.data[0]['changes']}
    assert fields['Notiz']['before'] == 'Alte Notiz'
    assert fields['Notiz']['after'] == 'Neue Notiz'
    assert fields['Beginn']['before'] != fields['Beginn']['after']
