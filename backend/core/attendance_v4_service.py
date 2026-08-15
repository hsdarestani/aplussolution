from __future__ import annotations

from datetime import timedelta
from math import asin, cos, radians, sin, sqrt

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .attendance_v4_models import (
    AttendanceAttestation,
    AttendanceBreak,
    AttendanceClockEvent,
    AttendanceNotice,
    AttendancePolicy,
)
from .models import Shift, TimeEntry, User, WorkerProfile
from .shift_slots import ShiftSlot


def attendance_policy_for_shift(shift=None, location=None):
    location_id = getattr(location, 'id', None) or getattr(shift, 'location_id', None)
    policies = AttendancePolicy.objects.filter(active=True)
    if location_id:
        scoped = policies.filter(location_id=location_id).order_by('-priority', '-updated_at').first()
        if scoped:
            return scoped
    global_policy = policies.filter(location__isnull=True).order_by('-priority', '-updated_at').first()
    return global_policy or AttendancePolicy(name='Standard', active=True)


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '') if request else ''
    return (forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR')) if request else None


def _distance_m(shift, lat, lng):
    if not shift or not getattr(shift, 'location_id', None):
        return None
    location = shift.location
    if location.latitude is None or location.longitude is None:
        return None
    if lat in (None, '') or lng in (None, ''):
        return None
    try:
        lat1, lon1 = radians(float(lat)), radians(float(lng))
        lat2, lon2 = radians(float(location.latitude)), radians(float(location.longitude))
    except (TypeError, ValueError):
        return None
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371000 * 2 * asin(sqrt(value))


def create_notice(*, worker, notice_type, shift=None, entry=None, break_record=None, severity='warning', value_minutes=None, details=None, dedupe_key=None):
    key = dedupe_key or ':'.join([
        str(notice_type),
        str(getattr(worker, 'id', '')),
        str(getattr(shift, 'id', '')),
        str(getattr(entry, 'id', '')),
        str(getattr(break_record, 'id', '')),
    ])
    notice, _ = AttendanceNotice.objects.get_or_create(
        dedupe_key=key[:180],
        defaults={
            'worker': worker,
            'shift': shift,
            'entry': entry,
            'break_record': break_record,
            'notice_type': notice_type,
            'severity': severity,
            'value_minutes': value_minutes,
            'details': details or {},
        },
    )
    return notice


def _location_rule(*, worker, shift, entry, lat, lng, policy, phase):
    mode = policy.clock_in_location_mode if phase == 'clock_in' else policy.clock_out_location_mode
    if mode == AttendancePolicy.Enforcement.OFF or not shift or not shift.location_id:
        return None
    location = shift.location
    if location.latitude is None or location.longitude is None:
        return None
    distance = _distance_m(shift, lat, lng)
    if distance is None:
        message = 'Für diesen Einsatz ist die Standortfreigabe erforderlich.'
        outside = True
    else:
        outside = distance > int(location.geofence_radius_m or 0)
        message = f'Du befindest dich {round(distance)} m vom Einsatzort entfernt. Erlaubt sind {location.geofence_radius_m} m.'
    if not outside:
        return None
    create_notice(
        worker=worker,
        shift=shift,
        entry=entry,
        notice_type=AttendanceNotice.Type.WRONG_LOCATION,
        severity=AttendanceNotice.Severity.WARNING,
        details={'phase': phase, 'distance_m': round(distance) if distance is not None else None, 'radius_m': location.geofence_radius_m},
        dedupe_key=f'wrong-location:{phase}:{worker.id}:{shift.id}:{timezone.localdate()}',
    )
    if mode == AttendancePolicy.Enforcement.BLOCK:
        raise ValidationError(message)
    return message


def _clock_time_notices(*, worker, shift, entry, now, policy, phase):
    if not shift:
        return
    if phase == 'clock_in':
        earliest = shift.starts_at - timedelta(minutes=int(policy.early_clock_in_minutes or 0))
        if now < earliest:
            minutes = int((shift.starts_at - now).total_seconds() // 60)
            create_notice(
                worker=worker, shift=shift, entry=entry,
                notice_type=AttendanceNotice.Type.EARLY_CLOCK_IN,
                severity=AttendanceNotice.Severity.INFO,
                value_minutes=minutes,
                details={'allowed_early_minutes': policy.early_clock_in_minutes},
                dedupe_key=f'early-in:{worker.id}:{shift.id}',
            )
            if policy.early_clock_in_mode == AttendancePolicy.Enforcement.BLOCK:
                raise ValidationError(f'Einstempeln ist frühestens {policy.early_clock_in_minutes} Minuten vor Schichtbeginn möglich.')
        late_after = shift.starts_at + timedelta(minutes=int(policy.late_clock_in_grace_minutes or 0))
        if now > late_after:
            minutes = max(1, int((now - shift.starts_at).total_seconds() // 60))
            create_notice(
                worker=worker, shift=shift, entry=entry,
                notice_type=AttendanceNotice.Type.LATE_CLOCK_IN,
                severity=AttendanceNotice.Severity.WARNING,
                value_minutes=minutes,
                dedupe_key=f'late-in:{worker.id}:{shift.id}',
            )
    else:
        early_before = shift.ends_at - timedelta(minutes=int(policy.early_clock_out_grace_minutes or 0))
        if now < early_before:
            minutes = max(1, int((shift.ends_at - now).total_seconds() // 60))
            create_notice(
                worker=worker, shift=shift, entry=entry,
                notice_type=AttendanceNotice.Type.EARLY_CLOCK_OUT,
                severity=AttendanceNotice.Severity.WARNING,
                value_minutes=minutes,
                dedupe_key=f'early-out:{worker.id}:{shift.id}:{entry.id}',
            )
        late_after = shift.ends_at + timedelta(minutes=int(policy.late_clock_out_grace_minutes or 0))
        if now > late_after:
            minutes = max(1, int((now - shift.ends_at).total_seconds() // 60))
            create_notice(
                worker=worker, shift=shift, entry=entry,
                notice_type=AttendanceNotice.Type.LATE_CLOCK_OUT,
                severity=AttendanceNotice.Severity.INFO,
                value_minutes=minutes,
                dedupe_key=f'late-out:{worker.id}:{shift.id}:{entry.id}',
            )


def _assigned_shift(worker, shift_id=None, now=None):
    now = now or timezone.now()
    ownership = Q(slots__worker=worker, slots__status=ShiftSlot.Status.CLAIMED) | Q(worker=worker)
    qs = Shift.objects.filter(ownership).select_related('location', 'position', 'client').distinct()
    if shift_id:
        return qs.filter(pk=shift_id).first()
    return qs.filter(
        starts_at__lte=now + timedelta(hours=4),
        ends_at__gte=now - timedelta(hours=4),
        status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED],
    ).order_by('starts_at').first()


def _planned_break_minutes(shift, policy):
    if not shift:
        return 0
    if int(shift.break_minutes or 0) > 0:
        return int(shift.break_minutes)
    scheduled = int((shift.ends_at - shift.starts_at).total_seconds() // 60)
    if scheduled >= int(policy.required_break_after_minutes or 0):
        return int(policy.required_break_minutes or 0)
    return 0


def _ensure_planned_break(entry, policy):
    minutes = _planned_break_minutes(entry.shift, policy)
    if minutes <= 0:
        return None
    existing = entry.attendance_breaks.exclude(status=AttendanceBreak.Status.CANCELLED).first()
    if existing:
        return existing
    return AttendanceBreak.objects.create(
        entry=entry,
        source=AttendanceBreak.Source.SCHEDULED,
        status=AttendanceBreak.Status.PLANNED,
        paid=bool(policy.default_break_paid),
        scheduled_minutes=minutes,
    )


def net_worked_minutes(entry):
    end = entry.clock_out or timezone.now()
    gross = max(0, int((end - entry.clock_in).total_seconds() // 60))
    try:
        breaks = list(entry.attendance_breaks.exclude(status=AttendanceBreak.Status.CANCELLED))
    except Exception:
        breaks = []
    if breaks:
        deductible = sum(item.deductible_minutes for item in breaks)
    else:
        deductible = int(entry.shift.break_minutes or 0) if entry.shift_id else 0
    return max(0, gross - deductible)


def break_summary(entry):
    rows = list(entry.attendance_breaks.exclude(status=AttendanceBreak.Status.CANCELLED))
    return {
        'paid_minutes': sum(item.actual_minutes for item in rows if item.paid and item.status == AttendanceBreak.Status.COMPLETED),
        'unpaid_minutes': sum(item.deductible_minutes for item in rows),
        'running': next((item for item in rows if item.status == AttendanceBreak.Status.RUNNING), None),
        'planned': next((item for item in rows if item.status == AttendanceBreak.Status.PLANNED), None),
        'rows': rows,
    }


def _clock_event(*, entry, kind, request=None, method=AttendanceClockEvent.Method.WEB, lat=None, lng=None, note='', photo=None, metadata=None):
    return AttendanceClockEvent.objects.create(
        entry=entry,
        kind=kind,
        method=method,
        lat=lat if lat not in ('', None) else None,
        lng=lng if lng not in ('', None) else None,
        ip_address=_client_ip(request),
        note=str(note or '')[:250],
        photo=photo,
        metadata=metadata or {},
    )


@transaction.atomic
def clock_in_worker(*, worker, shift_id=None, lat=None, lng=None, request=None, method=AttendanceClockEvent.Method.WEB, photo=None, now=None):
    now = now or timezone.now()
    if TimeEntry.objects.select_for_update().filter(worker=worker, clock_out__isnull=True).exists():
        raise ValidationError('Du bist bereits eingestempelt.')
    shift = _assigned_shift(worker, shift_id=shift_id, now=now)
    policy = attendance_policy_for_shift(shift)
    if shift_id and not shift:
        raise ValidationError('Die ausgewählte Schicht gehört nicht zu deinem Profil.')
    if not shift and not policy.allow_unscheduled_clock_in:
        raise ValidationError('Aktuell gibt es keine passende bestätigte Schicht zum Einstempeln.')
    if shift:
        _clock_time_notices(worker=worker, shift=shift, entry=None, now=now, policy=policy, phase='clock_in')
        _location_rule(worker=worker, shift=shift, entry=None, lat=lat, lng=lng, policy=policy, phase='clock_in')
    entry = TimeEntry.objects.create(
        worker=worker,
        shift=shift,
        clock_in=now,
        clock_in_lat=lat if lat not in ('', None) else None,
        clock_in_lng=lng if lng not in ('', None) else None,
        photo=photo,
    )
    _clock_event(entry=entry, kind=AttendanceClockEvent.Kind.CLOCK_IN, request=request, method=method, lat=lat, lng=lng, photo=photo)
    _ensure_planned_break(entry, policy)
    return entry


def _apply_break_compliance(entry, policy):
    required = _planned_break_minutes(entry.shift, policy)
    if required <= 0 or policy.default_break_paid:
        return
    summary = break_summary(entry)
    taken = int(summary['unpaid_minutes'])
    missing = max(0, required - taken)
    if missing <= 0:
        return
    if policy.auto_deduct_unpaid_breaks:
        AttendanceBreak.objects.create(
            entry=entry,
            source=AttendanceBreak.Source.AUTO_DEDUCT,
            status=AttendanceBreak.Status.COMPLETED,
            paid=False,
            scheduled_minutes=required,
            deducted_minutes=missing,
            note='Automatischer Pausenabzug gemäß Attendance Policy',
        )
        return
    notice_type = AttendanceNotice.Type.BREAK_MISSED if taken == 0 else AttendanceNotice.Type.BREAK_SHORT
    create_notice(
        worker=entry.worker,
        shift=entry.shift,
        entry=entry,
        notice_type=notice_type,
        severity=AttendanceNotice.Severity.WARNING,
        value_minutes=missing,
        details={'required_minutes': required, 'taken_unpaid_minutes': taken},
        dedupe_key=f'{notice_type}:{entry.id}',
    )


@transaction.atomic
def clock_out_worker(*, worker, lat=None, lng=None, request=None, method=AttendanceClockEvent.Method.WEB, photo=None, note='', now=None):
    now = now or timezone.now()
    entry = TimeEntry.objects.select_for_update().select_related('shift__location', 'shift__position', 'worker__user').filter(
        worker=worker, clock_out__isnull=True
    ).order_by('-clock_in').first()
    if not entry:
        raise ValidationError('Keine laufende Zeiterfassung gefunden.')
    if entry.attendance_breaks.filter(status=AttendanceBreak.Status.RUNNING).exists():
        raise ValidationError('Bitte beende zuerst deine laufende Pause.')
    policy = attendance_policy_for_shift(entry.shift)
    if entry.shift:
        _location_rule(worker=worker, shift=entry.shift, entry=entry, lat=lat, lng=lng, policy=policy, phase='clock_out')
        _clock_time_notices(worker=worker, shift=entry.shift, entry=entry, now=now, policy=policy, phase='clock_out')
    entry.clock_out = now
    entry.clock_out_lat = lat if lat not in ('', None) else None
    entry.clock_out_lng = lng if lng not in ('', None) else None
    entry.save(update_fields=['clock_out', 'clock_out_lat', 'clock_out_lng', 'updated_at'])
    _clock_event(entry=entry, kind=AttendanceClockEvent.Kind.CLOCK_OUT, request=request, method=method, lat=lat, lng=lng, note=note, photo=photo)
    _apply_break_compliance(entry, policy)
    if policy.break_attestation_required and not entry.attestations.filter(kind=AttendanceAttestation.Kind.BREAK).exists():
        create_notice(
            worker=worker, shift=entry.shift, entry=entry,
            notice_type=AttendanceNotice.Type.ATTESTATION_MISSING,
            severity=AttendanceNotice.Severity.INFO,
            details={'kind': AttendanceAttestation.Kind.BREAK},
            dedupe_key=f'attestation:break:{entry.id}',
        )
    if policy.end_of_shift_attestation_required and not entry.attestations.filter(kind=AttendanceAttestation.Kind.END_OF_SHIFT).exists():
        create_notice(
            worker=worker, shift=entry.shift, entry=entry,
            notice_type=AttendanceNotice.Type.ATTESTATION_MISSING,
            severity=AttendanceNotice.Severity.INFO,
            details={'kind': AttendanceAttestation.Kind.END_OF_SHIFT},
            dedupe_key=f'attestation:end:{entry.id}',
        )
    return entry, policy


@transaction.atomic
def start_break(*, worker, request=None, method=AttendanceClockEvent.Method.WEB, now=None):
    now = now or timezone.now()
    entry = TimeEntry.objects.select_for_update().filter(worker=worker, clock_out__isnull=True).first()
    if not entry:
        raise ValidationError('Du bist aktuell nicht eingestempelt.')
    if entry.attendance_breaks.filter(status=AttendanceBreak.Status.RUNNING).exists():
        raise ValidationError('Es läuft bereits eine Pause.')
    record = entry.attendance_breaks.filter(status=AttendanceBreak.Status.PLANNED).order_by('created_at').first()
    if not record:
        policy = attendance_policy_for_shift(entry.shift)
        record = AttendanceBreak.objects.create(
            entry=entry,
            source=AttendanceBreak.Source.MANUAL if method != AttendanceClockEvent.Method.TERMINAL else AttendanceBreak.Source.TERMINAL,
            paid=bool(policy.default_break_paid),
        )
    record.status = AttendanceBreak.Status.RUNNING
    record.started_at = now
    record.started_by = getattr(request, 'user', None) if request and getattr(request.user, 'is_authenticated', False) else None
    record.save(update_fields=['status', 'started_at', 'started_by', 'updated_at'])
    _clock_event(entry=entry, kind=AttendanceClockEvent.Kind.BREAK_START, request=request, method=method)
    return record


@transaction.atomic
def end_break(*, worker, request=None, method=AttendanceClockEvent.Method.WEB, now=None):
    now = now or timezone.now()
    entry = TimeEntry.objects.select_for_update().filter(worker=worker, clock_out__isnull=True).first()
    if not entry:
        raise ValidationError('Du bist aktuell nicht eingestempelt.')
    record = entry.attendance_breaks.select_for_update().filter(status=AttendanceBreak.Status.RUNNING).order_by('-started_at').first()
    if not record:
        raise ValidationError('Es läuft aktuell keine Pause.')
    if record.started_at and now <= record.started_at:
        raise ValidationError('Das Pausenende ist ungültig.')
    record.status = AttendanceBreak.Status.COMPLETED
    record.ended_at = now
    record.ended_by = getattr(request, 'user', None) if request and getattr(request.user, 'is_authenticated', False) else None
    record.save(update_fields=['status', 'ended_at', 'ended_by', 'updated_at'])
    _clock_event(entry=entry, kind=AttendanceClockEvent.Kind.BREAK_END, request=request, method=method)
    policy = attendance_policy_for_shift(entry.shift)
    if record.scheduled_minutes and record.actual_minutes < record.scheduled_minutes:
        create_notice(
            worker=worker, shift=entry.shift, entry=entry, break_record=record,
            notice_type=AttendanceNotice.Type.BREAK_SHORT,
            severity=AttendanceNotice.Severity.INFO,
            value_minutes=record.scheduled_minutes - record.actual_minutes,
            details={'scheduled_minutes': record.scheduled_minutes, 'actual_minutes': record.actual_minutes},
            dedupe_key=f'break-short:{record.id}',
        )
    return record


def submit_attestation(*, entry, worker, kind, answers, note='', source=AttendanceAttestation.Source.SELF_SERVICE):
    if entry.worker_id != worker.id:
        raise ValidationError('Dieser Zeiteintrag gehört nicht zu deinem Profil.')
    if kind not in AttendanceAttestation.Kind.values:
        raise ValidationError('Ungültige Bestätigungsart.')
    obj, _ = AttendanceAttestation.objects.update_or_create(
        entry=entry,
        kind=kind,
        defaults={'worker': worker, 'answers': answers or {}, 'note': str(note or ''), 'source': source, 'submitted_at': timezone.now()},
    )
    AttendanceNotice.objects.filter(
        entry=entry,
        notice_type=AttendanceNotice.Type.ATTESTATION_MISSING,
        status__in=[AttendanceNotice.Status.OPEN, AttendanceNotice.Status.ACKNOWLEDGED],
        details__kind=kind,
    ).update(status=AttendanceNotice.Status.RESOLVED, resolved_at=timezone.now())
    return obj


def _has_open_absence(slot):
    try:
        from .absence_models import ShiftAbsenceCase
        return ShiftAbsenceCase.objects.filter(
            slot=slot,
            status__in=[
                ShiftAbsenceCase.Status.REPORTED,
                ShiftAbsenceCase.Status.COVERAGE_PENDING,
                ShiftAbsenceCase.Status.OFFERED,
                ShiftAbsenceCase.Status.MOVED_TO_OPEN,
            ],
        ).exists()
    except Exception:
        return False


def _create_no_show_coverage(slot):
    if _has_open_absence(slot):
        return
    try:
        from .absence_models import ShiftAbsenceCase
        from .absence_service import report_absence
        report_absence(
            shift=slot.shift,
            absent_worker=slot.worker,
            reported_by=None,
            kind=ShiftAbsenceCase.Kind.NO_SHOW,
            note='Automatisch aus Attendance Notice: kein Check-in.',
            source=ShiftAbsenceCase.Source.ATTENDANCE,
            slot_id=slot.id,
        )
    except Exception:
        return


def scan_attendance_notices(now=None):
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
        minutes_since_start = int((now - slot.shift.starts_at).total_seconds() // 60)
        if not entry and minutes_since_start >= int(policy.late_clock_in_grace_minutes or 0):
            _, was_created = AttendanceNotice.objects.get_or_create(
                dedupe_key=f'missed-in:{slot.worker_id}:{slot.shift_id}',
                defaults={
                    'worker': slot.worker,
                    'shift': slot.shift,
                    'notice_type': AttendanceNotice.Type.MISSED_CLOCK_IN,
                    'severity': AttendanceNotice.Severity.WARNING,
                    'value_minutes': max(0, minutes_since_start),
                },
            )
            created['missed_clock_in'] += int(was_created)
        if not entry and minutes_since_start >= int(policy.no_show_after_minutes or 0):
            _, was_created = AttendanceNotice.objects.get_or_create(
                dedupe_key=f'no-show:{slot.worker_id}:{slot.shift_id}',
                defaults={
                    'worker': slot.worker,
                    'shift': slot.shift,
                    'notice_type': AttendanceNotice.Type.NO_SHOW,
                    'severity': AttendanceNotice.Severity.CRITICAL,
                    'value_minutes': max(0, minutes_since_start),
                },
            )
            created['no_show'] += int(was_created)
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
