from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import migrations
from django.db.models import Q
from django.utils import timezone


BERLIN = ZoneInfo('Europe/Berlin')
ASSIGNED_DAYS = {9, 10, 11}
OPEN_DAYS = {12, 14, 18, 19, 21, 22, 23, 24, 26, 27}
ALL_DAYS = ASSIGNED_DAYS | OPEN_DAYS
RECOVERY_TAG = 'spenerhaus-sept-2026'


def send_spenerhaus_notifications(apps, schema_editor):
    # Use the runtime models intentionally so Notification post_save signals fire and
    # native push delivery is queued exactly like notifications created through the API.
    from core.models import Notification, Shift, User, WorkerProfile
    from core.shift_rules import shift_visible_to_worker
    from core.shift_slots import ShiftSlot

    created_assigned = 0
    created_open = 0
    created_admin = 0

    for day in sorted(ALL_DAYS):
        starts_at = datetime(2026, 9, day, 8, 0, tzinfo=BERLIN)
        ends_at = datetime(2026, 9, day, 13, 0, tzinfo=BERLIN)
        shift = (
            Shift.objects.select_related('client', 'location', 'position', 'worker__user')
            .filter(
                client__name__icontains='Spenerhaus',
                location__name__icontains='Spenerhaus',
                starts_at=starts_at,
                ends_at=ends_at,
            )
            .filter(Q(position__name__iexact='Housekeeping') | Q(position__name__iexact='Houskeeping'))
            .exclude(status=Shift.Status.CANCELLED)
            .first()
        )
        if not shift:
            raise RuntimeError(f'Spenerhaus notification recovery: shift for 2026-09-{day:02d} not found.')

        local_start = timezone.localtime(shift.starts_at)
        location_name = shift.location.name or 'Einsatzort'
        position_name = shift.position.name or 'Schicht'

        if day in ASSIGNED_DAYS:
            slot = (
                ShiftSlot.objects.filter(
                    shift=shift,
                    status=ShiftSlot.Status.CLAIMED,
                    worker__isnull=False,
                )
                .select_related('worker__user')
                .first()
            )
            if not slot:
                raise RuntimeError(
                    f'Spenerhaus notification recovery: assigned slot for 2026-09-{day:02d} not found.'
                )
            _, was_created = Notification.objects.get_or_create(
                user=slot.worker.user,
                kind=f'shift-admin-assigned-{slot.id}',
                defaults={
                    'title': 'Neue Schicht zugeteilt',
                    'body': f'{local_start:%d.%m.%Y %H:%M} – {location_name}',
                    'action_url': '/schedule',
                },
            )
            created_assigned += int(was_created)
            continue

        if shift.status != Shift.Status.PUBLISHED or shift.ends_at <= timezone.now():
            continue
        if not ShiftSlot.objects.filter(
            shift=shift,
            status=ShiftSlot.Status.OPEN,
            worker__isnull=True,
        ).exists():
            continue

        assigned_ids = set(
            ShiftSlot.objects.filter(
                shift=shift,
                status=ShiftSlot.Status.CLAIMED,
                worker__isnull=False,
            ).values_list('worker_id', flat=True)
        )
        body = f'{local_start:%d.%m.%Y %H:%M} · {position_name} · {location_name}'
        worker_count = 0
        workers = (
            WorkerProfile.objects.filter(active=True, user__is_active=True)
            .exclude(user__email__iendswith='@sync.invalid')
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

            # Skip if this worker already received any OpenShift notification for the
            # same shift through the normal app flow; otherwise create a deterministic
            # recovery notification so restarts cannot duplicate it.
            already_notified = Notification.objects.filter(
                user=worker.user,
                title='Neue OpenShift verfügbar',
                kind__startswith='open-shift-',
                kind__endswith=f'-{shift.id}',
            ).exists()
            if already_notified:
                continue

            _, was_created = Notification.objects.get_or_create(
                user=worker.user,
                kind=f'open-shift-{RECOVERY_TAG}-{shift.id}',
                defaults={
                    'title': 'Neue OpenShift verfügbar',
                    'body': body,
                    'action_url': '/schedule',
                },
            )
            worker_count += int(was_created)
            created_open += int(was_created)

        summary_body = (
            f'Benachrichtigung für {worker_count} Mitarbeiter ausgelöst · {body}'
            if worker_count > 0
            else f'Keine passenden Mitarbeiter benachrichtigt · {body}'
        )
        for admin in User.objects.filter(role=User.Role.ADMIN, is_active=True):
            if Notification.objects.filter(
                user=admin,
                title='OpenShift veröffentlicht',
                kind__startswith='admin-open-shift-summary-',
                kind__endswith=f'-{shift.id}',
            ).exists():
                continue
            _, was_created = Notification.objects.get_or_create(
                user=admin,
                kind=f'admin-open-shift-summary-{RECOVERY_TAG}-{shift.id}',
                defaults={
                    'title': 'OpenShift veröffentlicht',
                    'body': summary_body,
                    'action_url': '/schedule',
                },
            )
            created_admin += int(was_created)

    print(
        'Spenerhaus notification recovery complete: '
        f'{created_assigned} assigned, {created_open} OpenShift, {created_admin} admin summaries created.'
    )


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('core', '0028_spenerhaus_housekeeping_schedule_update'),
    ]

    operations = [
        migrations.RunPython(send_spenerhaus_notifications, migrations.RunPython.noop),
    ]
