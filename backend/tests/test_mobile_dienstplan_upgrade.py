from datetime import datetime, time, timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.models import ClientCompany, Location, Notification, Shift, User, WorkerProfile
from core.notification_settings import render_push_notification


def aware_on(day, hour=9):
    return timezone.make_aware(datetime.combine(day, time(hour=hour)), timezone.get_current_timezone())


@pytest.mark.django_db
def test_mobile_schedule_is_bounded_but_keeps_future_open_shifts(auth_admin, company, location, position):
    today = timezone.localdate()
    in_week = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=aware_on(today + timedelta(days=1)),
        ends_at=aware_on(today + timedelta(days=1), 15),
        status=Shift.Status.DRAFT,
    )
    old = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=aware_on(today - timedelta(days=60)),
        ends_at=aware_on(today - timedelta(days=60), 15),
        status=Shift.Status.DRAFT,
    )
    future_open = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=aware_on(today + timedelta(days=40)),
        ends_at=aware_on(today + timedelta(days=40), 15),
        status=Shift.Status.PUBLISHED,
        required_count=1,
    )

    response = auth_admin.get(
        f'/api/admin/mobile-schedule/?date_from={today.isoformat()}&date_to={(today + timedelta(days=6)).isoformat()}'
    )
    assert response.status_code == 200
    ids = {row['id'] for row in response.json()['shifts']}
    assert str(in_week.id) in ids
    assert str(future_open.id) in ids
    assert str(old.id) not in ids


@pytest.mark.django_db
def test_unassigned_draft_shift_is_invisible_to_worker(auth_worker, company, location, position):
    today = timezone.localdate() + timedelta(days=3)
    draft = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=aware_on(today),
        ends_at=aware_on(today, 15),
        status=Shift.Status.DRAFT,
        required_count=1,
    )

    response = auth_worker.get('/api/shifts/')
    assert response.status_code == 200
    payload = response.json()
    rows = payload.get('results', payload) if isinstance(payload, dict) else payload
    assert str(draft.id) not in {row['id'] for row in rows}


@pytest.mark.django_db
def test_schedule_pdf_filters_and_returns_real_pdf(auth_admin, shift):
    shift.schedule_groups = ['service']
    shift.save(update_fields=['schedule_groups', 'updated_at'])
    day = timezone.localtime(shift.starts_at).date()
    response = auth_admin.get(
        '/api/reports/schedule.pdf',
        {
            'date_from': day.isoformat(),
            'date_to': day.isoformat(),
            'workers': str(shift.worker_id),
            'clients': str(shift.client_id),
            'groups': 'service',
        },
    )
    assert response.status_code == 200
    assert response['Content-Type'] == 'application/pdf'
    assert response.content.startswith(b'%PDF')
    assert len(response.content) > 500


@pytest.mark.django_db
def test_admin_can_disable_and_edit_push_family(auth_admin, worker_user):
    response = auth_admin.get('/api/push/settings/')
    assert response.status_code == 200
    rules = {rule['key']: rule for rule in response.json()['rules']}
    assert rules['pickup_rejected']['enabled'] is False
    assert rules['attendance_auto_end']['enabled'] is False

    response = auth_admin.put(
        '/api/push/settings/',
        {
            'rules': [
                {
                    'key': 'open_shift',
                    'enabled': False,
                    'title_template': 'A+ · {title}',
                    'body_template': 'Neu: {body}',
                }
            ]
        },
        format='json',
    )
    assert response.status_code == 200
    notification = Notification(
        user=worker_user,
        kind='open-shift-created-test',
        title='Neue Schicht verfügbar',
        body='05.09.2026 · 14:00–22:30',
    )
    enabled, title, body, key = render_push_notification(notification)
    assert key == 'open_shift'
    assert enabled is False
    assert title == 'A+ · Neue Schicht verfügbar'
    assert body == 'Neu: 05.09.2026 · 14:00–22:30'


@pytest.mark.django_db
def test_local_location_name_survives_later_wiw_sync(location):
    first_sync = timezone.now() - timedelta(minutes=10)
    Location.objects.filter(pk=location.pk).update(wiw_synced_at=first_sync)
    location.refresh_from_db()

    location.name = 'Lokaler Einsatzort'
    location.save(update_fields=['name', 'updated_at'])

    location.refresh_from_db()
    location.name = 'WIW Location 123'
    location.wiw_synced_at = timezone.now()
    location.wiw_payload = {'name': 'WIW Location 123'}
    location.save()
    location.refresh_from_db()
    assert location.name == 'Lokaler Einsatzort'
    assert location.wiw_payload['name'] == 'WIW Location 123'


@pytest.mark.django_db
def test_configure_schedule_workers_changes_only_approved_workforce(db):
    tooba_user = User.objects.create_user(
        'tooba@example.com', 'Pass123456!', first_name='Tooba', last_name='Amjad', role=User.Role.WORKER
    )
    tooba = WorkerProfile.objects.create(
        user=tooba_user,
        employee_number='CFG-TOOBA',
        schedule_groups=['housekeeping'],
        open_shift_client_ids=['00000000-0000-0000-0000-000000000001'],
    )
    lara_user = User.objects.create_user(
        'lara@example.com', 'Pass123456!', first_name='Lara', last_name='Mohieddine', role=User.Role.WORKER
    )
    WorkerProfile.objects.create(user=lara_user, employee_number='CFG-LARA')
    julia_user = User.objects.create_user(
        'julia@example.com', 'Pass123456!', first_name='Julia', last_name='Stahl', role=User.Role.CLIENT
    )
    WorkerProfile.objects.create(user=julia_user, employee_number='CFG-JULIA')
    other_user = User.objects.create_user(
        'other@example.com', 'Pass123456!', first_name='Other', last_name='Worker', role=User.Role.WORKER
    )
    other = WorkerProfile.objects.create(
        user=other_user,
        employee_number='CFG-OTHER',
        schedule_groups=['housekeeping'],
        open_shift_client_ids=['00000000-0000-0000-0000-000000000002'],
    )

    call_command('configure_schedule_workers')

    tooba.refresh_from_db()
    other.refresh_from_db()
    assert tooba.schedule_groups == ['service']
    assert tooba.open_shift_client_ids == []
    assert other.schedule_groups == ['housekeeping']
    assert other.open_shift_client_ids == ['00000000-0000-0000-0000-000000000002']
    assert not User.objects.filter(pk=lara_user.pk).exists()
    assert User.objects.filter(pk=julia_user.pk).exists()
    assert not WorkerProfile.objects.filter(user_id=julia_user.pk).exists()
