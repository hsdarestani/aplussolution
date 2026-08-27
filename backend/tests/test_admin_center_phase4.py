from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.attendance_models import TimeEntryCorrection
from core.models import (
    ClientOrder,
    Contract,
    ContractTemplate,
    EmployeeMasterData,
    IntegrationSyncRun,
    Shift,
    TimeEntry,
)
from core.shift_slots import ShiftSlot


@pytest.mark.django_db
def test_admin_exception_center_collects_actionable_work(auth_admin, worker_user, company, location, position, admin_user):
    now = timezone.now()
    EmployeeMasterData.objects.create(
        worker=worker_user.worker_profile,
        completeness=45,
        missing_fields=['iban', 'tax_identification_number'],
    )
    demand = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=now + timedelta(hours=3),
        ends_at=now + timedelta(hours=8),
        status=Shift.Status.PUBLISHED,
        required_count=2,
    )
    first_slot = demand.slots.order_by('created_at').first()
    first_slot.worker = worker_user.worker_profile
    first_slot.status = ShiftSlot.Status.CLAIMED
    first_slot.claimed_at = now
    first_slot.save(update_fields=['worker', 'status', 'claimed_at', 'updated_at'])

    late_shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=now - timedelta(hours=1),
        ends_at=now + timedelta(hours=3),
        status=Shift.Status.PUBLISHED,
        required_count=1,
    )
    late_slot = late_shift.slots.first()
    late_slot.worker = worker_user.worker_profile
    late_slot.status = ShiftSlot.Status.CLAIMED
    late_slot.claimed_at = now - timedelta(hours=2)
    late_slot.save(update_fields=['worker', 'status', 'claimed_at', 'updated_at'])

    entry = TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        shift=demand,
        clock_in=now - timedelta(hours=4),
        clock_out=now - timedelta(hours=1),
        approved=False,
    )
    TimeEntryCorrection.objects.create(
        entry=entry,
        requested_by=worker_user.worker_profile,
        requested_clock_in=entry.clock_in - timedelta(minutes=15),
        reason='Tatsächlicher Beginn war früher.',
    )
    template = ContractTemplate.objects.create(
        name='Phase4 Arbeitsvertrag',
        slug='phase4-employment',
        kind=ContractTemplate.Kind.EMPLOYMENT,
        schema={},
    )
    Contract.objects.create(
        template=template,
        worker=worker_user.worker_profile,
        title='Arbeitsvertrag Phase 4',
        status=Contract.Status.SENT,
        ends_on=timezone.localdate() + timedelta(days=5),
        created_by=admin_user,
    )
    IntegrationSyncRun.objects.create(
        provider='personio',
        status=IntegrationSyncRun.Status.FAILED,
        mode='incremental',
        errors=[{'error': 'API nicht erreichbar'}],
    )

    response = auth_admin.get('/api/admin/exceptions/')
    assert response.status_code == 200
    categories = {item['category'] for item in response.data['results']}
    assert {'staffing', 'attendance', 'contracts', 'documents', 'integrations'} <= categories
    assert response.data['summary']['critical'] >= 2
    assert any(item['object_id'] == str(demand.id) and item['category'] == 'staffing' for item in response.data['results'])
    assert any(item['object_id'] == str(late_shift.id) and item['title'] == 'Kein Check-in erfasst' for item in response.data['results'])


@pytest.mark.django_db
def test_admin_exception_center_filters_category_and_query(auth_admin, worker_user):
    EmployeeMasterData.objects.create(
        worker=worker_user.worker_profile,
        completeness=60,
        missing_fields=['iban'],
    )
    response = auth_admin.get('/api/admin/exceptions/?category=documents&q=Anna')
    assert response.status_code == 200
    assert response.data['results']
    assert all(item['category'] == 'documents' for item in response.data['results'])
    assert all('anna' in f"{item['title']} {item['message']}".lower() for item in response.data['results'])


@pytest.mark.django_db
def test_worker_cannot_access_admin_exception_center_or_global_search(worker_user):
    client = APIClient(); client.force_authenticate(worker_user)
    assert client.get('/api/admin/exceptions/').status_code == 403
    assert client.get('/api/search/global/?q=Anna').status_code == 403


@pytest.mark.django_db
def test_global_search_finds_core_operational_entities(auth_admin, worker_user, company, location, position, admin_user):
    now = timezone.now()
    company.name = 'Acme Event GmbH'
    company.save(update_fields=['name', 'updated_at'])
    order = ClientOrder.objects.create(
        client=company,
        location=location,
        title='Acme Sommergala',
        description='Servicepersonal für Acme',
        starts_at=now + timedelta(days=2),
        ends_at=now + timedelta(days=2, hours=8),
        requested_staff=4,
        created_by=admin_user,
    )
    Shift.objects.create(
        order=order,
        client=company,
        location=location,
        position=position,
        starts_at=order.starts_at,
        ends_at=order.ends_at,
        status=Shift.Status.PUBLISHED,
        required_count=4,
    )
    template = ContractTemplate.objects.create(
        name='Acme Rahmenvertrag',
        slug='acme-contract',
        kind=ContractTemplate.Kind.EMPLOYMENT,
        schema={},
    )
    Contract.objects.create(
        template=template,
        client=company,
        title='Acme Vertrag Sommergala',
        status=Contract.Status.READY,
        created_by=admin_user,
    )

    response = auth_admin.get('/api/search/global/?q=Acme&limit=10')
    assert response.status_code == 200
    types = {item['type'] for item in response.data['results']}
    assert {'client', 'order', 'shift', 'contract'} <= types
    assert response.data['total'] >= 4

    worker_search = auth_admin.get('/api/search/global/?q=Anna')
    assert worker_search.status_code == 200
    assert any(item['type'] == 'worker' and 'Anna' in item['label'] for item in worker_search.data['results'])


@pytest.mark.django_db
def test_searchable_admin_lists_support_search_and_ordering(auth_admin, worker_user, company, location, admin_user):
    now = timezone.now()
    order = ClientOrder.objects.create(
        client=company,
        location=location,
        title='Suchbarer Messeauftrag',
        starts_at=now + timedelta(days=3),
        ends_at=now + timedelta(days=3, hours=6),
        requested_staff=2,
        created_by=admin_user,
    )
    worker_response = auth_admin.get('/api/workers/?search=Anna&ordering=employee_number')
    assert worker_response.status_code == 200
    assert any(item['employee_number'] == worker_user.worker_profile.employee_number for item in worker_response.data['results'])

    order_response = auth_admin.get('/api/orders/?search=Messeauftrag&ordering=-starts_at')
    assert order_response.status_code == 200
    assert any(item['id'] == str(order.id) for item in order_response.data['results'])


@pytest.mark.django_db
def test_phase4_exception_center_ignores_imported_wiw_time_audit_rows(auth_admin, worker_user, shift):
    now = timezone.now()
    entry = TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        shift=shift,
        clock_in=now - timedelta(days=10, hours=5),
        clock_out=now - timedelta(days=10, hours=1),
        approved=False,
        wiw_time_id='wiw-phase4-readonly-1',
    )
    correction = TimeEntryCorrection.objects.create(
        entry=entry,
        requested_by=worker_user.worker_profile,
        requested_clock_in=entry.clock_in - timedelta(minutes=30),
        reason='Legacy correction linked to imported history.',
    )

    response = auth_admin.get('/api/admin/exceptions/?category=attendance&limit=200')
    assert response.status_code == 200
    assert all(item['object_id'] != str(entry.id) for item in response.data['results'])
    assert all(item['object_id'] != str(correction.id) for item in response.data['results'])


@pytest.mark.django_db
def test_phase4_global_search_and_documents_hide_migration_only_worker_profiles(auth_admin, worker_user):
    worker_user.email = 'anna.phase4@sync.invalid'
    worker_user.save(update_fields=['email'])
    EmployeeMasterData.objects.create(
        worker=worker_user.worker_profile,
        completeness=10,
        missing_fields=['iban', 'tax_identification_number'],
    )

    search = auth_admin.get('/api/search/global/?q=Anna&limit=10')
    assert search.status_code == 200
    assert all(item['id'] != str(worker_user.worker_profile.id) for item in search.data['results'] if item['type'] == 'worker')

    exceptions = auth_admin.get('/api/admin/exceptions/?category=documents&limit=200')
    assert exceptions.status_code == 200
    assert all(item['object_id'] != str(worker_user.worker_profile.id) for item in exceptions.data['results'])


@pytest.mark.django_db
def test_phase4_ignores_old_wiw_failures_once_wiw_sync_is_disabled(auth_admin, settings):
    settings.WIW_SYNC_ENABLED = False
    failed = IntegrationSyncRun.objects.create(
        provider='wiw',
        status=IntegrationSyncRun.Status.FAILED,
        mode='final_full',
        errors=[{'error': 'Historical cutover attempt failed before the successful import.'}],
    )

    response = auth_admin.get('/api/admin/exceptions/?category=integrations&limit=200')
    assert response.status_code == 200
    assert all(item['object_id'] != str(failed.id) for item in response.data['results'])
