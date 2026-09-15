import pytest
from rest_framework.test import APIClient

from core.models import ClientCompany, User


@pytest.mark.django_db
def test_admin_can_reset_client_portal_password(auth_admin, client_user, company):
    old_password_hash = client_user.password

    response = auth_admin.post(
        f'/api/clients/{company.id}/reset-password/',
        {'contact_id': str(client_user.id)},
        format='json',
    )

    assert response.status_code == 200
    assert response.data['email'] == client_user.email
    temporary_password = response.data['temporary_password']
    assert temporary_password
    assert len(temporary_password) >= 10

    client_user.refresh_from_db()
    assert client_user.password != old_password_hash
    assert client_user.check_password(temporary_password)


@pytest.mark.django_db
def test_manager_cannot_reset_client_portal_password(api_client, manager_user, client_user, company):
    api_client.force_authenticate(manager_user)
    old_password_hash = client_user.password

    response = api_client.post(
        f'/api/clients/{company.id}/reset-password/',
        {'contact_id': str(client_user.id)},
        format='json',
    )

    assert response.status_code == 403
    client_user.refresh_from_db()
    assert client_user.password == old_password_hash


@pytest.mark.django_db
def test_reset_rejects_contact_from_another_customer(auth_admin, client_user, company):
    other_user = User.objects.create_user(
        'other-client@example.com',
        'StrongPass123!',
        role=User.Role.CLIENT,
        is_onboarded=True,
    )
    other_company = ClientCompany.objects.create(name='Andere GmbH', customer_number='KD-OTHER')
    other_company.contacts.add(other_user)

    response = auth_admin.post(
        f'/api/clients/{company.id}/reset-password/',
        {'contact_id': str(other_user.id)},
        format='json',
    )

    assert response.status_code == 400
    assert 'gehört nicht zu diesem Kunden' in response.data['detail']
    assert other_user.check_password('StrongPass123!')


@pytest.mark.django_db
def test_reset_does_not_create_missing_client_portal_account(auth_admin):
    company = ClientCompany.objects.create(name='Ohne Login GmbH', customer_number='KD-NOLOGIN')

    response = auth_admin.post(f'/api/clients/{company.id}/reset-password/', {}, format='json')

    assert response.status_code == 400
    assert 'kein aktiver Portal-Zugang' in response.data['detail']
    assert company.contacts.count() == 0
