from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import Notification, Shift, TimeOffRequest, User, WorkerProfile
from .scheduler_completion_service import ensure_time_off_allowed
from .scheduling_models import WorkerPositionQualification
from .self_service_models import (
    AvailabilityPreferenceSeries,
    OpenShiftPolicy,
    OpenShiftRequest,
    SelfServiceSettings,
    ShiftCoverageRequest,
    TimeOffRequestDetail,
    TimeOffType,
    UserSelfServicePreference,
)
from .shift_slots import ShiftSlot


def _zone_for_shift(shift: Shift):
    try:
        return ZoneInfo(shift.location.timezone or 'Europe/Berlin')
    except Exception:
        return ZoneInfo('Europe/Berlin')


def _local_date(value, shift: Shift):
    return value.astimezone(_zone_for_shift(shift)).date()


def _local_time(value, shift: Shift):
    return value.astimezone(_zone_for_shift(shift)).time().replace(tzinfo=None)


def _date_matches_series(series: AvailabilityPreferenceSeries, day):
    if day < series.starts_on or day > series.ends_on:
        return False
    recurrence = series.recurrence
    if recurrence == AvailabilityPreferenceSeries.Recurrence.ONCE:
        return True
    if recurrence == AvailabilityPreferenceSeries.Recurrence.DAILY:
        return True
    weekdays = {int(value) for value in (series.weekdays or [series.starts_on.weekday()])}
    if day.weekday() not in weekdays:
        return False
    if recurrence == AvailabilityPreferenceSeries.Recurrence.WEEKLY:
        return True
    if recurrence == AvailabilityPreferenceSeries.Recurrence.TWO_WEEKS:
        return ((day - series.starts_on).days // 7) % 2 == 0
    return False


def _series_overlaps_shift(series: AvailabilityPreferenceSeries, shift: Shift):
    local_start = shift.starts_at.astimezone(_zone_for_shift(shift))
    local_end = shift.ends_at.astimezone(_zone_for_shift(shift))
    day = local_start.date()
    last_day = local_end.date()
    while day <= last_day:
        if _date_matches_series(series, day):
            if series.all_day:
                return True
            if not series.start_time or not series.end_time:
                return True
            day_start = datetime.combine(day, series.start_time, tzinfo=_zone_for_shift(shift))
            end_day = day if series.end_time > series.start_time else day + timedelta(days=1)
            day_end = datetime.combine(end_day, series.end_time, tzinfo=_zone_for_shift(shift))
            if day_start < local_end and day_end > local_start:
                return True
        day += timedelta(days=1)
    return False


def availability_preferences_for_shift(worker: WorkerProfile, shift: Shift):
    rows = AvailabilityPreferenceSeries.objects.filter(
        worker=worker,
        active=True,
        starts_on__lte=_local_date(shift.ends_at, shift),
        ends_on__gte=_local_date(shift.starts_at, shift),
    )
    preferred = False
    unavailable = False
    matched = []
    for series in rows:
        if not _series_overlaps_shift(series, shift):
            continue
        matched.append(series)
        if series.kind == AvailabilityPreferenceSeries.Kind.UNAVAILABLE:
            unavailable = True
        elif series.kind == AvailabilityPreferenceSeries.Kind.PREFERRED:
            preferred = True
    return {'unavailable': unavailable, 'preferred': preferred, 'series': matched}


def preferred_availability_bonus(worker: WorkerProfile, shift: Shift):
    return 150 if availability_preferences_for_shift(worker, shift)['preferred'] else 0


def recurring_unavailable(worker: WorkerProfile, shift: Shift):
    return availability_preferences_for_shift(worker, shift)['unavailable']


def validate_availability_series(series_data, *, actor: User, instance=None):
    settings = SelfServiceSettings.load()
    starts_on = series_data.get('starts_on', getattr(instance, 'starts_on', None))
    ends_on = series_data.get('ends_on', getattr(instance, 'ends_on', None))
    recurrence = series_data.get('recurrence', getattr(instance, 'recurrence', AvailabilityPreferenceSeries.Recurrence.ONCE))
    all_day = series_data.get('all_day', getattr(instance, 'all_day', True))
    start_time = series_data.get('start_time', getattr(instance, 'start_time', None))
    end_time = series_data.get('end_time', getattr(instance, 'end_time', None))
    weekdays = series_data.get('weekdays', getattr(instance, 'weekdays', [])) or []
    if not starts_on or not ends_on:
        raise ValidationError('Start- und Enddatum sind erforderlich.')
    if ends_on < starts_on:
        raise ValidationError('Enddatum darf nicht vor dem Startdatum liegen.')
    if ends_on > starts_on + timedelta(days=366):
        raise ValidationError('Wiederholungen dürfen maximal ein Jahr laufen.')
    if not all_day and (not start_time or not end_time):
        raise ValidationError('Für eine Teilzeit-Verfügbarkeit sind Start- und Endzeit erforderlich.')
    if recurrence in {AvailabilityPreferenceSeries.Recurrence.WEEKLY, AvailabilityPreferenceSeries.Recurrence.TWO_WEEKS}:
        if not weekdays:
            raise ValidationError('Für wöchentliche Wiederholungen muss mindestens ein Wochentag gewählt werden.')
        if any(int(day) < 0 or int(day) > 6 for day in weekdays):
            raise ValidationError('Wochentage müssen zwischen 0 (Montag) und 6 (Sonntag) liegen.')
    if actor.role == User.Role.WORKER:
        if not settings.availability_enabled:
            raise PermissionDenied('Mitarbeiter dürfen ihre Verfügbarkeit derzeit nicht ändern.')
        earliest = timezone.localdate() + timedelta(days=int(settings.availability_notice_days or 0))
        if starts_on < earliest:
            raise ValidationError(f'Verfügbarkeitsänderungen benötigen {settings.availability_notice_days} Tag(e) Vorlauf.')
    return True


def validate_series_change_cutoff(series: AvailabilityPreferenceSeries, actor: User):
    if actor.role != User.Role.WORKER:
        return
    settings = SelfServiceSettings.load()
    if not settings.availability_enabled:
        raise PermissionDenied('Mitarbeiter dürfen ihre Verfügbarkeit derzeit nicht ändern.')
    earliest = timezone.localdate() + timedelta(days=int(settings.availability_notice_days or 0))
    if series.starts_on < earliest:
        raise ValidationError(f'Diese Verfügbarkeit liegt innerhalb des {settings.availability_notice_days}-Tage-Vorlaufs.')


def worker_position_ids(worker: WorkerProfile):
    qualification_ids = WorkerPositionQualification.objects.filter(
        worker=worker,
        active=True,
    ).values_list('position_id', flat=True)
    assignment_ids = Shift.objects.filter(
        Q(slots__worker=worker, slots__status=ShiftSlot.Status.CLAIMED) | Q(worker=worker),
    ).exclude(status=Shift.Status.CANCELLED).values_list('position_id', flat=True)
    return {str(value) for value in qualification_ids} | {str(value) for value in assignment_ids}


def coworker_directory_for(user: User):
    settings = SelfServiceSettings.load()
    if user.role == User.Role.WORKER and settings.global_user_privacy:
        return {'visible': False, 'global_privacy': True, 'workers': []}
    workers = WorkerProfile.objects.filter(active=True, user__is_active=True).select_related('user').exclude(user=user)
    rows = []
    for worker in workers:
        pref, _ = UserSelfServicePreference.objects.get_or_create(user=worker.user)
        reveal_contact = user.role in {User.Role.ADMIN, User.Role.MANAGER} or not pref.hide_contact_info
        rows.append({
            'id': str(worker.id),
            'name': worker.user.get_full_name() or worker.user.email,
            'email': worker.user.email if reveal_contact else None,
            'phone': worker.user.phone if reveal_contact else None,
            'contact_hidden': not reveal_contact,
        })
    return {'visible': True, 'global_privacy': settings.global_user_privacy, 'workers': rows}


def team_schedule_for(user: User, *, starts_at, ends_at):
    settings = SelfServiceSettings.load()
    if user.role in {User.Role.ADMIN, User.Role.MANAGER}:
        qs = Shift.objects.filter(starts_at__lt=ends_at, ends_at__gt=starts_at).exclude(status=Shift.Status.CANCELLED)
    elif user.role == User.Role.WORKER:
        if settings.global_user_privacy or settings.team_schedule_visibility == SelfServiceSettings.TeamScheduleVisibility.NONE:
            return []
        qs = Shift.objects.filter(starts_at__lt=ends_at, ends_at__gt=starts_at).exclude(status=Shift.Status.CANCELLED)
        if settings.team_schedule_visibility == SelfServiceSettings.TeamScheduleVisibility.POSITIONS:
            qs = qs.filter(position_id__in=worker_position_ids(user.worker_profile))
    else:
        return []
    qs = qs.select_related('position', 'location').prefetch_related('slots__worker__user').distinct().order_by('starts_at')
    result = []
    for shift in qs:
        names = [slot.worker.user.get_full_name() or slot.worker.user.email for slot in shift.slots.all() if slot.status == ShiftSlot.Status.CLAIMED and slot.worker_id]
        result.append({
            'id': str(shift.id),
            'position': shift.position.name,
            'location': shift.location.name,
            'starts_at': shift.starts_at,
            'ends_at': shift.ends_at,
            'workers': names,
        })
    return result


def _hours_until_shift(shift: Shift):
    return (shift.starts_at - timezone.now()).total_seconds() / 3600


def _ensure_before_cutoff(shift: Shift, cutoff_hours: int, label: str):
    if shift.starts_at <= timezone.now():
        raise ValidationError('Bereits begonnene Schichten können nicht geändert werden.')
    if _hours_until_shift(shift) < int(cutoff_hours or 0):
        raise ValidationError(f'{label} ist nur bis {cutoff_hours} Stunde(n) vor Schichtbeginn möglich.')


def owned_slot(shift: Shift, worker: WorkerProfile, *, lock=False):
    qs = ShiftSlot.objects.filter(shift=shift, worker=worker, status=ShiftSlot.Status.CLAIMED)
    if lock:
        qs = qs.select_for_update()
    slot = qs.first()
    if not slot:
        raise ValidationError('Aktive eigene Schichtbelegung wurde nicht gefunden.')
    return slot


def validate_release(worker: WorkerProfile, shift: Shift):
    settings = SelfServiceSettings.load()
    if not settings.allow_shift_release:
        raise PermissionDenied('Schichtfreigabe ist für Mitarbeiter deaktiviert.')
    owned_slot(shift, worker)
    _ensure_before_cutoff(shift, settings.release_cutoff_hours, 'Freigeben')
    return True


def create_coverage_request(worker: WorkerProfile, *, shift: Shift, kind: str, offered_to=None, note=''):
    settings = SelfServiceSettings.load()
    owned_slot(shift, worker)
    if kind == ShiftCoverageRequest.Kind.DROP:
        if not settings.allow_shift_drop:
            raise PermissionDenied('Schichtabgabe ist deaktiviert.')
        _ensure_before_cutoff(shift, settings.drop_cutoff_hours, 'Abgeben')
    elif kind == ShiftCoverageRequest.Kind.SWAP:
        if settings.global_user_privacy:
            raise PermissionDenied('Schichttausch ist bei globalem Datenschutz deaktiviert.')
        if not settings.allow_shift_swap:
            raise PermissionDenied('Schichttausch ist deaktiviert.')
        _ensure_before_cutoff(shift, settings.swap_cutoff_hours, 'Tauschen')
    else:
        raise ValidationError('Ungültige Coverage-Art.')
    if offered_to and offered_to.id == worker.id:
        raise ValidationError('Eine Schicht kann nicht an dich selbst angeboten werden.')
    if kind == ShiftCoverageRequest.Kind.SWAP and not offered_to:
        raise ValidationError('Für einen Schichttausch muss ein Zielmitarbeiter gewählt werden.')
    if settings.global_user_privacy and kind == ShiftCoverageRequest.Kind.DROP:
        offered_to = None
    requires_review = settings.require_manager_review_swaps_drops or not offered_to
    status = ShiftCoverageRequest.Status.PENDING_REVIEW if requires_review else ShiftCoverageRequest.Status.PENDING_ACCEPTANCE
    obj = ShiftCoverageRequest.objects.create(
        kind=kind,
        shift=shift,
        requested_by=worker,
        offered_to=offered_to,
        status=status,
        note=str(note or '').strip(),
    )
    if offered_to and status == ShiftCoverageRequest.Status.PENDING_ACCEPTANCE:
        _notify(offered_to.user, 'coverage-request', 'Neue Schichtanfrage', f'{worker.user.get_full_name() or worker.user.email}: {shift.position.name}', '/schedule')
    else:
        _notify_managers('coverage-review', 'Coverage-Anfrage zur Prüfung', f'{worker.user.get_full_name() or worker.user.email}: {shift.position.name}')
    return obj


def _notify(user, kind, title, body, action_url='/schedule'):
    Notification.objects.create(user=user, kind=kind, title=title, body=body, action_url=action_url)


def _notify_managers(kind, title, body):
    for user in User.objects.filter(role__in=[User.Role.ADMIN, User.Role.MANAGER], is_active=True):
        _notify(user, kind, title, body, '/operations')


def review_coverage_request(obj: ShiftCoverageRequest, *, manager: User, approve: bool, offered_to=None):
    if obj.status != ShiftCoverageRequest.Status.PENDING_REVIEW:
        raise ValidationError('Diese Anfrage wartet nicht auf eine Manager-Prüfung.')
    if offered_to:
        obj.offered_to = offered_to
    if not approve:
        obj.status = ShiftCoverageRequest.Status.DENIED
        obj.reviewed_by = manager
        obj.reviewed_at = timezone.now()
        obj.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'offered_to', 'updated_at'])
        _notify(obj.requested_by.user, 'coverage-denied', 'Coverage-Anfrage abgelehnt', obj.shift.position.name)
        return obj
    if not obj.offered_to_id:
        raise ValidationError('Vor der Freigabe muss ein Zielmitarbeiter ausgewählt werden.')
    from .scheduling_rules import ensure_worker_eligible
    ensure_worker_eligible(obj.offered_to, obj.shift)
    obj.status = ShiftCoverageRequest.Status.PENDING_ACCEPTANCE
    obj.reviewed_by = manager
    obj.reviewed_at = timezone.now()
    obj.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'offered_to', 'updated_at'])
    _notify(obj.offered_to.user, 'coverage-request', 'Neue Schichtanfrage', f'{obj.requested_by.user.get_full_name() or obj.requested_by.user.email}: {obj.shift.position.name}')
    return obj


def cancel_coverage_request(obj: ShiftCoverageRequest, actor: User):
    if actor.id != obj.requested_by.user_id and actor.role not in {User.Role.ADMIN, User.Role.MANAGER}:
        raise PermissionDenied('Keine Berechtigung zum Zurückziehen dieser Anfrage.')
    if obj.status not in {ShiftCoverageRequest.Status.PENDING_REVIEW, ShiftCoverageRequest.Status.PENDING_ACCEPTANCE}:
        raise ValidationError('Diese Anfrage kann nicht mehr zurückgezogen werden.')
    obj.status = ShiftCoverageRequest.Status.CANCELED
    obj.save(update_fields=['status', 'updated_at'])
    return obj


@transaction.atomic
def accept_coverage_request(obj_id, *, recipient: WorkerProfile, offered_shift=None):
    obj = ShiftCoverageRequest.objects.select_for_update().select_related(
        'shift__position', 'shift__location', 'requested_by__user', 'offered_to__user'
    ).get(pk=obj_id)
    if obj.status != ShiftCoverageRequest.Status.PENDING_ACCEPTANCE:
        raise ValidationError('Diese Anfrage wartet nicht auf deine Annahme.')
    if obj.offered_to_id != recipient.id:
        raise PermissionDenied('Diese Anfrage ist einem anderen Mitarbeiter zugeordnet.')
    requester_slot = owned_slot(obj.shift, obj.requested_by, lock=True)
    from .scheduling_rules import ensure_worker_eligible
    from .shift_service import refresh_shift_state

    if obj.kind == ShiftCoverageRequest.Kind.DROP:
        ensure_worker_eligible(recipient, obj.shift)
        requester_slot.worker = recipient
        requester_slot.source = 'shift_drop'
        requester_slot.claimed_at = timezone.now()
        requester_slot.save(update_fields=['worker', 'source', 'claimed_at', 'updated_at'])
        refresh_shift_state(obj.shift)
    else:
        if not offered_shift:
            raise ValidationError('Für den Tausch muss eine eigene Gegenschicht ausgewählt werden.')
        recipient_slot = owned_slot(offered_shift, recipient, lock=True)
        if offered_shift.id == obj.shift_id:
            raise ValidationError('Die Gegenschicht muss eine andere Schicht sein.')
        # Ignore the two assignments that are being exchanged while validating the hypothetical schedule.
        ShiftSlot.objects.filter(pk__in=[requester_slot.pk, recipient_slot.pk]).update(status=ShiftSlot.Status.OPEN)
        try:
            ensure_worker_eligible(recipient, obj.shift)
            ensure_worker_eligible(obj.requested_by, offered_shift)
        except Exception:
            ShiftSlot.objects.filter(pk=requester_slot.pk).update(status=ShiftSlot.Status.CLAIMED)
            ShiftSlot.objects.filter(pk=recipient_slot.pk).update(status=ShiftSlot.Status.CLAIMED)
            raise
        requester_slot.status = ShiftSlot.Status.CLAIMED
        requester_slot.worker = recipient
        requester_slot.source = 'shift_swap'
        requester_slot.claimed_at = timezone.now()
        requester_slot.save(update_fields=['status', 'worker', 'source', 'claimed_at', 'updated_at'])
        recipient_slot.status = ShiftSlot.Status.CLAIMED
        recipient_slot.worker = obj.requested_by
        recipient_slot.source = 'shift_swap'
        recipient_slot.claimed_at = timezone.now()
        recipient_slot.save(update_fields=['status', 'worker', 'source', 'claimed_at', 'updated_at'])
        obj.offered_shift = offered_shift
        refresh_shift_state(obj.shift)
        refresh_shift_state(offered_shift)
    obj.status = ShiftCoverageRequest.Status.ACCEPTED
    obj.accepted_at = timezone.now()
    obj.save(update_fields=['status', 'accepted_at', 'offered_shift', 'updated_at'])
    _notify(obj.requested_by.user, 'coverage-accepted', 'Coverage-Anfrage angenommen', obj.shift.position.name)
    return obj


def decline_coverage_request(obj: ShiftCoverageRequest, recipient: WorkerProfile):
    if obj.offered_to_id != recipient.id:
        raise PermissionDenied('Diese Anfrage ist einem anderen Mitarbeiter zugeordnet.')
    if obj.status != ShiftCoverageRequest.Status.PENDING_ACCEPTANCE:
        raise ValidationError('Diese Anfrage kann nicht mehr abgelehnt werden.')
    obj.status = ShiftCoverageRequest.Status.DECLINED
    obj.save(update_fields=['status', 'updated_at'])
    _notify(obj.requested_by.user, 'coverage-declined', 'Coverage-Anfrage nicht angenommen', obj.shift.position.name)
    return obj


def open_shift_policy_for(shift: Shift):
    policy, _ = OpenShiftPolicy.objects.get_or_create(shift=shift)
    return policy


def worker_can_access_open_shift(worker: WorkerProfile, shift: Shift):
    if shift.status != Shift.Status.PUBLISHED or shift.starts_at <= timezone.now():
        return False, 'Schicht ist nicht offen.'
    if not shift.slots.filter(status=ShiftSlot.Status.OPEN, worker__isnull=True).exists():
        return False, 'Keine freien Plätze.'
    policy = open_shift_policy_for(shift)
    if policy.audience_mode == OpenShiftPolicy.AudienceMode.SELECTED and not policy.selected_workers.filter(pk=worker.pk).exists():
        return False, 'Schicht wurde dir nicht angeboten.'
    from .shift_service import ensure_worker_can_claim
    try:
        ensure_worker_can_claim(worker, shift)
    except Exception as exc:
        detail = getattr(exc, 'detail', str(exc))
        if isinstance(detail, list):
            detail = detail[0]
        return False, str(detail)
    return True, ''


def submit_open_shift_request(worker: WorkerProfile, shift: Shift, note=''):
    allowed, reason = worker_can_access_open_shift(worker, shift)
    if not allowed:
        raise ValidationError(reason)
    policy = open_shift_policy_for(shift)
    if not policy.require_approval:
        from .shift_service import claim_shift
        slot = claim_shift(shift.id, worker)
        request, _ = OpenShiftRequest.objects.update_or_create(
            shift=shift,
            worker=worker,
            defaults={
                'status': OpenShiftRequest.Status.ACCEPTED,
                'note': str(note or '').strip(),
                'decided_at': timezone.now(),
            },
        )
        return request, slot
    request, _ = OpenShiftRequest.objects.update_or_create(
        shift=shift,
        worker=worker,
        defaults={
            'status': OpenShiftRequest.Status.PENDING_APPROVAL,
            'note': str(note or '').strip(),
            'decided_by': None,
            'decided_at': None,
        },
    )
    _notify_managers('open-shift-bid', 'Neue OpenShift-Bewerbung', f'{worker.user.get_full_name() or worker.user.email}: {shift.position.name}')
    return request, None


@transaction.atomic
def decide_open_shift_request(request_id, *, manager: User, approve: bool):
    row = OpenShiftRequest.objects.select_for_update().select_related('shift__position', 'worker__user').get(pk=request_id)
    if row.status != OpenShiftRequest.Status.PENDING_APPROVAL:
        raise ValidationError('Diese Bewerbung wartet nicht auf eine Entscheidung.')
    if not approve:
        row.status = OpenShiftRequest.Status.DENIED
        row.decided_by = manager
        row.decided_at = timezone.now()
        row.save(update_fields=['status', 'decided_by', 'decided_at', 'updated_at'])
        _notify(row.worker.user, 'open-shift-denied', 'OpenShift nicht vergeben', row.shift.position.name)
        return row, None
    allowed, reason = worker_can_access_open_shift(row.worker, row.shift)
    if not allowed:
        raise ValidationError(reason)
    from .shift_service import claim_shift
    slot = claim_shift(row.shift_id, row.worker)
    row.status = OpenShiftRequest.Status.ACCEPTED
    row.decided_by = manager
    row.decided_at = timezone.now()
    row.save(update_fields=['status', 'decided_by', 'decided_at', 'updated_at'])
    OpenShiftRequest.objects.filter(
        shift=row.shift,
        status=OpenShiftRequest.Status.PENDING_APPROVAL,
    ).exclude(pk=row.pk).update(status=OpenShiftRequest.Status.DENIED, decided_by=manager, decided_at=timezone.now())
    _notify(row.worker.user, 'open-shift-approved', 'OpenShift genehmigt', row.shift.position.name)
    return row, slot


def cancel_open_shift_request(row: OpenShiftRequest, worker: WorkerProfile):
    if row.worker_id != worker.id:
        raise PermissionDenied('Diese Bewerbung gehört nicht zu deinem Profil.')
    if row.status != OpenShiftRequest.Status.PENDING_APPROVAL:
        raise ValidationError('Diese Bewerbung kann nicht mehr zurückgezogen werden.')
    row.status = OpenShiftRequest.Status.CANCELED
    row.save(update_fields=['status', 'updated_at'])
    return row


def validate_time_off_request(worker: WorkerProfile, *, time_off_type: TimeOffType, starts_on, ends_on, paid=False, paid_hours=None, all_day=True, start_time=None, end_time=None, actor=None):
    settings = SelfServiceSettings.load()
    if actor and actor.role == User.Role.WORKER and not settings.time_off_enabled:
        raise PermissionDenied('Abwesenheitsanfragen sind derzeit deaktiviert.')
    if ends_on < starts_on:
        raise ValidationError('Enddatum darf nicht vor dem Startdatum liegen.')
    today = timezone.localdate()
    if starts_on < today and not time_off_type.allow_past:
        raise ValidationError(f'„{time_off_type.name}“ kann nicht rückwirkend beantragt werden.')
    if actor and actor.role == User.Role.WORKER and not time_off_type.ignores_notice:
        earliest = today + timedelta(days=int(settings.time_off_notice_days or 0))
        if starts_on < earliest:
            raise ValidationError(f'Abwesenheitsanfragen benötigen {settings.time_off_notice_days} Tag(e) Vorlauf.')
    if paid and not time_off_type.allow_paid:
        raise ValidationError(f'„{time_off_type.name}“ kann nicht als bezahlt beantragt werden.')
    if not paid and not time_off_type.allow_unpaid:
        raise ValidationError(f'„{time_off_type.name}“ kann nicht als unbezahlt beantragt werden.')
    if not all_day:
        if starts_on != ends_on:
            raise ValidationError('Teiltag-Abwesenheit muss an einem einzelnen Tag liegen.')
        if not start_time or not end_time or end_time <= start_time:
            raise ValidationError('Für Teiltag-Abwesenheit ist ein gültiger Zeitbereich erforderlich.')
    if paid:
        if paid_hours is None:
            raise ValidationError('Bezahlte Stunden sind erforderlich.')
        days = (ends_on - starts_on).days + 1
        maximum = Decimal(settings.time_off_max_paid_hours_per_day) * days
        if Decimal(paid_hours) > maximum:
            raise ValidationError(f'Maximal {maximum} bezahlte Stunden sind für diesen Zeitraum zulässig.')
    ensure_time_off_allowed(worker, starts_on, ends_on)
    return True


@transaction.atomic
def create_detailed_time_off(worker: WorkerProfile, *, actor: User, time_off_type: TimeOffType, starts_on, ends_on, reason='', paid=False, paid_hours=None, all_day=True, start_time=None, end_time=None):
    validate_time_off_request(
        worker,
        time_off_type=time_off_type,
        starts_on=starts_on,
        ends_on=ends_on,
        paid=paid,
        paid_hours=paid_hours,
        all_day=all_day,
        start_time=start_time,
        end_time=end_time,
        actor=actor,
    )
    request = TimeOffRequest.objects.create(
        worker=worker,
        starts_on=starts_on,
        ends_on=ends_on,
        reason=str(reason or '').strip(),
    )
    TimeOffRequestDetail.objects.create(
        request=request,
        time_off_type=time_off_type,
        all_day=all_day,
        start_time=start_time if not all_day else None,
        end_time=end_time if not all_day else None,
        paid=bool(paid),
        paid_hours=paid_hours if paid else None,
    )
    _notify_managers('time-off-request', 'Neue Abwesenheitsanfrage', f'{worker.user.get_full_name() or worker.user.email}: {time_off_type.name}')
    return request
