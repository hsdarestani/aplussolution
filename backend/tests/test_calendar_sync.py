from datetime import timedelta
from urllib.parse import urlsplit

import pytest
from django.test import Client, override_settings
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

    feed_path = urlsplit(payload['feed_url']).path
    public = Client().get(feed_path)
    assert public.status_code == 200
    assert public['Content-Type'].startswith('text/calendar')
    text = public.content.decode('utf-8')
    assert f'UID:shift-{shift.id}@aplus-solution.de' in text
    assert 'Bitte Seiteneingang nutzen' in text


@pytest.mark.django_db
@override_settings(ALLOWED_HOSTS=['testserver', 'app.aplus-solution.de'])
def test_calendar_subscription_forces_https_for_public_host(auth_worker):
    response = auth_worker.get(
        '/api/calendar/subscription/',
        HTTP_HOST='app.aplus-solution.de',
        HTTP_X_FORWARDED_PROTO='http',
    )

    assert response.status_code == 200
    payload = response.data
    assert payload['feed_url'].startswith('https://app.aplus-solution.de/api/calendar/feed/')
    assert payload['webcal_url'].startswith('webcal://app.aplus-solution.de/api/calendar/feed/')
    assert 'cid=https%3A%2F%2Fapp.aplus-solution.de%2Fapi%2Fcalendar%2Ffeed%2F' in payload['google_url']


@pytest.mark.django_db
@override_settings(ALLOWED_HOSTS=['testserver', 'app.aplus-solution.de'])
def test_ios_calendar_subscription_opens_native_webcal_with_https_feed(auth_worker):
    response = auth_worker.get(
        '/api/calendar/subscription/',
        HTTP_HOST='app.aplus-solution.de',
        HTTP_USER_AGENT='Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X)',
    )

    assert response.status_code == 200
    payload = response.data
    assert payload['feed_url'] == ''
    assert payload['https_feed_url'].startswith('https://app.aplus-solution.de/api/calendar/feed/')
    assert payload['webcal_url'].startswith('webcal://app.aplus-solution.de/api/calendar/feed/')
    assert payload['webcal_url'].endswith('.ics')
    assert 'calendar.google.com' in payload['google_url']
    assert response['Cache-Control'].startswith('private, no-store')


@pytest.mark.django_db
def test_calendar_feed_folds_multibyte_long_notes(auth_worker, shift):
    from core.calendar_sync import _fold_ical_line

    note = ('Überweisung München — ' * 12) + '✓'
    shift.notes = note
    shift.status = Shift.Status.CONFIRMED
    shift.starts_at = timezone.now() + timedelta(days=1)
    shift.ends_at = shift.starts_at + timedelta(hours=4)
    shift.save(update_fields=['notes', 'status', 'starts_at', 'ends_at', 'updated_at'])

    subscription = auth_worker.get('/api/calendar/subscription/')
    url = subscription.data['https_feed_url']
    response = Client().get(urlsplit(url).path)
    assert response.status_code == 200
    content = response.content.decode('utf-8')
    physical_lines = content.split('\r\n')
    assert all(len(line.encode('utf-8')) <= 75 for line in physical_lines)
    assert '\r\n ' in content
    assert _fold_ical_line('SUMMARY:Köln').startswith('SUMMARY:Köln')


@pytest.mark.django_db
def test_calendar_subscription_is_worker_only(auth_admin):
    response = auth_admin.get('/api/calendar/subscription/')
    assert response.status_code == 403


@pytest.mark.django_db
def test_calendar_feed_rejects_bad_token():
    response = Client().get('/api/calendar/feed/not-a-valid-token.ics')
    assert response.status_code == 404
