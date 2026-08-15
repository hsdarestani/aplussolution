from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import ClientCompany, Location, Position, Shift, User, WorkerProfile
from core.scheduling_rules import evaluate_worker_for_shift
from core.workplace_access import seed_system_roles
from core.workplace_models import AccessRole, UserAccessAssignment, WorkplaceSettings


pytestmark = pytest.mark.django_db


def manager_client(manager):
    client = APIClient()
    client.force_authenticate(manager)
    return client


def assign_role(manager, code, *, scope='all', locations=None, workers=None, share=False):
    seed_system_roles()
    role = AccessRole.objects.get(code=code)
    assignment = UserAccessAssignment.objects.create(user=manager, access_role=role, scope_mode=scope, can_share_labor=share)
    if locations:
        assignment.locations.set(locations)
    if workers:
        assignment.workers.set(workers)
    return assignment


def unpack(response):
    body = response.json()
    return body if isinstance(body, list) else body.get('results', [])


def test_admin_can_manage_workplace_settings(auth_admin):
    seed_system_roles()
    response = auth_admin.get('/api/workplace/snapshot/')
    assert response.status_code == 200
    assert {'dispatcher', 'supervisor', 'scheduler', 'payroll', 'viewer'} <= {item['code'] for item in response.json()['roles']}
    assert response.json()['can_manage_settings'] is True
    assert response.json()['can_manage_roles'] is True

    response = auth_admin.patch('/api/workplace/settings/', {
        'timezone': 'Europe/Berlin',
        'week_starts_on': 6,
        'currency': 'CHF',
        'overtime_daily_hours': '9.00',
        'overtime_weekly_hours': '42.00',
        'overtime_mode': 'block',
        'overtime_multiplier': '1.50',
        'labor_sharing_enabled': False,
    }, format='json')
    assert response.status_code == 200
    stored = WorkplaceSettings.load()
    assert stored.week_starts_on == 6
    assert stored.currency == 'CHF'
    assert stored.overtime_mode == 'block'
    assert stored.labor_sharing_enabled is False


def test_scheduler_role_cannot_open_payroll(manager_user):
    assign_role(manager_user, 'scheduler', scope='all')
    client = manager_client(manager_user)
    assert client.get('/api/shifts/').status_code == 200
    assert client.get('/api/pay-periods/').status_code == 403
    assert client.get('/api/workplace/settings/').status_code == 403


def test_scoped_supervisor_only_sees_scoped_workers_and_shifts(manager_user, worker_user, second_worker, company, location, position):
    other_company = ClientCompany.objects.create(name='Andere GmbH', customer_number='KD-099')
    other_location = Location.objects.create(client=other_company, name='Berlin', address='Berlin')
    now = timezone.now() + timedelta(days=2)
    scoped_shift = Shift.objects.create(client=company, location=location, position=position, starts_at=now, ends_at=now + timedelta(hours=5), status=Shift.Status.PUBLISHED)
    Shift.objects.create(client=other_company, location=other_location, position=position, starts_at=now, ends_at=now + timedelta(hours=5), status=Shift.Status.PUBLISHED)
    assignment = assign_role(manager_user, 'supervisor', scope='scoped', locations=[location], workers=[worker_user.worker_profile])
    client = manager_client(manager_user)

    workers = unpack(client.get('/api/workers/'))
    assert {item['id'] for item in workers} == {str(worker_user.worker_profile.id)}
    shifts = unpack(client.get('/api/shifts/'))
    assert {item['id'] for item in shifts} == {str(scoped_shift.id)}

    snapshot = client.get('/api/workplace/snapshot/')
    assert snapshot.status_code == 200
    assert snapshot.json()['current_user']['scope']['mode'] == 'scoped'
    assert {item['id'] for item in snapshot.json()['workers']} == {str(worker_user.worker_profile.id)}
    assert snapshot.json()['assignments'][0]['user'] == str(manager_user.id)


def test_wage_fields_are_redacted_for_role_without_wage_access(manager_user, worker_user):
    assign_role(manager_user, 'scheduler', scope='all')
    client = manager_client(manager_user)
    response = client.get('/api/workers/')
    assert response.status_code == 200
    row = unpack(response)[0]
    assert row['tariff_hourly_rate'] is None
    assert row['extra_allowance'] is None
    assert row['wage_hidden'] is True


def test_labor_sharing_controls_cross_scope_assignment(manager_user, worker_user, second_worker, company, location, position):
    settings = WorkplaceSettings.load()
    settings.labor_sharing_enabled = True
    settings.overtime_mode = 'off'
    settings.save(update_fields=['labor_sharing_enabled', 'overtime_mode', 'updated_at'])
    assignment = assign_role(manager_user, 'supervisor', scope='scoped', locations=[location], workers=[worker_user.worker_profile], share=False)
    now = timezone.now() + timedelta(days=4)
    shift = Shift.objects.create(client=company, location=location, position=position, starts_at=now, ends_at=now + timedelta(hours=5), status=Shift.Status.PUBLISHED, required_count=1)
    client = manager_client(manager_user)

    response = client.post('/api/scheduling/assign/', {'shift': str(shift.id), 'worker': str(second_worker.id)}, format='json')
    assert response.status_code == 403

    assignment.can_share_labor = True
    assignment.save(update_fields=['can_share_labor', 'updated_at'])
    response = client.post('/api/scheduling/assign/', {'shift': str(shift.id), 'worker': str(second_worker.id)}, format='json')
    assert response.status_code == 200
    assert response.json()['worker'] == str(second_worker.id)


def test_workplace_overtime_threshold_can_block_assignment(second_worker, company, location, position):
    settings = WorkplaceSettings.load()
    settings.week_starts_on = 0
    settings.overtime_daily_hours = '8.00'
    settings.overtime_weekly_hours = '40.00'
    settings.overtime_mode = 'block'
    settings.save()
    start = (timezone.now() + timedelta(days=7)).replace(hour=8, minute=0, second=0, microsecond=0)
    candidate = Shift.objects.create(client=company, location=location, position=position, starts_at=start, ends_at=start + timedelta(hours=9), break_minutes=0, status=Shift.Status.DRAFT)

    result = evaluate_worker_for_shift(second_worker, candidate)
    codes = {item['code'] for item in result['blockers']}
    assert 'daily_overtime_threshold' in codes
    assert result['eligible'] is False
    assert result['overtime']['daily_hours'] == '8.00'
