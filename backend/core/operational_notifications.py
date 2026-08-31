from __future__ import annotations

import uuid
from datetime import timedelta

from django.conf import settings
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Notification, Shift, TimeEntry, User, WorkerProfile
from .shift_rules import shift_visible_to_worker
from .shift_slots import ShiftSlot


SYNTHETIC_MIGRATION_EMAIL_SUFFIX = '@sync.invalid'


def _event_key(prefix: str) -> str:
    return f'{prefix}-{uuid.uuid4().hex[:12]}'


def _shift_body(shift: Shift) -> str:
    local_start = timezone.localtime(shift.starts_at)
    location = getattr(shift.location, 'name', '') or 'Einsatzort'
    position = getattr(shift.position, 'name', '') or 'Schicht'
    return f'{local_start:%d.%m.%Y %H:%M} · {position} · {location}'


def _notify_admin_open_shift_summary(shift: Shift, event: str, worker_count: int) -> int:
    """Create one admin notification for an OpenShift fan-out, not one per worker."""
    if worker_count <= 0:
        return 0
    created = 0
    for admin in User.objects.filter(role=User.Role.ADMIN, is_active=True):
        _, was_created = Notification.objects.get_or_create(
            user=admin,
            kind=f'admin-open-shift-summary-{event}-{shift.id}',
            defaults={
                'title': 'OpenShift veröffentlicht',
                'body': f'Benachrichtigung für {worker_count} Mitarbeiter ausgelöst · {_shift_body(shift)}',
                'action_url': '/schedule',
            },
        )
        created += int(was_created)
    return created


def notify_open_shift_available(shift: Shift, reason: str = 'available') -> int:
    """Notify every active employee who can actually see/take this OpenShift."""
    try:
        shift = Shift.objects.select_related('client', 'location', 'position').get(pk=shift.pk)
    except Shift.DoesNotExist:
        return 0
    if shift.status != Shift.Status.PUBLISHED or shift.ends_at <= timezone.now():
        return 0
    if not ShiftSlot.objects.filter(shift=shift, status=ShiftSlot.Status.OPEN, worker__isnull=True).exists():
        return 0

    assigned_ids = set(
        ShiftSlot.objects.filter(shift=shift, status=ShiftSlot.Status.CLAIMED, worker__isnull=False)
        .values_list('worker_id', flat=True)
    )
    event = _event_key(reason)
    created = 0
    workers = (
        WorkerProfile.objects.filter(active=True, user__is_active=True)
        .exclude(user__email__iendswith=SYNTHETIC_MIGRATION_EMAIL_SUFFIX)
        .select_related('user')
    )
    for worker in workers:
        if worker.id in assigned_ids:
            continue
        try:
            if not shift_visible_to_worker(shift, worker):
                continue
        except Exception:
            continue
        Notification.objects.create(
            user=worker.user,
            kind=f'open-shift-{event}-{shift.id}',
            title='Neue OpenShift verfügbar',
            body=_shift_body(shift),
            action_url='/schedule',
        )
        created += 1

    _notify_admin_open_shift_summary(shift, event, created)
    return created


def notify_worker_shift_event(user: User | None, shift: Shift, title: str, reason: str) -> int:
    if not user or not user.is_active:
        return 0
    Notification.objects.create(
        user=user,
        kind=f'shift-event-{reason}-{shift.id}-{uuid.uuid4().hex[:10]}',
        title=title,
        body=_shift_body(shift),
        action_url='/schedule',
    )
    return 1


def notify_claimed_workers_shift_changed(shift: Shift, title: str = 'Schicht aktualisiert', reason: str = 'updated') -> int:
    users = []
    seen = set()
    for slot in (
        ShiftSlot.objects.filter(shift=shift, status=ShiftSlot.Status.CLAIMED, worker__isnull=False)
        .select_related('worker__user')
    ):
        user = slot.worker.user
        if user.id not in seen:
            users.append(user)
            seen.add(user.id)
    if shift.worker_id and shift.worker.user_id not in seen:
        users.append(shift.worker.user)
    return sum(notify_worker_shift_event(user, shift, title, reason) for user in users)


def notify_managers_attendance(entry: TimeEntry, event: str) -> int:
    worker_name = entry.worker.user.get_full_name() or entry.worker.user.email
    shift = entry.shift
    if event == 'check_in':
        title = 'Mitarbeiter eingecheckt'
        moment = entry.clock_in
    else:
        title = 'Mitarbeiter ausgecheckt'
        moment = entry.clock_out or timezone.now()
    when = timezone.localtime(moment).strftime('%d.%m.%Y %H:%M')
    location = shift.location.name if shift and shift.location_id else 'ohne Einsatzort'
    body = f'{worker_name} · {when} · {location}'
    count = 0
    for recipient in User.objects.filter(role__in=[User.Role.ADMIN, User.Role.MANAGER], is_active=True):
        Notification.objects.create(
            user=recipient,
            kind=f'attendance-{event}-{entry.id}',
            title=title,
            body=body,
            action_url='/time',
        )
        count += 1
    return count


def dispatch_attendance_reminders() -> dict:
    now = timezone.now()
    grace = max(5, int(getattr(settings, 'ATTENDANCE_REMINDER_MINUTES', 15)))
    threshold = now - timedelta(minutes=grace)
    checkin = checkout = 0

    slots = (
        ShiftSlot.objects.filter(
            status=ShiftSlot.Status.CLAIMED,
            worker__isnull=False,
            shift__starts_at__lte=threshold,
            shift__starts_at__gte=now - timedelta(hours=6),
            shift__ends_at__gte=now,
            shift__status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED],
        )
        .select_related('worker__user', 'shift__location', 'shift__position')
    )
    for slot in slots:
        if TimeEntry.objects.filter(worker=slot.worker, shift=slot.shift, wiw_time_id__isnull=True).exists():
            continue
        _, created = Notification.objects.get_or_create(
            user=slot.worker.user,
            kind=f'attendance-checkin-reminder-{slot.id}',
            defaults={
                'title': 'Check-in nicht vergessen',
                'body': f'Deine Schicht hat vor {grace} Minuten begonnen. Bitte jetzt einchecken.',
                'action_url': '/time',
            },
        )
        checkin += int(created)

    entries = (
        TimeEntry.objects.filter(
            wiw_time_id__isnull=True,
            clock_out__isnull=True,
            shift__isnull=False,
            shift__ends_at__lte=threshold,
            shift__ends_at__gte=now - timedelta(hours=12),
        )
        .select_related('worker__user', 'shift__location')
    )
    for entry in entries:
        _, created = Notification.objects.get_or_create(
            user=entry.worker.user,
            kind=f'attendance-checkout-reminder-{entry.id}',
            defaults={
                'title': 'Check-out nicht vergessen',
                'body': f'Deine Schicht ist seit {grace} Minuten beendet. Bitte jetzt auschecken.',
                'action_url': '/time',
            },
        )
        checkout += int(created)
    return {'checkin': checkin, 'checkout': checkout, 'grace_minutes': grace}


def ensure_registration_completed_notification(user: User) -> int:
    """Notify managers once when an employee/customer has actually entered the portal.

    New invitation/onboarding flows call this via the onboarding state transition.
    Legacy accounts that were historically created as already-onboarded are covered
    by calling the same idempotent helper after their first successful login.
    """
    if user.role not in {User.Role.WORKER, User.Role.CLIENT}:
        return 0
    role_label = 'Mitarbeiter' if user.role == User.Role.WORKER else 'Kunde'
    name = user.get_full_name() or user.email
    created_count = 0
    for recipient in User.objects.filter(role__in=[User.Role.ADMIN, User.Role.MANAGER], is_active=True):
        _, created = Notification.objects.get_or_create(
            user=recipient,
            kind=f'portal-registration-complete-{user.id}',
            defaults={
                'title': f'{role_label} registriert',
                'body': f'{name} hat die Registrierung abgeschlossen.',
                'action_url': '/people',
            },
        )
        created_count += int(created)
    return created_count


@receiver(pre_save, sender=User)
def remember_onboarding_state(sender, instance, **kwargs):
    if not instance.pk:
        instance._aplus_was_onboarded = False
        return
    instance._aplus_was_onboarded = bool(
        User.objects.filter(pk=instance.pk).values_list('is_onboarded', flat=True).first()
    )


@receiver(post_save, sender=User)
def notify_registration_completed(sender, instance, created=False, **kwargs):
    if created or instance.role not in {User.Role.WORKER, User.Role.CLIENT}:
        return
    if not instance.is_onboarded or getattr(instance, '_aplus_was_onboarded', False):
        return
    ensure_registration_completed_notification(instance)
