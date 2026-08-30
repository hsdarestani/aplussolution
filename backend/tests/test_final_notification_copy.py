from django.utils import timezone
import pytest

from core.models import Notification
from core.push_signals import native_push_suppressed
from core.shift_slots import ShiftSlot


@pytest.mark.django_db
def test_admin_assignment_is_implicitly_confirmed(shift, second_worker):
    shift.confirmation_required = True
    shift.save(update_fields=['confirmation_required', 'updated_at'])

    slot = ShiftSlot.objects.create(
        shift=shift,
        worker=second_worker,
        status=ShiftSlot.Status.CLAIMED,
        source='admin_assignment',
        confirmation_status=ShiftSlot.ConfirmationStatus.PENDING,
        confirmation_requested_at=timezone.now(),
    )
    slot.refresh_from_db()

    assert slot.confirmation_status == ShiftSlot.ConfirmationStatus.CONFIRMED
    assert slot.confirmation_requested_at is None
    assert slot.confirmation_decided_at is not None


@pytest.mark.django_db
def test_open_shift_copy_uses_approved_compact_format(shift, worker_user):
    notification = Notification.objects.create(
        user=worker_user,
        kind=f'open-shift-publish-abcdef123456-{shift.id}',
        title='old title',
        body='old body',
        action_url='/schedule',
    )
    notification.refresh_from_db()

    start = timezone.localtime(shift.starts_at)
    end = timezone.localtime(shift.ends_at)
    assert notification.title == 'Neue Schicht verfügbar'
    assert notification.body == (
        f'{start:%d.%m.%Y} · {start:%H:%M}–{end:%H:%M} Uhr\n'
        f'{shift.location.name} - {shift.position.name}'
    )


@pytest.mark.django_db
def test_direct_assignment_copy_does_not_ask_for_confirmation(shift, second_worker):
    slot = ShiftSlot.objects.create(
        shift=shift,
        worker=second_worker,
        status=ShiftSlot.Status.CLAIMED,
        source='admin_assignment',
    )
    notification = Notification.objects.create(
        user=second_worker.user,
        kind=f'shift-admin-assigned-{slot.id}',
        title='Schicht bestätigen',
        body='legacy',
        action_url='/schedule',
    )
    notification.refresh_from_db()

    assert notification.title == 'Lukas Schmidt übernimmt folgende Schicht:'
    assert 'Bitte Schicht bestätigen' not in notification.title
    assert shift.location.name in notification.body
    assert shift.position.name in notification.body


@pytest.mark.django_db
def test_manual_and_24h_reminder_copy(shift, worker_user):
    manual = Notification.objects.create(
        user=worker_user,
        kind=f'shift-event-manual-reminder-{shift.id}-abcdef1234',
        title='legacy',
        body='legacy',
    )
    slot = shift.slots.exclude(status=ShiftSlot.Status.CANCELLED).first()
    day_before = Notification.objects.create(
        user=worker_user,
        kind=f'shift-24h-{slot.id}',
        title='legacy',
        body='legacy',
    )
    manual.refresh_from_db()
    day_before.refresh_from_db()

    start = timezone.localtime(shift.starts_at)
    assert manual.title == 'Erinnerung an deine Schicht'
    assert f'{start:%d.%m.%Y} von ' in manual.body
    assert day_before.title == 'Erinnerung:'
    assert day_before.body == f'Dein Einsatz beginnt morgen um {start:%H:%M} Uhr'


@pytest.mark.django_db
def test_rejected_pickup_and_confirmation_status_are_native_push_suppressed(worker_user):
    pickup = Notification(
        user=worker_user,
        kind='pickup-2e85398b-63ae-4ff2-9a13-cf9394e404af-rejected',
        title='Schichtübernahme abgelehnt',
        body='',
    )
    confirmation = Notification(
        user=worker_user,
        kind='shift-confirmation-admin-2e85398b-63ae-4ff2-9a13-cf9394e404af-confirmed-123',
        title='Schichtbestätigung aktualisiert',
        body='',
    )
    release_rejection = Notification(
        user=worker_user,
        kind='shift-release-2e85398b-63ae-4ff2-9a13-cf9394e404af-rejected',
        title='Schichtfreigabe abgelehnt',
        body='',
    )

    assert native_push_suppressed(pickup) is True
    assert native_push_suppressed(confirmation) is True
    assert native_push_suppressed(release_rejection) is False


@pytest.mark.django_db
def test_attendance_reminders_use_final_short_copy(worker_user):
    checkin = Notification.objects.create(
        user=worker_user,
        kind='attendance-checkin-reminder-2e85398b-63ae-4ff2-9a13-cf9394e404af',
        title='legacy',
        body='legacy',
    )
    checkout = Notification.objects.create(
        user=worker_user,
        kind='attendance-checkout-reminder-2e85398b-63ae-4ff2-9a13-cf9394e404af',
        title='legacy',
        body='legacy',
    )
    checkin.refresh_from_db()
    checkout.refresh_from_db()

    assert checkin.title == 'Check-in nicht vergessen'
    assert checkin.body == 'Deine Schicht hat vor 15 Minuten begonnen'
    assert checkout.title == 'Check-out nicht vergessen'
    assert checkout.body == 'Deine Schicht hat vor 15 Minuten geendet'
