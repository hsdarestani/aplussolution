from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import ClientCompany, Location, Position, Shift, User
from core.portal_models import ClientPortalAccess

pytestmark = pytest.mark.django_db


def _create_scoped(auth_admin, company, location, positions, email='housekeeping@example.com'):
    return auth_admin.post(f'/api/clients/{company.id}/portal-users/', {
        'first_name': 'Test', 'last_name': 'Contact', 'email': email,
        'read_only': True, 'location_scope_id': str(location.id),
        'position_ids': [str(pos.id) for pos in positions],
    }, format='json')


def test_manager_can_add_contact_to_existing_customer_without_changing_existing_login(
    auth_admin, company, location, position, client_user
):
    old_hash = client_user.password
    response = _create_scoped(auth_admin, company, location, [position])
    assert response.status_code == 201, response.data
    assert response.data['temporary_password']
    assert client_user.password == old_hash
    account_id = response.data['account']['id']
    account = User.objects.get(pk=account_id)
    assert account.check_password(response.data['temporary_password'])
    assert account.role == User.Role.CLIENT
    assert company.contacts.filter(pk=account.pk).exists()
    access = ClientPortalAccess.objects.get(user=account)
    assert access.read_only is True
    assert access.client == company
    assert access.location_scope == location
    assert access.capabilities['position_ids'] == [str(position.id)]
    listing = auth_admin.get(f'/api/clients/{company.id}/portal-users/')
    assert listing.status_code == 200
    assert len(listing.data['accounts']) == 2


def test_scope_enforced_for_schedule_dashboard_and_all_other_client_apis(
    auth_admin, company, location, position, shift
):
    front = Position.objects.create(name='Front Office')
    other = Position.objects.create(name='Security')
    start = timezone.now() + timedelta(hours=2)
    Shift.objects.create(client=company, location=location, position=front, starts_at=start,
                         ends_at=start + timedelta(hours=4), status=Shift.Status.CONFIRMED)
    Shift.objects.create(client=company, location=location, position=other, starts_at=start,
                         ends_at=start + timedelta(hours=4), status=Shift.Status.CONFIRMED)
    second_site = Location.objects.create(client=company, name='Other site', address='Test')
    Shift.objects.create(client=company, location=second_site, position=front, starts_at=start,
                         ends_at=start + timedelta(hours=4), status=Shift.Status.CONFIRMED)
    created = _create_scoped(auth_admin, company, location, [position, front])
    assert created.status_code == 201, created.data
    account = User.objects.get(pk=created.data['account']['id'])
    visitor = APIClient()
    visitor.force_authenticate(account)
    shifts = visitor.get('/api/portal/client-shifts/')
    assert shifts.status_code == 200
    assert len(shifts.data) == 2
    assert str(shift.id) in {entry['id'] for entry in shifts.data}
    summary = visitor.get('/api/portal/client-dashboard/')
    assert summary.status_code == 200
    assert summary.data['upcoming_shifts'] == 2
    payload = visitor.get('/api/portal/client-access/')
    assert payload.status_code == 200
    assert set(payload.data['position_scope_ids']) == {str(position.id), str(front.id)}
    assert payload.data['capabilities']['schedule'] is True
    assert visitor.get('/api/orders/').status_code == 403
    assert visitor.get('/api/clients/').status_code == 403
    assert visitor.get('/api/clients/%s/akte/' % company.id).status_code == 403
    assert visitor.post('/api/portal/shift-change-requests/', {}, format='json').status_code == 403


def test_cross_customer_and_scope_validation_do_not_leak_or_attach_accounts(
    auth_admin, auth_client, company, location, position
):
    foreign = ClientCompany.objects.create(name='Fremd', customer_number='KD-PERM-2')
    other_site = Location.objects.create(client=foreign, name='Foreign', address='A')
    request_path = f'/api/clients/{company.id}/portal-users/'
    payload = {
        'first_name': 'T', 'last_name': 'C', 'email': 'cross@example.com',
        'read_only': True, 'location_scope_id': str(other_site.id),
        'position_ids': [str(position.id)],
    }
    assert auth_admin.post(request_path, payload, format='json').status_code == 400
    assert not User.objects.filter(email='cross@example.com').exists()
    payload['location_scope_id'] = str(location.id)
    assert auth_admin.post(request_path, payload, format='json').status_code == 201
    assert auth_admin.post(request_path, payload, format='json').status_code == 400
    assert auth_client.get(request_path).status_code == 403
    assert auth_client.post(request_path, payload, format='json').status_code == 403
    assert auth_admin.get(f'/api/clients/{foreign.id}/portal-users/').data['accounts'] == []


def test_manager_can_edit_disable_and_reset_one_named_account(
    auth_admin, company, location, position, client_user
):
    created = _create_scoped(auth_admin, company, location, [position])
    account_id = created.data['account']['id']
    detail = f'/api/clients/{company.id}/portal-users/{account_id}/'
    original_password = client_user.password
    updated = auth_admin.patch(detail, {
        'first_name': 'New', 'last_name': 'Name', 'read_only': True,
        'location_scope_id': str(location.id), 'position_ids': [str(position.id)],
        'is_active': False,
    }, format='json')
    assert updated.status_code == 200, updated.data
    assert updated.data['account']['is_active'] is False
    assert User.objects.get(pk=account_id).is_active is False
    assert client_user.password == original_password
    reset = auth_admin.post(detail + 'reset-password/', {}, format='json')
    assert reset.status_code == 200
    assert User.objects.get(pk=account_id).check_password(reset.data['temporary_password'])
    assert client_user.password == original_password


def test_full_access_cannot_be_partially_scoped(auth_admin, company, location, position):
    forbidden = auth_admin.post(f'/api/clients/{company.id}/portal-users/', {
        'email': 'invalid-full@example.com', 'first_name': 'Test', 'last_name': 'Name',
        'read_only': False, 'location_scope_id': str(location.id),
        'position_ids': [str(position.id)],
    }, format='json')
    assert forbidden.status_code == 400
    assert not User.objects.filter(email='invalid-full@example.com').exists()
