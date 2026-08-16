from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Notification, Shift, TimeEntry, TimeOffRequest
from core.scheduler_completion_models import (
    ScheduleAnnotation,
    ScheduleTask,
    ScheduleTaskList,
    SchedulerColorOverride,
    SchedulerCompletionSettings,
    ShiftConfirmation,
)
from core.scheduler_completion_service import sync_shift_confirmations
from core.shift_slots import ShiftSlot


def _claim_slot(shift, worker, source='manager_assign'):
    slot = shift.slots.exclude(status=ShiftSlot.Status.CANCELLED).order_by('created_at').first()
    assert slot is not None
    slot.worker = worker
    slot.status = ShiftSlot.Status.CLAIMED
    slot.source = source
    slot.claimed_at = timezone.now()
    slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'updated_at'])
    return slot


def _future_shift(company, location, position, *, hours_from_now=48, hours=4, status=Shift.Status.PUBLISHED):
    start = timezone.now() + timedelta(hours=hours_from_now)
    return Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=start,
        ends_at=start + timedelta(hours=hours),
        status=status,
        is_open=status == Shift.Status.PUBLISHED,
        published_at=timezone.now() if status == Shift.Status.PUBLISHED else None,
    )


@pytest.mark.django_db
def test_scheduler_completion_settings_follow_schedule_edit_capability(api_client, auth_admin, manager_user):
    api_client.force_authenticate(manager_user)
    read = api_client.get('/api/scheduling/completion-settings/')
    assert read.status_code == 200
    assert read.data['can_manage'] is True
    manager_changed = api_client.patch('/api/scheduling/completion-settings/', {'allow_overlapping_open_shifts': True}, format='json')
    assert manager_changed.status_code == 200
    assert manager_changed.data['allow_overlapping_open_shifts'] is True

    changed = auth_admin.patch('/api/scheduling/completion-settings/', {
        'allow_overlapping_open_shifts': False,
        'require_shift_confirmation': False,
    }, format='json')
    assert changed.status_code == 200
    assert changed.data['allow_overlapping_open_shifts'] is False
    assert changed.data['require_shift_confirmation'] is False


@pytest.mark.django_db
def test_published_assignment_requires_confirmation_resets_on_republish_and_clears_on_release(auth_admin, auth_worker, worker_user, shift):
    slot = _claim_slot(shift, worker_user.worker_profile)
    confirmation = ShiftConfirmation.objects.get(slot=slot)
    assert confirmation.confirmed_at is None

    pending = auth_worker.get('/api/scheduling/confirmations/')
    assert pending.status_code == 200
    assert pending.data['pending_count'] == 1

    confirmed = auth_worker.post(f'/api/scheduling/confirmations/{slot.id}/confirm/', {}, format='json')
    assert confirmed.status_code == 200
    confirmation.refresh_from_db()
    assert confirmation.confirmed_at is not None

    sync_shift_confirmations(shift)
    confirmation.refresh_from_db()
    assert confirmation.confirmed_at is not None, 'legacy confirmed shifts must not reset on every sync'

    republished = auth_admin.post(f'/api/shifts/{shift.id}/publish/', {}, format='json')
    assert republished.status_code == 200
    confirmation.refresh_from_db()
    assert confirmation.confirmed_at is None

    released = auth_worker.post(f'/api/shifts/{shift.id}/release/', {}, format='json')
    assert released.status_code == 200
    assert not ShiftConfirmation.objects.filter(slot=slot).exists()


@pytest.mark.django_db
def test_block_time_off_annotation_is_enforced_only_for_affected_worker(auth_worker, api_client, worker_user, second_worker, shift, location):
    day = timezone.localtime(shift.starts_at).date()
    ScheduleAnnotation.objects.create(
        kind=ScheduleAnnotation.Kind.BLOCK_TIME_OFF,
        title='Inventur',
        starts_on=day,
        ends_on=day,
        location=location,
        active=True,
    )
    blocked = auth_worker.post('/api/time-off/', {
        'starts_on': day.isoformat(),
        'ends_on': day.isoformat(),
        'reason': 'Privat',
    }, format='json')
    assert blocked.status_code == 400
    assert 'gesperrt' in str(blocked.data)
    assert not TimeOffRequest.objects.filter(worker=worker_user.worker_profile).exists()

    api_client.force_authenticate(second_worker.user)
    allowed = api_client.post('/api/time-off/', {
        'starts_on': day.isoformat(),
        'ends_on': day.isoformat(),
        'reason': 'Privat',
    }, format='json')
    assert allowed.status_code == 201
    assert TimeOffRequest.objects.filter(worker=second_worker).exists()


@pytest.mark.django_db
def test_business_closed_can_release_future_assignments(auth_admin, worker_user, company, location, position):
    shift = _future_shift(company, location, position)
    slot = _claim_slot(shift, worker_user.worker_profile)
    assert ShiftConfirmation.objects.filter(slot=slot).exists()
    day = timezone.localtime(shift.starts_at).date()

    response = auth_admin.post('/api/schedule-annotations/', {
        'kind': 'business_closed',
        'title': 'Standort geschlossen',
        'message': 'Kein Einsatz',
        'starts_on': day.isoformat(),
        'ends_on': day.isoformat(),
        'location': str(location.id),
        'business_closed_action': 'open',
    }, format='json')
    assert response.status_code == 201
    assert response.data['business_closed_result']['changed'] == 1
    slot.refresh_from_db()
    shift.refresh_from_db()
    assert slot.worker_id is None
    assert slot.status == ShiftSlot.Status.OPEN
    assert shift.status == Shift.Status.PUBLISHED
    assert shift.is_open is True
    assert not ShiftConfirmation.objects.filter(slot=slot).exists()
    assert Notification.objects.filter(user=worker_user, title__icontains='Betriebsschließung').exists()


@pytest.mark.django_db
def test_business_closed_delete_skips_shift_with_time_entry(auth_admin, worker_user, company, location, position):
    shift = _future_shift(company, location, position)
    _claim_slot(shift, worker_user.worker_profile)
    TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        shift=shift,
        clock_in=shift.starts_at,
        clock_out=shift.starts_at + timedelta(hours=1),
    )
    day = timezone.localtime(shift.starts_at).date()
    response = auth_admin.post('/api/schedule-annotations/', {
        'kind': 'business_closed',
        'title': 'Standort geschlossen',
        'starts_on': day.isoformat(),
        'ends_on': day.isoformat(),
        'location': str(location.id),
        'business_closed_action': 'delete',
    }, format='json')
    assert response.status_code == 201
    assert response.data['business_closed_result']['changed'] == 0
    assert response.data['business_closed_result']['skipped'][0]['reason'] == 'Zeiterfassung vorhanden'
    assert Shift.objects.filter(pk=shift.pk).exists()


@pytest.mark.django_db
def test_overlapping_open_shift_toggle_only_relaxes_worker_self_claim(auth_admin, auth_worker, worker_user, company, location, position):
    base = _future_shift(company, location, position, hours_from_now=50)
    _claim_slot(base, worker_user.worker_profile)
    target = _future_shift(company, location, position, hours_from_now=51)

    blocked = auth_worker.post(f'/api/shifts/{target.id}/claim/', {}, format='json')
    assert blocked.status_code == 400
    assert 'bereits eine Schicht' in str(blocked.data)

    settings = SchedulerCompletionSettings.load()
    settings.allow_overlapping_open_shifts = True
    settings.save(update_fields=['allow_overlapping_open_shifts', 'updated_at'])
    claimed = auth_worker.post(f'/api/shifts/{target.id}/claim/', {}, format='json')
    assert claimed.status_code == 200
    assert ShiftSlot.objects.filter(shift=target, worker=worker_user.worker_profile, status='claimed').exists()

    strict_target = _future_shift(company, location, position, hours_from_now=51)
    strict = auth_admin.post('/api/scheduling/assign/', {
        'shift': str(strict_target.id),
        'worker': str(worker_user.worker_profile.id),
    }, format='json')
    assert strict.status_code == 400
    assert 'bereits eine Schicht' in str(strict.data)


@pytest.mark.django_db
def test_worker_task_list_hides_other_assignments_and_allows_relevant_position_tasks(auth_worker, worker_user, second_worker, company, location, position):
    shift = _future_shift(company, location, position, hours_from_now=72)
    _claim_slot(shift, worker_user.worker_profile)
    work_date = shift.starts_at.date()
    task_list = ScheduleTaskList.objects.create(title='Opening', work_date=work_date, location=location)
    own = ScheduleTask.objects.create(task_list=task_list, title='Eigene Aufgabe', assignee=worker_user.worker_profile)
    other = ScheduleTask.objects.create(task_list=task_list, title='Fremde Aufgabe', assignee=second_worker)
    ScheduleTask.objects.create(task_list=task_list, title='Allgemein')
    ScheduleTask.objects.create(task_list=task_list, title='Positionsaufgabe', position=position)

    snapshot = auth_worker.get('/api/scheduling/completion-snapshot/')
    assert snapshot.status_code == 200
    row = next(item for item in snapshot.data['task_lists'] if item['id'] == str(task_list.id))
    titles = {item['title'] for item in row['tasks']}
    assert titles == {'Eigene Aufgabe', 'Allgemein', 'Positionsaufgabe'}
    assert row['task_count'] == 3

    hidden = auth_worker.post(f'/api/schedule-tasks/{other.id}/complete/', {'completed': True}, format='json')
    assert hidden.status_code == 404
    completed = auth_worker.post(f'/api/schedule-tasks/{own.id}/complete/', {'completed': True}, format='json')
    assert completed.status_code == 200
    own.refresh_from_db()
    assert own.completed_at is not None


@pytest.mark.django_db
def test_shift_position_location_colors_and_timezone_preferences(auth_admin, worker_user, shift, position, location):
    position.color = '#445566'
    position.save(update_fields=['color'])
    shift_color = auth_admin.post('/api/scheduler-colors/', {
        'target_type': 'shift', 'target_id': str(shift.id), 'color': '#112233',
    }, format='json')
    assert shift_color.status_code == 201
    location_color = auth_admin.post('/api/scheduler-colors/', {
        'target_type': 'location', 'target_id': str(location.id), 'color': '#778899',
    }, format='json')
    assert location_color.status_code == 201

    detail = auth_admin.get(f'/api/shifts/{shift.id}/')
    assert detail.status_code == 200
    assert detail.data['shift_color'] == '#112233'
    assert detail.data['position_color'] == '#445566'
    assert detail.data['location_color'] == '#778899'
    assert detail.data['location_timezone'] == location.timezone

    invalid = auth_admin.patch('/api/scheduling/display-preferences/', {'local_timezone': 'Mars/Olympus'}, format='json')
    assert invalid.status_code == 400
    valid = auth_admin.patch('/api/scheduling/display-preferences/', {
        'color_mode': 'location', 'timezone_mode': 'local', 'local_timezone': 'America/New_York',
    }, format='json')
    assert valid.status_code == 200
    assert valid.data['color_mode'] == 'location'
    assert valid.data['timezone_mode'] == 'local'
    assert valid.data['local_timezone'] == 'America/New_York'


@pytest.mark.django_db
def test_confirmation_setting_off_removes_existing_pending_confirmations(auth_admin, worker_user, shift):
    slot = _claim_slot(shift, worker_user.worker_profile)
    assert ShiftConfirmation.objects.filter(slot=slot).exists()
    response = auth_admin.patch('/api/scheduling/completion-settings/', {'require_shift_confirmation': False}, format='json')
    assert response.status_code == 200
    assert not ShiftConfirmation.objects.exists()


@pytest.mark.django_db
def test_color_endpoint_rejects_invalid_hex(auth_admin, shift):
    response = auth_admin.post('/api/scheduler-colors/', {
        'target_type': SchedulerColorOverride.Target.SHIFT,
        'target_id': str(shift.id),
        'color': 'red',
    }, format='json')
    assert response.status_code == 400
