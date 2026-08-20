from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import ClientCompany, Contract, ContractTemplate, Location, Notification, Position, Shift, TimeEntry, User, WorkerProfile
from core.portal_models import PortalInvitation
from core.portal_service import create_portal_invitation


@pytest.mark.django_db
def test_invitation_stores_only_hash_and_activates_once(settings, admin_user, worker_user):
    settings.APP_URL = 'https://solution.smarbiz.sbs'
    settings.EMAIL_HOST = ''
    worker_user.set_unusable_password()
    worker_user.is_onboarded = False
    worker_user.save(update_fields=['password', 'is_onboarded'])

    invitation, url, delivered = create_portal_invitation(worker_user.worker_profile, admin_user)
    raw = url.split('token=', 1)[1]
    assert delivered is False
    assert raw not in invitation.token_hash
    assert len(invitation.token_hash) == 64

    public = APIClient()
    valid = public.post('/api/auth/activation/validate/', {'token': raw}, format='json')
    assert valid.status_code == 200
    complete = public.post('/api/auth/activation/complete/', {
        'token': raw,
        'password': 'NewSecurePass123!',
        'password_confirm': 'NewSecurePass123!',
    }, format='json')
    assert complete.status_code == 200
    assert complete.data['access'] and complete.data['refresh']
    worker_user.refresh_from_db()
    assert worker_user.is_onboarded is True
    assert worker_user.check_password('NewSecurePass123!')
    reused = public.post('/api/auth/activation/validate/', {'token': raw}, format='json')
    assert reused.status_code == 400


@pytest.mark.django_db
def test_invitation_rejects_synthetic_wiw_email(settings, admin_user):
    user = User.objects.create(email='wiw-123@sync.invalid', role='worker', first_name='NoMail', wiw_id='123', is_active=True)
    user.set_unusable_password(); user.save()
    worker = WorkerProfile.objects.create(user=user, employee_number='WIW-123', wiw_user_id='123')
    with pytest.raises(ValueError, match='E-Mail'):
        create_portal_invitation(worker, admin_user)


@pytest.mark.django_db
def test_expired_activation_token_is_rejected(settings, admin_user, worker_user):
    settings.EMAIL_HOST = ''
    worker_user.set_unusable_password(); worker_user.save(update_fields=['password'])
    invitation, url, _ = create_portal_invitation(worker_user.worker_profile, admin_user)
    invitation.expires_at = timezone.now() - timedelta(minutes=1)
    invitation.save(update_fields=['expires_at'])
    response = APIClient().post('/api/auth/activation/validate/', {'token': url.split('token=', 1)[1]}, format='json')
    assert response.status_code == 400
    assert 'abgelaufen' in response.data['detail']


@pytest.mark.django_db
def test_synced_unusable_worker_is_not_marked_onboarded():
    user = User.objects.create(email='sync@example.com', role='worker', wiw_id='999', is_onboarded=True)
    user.set_unusable_password(); user.save()
    user.refresh_from_db()
    assert user.is_onboarded is False


@pytest.mark.django_db
def test_admin_invite_endpoint_returns_link_when_smtp_missing(settings, auth_admin, worker_user):
    settings.EMAIL_HOST = ''
    worker_user.set_unusable_password(); worker_user.is_onboarded = False; worker_user.save(update_fields=['password','is_onboarded'])
    response = auth_admin.post(f'/api/workers/{worker_user.worker_profile.id}/invite/', {}, format='json')
    assert response.status_code == 201
    assert response.data['delivered'] is False
    assert response.data['activation_url'].startswith(settings.APP_URL)
    assert PortalInvitation.objects.filter(user=worker_user, used_at__isnull=True).count() == 1


@pytest.mark.django_db
def test_new_worker_onboard_requires_portal_activation(auth_admin):
    response = auth_admin.post('/api/workers/onboard/', {
        'email': 'new-worker@example.com',
        'first_name': 'Neu',
        'last_name': 'Mitarbeiter',
        'employee_number': 'MA-NEW-001',
    }, format='json')

    assert response.status_code == 201
    assert response.data['temporary_password'] is None
    assert response.data['requires_activation'] is True

    user = User.objects.get(email='new-worker@example.com')
    assert user.has_usable_password() is False
    assert user.is_onboarded is False

    status_response = auth_admin.get('/api/workers/portal-status/?search=new-worker@example.com')
    assert status_response.status_code == 200
    assert len(status_response.data) == 1
    assert status_response.data[0]['state'] == 'not_activated'


@pytest.mark.django_db
def test_worker_home_uses_claimed_slots_not_legacy_worker(auth_worker, worker_user, company, location, position):
    now = timezone.now()
    own = Shift.objects.create(
        client=company, location=location, position=position,
        starts_at=now + timedelta(hours=2), ends_at=now + timedelta(hours=6),
        status='published', is_open=True, required_count=2,
    )
    claimed = auth_worker.post(f'/api/shifts/{own.id}/claim/', {}, format='json')
    assert claimed.status_code == 200
    own.refresh_from_db()
    assert own.worker_id is None

    available = Shift.objects.create(
        client=company, location=location, position=position,
        starts_at=now + timedelta(days=1), ends_at=now + timedelta(days=1, hours=4),
        status='published', is_open=True, required_count=1,
    )
    TimeEntry.objects.create(worker=worker_user.worker_profile, clock_in=now - timedelta(hours=2), clock_out=now - timedelta(hours=1))
    Notification.objects.create(user=worker_user, title='Test', body='Hinweis')

    response = auth_worker.get('/api/employee/home/')
    assert response.status_code == 200
    assert response.data['next_shift']['id'] == str(own.id)
    assert response.data['available_count'] >= 1
    assert any(item['id'] == str(available.id) for item in response.data['available_shifts'])
    assert response.data['month_worked_minutes'] >= 60
    assert response.data['unread_notifications'] >= 1


@pytest.mark.django_db
def test_employee_home_ignores_imported_and_open_time_rows(auth_worker, worker_user):
    now = timezone.now()
    TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        clock_in=now - timedelta(hours=2),
        clock_out=now - timedelta(hours=1),
        approved=True,
    )
    TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        clock_in=now - timedelta(hours=10),
        clock_out=now - timedelta(hours=1),
        approved=False,
        wiw_time_id='legacy-time-home-1',
    )
    TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        clock_in=now - timedelta(hours=20),
        clock_out=None,
        approved=False,
        wiw_time_id='legacy-time-home-open',
    )

    response = auth_worker.get('/api/employee/home/')

    assert response.status_code == 200
    assert response.data['month_worked_minutes'] == 60


@pytest.mark.django_db
def test_portal_status_route_is_not_shadowed_by_worker_detail(auth_admin, worker_user):
    response = auth_admin.get('/api/workers/portal-status/')
    assert response.status_code == 200
    assert isinstance(response.data, list)
    assert any(item['worker_id'] == str(worker_user.worker_profile.id) for item in response.data)


@pytest.mark.django_db
def test_portal_status_and_bulk_invite_skip_synthetic_migration_workers(settings, auth_admin):
    settings.EMAIL_HOST = ''
    user = User.objects.create(email='wiw-portal-only@sync.invalid', role='worker', is_active=True)
    user.set_unusable_password(); user.save()
    worker = WorkerProfile.objects.create(user=user, employee_number='WIW-PORTAL-ONLY', active=True, wiw_user_id='portal-only')

    statuses = auth_admin.get('/api/workers/portal-status/?search=WIW-PORTAL-ONLY')
    assert statuses.status_code == 200
    assert statuses.data == []

    bulk = auth_admin.post('/api/workers/bulk-invite/', {'worker_ids': [str(worker.id)]}, format='json')
    assert bulk.status_code == 200
    assert bulk.data['count'] == 0
    assert bulk.data['results'] == []
    assert not PortalInvitation.objects.filter(user=user).exists()

    direct = auth_admin.post(f'/api/workers/{worker.id}/invite/', {}, format='json')
    assert direct.status_code == 404


@pytest.mark.django_db
def test_worker_list_api_hides_synthetic_migration_rows(auth_admin):
    user = User.objects.create(email='wiw-list-only@sync.invalid', role='worker', is_active=True)
    user.set_unusable_password(); user.save()
    worker = WorkerProfile.objects.create(user=user, employee_number='WIW-LIST-ONLY', active=True, wiw_user_id='list-only')

    response = auth_admin.get('/api/workers/?search=WIW-LIST-ONLY')
    assert response.status_code == 200
    rows = response.data.get('results', response.data) if hasattr(response.data, 'get') else response.data
    assert all(str(item['id']) != str(worker.id) for item in rows)


@pytest.mark.django_db
def test_bulk_invite_route_accepts_post_instead_of_worker_detail_405(settings, auth_admin, worker_user):
    settings.EMAIL_HOST = ''
    worker_user.set_unusable_password()
    worker_user.is_onboarded = False
    worker_user.save(update_fields=['password', 'is_onboarded'])

    response = auth_admin.post(
        '/api/workers/bulk-invite/',
        {'worker_ids': [str(worker_user.worker_profile.id)]},
        format='json',
    )

    assert response.status_code == 200
    assert response.data['count'] == 1
    assert response.data['results'][0]['worker_id'] == str(worker_user.worker_profile.id)
    assert 'activation_url' in response.data['results'][0]
