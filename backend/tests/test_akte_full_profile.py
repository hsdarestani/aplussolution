import pytest

from core.models import ClientCompany, EmployeeMasterData, User


@pytest.mark.django_db
def test_admin_can_edit_worker_akte_user_profile_and_master_data(auth_admin, worker_user):
    worker = worker_user.worker_profile
    response = auth_admin.patch(
        f'/api/workers/{worker.id}/akte/',
        {
            'profile': {
                'first_name': 'Anna Maria',
                'last_name': 'Becker',
                'email': 'anna.akte@example.test',
                'phone': '+4969123456',
                'employee_number': 'MA-AKTE-1',
                'employment_type': 'teilzeit',
                'monthly_hours': '90.00',
                'tariff_hourly_rate': '16.50',
                'extra_allowance': '1.50',
                'active': True,
            },
            'master_data': {
                'street': 'Musterstraße 1',
                'postal_code': '60311',
                'city': 'Frankfurt am Main',
                'iban': 'DE02120300000000202051',
            },
        },
        format='json',
    )
    assert response.status_code == 200, response.data
    worker.refresh_from_db(); worker.user.refresh_from_db()
    assert worker.user.first_name == 'Anna Maria'
    assert worker.user.email == 'anna.akte@example.test'
    assert worker.employee_number == 'MA-AKTE-1'
    assert str(worker.monthly_hours) == '90.00'
    master = EmployeeMasterData.objects.get(worker=worker)
    assert master.data['city'] == 'Frankfurt am Main'
    assert response.data['master_data']['data']['street'] == 'Musterstraße 1'


@pytest.mark.django_db
def test_worker_cannot_edit_own_akte(auth_worker, worker_user):
    response = auth_worker.patch(
        f'/api/workers/{worker_user.worker_profile.id}/akte/',
        {'profile': {'tariff_hourly_rate': '99.00'}},
        format='json',
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_can_edit_client_akte_and_primary_contact(auth_admin, client_user):
    company = client_user.client_companies.get()
    response = auth_admin.patch(
        f'/api/clients/{company.id}/akte/',
        {'profile': {
            'name': 'Kunde Akte GmbH',
            'customer_number': 'KD-AKTE-1',
            'address': 'Neue Straße 10, Frankfurt',
            'vat_id': 'DE123456789',
            'notes': 'Wichtiger Kunde',
            'active': True,
            'contract_visibility_enabled': False,
            'contact_first_name': 'Klara Neu',
            'contact_email': 'klara.neu@example.test',
            'contact_phone': '+4969987654',
        }},
        format='json',
    )
    assert response.status_code == 200, response.data
    company.refresh_from_db(); client_user.refresh_from_db()
    assert company.name == 'Kunde Akte GmbH'
    assert company.customer_number == 'KD-AKTE-1'
    assert company.contract_visibility_enabled is False
    assert client_user.first_name == 'Klara Neu'
    assert client_user.email == 'klara.neu@example.test'


@pytest.mark.django_db
def test_admin_can_create_missing_client_contact_by_saving_akte(auth_admin):
    company = ClientCompany.objects.create(name='Altbestand GmbH', customer_number='KD-ALT-1')

    response = auth_admin.patch(
        f'/api/clients/{company.id}/akte/',
        {'profile': {
            'name': 'Altbestand GmbH',
            'customer_number': 'KD-ALT-1',
            'contact_first_name': 'Maria',
            'contact_last_name': 'Muster',
            'contact_email': 'maria.muster@example.test',
            'contact_phone': '+4969000111',
        }},
        format='json',
    )

    assert response.status_code == 200, response.data
    company.refresh_from_db()
    contact = company.contacts.get()
    assert contact.role == User.Role.CLIENT
    assert contact.email == 'maria.muster@example.test'
    assert contact.first_name == 'Maria'
    assert contact.last_name == 'Muster'
    assert contact.phone == '+4969000111'
    assert contact.is_active is True
    assert contact.has_usable_password() is False
    assert response.data['profile']['contacts_detail'][0]['email'] == 'maria.muster@example.test'


@pytest.mark.django_db
def test_saving_client_without_contact_values_does_not_force_portal_contact(auth_admin):
    company = ClientCompany.objects.create(name='Nur Firma GmbH', customer_number='KD-NUR-1')

    response = auth_admin.patch(
        f'/api/clients/{company.id}/akte/',
        {'profile': {
            'name': 'Nur Firma Neu GmbH',
            'customer_number': 'KD-NUR-1',
            'contact_first_name': '',
            'contact_last_name': '',
            'contact_email': '',
            'contact_phone': '',
        }},
        format='json',
    )

    assert response.status_code == 200, response.data
    company.refresh_from_db()
    assert company.name == 'Nur Firma Neu GmbH'
    assert company.contacts.count() == 0


@pytest.mark.django_db
def test_saving_missing_client_contact_rejects_duplicate_email(auth_admin):
    existing = User.objects.create_user(
        email='used@example.test',
        password='StrongPass123!',
        role=User.Role.CLIENT,
        is_onboarded=True,
    )
    other_company = ClientCompany.objects.create(name='Andere GmbH', customer_number='KD-OTHER-AKTE')
    other_company.contacts.add(existing)
    company = ClientCompany.objects.create(name='Neu GmbH', customer_number='KD-NEW-AKTE')

    response = auth_admin.patch(
        f'/api/clients/{company.id}/akte/',
        {'profile': {
            'name': 'Neu GmbH',
            'customer_number': 'KD-NEW-AKTE',
            'contact_email': 'used@example.test',
        }},
        format='json',
    )

    assert response.status_code == 400
    assert 'bereits vergeben' in response.data['detail']
    assert company.contacts.count() == 0


@pytest.mark.django_db
def test_client_cannot_edit_own_company_akte(auth_client, client_user):
    company = client_user.client_companies.get()
    response = auth_client.patch(f'/api/clients/{company.id}/akte/', {'profile': {'name': 'Manipuliert GmbH'}}, format='json')
    assert response.status_code == 403
    company.refresh_from_db()
    assert company.name != 'Manipuliert GmbH'
