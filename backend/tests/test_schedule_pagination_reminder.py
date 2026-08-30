from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.core import mail
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from core import tasks
from core.models import Notification, Shift
from core.pagination import PathAwarePagination
from core.shift_slots import ShiftSlot


def test_shift_endpoints_use_large_page_size():
    factory = APIRequestFactory()
    pagination = PathAwarePagination()
    assert pagination.get_page_size(Request(factory.get('/api/shifts/'))) == 5000
    assert pagination.get_page_size(Request(factory.get('/api/shifts/mine/'))) == 5000
    assert pagination.get_page_size(Request(factory.get('/api/workers/'))) == 50


@pytest.mark.django_db
def test_shift_reminder_uses_berlin_local_time(monkeypatch, worker_user, company, location, position):
    reference = datetime(2026, 8, 22, 7, 0, tzinfo=dt_timezone.utc)
    starts_at = reference + timedelta(hours=24)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=5),
        status=Shift.Status.CONFIRMED,
    )
    slot = shift.slots.first()
    slot.worker = worker_user.worker_profile
    slot.status = ShiftSlot.Status.CLAIMED
    slot.claimed_at = reference
    slot.save(update_fields=['worker', 'status', 'claimed_at', 'updated_at'])

    monkeypatch.setattr(tasks.timezone, 'now', lambda: reference)
    assert tasks.send_shift_reminders() == 1

    notification = Notification.objects.get(user=worker_user, kind=f'shift-24h-{slot.id}')
    assert notification.title == 'Erinnerung:'
    assert notification.body == 'Dein Einsatz beginnt morgen um 09:00 Uhr'
    assert len(mail.outbox) == 1
    assert '23.08.2026 09:00' in mail.outbox[0].body
    assert '23.08.2026 07:00' not in mail.outbox[0].body
