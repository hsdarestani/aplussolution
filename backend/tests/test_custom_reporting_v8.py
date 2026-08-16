from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import AuditLog, ClientCompany, Location, Shift, TimeEntry
from core.reporting_models import ReportDefinition, ReportRun, ReportSchedule
from core.reporting_tasks import deliver_due_reports
from core.workplace_models import AccessRole, UserAccessAssignment


def _report_role(manager, permissions, location=None, workers=None, wage='none'):
    role = AccessRole.objects.create(
        code=f'report-role-{manager.id}', name='Report Rolle', permissions=permissions, wage_visibility=wage,
    )
    assignment = UserAccessAssignment.objects.create(user=manager, access_role=role, scope_mode='scoped')
    if location:
        assignment.locations.add(location)
    if workers:
        assignment.workers.add(*workers)
    return assignment


@pytest.mark.django_db
def test_catalog_redacts_wage_fields_without_wage_permission(api_client, manager_user, location, worker_user):
    _report_role(manager_user, ['manager.access', 'reports.view'], location, [worker_user.worker_profile])
    api_client.force_authenticate(manager_user)
    response = api_client.get('/api/reports/builder/catalog/')
    assert response.status_code == 200
    assert response.data['can_manage'] is False
    labor = next(item for item in response.data['sources'] if item['key'] == 'labor')
    keys = {field['key'] for field in labor['fields']}
    assert 'scheduled_minutes' in keys
    assert 'scheduled_cost' not in keys
    assert 'actual_cost' not in keys


@pytest.mark.django_db
def test_preview_is_scope_aware_and_cannot_request_wage_columns(api_client, manager_user, worker_user, second_worker, company, location, position):
    _report_role(manager_user, ['manager.access', 'reports.view'], location, [worker_user.worker_profile])
    now = timezone.now()
    Shift.objects.create(client=company, location=location, position=position, worker=worker_user.worker_profile, starts_at=now, ends_at=now + timedelta(hours=4), status=Shift.Status.CONFIRMED)
    other_company = ClientCompany.objects.create(name='Andere GmbH', customer_number='KD-999')
    other_location = Location.objects.create(client=other_company, name='Andere Stadt', address='Andere 1')
    Shift.objects.create(client=other_company, location=other_location, position=position, worker=second_worker, starts_at=now, ends_at=now + timedelta(hours=4), status=Shift.Status.CONFIRMED)
    api_client.force_authenticate(manager_user)
    local_day = timezone.localtime(now).date().isoformat()
    payload = {
        'data_source': 'shifts',
        'columns': ['employee_number', 'employee_name', 'location'],
        'filters': {'date_from': local_day, 'date_to': local_day},
    }
    response = api_client.post('/api/reports/builder/preview/', payload, format='json')
    assert response.status_code == 200
    assert {row['employee_number'] for row in response.data['rows']} == {'MA-001'}
    denied = api_client.post('/api/reports/builder/preview/', {**payload, 'columns': ['employee_name', 'hourly_rate']}, format='json')
    assert denied.status_code == 403


@pytest.mark.django_db
def test_saved_report_exports_csv_and_xlsx_and_audits_run(auth_admin, shift):
    day = timezone.localtime(shift.starts_at).date().isoformat()
    created = auth_admin.post('/api/reports/builder/definitions/', {
        'name': 'Dienstplan Test', 'data_source': 'shifts',
        'columns': ['date', 'employee_name', 'location', 'scheduled_minutes'],
        'filters': {'date_from': day, 'date_to': day},
        'sort': [{'field': 'employee_name', 'direction': 'asc'}],
    }, format='json')
    assert created.status_code == 201
    report_id = created.data['id']

    csv_response = auth_admin.post(f'/api/reports/builder/definitions/{report_id}/run/', {'file_format': 'csv'}, format='json')
    assert csv_response.status_code == 200
    assert csv_response['Content-Type'].startswith('text/csv')
    assert b'Dienstplan' not in csv_response.content
    assert 'Anna Becker' in csv_response.content.decode('utf-8-sig')
    assert csv_response['X-APlus-Report-Rows'] == '1'

    xlsx_response = auth_admin.post(f'/api/reports/builder/definitions/{report_id}/run/', {'file_format': 'xlsx'}, format='json')
    assert xlsx_response.status_code == 200
    assert xlsx_response.content[:2] == b'PK'
    assert ReportRun.objects.filter(report_id=report_id, status=ReportRun.Status.SUCCESS).count() == 2
    assert AuditLog.objects.filter(action='report.executed', object_id=report_id).count() == 2


@pytest.mark.django_db
def test_labor_report_compares_scheduled_actual_and_cost(auth_admin, worker_user, shift):
    shift.starts_at = timezone.now() - timedelta(hours=6)
    shift.ends_at = timezone.now() - timedelta(hours=2)
    shift.save(update_fields=['starts_at', 'ends_at', 'updated_at'])
    TimeEntry.objects.create(
        worker=worker_user.worker_profile, shift=shift,
        clock_in=shift.starts_at + timedelta(minutes=15), clock_out=shift.ends_at + timedelta(minutes=30), approved=True,
    )
    day = timezone.localtime(shift.starts_at).date().isoformat()
    response = auth_admin.post('/api/reports/builder/preview/', {
        'data_source': 'labor',
        'columns': ['employee_name', 'scheduled_minutes', 'actual_minutes', 'variance_minutes', 'scheduled_cost', 'actual_cost'],
        'filters': {'date_from': day, 'date_to': day},
    }, format='json')
    assert response.status_code == 200
    row = response.data['rows'][0]
    assert row['employee_name'] == 'Anna Becker'
    assert row['scheduled_minutes'] == 240
    assert row['actual_minutes'] == 255
    assert row['variance_minutes'] == 15
    assert row['actual_cost'] != row['scheduled_cost']


@pytest.mark.django_db
def test_grouped_aggregation_is_whitelisted(auth_admin, shift):
    day = timezone.localtime(shift.starts_at).date().isoformat()
    response = auth_admin.post('/api/reports/builder/preview/', {
        'data_source': 'shifts',
        'columns': ['location'],
        'filters': {'date_from': day, 'date_to': day},
        'group_by': ['location'],
        'aggregates': [{'field': 'scheduled_minutes', 'op': 'sum', 'alias': 'minutes', 'label': 'Plan-Minuten'}],
    }, format='json')
    assert response.status_code == 200
    assert response.data['columns'][1]['key'] == 'minutes'
    assert response.data['rows'][0]['minutes'] > 0


@pytest.mark.django_db
def test_report_schedule_requires_manage_and_delivers_attachment(api_client, manager_user, auth_admin, admin_user, shift):
    day = timezone.localtime(shift.starts_at).date().isoformat()
    report = ReportDefinition.objects.create(
        name='Tagesreport', data_source='shifts', columns=['date', 'employee_name'],
        filters={'date_from': day, 'date_to': day}, created_by=admin_user,
    )
    _report_role(manager_user, ['manager.access', 'reports.view'], shift.location, [shift.worker])
    api_client.force_authenticate(manager_user)
    denied = api_client.post('/api/reports/builder/schedules/', {
        'report': str(report.id), 'frequency': 'daily', 'recipients': ['ops@example.com'],
    }, format='json')
    assert denied.status_code == 403

    created = auth_admin.post('/api/reports/builder/schedules/', {
        'report': str(report.id), 'frequency': 'daily', 'file_format': 'xlsx',
        'recipients': ['ops@example.com'], 'local_hour': 8,
    }, format='json')
    assert created.status_code == 201
    schedule = ReportSchedule.objects.get(pk=created.data['id'])
    schedule.next_run_at = timezone.now() - timedelta(minutes=1)
    schedule.save(update_fields=['next_run_at', 'updated_at'])
    result = deliver_due_reports()
    assert result['delivered'] == 1
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ['ops@example.com']
    assert mail.outbox[0].attachments[0][0].endswith('.xlsx')
    schedule.refresh_from_db()
    assert schedule.last_run_at is not None
    assert schedule.next_run_at > timezone.now()
    assert ReportRun.objects.filter(schedule=schedule, trigger='scheduled', status='success').exists()


@pytest.mark.django_db
def test_shift_history_uses_audit_log_with_scope(auth_admin, admin_user, shift):
    AuditLog.objects.create(actor=admin_user, action='shift.updated', object_type='Shift', object_id=str(shift.id), metadata={'status': 'confirmed'})
    day = timezone.localdate().isoformat()
    response = auth_admin.post('/api/reports/builder/preview/', {
        'data_source': 'shift_history', 'columns': ['action', 'actor', 'shift_id', 'metadata'],
        'filters': {'date_from': day, 'date_to': day},
    }, format='json')
    assert response.status_code == 200
    assert any(row['action'] == 'shift.updated' and row['shift_id'] == str(shift.id) for row in response.data['rows'])
