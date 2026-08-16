from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Shift, TimeEntry
from core.premium_models import SchedulingPolicy
from core.shift_slots import ShiftSlot


@pytest.mark.django_db
def test_premium_policy_and_auto_schedule(auth_admin, company, location, position, worker_user, second_worker):
    policy = auth_admin.get('/api/premium/scheduling-policy/')
    assert policy.status_code == 200
    assert policy.data['auto_schedule_enabled'] is True

    start = timezone.now() + timedelta(days=2)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=start,
        ends_at=start + timedelta(hours=6),
        status=Shift.Status.PUBLISHED,
        required_count=1,
    )
    assert shift.slots.filter(status=ShiftSlot.Status.OPEN).count() == 1

    response = auth_admin.post('/api/premium/auto-schedule/', {
        'start': (start - timedelta(hours=1)).isoformat(),
        'end': (start + timedelta(days=1)).isoformat(),
        'apply': True,
    }, format='json')
    assert response.status_code == 200
    assert response.data['assigned'] == 1
    slot = shift.slots.get()
    slot.refresh_from_db()
    shift.refresh_from_db()
    assert slot.status == ShiftSlot.Status.CLAIMED
    assert slot.worker_id in {worker_user.worker_profile.id, second_worker.id}
    assert shift.status == Shift.Status.CONFIRMED


@pytest.mark.django_db
def test_pickup_approval_mode(auth_admin, auth_worker, company, location, position, worker_user):
    SchedulingPolicy.objects.create(name='Approval', pickup_approval_required=True)
    start = timezone.now() + timedelta(days=3)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=start,
        ends_at=start + timedelta(hours=5),
        status=Shift.Status.PUBLISHED,
    )

    response = auth_worker.post(f'/api/shifts/{shift.id}/claim/', {}, format='json')
    assert response.status_code == 202
    assert response.data['pending_approval'] is True
    request_id = response.data['request_id']
    assert not shift.slots.filter(worker=worker_user.worker_profile, status=ShiftSlot.Status.CLAIMED).exists()

    pending = auth_admin.get('/api/premium/pickup-requests/')
    assert pending.status_code == 200
    assert any(row['id'] == request_id for row in pending.data)

    decision = auth_admin.post(f'/api/premium/pickup-requests/{request_id}/decide/', {'status': 'approved'}, format='json')
    assert decision.status_code == 200
    assert decision.data['status'] == 'approved'
    assert shift.slots.filter(worker=worker_user.worker_profile, status=ShiftSlot.Status.CLAIMED).exists()


@pytest.mark.django_db
def test_shift_task_list_flow(auth_admin, auth_worker, shift, location, worker_user):
    created = auth_admin.post('/api/premium/task-lists/', {
        'name': 'Schichtabschluss',
        'kind': 'shift',
        'location_id': str(location.id),
        'items': [
            {'title': 'Arbeitsplatz prüfen', 'required': True},
            {'title': 'Material melden', 'required': True},
        ],
    }, format='json')
    assert created.status_code == 201

    assigned = auth_admin.post(f"/api/premium/task-lists/{created.data['id']}/assign/", {
        'shift_id': str(shift.id),
        'worker_id': str(worker_user.worker_profile.id),
    }, format='json')
    assert assigned.status_code == 201

    runs = auth_worker.get('/api/premium/task-runs/')
    assert runs.status_code == 200
    run = next(row for row in runs.data if row['id'] == assigned.data['id'])
    assert len(run['items']) == 2

    for item in run['items']:
        completed = auth_worker.post(f"/api/premium/task-runs/{run['id']}/complete/", {'item_id': item['id']}, format='json')
        assert completed.status_code == 200
    assert completed.data['run_closed'] is True


@pytest.mark.django_db
def test_staff_callout_reopens_legacy_capacity(auth_worker, shift, worker_user):
    assert shift.worker_id == worker_user.worker_profile.id
    assert shift.slots.filter(status=ShiftSlot.Status.OPEN).exists()
    response = auth_worker.post('/api/premium/callouts/', {
        'shift_id': str(shift.id),
        'reason': 'Krank',
    }, format='json')
    assert response.status_code == 201
    assert response.data['status'] == 'open'
    shift.refresh_from_db()
    assert shift.worker_id is None
    assert shift.status == Shift.Status.PUBLISHED
    assert shift.slots.filter(worker__isnull=True, status=ShiftSlot.Status.OPEN).exists()


@pytest.mark.django_db
def test_schedule_template_membership_timezone_and_forecast(auth_admin, company, location, position, worker_user):
    membership = auth_admin.post('/api/premium/worker-locations/', {
        'worker_id': str(worker_user.worker_profile.id),
        'location_id': str(location.id),
        'home': True,
    }, format='json')
    assert membership.status_code == 201

    template = auth_admin.post('/api/premium/schedule-templates/', {
        'name': 'Messewoche',
        'location_id': str(location.id),
        'items': [{
            'weekday': 0,
            'start_time': '09:00:00',
            'end_time': '17:00:00',
            'position_id': str(position.id),
            'required_count': 2,
        }],
    }, format='json')
    assert template.status_code == 201
    applied = auth_admin.post(f"/api/premium/schedule-templates/{template.data['id']}/apply/", {
        'week_start': (timezone.localdate() + timedelta(days=7)).isoformat(),
        'client_id': str(company.id),
    }, format='json')
    assert applied.status_code == 201
    assert applied.data['created'] == 1

    forecast = auth_admin.post('/api/premium/forecasts/', {
        'location_id': str(location.id),
        'date': (timezone.localdate() + timedelta(days=7)).isoformat(),
        'metric_name': 'Besucher',
        'unit': 'Personen',
        'projected_units': '1200',
        'projected_sales': '5000',
        'labor_budget_percent': '20',
    }, format='json')
    assert forecast.status_code == 201
    rows = auth_admin.get(f"/api/premium/forecasts/?start={timezone.localdate().isoformat()}&end={(timezone.localdate()+timedelta(days=30)).isoformat()}&location_id={location.id}")
    assert rows.status_code == 200
    assert rows.data[0]['location'] == location.name

    tz = auth_admin.get('/api/premium/schedule-timezone/?timezone=Europe/Berlin')
    assert tz.status_code == 200
    assert tz.data['timezone'] == 'Europe/Berlin'


@pytest.mark.django_db
def test_custom_reports_tags_and_time_off_categories(auth_admin, company, location, position):
    tag = auth_admin.post('/api/premium/tags/', {'name': 'VIP', 'color': '#111111'}, format='json')
    assert tag.status_code == 201
    shift_start = timezone.now() + timedelta(days=5)
    shift = Shift.objects.create(client=company, location=location, position=position, starts_at=shift_start, ends_at=shift_start + timedelta(hours=4), status=Shift.Status.DRAFT)
    tagged = auth_admin.post(f'/api/premium/shifts/{shift.id}/tags/', {'tag_ids': [tag.data['id']]}, format='json')
    assert tagged.status_code == 200

    category = auth_admin.post('/api/premium/time-off-categories/', {'name': 'Sonderurlaub', 'code': 'special', 'paid': True}, format='json')
    assert category.status_code == 201
    categories = auth_admin.get('/api/premium/time-off-categories/')
    assert any(row['code'] == 'special' for row in categories.data)

    report = auth_admin.post('/api/premium/reports/', {
        'name': 'Schichten nach Status', 'kind': 'shifts',
        'columns': ['shift_id', 'location', 'status'],
        'filters': {'status': 'draft'},
        'sorting': [{'field': 'location', 'direction': 'asc'}],
        'shared': True,
    }, format='json')
    assert report.status_code == 201
    result = auth_admin.post(f"/api/premium/reports/{report.data['id']}/run/", {
        'start': (timezone.now() - timedelta(days=1)).isoformat(),
        'end': (timezone.now() + timedelta(days=30)).isoformat(),
    }, format='json')
    assert result.status_code == 200
    assert result.data['rows'][0]['status'] == 'draft'


@pytest.mark.django_db
def test_public_api_key_is_hashed_and_scoped(auth_admin, worker_user):
    issued = auth_admin.post('/api/premium/api-keys/', {
        'name': 'HR read only',
        'scopes': ['users:read'],
    }, format='json')
    assert issued.status_code == 201
    raw = issued.data['key']
    assert raw.startswith('aplus_')

    client = APIClient()
    response = client.get('/api/public/v1/users/', HTTP_X_API_KEY=raw)
    assert response.status_code == 200
    assert any(row['email'] == worker_user.email for row in response.data['results'])

    denied = client.post('/api/public/v1/shifts/', {}, format='json', HTTP_X_API_KEY=raw)
    assert denied.status_code in {401, 403}


@pytest.mark.django_db
def test_webhook_and_integration_configuration_without_external_network(auth_admin, worker_user, shift):
    webhook = auth_admin.post('/api/premium/webhooks/', {
        'name': 'ERP',
        'endpoint_url': 'https://example.invalid/webhook',
        'events': ['shifts.*'],
    }, format='json')
    assert webhook.status_code == 201
    hooks = auth_admin.get('/api/premium/webhooks/')
    assert any(row['id'] == webhook.data['id'] for row in hooks.data)

    TimeEntry.objects.create(
        worker=worker_user.worker_profile, shift=shift,
        clock_in=timezone.now() - timedelta(hours=3), clock_out=timezone.now(), approved=True,
    )
    integration = auth_admin.post('/api/premium/integrations/', {
        'name': 'Payroll export', 'kind': 'payroll', 'provider': 'generic-payroll',
    }, format='json')
    assert integration.status_code == 201
    exported = auth_admin.post(f"/api/premium/integrations/{integration.data['id']}/sync/", {
        'start': (timezone.now() - timedelta(days=1)).isoformat(),
        'end': (timezone.now() + timedelta(days=1)).isoformat(),
    }, format='json')
    assert exported.status_code == 200
    assert exported.data['mode'] == 'export'
    assert len(exported.data['payload']['records']) == 1


@pytest.mark.django_db
def test_saml_status_is_safe_when_unconfigured(api_client):
    response = api_client.get('/api/auth/saml/status/')
    assert response.status_code == 200
    assert response.data['enabled'] is False
