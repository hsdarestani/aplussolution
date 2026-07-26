from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import ClientCompany, Location, Position, Shift, User, WorkerProfile


@pytest.fixture(autouse=True)
def test_settings(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / 'media'
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    settings.COMPANY_NAME = 'A+ Solution GmbH'
    settings.COMPANY_ADDRESS = 'Carl-Sonnenschein-Str. 57, 65936 Frankfurt am Main'
    settings.COMPANY_BUSINESS_NUMBER = 'BETRIEB-1'
    settings.AUEG_LICENSE_AUTHORITY = 'Agentur für Arbeit Düsseldorf'
    settings.AUEG_LICENSE_DATE = '19.04.2026'
    settings.WIW_SYNC_ENABLED = True
    return settings


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_user(db):
    return User.objects.create_user('admin@example.com', 'StrongPass123!', first_name='Admin', role=User.Role.ADMIN, is_staff=True)


@pytest.fixture
def manager_user(db):
    return User.objects.create_user('manager@example.com', 'StrongPass123!', first_name='Manager', role=User.Role.MANAGER)


@pytest.fixture
def worker_user(db):
    user = User.objects.create_user('worker@example.com', 'StrongPass123!', first_name='Anna', last_name='Becker', phone='+491234', role=User.Role.WORKER, is_onboarded=True)
    WorkerProfile.objects.create(user=user, employee_number='MA-001', employment_type='minijob', monthly_hours='38.90', tariff_hourly_rate='14.50')
    return user


@pytest.fixture
def second_worker(db):
    user = User.objects.create_user('worker2@example.com', 'StrongPass123!', first_name='Lukas', last_name='Schmidt', role=User.Role.WORKER, is_onboarded=True)
    return WorkerProfile.objects.create(user=user, employee_number='MA-002', employment_type='teilzeit', monthly_hours='80', tariff_hourly_rate='15.00')


@pytest.fixture
def client_user(db):
    user = User.objects.create_user('client@example.com', 'StrongPass123!', first_name='Klara', role=User.Role.CLIENT, is_onboarded=True)
    company = ClientCompany.objects.create(name='Kunde GmbH', customer_number='KD-001', address='Kundenweg 1, Frankfurt')
    company.contacts.add(user)
    return user


@pytest.fixture
def company(client_user):
    return client_user.client_companies.get()


@pytest.fixture
def position(db):
    return Position.objects.create(name='Servicekraft')


@pytest.fixture
def location(company):
    return Location.objects.create(client=company, name='Messe Frankfurt', address='Messeplatz 1', latitude='50.110000', longitude='8.680000', geofence_radius_m=250)


@pytest.fixture
def shift(worker_user, company, location, position):
    now = timezone.now() + timedelta(hours=1)
    return Shift.objects.create(
        client=company,
        location=location,
        position=position,
        worker=worker_user.worker_profile,
        starts_at=now,
        ends_at=now + timedelta(hours=6),
        status=Shift.Status.CONFIRMED,
    )


@pytest.fixture
def auth_admin(admin_user):
    client = APIClient()
    client.force_authenticate(admin_user)
    return client


@pytest.fixture
def auth_worker(worker_user):
    client = APIClient()
    client.force_authenticate(worker_user)
    return client


@pytest.fixture
def auth_client(client_user):
    client = APIClient()
    client.force_authenticate(client_user)
    return client
