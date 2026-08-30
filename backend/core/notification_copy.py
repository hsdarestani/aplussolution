from __future__ import annotations

import re

from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Announcement, Contract, Message, Notification, Shift, ShiftSwapRequest, TimeEntry, User
from .premium_approval_models import ShiftPickupRequest, ShiftReleaseRequest
from .shift_slots import ShiftSlot


_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _uuids(value: str) -> list[str]:
    return _UUID_RE.findall(str(value or ''))


def _worker_name_from_user(user: User | None) -> str:
    if not user:
        return 'Mitarbeiter'
    return user.get_full_name() or user.email or 'Mitarbeiter'


def _worker_name(worker) -> str:
    return _worker_name_from_user(getattr(worker, 'user', None))


def _shift_window(shift: Shift) -> str:
    start = timezone.localtime(shift.starts_at)
    end = timezone.localtime(shift.ends_at)
    return f'{start:%d.%m.%Y} · {start:%H:%M}–{end:%H:%M} Uhr'


def _shift_detail(shift: Shift) -> str:
    location = getattr(getattr(shift, 'location', None), 'name', '') or 'Location'
    position = getattr(getattr(shift, 'position', None), 'name', '') or 'Position'
    return f'{location} - {position}'


def _shift_lines(shift: Shift) -> str:
    return f'{_shift_window(shift)}\n{_shift_detail(shift)}'


def _shift_by_id(value: str):
    try:
        return Shift.objects.select_related('location', 'position', 'client').get(pk=value)
    except (Shift.DoesNotExist, ValueError, TypeError):
        return None


def _slot_by_id(value: str):
    try:
        return ShiftSlot.objects.select_related(
            'shift__location', 'shift__position', 'shift__client', 'worker__user'
        ).get(pk=value)
    except (ShiftSlot.DoesNotExist, ValueError, TypeError):
        return None


def _entry_by_id(value: str):
    try:
        return TimeEntry.objects.select_related(
            'worker__user', 'shift__location', 'shift__position'
        ).get(pk=value)
    except (TimeEntry.DoesNotExist, ValueError, TypeError):
        return None


def _shift_for_kind(kind: str):
    tokens = _uuids(kind)
    if not tokens:
        return None
    if kind.startswith(('shift-admin-assigned-', 'shift-claimed-', 'shift-24h-', 'attendance-checkin-reminder-')):
        slot = _slot_by_id(tokens[0])
        return slot.shift if slot else None
    if kind.startswith('attendance-checkout-reminder-'):
        entry = _entry_by_id(tokens[0])
        return entry.shift if entry else None
    if kind.startswith(('shift-event-', 'open-shift-')):
        return _shift_by_id(tokens[-1])
    return None


def _pickup_for_kind(kind: str):
    tokens = _uuids(kind)
    if not tokens:
        return None
    try:
        return ShiftPickupRequest.objects.select_related(
            'worker__user', 'shift__location', 'shift__position'
        ).get(pk=tokens[0])
    except (ShiftPickupRequest.DoesNotExist, ValueError, TypeError):
        return None


def _release_for_kind(kind: str):
    tokens = _uuids(kind)
    if not tokens:
        return None
    try:
        return ShiftReleaseRequest.objects.select_related(
            'worker__user', 'requested_worker__user',
            'shift__location', 'shift__position', 'shift__client',
        ).get(pk=tokens[0])
    except (ShiftReleaseRequest.DoesNotExist, ValueError, TypeError):
        return None


def _swap_for_notification(instance: Notification):
    kind = str(instance.kind or '')
    tokens = _uuids(kind)
    qs = ShiftSwapRequest.objects.select_related(
        'shift__location', 'shift__position', 'requested_by__user', 'offered_to__user'
    )
    if tokens:
        try:
            return qs.get(pk=tokens[0])
        except (ShiftSwapRequest.DoesNotExist, ValueError, TypeError):
            pass
    if kind == 'shift-swap-decision' and instance.user_id:
        return qs.filter(requested_by__user_id=instance.user_id).order_by('-updated_at').first()
    if kind == 'shift-swap':
        if instance.user_id:
            targeted = qs.filter(offered_to__user_id=instance.user_id).order_by('-created_at').first()
            if targeted:
                return targeted
        return qs.order_by('-created_at').first()
    return None


def _contract_for_kind(kind: str):
    tokens = _uuids(kind)
    if not tokens:
        return None
    try:
        return Contract.objects.select_related('worker__user', 'client').get(pk=tokens[-1])
    except (Contract.DoesNotExist, ValueError, TypeError):
        return None


def _contract_subject(contract: Contract) -> str:
    if contract.worker_id:
        return _worker_name(contract.worker)
    if contract.client_id:
        return contract.client.name
    return 'Vertrag'


def _set(instance: Notification, title: str, body: str = '') -> None:
    instance.title = title
    instance.body = body


@receiver(pre_save, sender=ShiftSlot, dispatch_uid='aplus_final_direct_assignment_confirmation')
def finalize_direct_assignments(sender, instance: ShiftSlot, **kwargs):
    """An admin-selected/approved worker does not need a second confirmation."""
    if not instance.worker_id or instance.status != ShiftSlot.Status.CLAIMED:
        return
    if instance.source not in {'admin_assignment', 'admin_approved_transfer', 'shift_swap', 'approved_pickup'}:
        return
    instance.confirmation_status = ShiftSlot.ConfirmationStatus.CONFIRMED
    instance.confirmation_requested_at = None
    instance.confirmation_decided_at = instance.confirmation_decided_at or timezone.now()


@receiver(pre_save, sender=Notification, dispatch_uid='aplus_final_notification_copy')
def apply_final_notification_copy(sender, instance: Notification, **kwargs):
    """Normalize native/in-app notification copy to the final approved German wording.

    This lives at the Notification boundary so every producer (schedule, attendance,
    contracts, messages, reminders) gets the same wording and admin mirror pushes
    see exactly the text sent to the employee.
    """
    kind = str(instance.kind or '')

    # 1, 4, 5, 6: shift events with a shift id embedded in the kind.
    if kind.startswith('open-shift-'):
        shift = _shift_for_kind(kind)
        if shift:
            _set(instance, 'Neue Schicht verfügbar', _shift_lines(shift))
        return

    if kind.startswith('shift-event-'):
        shift = _shift_for_kind(kind)
        if not shift:
            return
        if '-manual-reminder-' in kind:
            start = timezone.localtime(shift.starts_at)
            end = timezone.localtime(shift.ends_at)
            _set(
                instance,
                'Erinnerung an deine Schicht',
                f'{start:%d.%m.%Y} von {start:%H:%M}–{end:%H:%M} Uhr\n{_shift_detail(shift)}',
            )
        elif '-deleted-' in kind or '-card-delete-' in kind:
            _set(instance, 'Schicht gelöscht am', _shift_lines(shift))
        else:
            start = timezone.localtime(shift.starts_at)
            end = timezone.localtime(shift.ends_at)
            _set(
                instance,
                'Deine Schicht wurde aktualisiert',
                f'{start:%d.%m.%Y} · neu {start:%H:%M}–{end:%H:%M} Uhr\n{_shift_detail(shift)}',
            )
        return

    # 2: direct/admin-approved assignment. This is already accepted, never a confirmation request.
    if kind.startswith(('shift-admin-assigned-', 'shift-release-transfer-')):
        if kind.startswith('shift-admin-assigned-'):
            slot = _slot_by_id((_uuids(kind) or [''])[0])
            shift = slot.shift if slot else None
            worker_name = _worker_name(slot.worker) if slot and slot.worker_id else _worker_name_from_user(instance.user)
        else:
            release = _release_for_kind(kind)
            shift = release.shift if release else None
            worker_name = _worker_name(release.requested_worker) if release and release.requested_worker_id else _worker_name_from_user(instance.user)
        if shift:
            _set(instance, f'{worker_name} übernimmt folgende Schicht:', _shift_lines(shift))
        return

    # 3: confirmation requests that are not direct admin assignments.
    if instance.title in {'Schicht bestätigen', 'Bitte Schicht bestätigen'}:
        shift = _shift_for_kind(kind)
        if not shift and kind.startswith('shift-release-transfer-'):
            release = _release_for_kind(kind)
            shift = release.shift if release else None
        if shift:
            _set(instance, 'Bitte Schicht bestätigen', f'{_worker_name_from_user(instance.user)} · {_shift_window(shift)}')
        return

    # 7: automatic 24-hour reminder.
    if kind.startswith('shift-24h-'):
        shift = _shift_for_kind(kind)
        if shift:
            start = timezone.localtime(shift.starts_at)
            _set(instance, 'Erinnerung:', f'Dein Einsatz beginnt morgen um {start:%H:%M} Uhr')
        return

    # 9: worker claimed an OpenShift.
    if kind.startswith('shift-claimed-'):
        shift = _shift_for_kind(kind)
        if shift:
            _set(instance, 'Schicht übernommen am', _shift_window(shift))
        return

    # 10-12: pickup request / approval. Rejection is kept as an in-app record but native push is suppressed.
    if kind.startswith('pickup-request-'):
        pickup = _pickup_for_kind(kind)
        if pickup:
            _set(
                instance,
                'Schichtanfrage',
                f'{_worker_name(pickup.worker)} möchte folgende Schicht übernehmen · {_shift_window(pickup.shift)}\n{_shift_detail(pickup.shift)}',
            )
        return
    if kind.startswith('pickup-'):
        pickup = _pickup_for_kind(kind)
        if pickup and kind.endswith('-approved'):
            day = timezone.localtime(pickup.shift.starts_at).strftime('%d.%m.%Y')
            _set(instance, f'Schichtübernahme für den {day} genehmigt', '')
        return

    # 13-15: release request / decision.
    if kind.startswith('shift-release-request-'):
        release = _release_for_kind(kind)
        if release:
            _set(
                instance,
                'Schichtfreigabe prüfen',
                f'{_worker_name(release.worker)} möchte aus der Schicht freigegeben werden · {_shift_window(release.shift)}\n{_shift_detail(release.shift)}',
            )
        return
    if kind.startswith('shift-release-') and not kind.startswith(('shift-release-request-', 'shift-release-transfer-')):
        release = _release_for_kind(kind)
        if release:
            if kind.endswith('-approved'):
                _set(
                    instance,
                    'Schichtfreigabe genehmigt',
                    f'Du wurdest aus dieser Schicht freigegeben · {_shift_window(release.shift)}\n{_shift_detail(release.shift)}',
                )
            elif kind.endswith('-rejected'):
                _set(instance, 'Schichtfreigabe abgelehnt', f'für den {_shift_window(release.shift)}')
        return

    # 20-21: shift swap request / decision.
    if kind == 'shift-swap' or kind.startswith('shift-swap-'):
        swap = _swap_for_notification(instance)
        if not swap:
            return
        requester = _worker_name(swap.requested_by)
        target = _worker_name(swap.offered_to) if swap.offered_to_id else 'einem anderen Mitarbeiter'
        if kind == 'shift-swap':
            _set(
                instance,
                'Neue Schichttauschanfrage',
                f'{requester} möchte ihre Schicht mit {target} tauschen\n{_shift_window(swap.shift)}\n{_shift_detail(swap.shift)}',
            )
        elif kind == 'shift-swap-decision':
            if swap.status == ShiftSwapRequest.Status.APPROVED:
                _set(
                    instance,
                    'Schichttausch bestätigt',
                    f'Dein Schichttausch wurde genehmigt · {requester} → {target} · {_shift_window(swap.shift)}',
                )
            elif swap.status == ShiftSwapRequest.Status.REJECTED:
                _set(instance, 'Schichttausch abgelehnt', f'Deine Tauschanfrage wurde abgelehnt · {_shift_window(swap.shift)}')
        elif kind.startswith('shift-swap-assigned-'):
            _set(
                instance,
                'Schichttausch bestätigt',
                f'Der Schichttausch wurde genehmigt · {requester} → {target} · {_shift_window(swap.shift)}',
            )
        return

    # 22-26: attendance.
    if kind.startswith('attendance-check_in-') or kind.startswith('attendance-check_out-'):
        tokens = _uuids(kind)
        entry = _entry_by_id(tokens[0]) if tokens else None
        if entry:
            worker_name = _worker_name(entry.worker)
            _set(instance, f'{worker_name} hat {"eingecheckt" if kind.startswith("attendance-check_in-") else "ausgecheckt"}', '')
        return
    if kind.startswith('offsite-checkout-'):
        tokens = _uuids(kind)
        entry = _entry_by_id(tokens[0]) if tokens else None
        if entry:
            worker_name = _worker_name(entry.worker)
            moment = timezone.localtime(entry.clock_out or timezone.now())
            location = entry.shift.location.name if entry.shift_id and entry.shift.location_id else 'Location'
            shift_time = _shift_window(entry.shift) if entry.shift_id else moment.strftime('%d.%m.%Y · %H:%M Uhr')
            _set(
                instance,
                'Check-out außerhalb des Einsatzortes',
                f'{worker_name} hat um {moment:%H:%M} Uhr außerhalb des erlaubten Bereichs ausgecheckt ·\n{shift_time} - {location}',
            )
        return
    if kind.startswith('attendance-checkin-reminder-'):
        _set(instance, 'Check-in nicht vergessen', 'Deine Schicht hat vor 15 Minuten begonnen')
        return
    if kind.startswith('attendance-checkout-reminder-'):
        _set(instance, 'Check-out nicht vergessen', 'Deine Schicht hat vor 15 Minuten geendet')
        return

    # 28-29: portal registration.
    if kind.startswith('portal-registration-complete-'):
        tokens = _uuids(kind)
        user = User.objects.filter(pk=tokens[0]).first() if tokens else None
        if user:
            name = _worker_name_from_user(user)
            if user.role == User.Role.WORKER:
                _set(instance, 'Mitarbeiterregistrierung abgeschlossen', f'{name} hat die Registrierung erfolgreich abgeschlossen')
            elif user.role == User.Role.CLIENT:
                company = user.client_companies.order_by('name').first()
                label = f'{name} / {company.name}' if company else name
                _set(instance, 'Kundenregistrierung abgeschlossen', f'{label} hat die Registrierung erfolgreich abgeschlossen')
        return

    # 30-33: contracts and signature reminders.
    if kind.startswith('contract-'):
        contract = _contract_for_kind(kind)
        if not contract:
            return
        subject = _contract_subject(contract)
        title = contract.title or f'Arbeitsvertrag {subject}'
        if kind.startswith('contract-sent-'):
            sent_at = timezone.localtime(contract.sent_at or timezone.now())
            _set(
                instance,
                'Dokument zur Prüfung bereit',
                f'{title}\nVersand: {sent_at:%d.%m.%Y, %H:%M} Uhr · Status: Unterschrift ausstehend.',
            )
        elif kind.startswith('contract-explicit-reminder-'):
            _set(instance, 'Erinnerung', f'{title} Bitte Dokument prüfen.')
        elif kind.startswith('contract-signature-'):
            match = re.search(r'contract-signature-(\d+)d-', kind)
            days = int(match.group(1)) if match else 0
            _set(instance, 'Unterschrift ausstehend', f'{title} - Seit {days} Tagen offen')
        else:
            match = re.search(r'contract-(?:end-)?(\d+)(?:d)?-', kind)
            days = int(match.group(1)) if match else None
            if days is not None:
                deadline = 'Vertrag endet heute' if days == 0 else f'Vertrag endet in {days} Tagen'
                _set(instance, 'Vertragsende', f'{deadline} - {subject}')
        return

    # 34: announcements.
    if kind.startswith('announcement-'):
        tokens = _uuids(kind)
        announcement = Announcement.objects.select_related('created_by').filter(pk=tokens[0]).first() if tokens else None
        if announcement:
            sender_name = _worker_name_from_user(announcement.created_by) if announcement.created_by_id else 'Administration'
            body = (announcement.body or 'Neue Mitteilung mit Anhang').strip()
            _set(instance, f'Neue Mitteilung von {sender_name}', body)
        return

    # 35: direct conversation messages.
    if kind.startswith('message-'):
        tokens = _uuids(kind)
        message = Message.objects.select_related('sender').filter(pk=tokens[0]).first() if tokens else None
        if message:
            sender_name = _worker_name_from_user(message.sender)
            _set(instance, f'Neue Nachricht von {sender_name}', (message.body or '').strip())
