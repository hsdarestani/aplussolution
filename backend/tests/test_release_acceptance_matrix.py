import json
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    ClientCompany,
    Conversation,
    Location,
    Notification,
    PayrollStatement,
    TimeOffRequest,
)
from core.order_automation import parse_order_text


def rows(response):
    if isinstance(response.data, dict) and 'results' in response.data:
        return response.data['results']
    return response.data


@pytest.mark.django_db
def test_geofence_rejects_missing_and_far_location_and_prevents_double_clock_in(
    auth_worker, shift
):
    shift.starts_at = timezone.now() - timedelta(minutes=5)
    shift.ends_at = timezone.now() + timedelta(hours=4)
    shift.save(update_fields=['starts_at', 'ends_at', 'updated_at'])

    missing = auth_worker.post(
        '/api/time-entries/clock_in/',
        {'shift': str(shift.id)},
        format='json',
    )
    assert missing.status_code == 400
    assert 'Standort' in str(missing.data)

    far = auth_worker.post(
        '/api/time-entries/clock_in/',
        {'shift': str(shift.id), 'lat': 52.5200, 'lng': 13.4050},
        format='json',
    )
    assert far.status_code == 400
    assert 'entfernt' in str(far.data)

    ok = auth_worker.post(
        '/api/time-entries/clock_in/',
        {'shift': str(shift.id), 'lat': 50.1100, 'lng': 8.6800},
        format='json',
    )
    assert ok.status_code == 201

    duplicate = auth_worker.post(
        '/api/time-entries/clock_in/',
        {'shift': str(shift.id), 'lat': 50.1100, 'lng': 8.6800},
        format='json',
    )
    assert duplicate.status_code == 400


@pytest.mark.django_db
def test_payroll_isolation_worker_sees_only_own_statement(
    auth_worker, worker_user, second_worker
):
    PayrollStatement.objects.create(
        worker=worker_user.worker_profile,
        period=timezone.localdate().replace(day=1),
        gross_amount='1200.00',
        net_amount='980.00',
        document=SimpleUploadedFile('own.pdf', b'%PDF-own', content_type='application/pdf'),
    )
    PayrollStatement.objects.create(
        worker=second_worker,
        period=timezone.localdate().replace(day=1),
        gross_amount='2200.00',
        net_amount='1700.00',
        document=SimpleUploadedFile('other.pdf', b'%PDF-other', content_type='application/pdf'),
    )

    response = auth_worker.get('/api/payroll/')
    assert response.status_code == 200
    data = rows(response)
    assert len(data) == 1
    assert str(data[0]['worker']) == str(worker_user.worker_profile.id)


@pytest.mark.django_db
def test_conversation_isolation_and_empty_message_validation(
    api_client, admin_user, worker_user, second_worker
):
    conversation = Conversation.objects.create(title='Release QA')
    conversation.participants.add(admin_user, worker_user)

    api_client.force_authenticate(second_worker.user)
    denied = api_client.get(f'/api/conversations/{conversation.id}/')
    assert denied.status_code == 404

    api_client.force_authenticate(worker_user)
    visible = api_client.get(f'/api/conversations/{conversation.id}/')
    assert visible.status_code == 200
    empty = api_client.post(
        f'/api/conversations/{conversation.id}/post_message/',
        {'body': '   '},
        format='json',
    )
    assert empty.status_code == 400


@pytest.mark.django_db
def test_notifications_are_user_scoped(api_client, worker_user, second_worker):
    own = Notification.objects.create(user=worker_user, title='Own', body='Only mine')
    Notification.objects.create(user=second_worker.user, title='Other', body='Not mine')
    api_client.force_authenticate(worker_user)
    response = api_client.get('/api/notifications/')
    assert response.status_code == 200
    data = rows(response)
    assert [item['id'] for item in data] == [str(own.id)]


@pytest.mark.django_db
def test_worker_cannot_submit_rating_or_download_admin_reports(
    auth_worker, worker_user
):
    rating = auth_worker.post(
        '/api/ratings/',
        {
            'worker': str(worker_user.worker_profile.id),
            'score': 5,
            'punctuality': 5,
            'quality': 5,
            'teamwork': 5,
        },
        format='json',
    )
    assert rating.status_code == 400

    assert auth_worker.get('/api/reports/timesheets.csv').status_code == 403
    assert auth_worker.get('/api/reports/schedule.csv').status_code == 403
    assert auth_worker.get('/api/reports/payroll-estimate.csv').status_code == 403


@pytest.mark.django_db
def test_schedule_report_contains_real_assignment(auth_admin, shift, worker_user):
    date_from = shift.starts_at.date()
    date_to = shift.ends_at.date()
    response = auth_admin.get(
        f'/api/reports/schedule.csv?date_from={date_from.isoformat()}&date_to={date_to.isoformat()}'
    )
    assert response.status_code == 200
    body = response.content.decode('utf-8-sig')
    assert 'Beginn;Ende;Kunde;Einsatzort;Position;Mitarbeiter;Status' in body
    assert worker_user.get_full_name() in body


@pytest.mark.django_db
def test_time_off_rejection_roundtrip(auth_worker, auth_admin, worker_user):
    start = timezone.localdate() + timedelta(days=14)
    created = auth_worker.post(
        '/api/time-off/',
        {
            'starts_on': start.isoformat(),
            'ends_on': (start + timedelta(days=1)).isoformat(),
            'reason': 'Release QA',
        },
        format='json',
    )
    assert created.status_code == 201
    decision = auth_admin.post(
        f"/api/time-off/{created.data['id']}/decide/",
        {'status': 'rejected'},
        format='json',
    )
    assert decision.status_code == 200
    request = TimeOffRequest.objects.get(pk=created.data['id'])
    assert request.status == TimeOffRequest.Status.REJECTED


@pytest.mark.django_db
def test_worker_and_client_archive_flows(auth_admin, worker_user, company):
    archived_worker = auth_admin.post(
        f'/api/workers/{worker_user.worker_profile.id}/archive/', {}, format='json'
    )
    assert archived_worker.status_code == 200
    worker_user.refresh_from_db()
    worker_user.worker_profile.refresh_from_db()
    assert worker_user.is_active is False
    assert worker_user.worker_profile.active is False

    archived_client = auth_admin.post(f'/api/clients/{company.id}/archive/', {}, format='json')
    assert archived_client.status_code == 200
    company.refresh_from_db()
    assert company.active is False


@pytest.mark.django_db
def test_client_can_only_list_own_locations(api_client, client_user, company):
    own = Location.objects.create(client=company, name='Own site', address='Own 1')
    other_contact = client_user.__class__.objects.create_user(
        'other-location-client@example.com',
        'StrongPass123!',
        role='client',
        is_onboarded=True,
    )
    other_company = ClientCompany.objects.create(name='Other GmbH', customer_number='QA-LOC-OTHER')
    other_company.contacts.add(other_contact)
    Location.objects.create(client=other_company, name='Other site', address='Other 1')

    api_client.force_authenticate(client_user)
    response = api_client.get('/api/locations/')
    assert response.status_code == 200
    data = rows(response)
    assert [item['id'] for item in data] == [str(own.id)]


@pytest.mark.django_db
def test_readiness_flags_track_real_external_configuration(auth_admin, settings):
    settings.GOOGLE_OAUTH_CLIENT_ID = ''
    settings.GOOGLE_OAUTH_CLIENT_SECRET = ''
    settings.GOOGLE_OAUTH_REDIRECT_URI = ''
    settings.APPLE_SERVICE_ID = ''
    settings.APPLE_TEAM_ID = ''
    settings.APPLE_KEY_ID = ''
    settings.APPLE_PRIVATE_KEY = ''
    settings.APPLE_PRIVATE_KEY_PATH = ''
    settings.APPLE_OAUTH_REDIRECT_URI = ''
    settings.EMAIL_HOST = ''
    settings.EMAIL_HOST_USER = ''

    response = auth_admin.get('/api/operations/readiness/')
    assert response.status_code == 200
    assert response.data['google_login'] is False
    assert response.data['apple_login'] is False
    assert response.data['email_delivery'] is False

    settings.GOOGLE_OAUTH_CLIENT_ID = 'client-id'
    settings.GOOGLE_OAUTH_CLIENT_SECRET = 'client-secret'
    settings.GOOGLE_OAUTH_REDIRECT_URI = 'https://example.test/google/callback'
    settings.APPLE_SERVICE_ID = 'service-id'
    settings.APPLE_TEAM_ID = 'team-id'
    settings.APPLE_KEY_ID = 'key-id'
    settings.APPLE_PRIVATE_KEY = 'private-key'
    settings.APPLE_OAUTH_REDIRECT_URI = 'https://example.test/apple/callback'
    settings.EMAIL_HOST = 'smtp.example.test'
    settings.EMAIL_HOST_USER = 'mailer@example.test'

    response = auth_admin.get('/api/operations/readiness/')
    assert response.status_code == 200
    assert response.data['google_login'] is True
    assert response.data['apple_login'] is True
    assert response.data['email_delivery'] is True


@pytest.mark.django_db
def test_openai_order_parser_contract_with_mocked_provider(settings):
    settings.WIW_OPENAI_KEY = 'test-openai-key'
    settings.WIW_OPENAI_MODEL = 'test-model'
    settings.WIW_HTTP_TIMEOUT = 5

    class FakeResponse:
        ok = True
        status_code = 200

        @staticmethod
        def json():
            return {
                'choices': [
                    {
                        'message': {
                            'content': json.dumps(
                                {
                                    'contract_no': 'AUF-2026-77',
                                    'shifts': [
                                        {
                                            'role': 'Servicekraft',
                                            'date': '2026-09-01',
                                            'start_time': '18:00',
                                            'end_time': '23:00',
                                            'count': 3,
                                            'location_text': 'Messe Frankfurt',
                                            'site_text': 'QA Kunde GmbH',
                                            'site_address': 'Messeplatz 1',
                                            'notes': 'Abendveranstaltung',
                                        }
                                    ],
                                }
                            )
                        }
                    }
                ]
            }

    class FakeSession:
        def __init__(self):
            self.calls = []

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return FakeResponse()

    session = FakeSession()
    parsed = parse_order_text(
        'Auftragsnummer AUF-2026-77: 3 Servicekräfte am 01.09.2026',
        session=session,
    )
    assert parsed['request_id'] == 'AUF-2026-77'
    assert parsed['shifts'][0]['count'] == 3
    assert session.calls[0][0] == 'https://api.openai.com/v1/chat/completions'
    assert session.calls[0][1]['headers']['Authorization'] == 'Bearer test-openai-key'
    assert session.calls[0][1]['json']['model'] == 'test-model'
