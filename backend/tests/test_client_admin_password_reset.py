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
    assert response.data['portal_access_created'] is False
    assert response.data['portal_access_reactivated'] is False
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
def test_reset_requires_email_when_client_has_no_portal_account(auth_admin):
    company = ClientCompany.objects.create(name='Ohne Login GmbH', customer_number='KD-NOLOGIN')

    response = auth_admin.post(f'/api/clients/{company.id}/reset-password/', {}, format='json')

    assert response.status_code == 400
    assert 'Kontakt-E-Mail' in response.data['detail']
    assert company.contacts.count() == 0


@pytest.mark.django_db
def test_reset_creates_first_client_portal_account_when_email_is_supplied(auth_admin):
    company = ClientCompany.objects.create(name='Neue Portal GmbH', customer_number='KD-PORTAL')

    response = auth_admin.post(
        f'/api/clients/{company.id}/reset-password/',
        {
            'contact_email': 'portal@example.com',
            'contact_first_name': 'Klara',
            'contact_last_name': 'Kunde',
            'contact_phone': '+4912345',
        },
        format='json',
    )

    assert response.status_code == 200
    assert response.data['portal_access_created'] is True
    assert response.data['portal_access_reactivated'] is False
    assert response.data['email'] == 'portal@example.com'

    contact = company.contacts.get()
    assert contact.role == User.Role.CLIENT
    assert contact.is_active is True
    assert contact.is_onboarded is True
    assert contact.first_name == 'Klara'
    assert contact.last_name == 'Kunde'
    assert contact.phone == '+4912345'
    assert contact.check_password(response.data['temporary_password'])


@pytest.mark.django_db
def test_reset_reactivates_inactive_linked_client_contact(auth_admin, client_user, company):
    client_user.is_active = False
    client_user.save(update_fields=['is_active'])

    response = auth_admin.post(
        f'/api/clients/{company.id}/reset-password/',
        {'contact_id': str(client_user.id)},
        format='json',
    )

    assert response.status_code == 200
    assert response.data['portal_access_created'] is False
    assert response.data['portal_access_reactivated'] is True

    client_user.refresh_from_db()
    assert client_user.is_active is True
    assert client_user.check_password(response.data['temporary_password'])


@pytest.mark.django_db
def test_reset_does_not_attach_email_that_is_already_registered(auth_admin):
    company = ClientCompany.objects.create(name='Konflikt GmbH', customer_number='KD-CONFLICT')
    existing = User.objects.create_user(
        'used@example.com',
        'StrongPass123!',
        role=User.Role.CLIENT,
        is_onboarded=True,
    )

    response = auth_admin.post(
        f'/api/clients/{company.id}/reset-password/',
        {'contact_email': existing.email},
        format='json',
    )

    assert response.status_code == 400
    assert 'bereits registriert' in response.data['detail']
    assert company.contacts.count() == 0
    assert existing.check_password('StrongPass123!')
