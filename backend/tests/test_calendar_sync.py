from datetime import timedelta
from urllib.parse import quote, urlsplit

import pytest
from django.core import signing
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
    assert payload['feed_url'].startswith('https://app.aplus-solution.de/calendar/')
    assert payload['webcal_url'].startswith('webcal://app.aplus-solution.de/calendar/')
    assert 'cid=https%3A%2F%2Fapp.aplus-solution.de%2Fcalendar%2F' in payload['google_url']


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
    assert payload['https_feed_url'].startswith('https://app.aplus-solution.de/calendar/')
    assert payload['webcal_url'].startswith('webcal://app.aplus-solution.de/calendar/')
    assert payload['webcal_url'].endswith('.ics')
    assert 'calendar.google.com' in payload['google_url']
    assert response['Cache-Control'].startswith('private, no-store')


@pytest.mark.django_db
@override_settings(ALLOWED_HOSTS=['testserver', 'app.aplus-solution.de'])
def test_apple_subscription_uses_unescaped_url_safe_signed_token(auth_worker):
    response = auth_worker.get(
        '/api/calendar/subscription/',
        HTTP_HOST='app.aplus-solution.de',
        HTTP_USER_AGENT='CalendarAgent/1.0 (iPhone; iOS 26)',
    )
    assert response.status_code == 200
    payload = response.data
    feed = payload['https_feed_url']
    assert feed.startswith('https://app.aplus-solution.de/calendar/')
    assert '%3A' not in feed.upper()
    assert '%' not in urlsplit(feed).path
    assert '~' in urlsplit(feed).path
    assert payload['webcal_url'] == feed.replace('https://', 'webcal://', 1)
    result = Client().get(urlsplit(feed).path, HTTP_HOST='app.aplus-solution.de')
    assert result.status_code == 200
    assert result['Content-Type'].startswith('text/calendar')
    assert result.content.startswith(b'BEGIN:VCALENDAR\r\n')
    assert result.content.endswith(b'END:VCALENDAR\r\n')


@pytest.mark.django_db
def test_clean_root_calendar_route_is_signed_and_does_not_require_login(auth_worker):
    link = auth_worker.get('/api/calendar/subscription/').data['https_feed_url']
    # A local Django host preserves the original route for development.
    worker_link = urlsplit(link).path
    assert Client().get(worker_link).status_code == 200
    assert Client().get('/calendar/invalid-token.ics').status_code == 404


@pytest.mark.django_db
def test_old_signed_calendar_links_remain_valid(worker_user):
    old_token = signing.Signer(salt='aplus.worker-calendar.v1').sign(
        str(worker_user.worker_profile.pk)
    )
    assert ':' in old_token
    encoded_path = '/api/calendar/feed/' + quote(old_token, safe='') + '.ics'
    response = Client().get(encoded_path)
    assert response.status_code == 200
    assert response['Content-Type'].startswith('text/calendar')
    assert response.content.startswith(b'BEGIN:VCALENDAR\r\n')


@pytest.mark.django_db
def test_url_safe_calendar_feed_rejects_tampering(auth_worker):
    subscription = auth_worker.get('/api/calendar/subscription/')
    path = urlsplit(subscription.data['https_feed_url']).path
    assert '~' in path
    assert Client().get(path.replace('~', '-')).status_code == 404


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
def test_worker_feed_uses_apple_accepted_minimal_calendar_format(auth_worker, shift):
    shift.status = Shift.Status.CONFIRMED
    shift.starts_at = timezone.now() + timedelta(days=1)
    shift.ends_at = shift.starts_at + timedelta(hours=2)
    shift.notes = 'Einsatznotiz Beispiel'
    shift.save(update_fields=['status', 'starts_at', 'ends_at', 'notes', 'updated_at'])

    subscription = auth_worker.get('/api/calendar/subscription/').data
    path = urlsplit(subscription['https_feed_url']).path
    response = Client().get(path)
    assert response.status_code == 200
    assert response['Content-Type'].startswith('text/calendar')
    assert 'Content-Disposition' not in response
    assert 'no-store' not in response['Cache-Control']
    content = response.content.decode('utf-8')
    assert content.startswith('BEGIN:VCALENDAR\r\n')
    assert content.endswith('END:VCALENDAR\r\n')
    assert f'UID:shift-{shift.pk}@aplus-solution.de' in content
    assert 'SUMMARY:' in content and 'DTSTART:' in content and 'DTEND:' in content
    assert 'Einsatznotiz Beispiel' in content
    assert 'X-PUBLISHED-TTL' not in content
    assert 'REFRESH-INTERVAL' not in content
    assert 'SEQUENCE:' not in content
    assert 'CATEGORIES:' not in content
    assert 'LAST-MODIFIED:' not in content
    assert all(len(line.encode('utf-8')) <= 75 for line in content.split('\r\n'))


@pytest.mark.django_db
def test_calendar_subscription_is_worker_only(auth_admin):
    response = auth_admin.get('/api/calendar/subscription/')
    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(ALLOWED_HOSTS=['testserver', 'app.aplus-solution.de'])
def test_calendar_head_preflight_matches_get_for_native_apple_calendar(auth_worker):
    feed_url = auth_worker.get(
        '/api/calendar/subscription/',
        HTTP_HOST='app.aplus-solution.de',
    ).data['https_feed_url']
    clean_path = urlsplit(feed_url).path
    assert clean_path.startswith('/calendar/')
    old_path = '/api/calendar/feed/' + clean_path.rsplit('/', 1)[-1]

    for path in (clean_path, old_path):
        get_response = Client().get(path, HTTP_HOST='app.aplus-solution.de')
        head_response = Client().head(path, HTTP_HOST='app.aplus-solution.de')
        assert get_response.status_code == 200
        assert head_response.status_code == 200
        assert get_response['Content-Type'].startswith('text/calendar')
        assert head_response['Content-Type'].startswith('text/calendar')

    assert Client().head('/calendar/invalid.ics', HTTP_HOST='app.aplus-solution.de').status_code == 404


@pytest.mark.django_db
def test_public_compatibility_fixture_is_real_ics_not_frontend_html():
    for method in ('get', 'head'):
        response = getattr(Client(), method)('/calendar-compatibility-test.ics')
        assert response.status_code == 200
        assert response['Content-Type'].startswith('text/calendar')
        assert '<html' not in response.content.decode('utf-8').lower()
        if method == 'get':
            assert response.content.startswith(b'BEGIN:VCALENDAR\r\n')
            assert response.content.endswith(b'END:VCALENDAR\r\n')
            assert response.content.count(b'BEGIN:VEVENT') == 1
            assert b'SUMMARY:A+ Solution Testtermin' in response.content
            assert all(len(line) <= 75 for line in response.content.split(b'\r\n'))


@pytest.mark.django_db
def test_calendar_feed_rejects_bad_token():
    response = Client().get('/api/calendar/feed/not-a-valid-token.ics')
    assert response.status_code == 404
