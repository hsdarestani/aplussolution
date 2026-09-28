from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from core.models import Shift


@pytest.mark.django_db
def test_worker_calendar_subscription_and_feed(auth_worker, worker_user, shift):
    starts_at = timezone.now() + timedelta(days=2)
    shift.starts_at = starts_at
    shift.ends_at = starts_at + timedelta(hours=6)
    shift.status = Shift.Status.CONFIRMED
    shift.notes = 'Bitte Seiteneingang nutzen'
    shift.save(update_fields=['starts_at', 'ends_at', 'status', 'notes', 'updated_at'])

    response = auth_worker.get('/api/calendar/subscription/')
    assert response.status_code == 200
    payload = response.data
    assert payload['automatic'] is True
    assert payload['feed_url'].endswith('.ics')
    assert payload['webcal_url'].startswith('webcal://')
    assert 'calendar.google.com' in payload['google_url']

    feed_path = payload['feed_url'].replace('http://testserver', '')
    public = Client().get(feed_path)
    assert public.status_code == 200
    assert public['Content-Type'].startswith('text/calendar')
    text = public.content.decode('utf-8')
    assert f'UID:shift-{shift.id}@aplus-solution.de' in text
    assert 'Bitte Seiteneingang nutzen' in text


@pytest.mark.django_db
def test_calendar_subscription_is_worker_only(auth_admin):
    response = auth_admin.get('/api/calendar/subscription/')
    assert response.status_code == 403


@pytest.mark.django_db
def test_calendar_feed_rejects_bad_token():
    response = Client().get('/api/calendar/feed/not-a-valid-token.ics')
    assert response.status_code == 404
