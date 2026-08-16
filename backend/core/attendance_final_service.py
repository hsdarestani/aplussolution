from __future__ import annotations

import ipaddress
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .attendance_v4_models import AttendanceClockEvent, AttendanceNotice, AttendancePolicy
from .attendance_v4_service import (
    _create_no_show_coverage,
    attendance_policy_for_shift,
    clock_in_worker,
    clock_out_worker,
)
from .models import Shift, TimeEntry
from .shift_slots import ShiftSlot


def client_ip(request):
    if not request:
        return None
    forwarded = str(request.META.get('HTTP_X_FORWARDED_FOR') or '').strip()
    value = forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR')
    try:
        return str(ipaddress.ip_address(value)) if value else None
    except ValueError:
        return None


def normalize_ip_networks(values):
    if values in (None, ''):
        return []
    if isinstance(values, str):
        values = [part.strip() for part in values.replace('\n', ',').split(',') if part.strip()]
    if not isinstance(values, (list, tuple)):
        raise ValidationError('IP-Freigaben müssen als Liste oder kommasepariert angegeben werden.')
    normalized = []
    for value in values:
        text = str(value or '').strip()
        if not text:
            continue
        try:
            if '/' in text:
                network = ipaddress.ip_network(text, strict=False)
            else:
                address = ipaddress.ip_address(text)
                network = ipaddress.ip_network(f'{address}/{address.max_prefixlen}', strict=False)
        except ValueError as exc:
            raise ValidationError(f'Ungültige IP-Adresse oder Netzwerk: {text}') from exc
        canonical = str(network)
        if canonical not in normalized:
            normalized.append(canonical)
    return normalized


def validate_ip_policy(mode, values):
    networks = normalize_ip_networks(values)
    if mode not in AttendancePolicy.Enforcement.values:
        raise ValidationError('Ungültiger IP-Prüfmodus.')
    if mode != AttendancePolicy.Enforcement.OFF and not networks:
        raise ValidationError('Für eine aktive IP-Prüfung muss mindestens eine IP-Adresse oder ein Netzwerk hinterlegt werden.')
    return networks


def _ip_allowed(value, networks):
    if not value:
        return False
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    for text in networks:
        try:
            if address in ipaddress.ip_network(text, strict=False):
                return True
        except ValueError:
            continue
    return False


def enforce_computer_ip(*, worker, shift, request, policy=None, phase='clock_in', method=AttendanceClockEvent.Method.WEB):
    if method != AttendanceClockEvent.Method.WEB:
        return None
    policy = policy or attendance_policy_for_shift(shift)
    mode = policy.computer_ip_mode
    if mode == AttendancePolicy.Enforcement.OFF:
        return None
    networks = normalize_ip_networks(policy.allowed_ip_networks)
    current_ip = client_ip(request)
    if _ip_allowed(current_ip, networks):
        return None
    message = 'Die Zeiterfassung ist von dieser IP-Adresse nicht freigegeben.'
    AttendanceNotice.objects.get_or_create(
        dedupe_key=f'computer-ip:{phase}:{worker.id}:{getattr(shift, "id", "none")}:{timezone.localdate()}',
        defaults={
            'worker': worker,
            'shift': shift,
            'notice_type': AttendanceNotice.Type.WRONG_LOCATION,
            'severity': AttendanceNotice.Severity.WARNING,
            'details': {
                'restriction': 'ip',
                'phase': phase,
                'ip_address': current_ip,
                'allowed_ip_networks': networks,
            },
        },
    )
    if mode == AttendancePolicy.Enforcement.BLOCK:
        raise ValidationError(message)
    return message


def resolve_missing_clock_notices(worker, shift, entry=None, now=None):
    if not shift:
        return 0
    now = now or timezone.now()
    return AttendanceNotice.objects.filter(
        worker=worker,
        shift=shift,
        notice_type__in=[AttendanceNotice.Type.MISSED_CLOCK_IN, AttendanceNotice.Type.NO_SHOW],
        status__in=[AttendanceNotice.Status.OPEN, AttendanceNotice.Status.ACKNOWLEDGED],
    ).update(
        status=AttendanceNotice.Status.RESOLVED,
        resolved_at=now,
        resolution_note='Automatisch erledigt: Zeiteintrag vorhanden.',
        entry=entry,
    )


@transaction.atomic
def clock_in_with_restrictions(*, worker, shift_id=None, lat=None, lng=None, request=None, method=AttendanceClockEvent.Method.WEB, photo=None, now=None):
    now = now or timezone.now()
    shift = None
    if shift_id:
        ownership = Q(slots__worker=worker, slots__status=ShiftSlot.Status.CLAIMED) | Q(worker=worker)
        shift = Shift.objects.filter(ownership, pk=shift_id).select_related('location', 'position').distinct().first()
    policy = attendance_policy_for_shift(shift)
    enforce_computer_ip(worker=worker, shift=shift, request=request, policy=policy, phase='clock_in', method=method)
    entry = clock_in_worker(
        worker=worker,
        shift_id=shift_id,
        lat=lat,
        lng=lng,
        request=request,
        method=method,
        photo=photo,
        now=now,
    )
    resolve_missing_clock_notices(worker, entry.shift, entry=entry, now=now)
    return entry


@transaction.atomic
def clock_out_with_restrictions(*, worker, lat=None, lng=None, request=None, method=AttendanceClockEvent.Method.WEB, photo=None, note='', now=None):
    entry = TimeEntry.objects.select_related('shift__location').filter(worker=worker, clock_out__isnull=True).order_by('-clock_in').first()
    policy = attendance_policy_for_shift(entry.shift if entry else None)
    enforce_computer_ip(worker=worker, shift=entry.shift if entry else None, request=request, policy=policy, phase='clock_out', method=method)
    return clock_out_worker(
        worker=worker,
        lat=lat,
        lng=lng,
        request=request,
        method=method,
        photo=photo,
        note=note,
        now=now,
    )


def scan_attendance_notices_final(now=None):
    now = now or timezone.now()
    created = {'missed_clock_in': 0, 'no_show': 0, 'missed_clock_out': 0}
    slots = ShiftSlot.objects.filter(
        status=ShiftSlot.Status.CLAIMED,
        worker__isnull=False,
        shift__status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED],
        shift__starts_at__lte=now,
        shift__ends_at__gte=now - timedelta(hours=12),
    ).select_related('worker__user', 'shift__location', 'shift__position')
    for slot in slots:
        policy = attendance_policy_for_shift(slot.shift)
        entry = TimeEntry.objects.filter(worker=slot.worker, shift=slot.shift).order_by('clock_in').first()
        minutes_since_start = max(0, int((now - slot.shift.starts_at).total_seconds() // 60))
        if entry:
            resolve_missing_clock_notices(slot.worker, slot.shift, entry=entry, now=now)
        elif now < slot.shift.ends_at and minutes_since_start >= int(policy.late_clock_in_grace_minutes or 0):
            _, was_created = AttendanceNotice.objects.get_or_create(
                dedupe_key=f'missed-in:{slot.worker_id}:{slot.shift_id}',
                defaults={
                    'worker': slot.worker,
                    'shift': slot.shift,
                    'notice_type': AttendanceNotice.Type.MISSED_CLOCK_IN,
                    'severity': AttendanceNotice.Severity.WARNING,
                    'value_minutes': minutes_since_start,
                    'details': {'lifecycle': 'in_progress'},
                },
            )
            created['missed_clock_in'] += int(was_created)
        elif now >= slot.shift.ends_at:
            _, was_created = AttendanceNotice.objects.get_or_create(
                dedupe_key=f'no-show:{slot.worker_id}:{slot.shift_id}',
                defaults={
                    'worker': slot.worker,
                    'shift': slot.shift,
                    'notice_type': AttendanceNotice.Type.NO_SHOW,
                    'severity': AttendanceNotice.Severity.CRITICAL,
                    'value_minutes': minutes_since_start,
                    'details': {'lifecycle': 'shift_ended'},
                },
            )
            created['no_show'] += int(was_created)
            AttendanceNotice.objects.filter(
                worker=slot.worker,
                shift=slot.shift,
                notice_type=AttendanceNotice.Type.MISSED_CLOCK_IN,
                status__in=[AttendanceNotice.Status.OPEN, AttendanceNotice.Status.ACKNOWLEDGED],
            ).update(
                status=AttendanceNotice.Status.RESOLVED,
                resolved_at=now,
                resolution_note='Automatisch in No-Show überführt.',
            )
            _create_no_show_coverage(slot)
        if entry and entry.clock_out is None and now > slot.shift.ends_at + timedelta(minutes=int(policy.missed_clock_out_after_minutes or 0)):
            _, was_created = AttendanceNotice.objects.get_or_create(
                dedupe_key=f'missed-out:{entry.id}',
                defaults={
                    'worker': slot.worker,
                    'shift': slot.shift,
                    'entry': entry,
                    'notice_type': AttendanceNotice.Type.MISSED_CLOCK_OUT,
                    'severity': AttendanceNotice.Severity.WARNING,
                    'value_minutes': int((now - slot.shift.ends_at).total_seconds() // 60),
                },
            )
            created['missed_clock_out'] += int(was_created)
    created['total'] = sum(created.values())
    return created


def clock_event_audit(entry):
    events = list(entry.clock_events.order_by('occurred_at'))
    clock_in = next((item for item in events if item.kind == AttendanceClockEvent.Kind.CLOCK_IN), None)
    clock_out = next((item for item in reversed(events) if item.kind == AttendanceClockEvent.Kind.CLOCK_OUT), None)
    return {
        'clock_in_ip': clock_in.ip_address if clock_in else None,
        'clock_out_ip': clock_out.ip_address if clock_out else None,
        'clock_in_method': clock_in.method if clock_in else None,
        'clock_out_method': clock_out.method if clock_out else None,
        'clock_in_lat': clock_in.lat if clock_in else entry.clock_in_lat,
        'clock_in_lng': clock_in.lng if clock_in else entry.clock_in_lng,
        'clock_out_lat': clock_out.lat if clock_out else entry.clock_out_lat,
        'clock_out_lng': clock_out.lng if clock_out else entry.clock_out_lng,
    }
