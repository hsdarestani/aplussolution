import re

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .ai_shift_normalizer import deterministic_order_request, normalize_order_request
from .models import Shift, ShiftImportPackage, WorkerProfile
from .native_cutover import approve_order
from .native_workforce import package_shifts
from .operational_notifications import notify_worker_shift_event
from .order_automation import extract_request_id, fallback_request_id, parse_order_text, similarity
from .permissions import IsAdminOrManager
from .services import audit
from .shift_slots import ShiftSlot


_ASSIGNMENT_LINE_RE = re.compile(r'^\s*(?:übernommen|uebernommen)\s+von\s+([^\n,.;]+?)\s*$', re.I | re.M)


def _assignment_from_note(notes: str) -> str:
    match = _ASSIGNMENT_LINE_RE.search(str(notes or ''))
    return match.group(1).strip() if match else ''


def _assignment_rules(raw_text: str) -> tuple[str, str]:
    text = str(raw_text or '')
    night = re.search(
        r'\bnachtdienst(?:e)?\b[^.\n]*?\bvon\s+([^\n,.;]+?)\s+(?:übernommen|uebernommen)\b',
        text,
        flags=re.I,
    )
    other = re.search(
        r'\balle\s+anderen\s+(?:dienste|schichten)\b[^.\n]*?\bvon\s+([^\n,.;]+?)\s+(?:übernommen|uebernommen)\b',
        text,
        flags=re.I,
    )
    return (
        night.group(1).strip() if night else '',
        other.group(1).strip() if other else '',
    )


def _is_night_shift(item: dict) -> bool:
    try:
        start_h, start_m = [int(value) for value in str(item.get('start_time') or '').split(':')[:2]]
        end_h, end_m = [int(value) for value in str(item.get('end_time') or '').split(':')[:2]]
    except (TypeError, ValueError):
        return False
    start = start_h * 60 + start_m
    end = end_h * 60 + end_m
    return end <= start or (start >= 20 * 60 and end <= 9 * 60)


def _worker_by_name(name: str) -> WorkerProfile | None:
    wanted = str(name or '').strip()
    if not wanted:
        return None
    best = None
    best_score = 0.72
    for worker in WorkerProfile.objects.filter(active=True, user__is_active=True).select_related('user'):
        label = worker.user.get_full_name() or worker.user.email or worker.employee_number
        score = similarity(wanted, label)
        if score >= best_score:
            best = worker
            best_score = score
    return best


def _validate_roster_count(parsed: dict) -> None:
    if not parsed.get('shift_count_mismatch'):
        return
    expected = int(parsed.get('expected_shift_count') or 0)
    actual = len(parsed.get('shifts') or [])
    raise ValueError(
        f'Im Text sind insgesamt {expected} einzelne Schichten angegeben, '
        f'aber die AI hat nur {actual} einzeln prüfbare Schichten erkannt. '
        'Bitte erneut analysieren oder die Datums-/Zeitliste eindeutiger angeben.'
    )


def _prepare_named_assignments(parsed: dict, raw_text: str) -> tuple[dict, dict[str, WorkerProfile]]:
    night_name, other_name = _assignment_rules(raw_text)
    workers_by_id: dict[str, WorkerProfile] = {}

    for item in parsed.get('shifts') or []:
        notes = str(item.get('notes') or '').strip()
        name = _assignment_from_note(notes)
        if not name:
            name = night_name if _is_night_shift(item) else other_name
        if not name:
            continue

        worker = _worker_by_name(name)
        if not worker:
            raise ValueError(f'Der Mitarbeiter „{name}“ wurde nicht eindeutig gefunden. Bitte Namen prüfen.')
        workers_by_id[str(worker.id)] = worker

        # Keep a human-readable assignment line until the shift is created. The
        # notification layer recognizes this line and therefore does not fan an
        # intended direct assignment out as an OpenShift to every employee.
        if not _assignment_from_note(notes):
            notes = (notes + f'\nÜbernommen von {worker.user.get_full_name() or name}').strip()
        item['notes'] = notes

    return parsed, workers_by_id


def _apply_named_assignments(result: dict, workers_by_id: dict[str, WorkerProfile]) -> int:
    package_id = result.get('package_id')
    if not package_id or not workers_by_id:
        return 0
    package = ShiftImportPackage.objects.filter(pk=package_id).first()
    if not package:
        return 0

    assigned = 0
    payload = dict(package.payload or {})
    payload_rows = payload.get('shifts') if isinstance(payload.get('shifts'), list) else []
    payload_by_id = {str(row.get('local_shift_id') or row.get('shift_id') or ''): row for row in payload_rows}

    for shift in package_shifts(package).select_related('worker__user').prefetch_related('slots'):
        name = _assignment_from_note(shift.notes)
        if not name:
            continue
        worker = _worker_by_name(name)
        if not worker or str(worker.id) not in workers_by_id:
            continue

        slot = shift.slots.filter(status=ShiftSlot.Status.OPEN, worker__isnull=True).order_by('created_at').first()
        if not slot:
            continue
        slot.worker = worker
        slot.status = ShiftSlot.Status.CLAIMED
        slot.source = 'ai_assignment'
        slot.claimed_at = timezone.now()
        slot.confirmation_status = ShiftSlot.ConfirmationStatus.CONFIRMED
        slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'confirmation_status', 'updated_at'])

        remaining_open = shift.slots.filter(status=ShiftSlot.Status.OPEN, worker__isnull=True).exists()
        cleaned_notes = _ASSIGNMENT_LINE_RE.sub('', str(shift.notes or '')).strip()
        updates = {
            'notes': cleaned_notes,
            'status': Shift.Status.PUBLISHED if remaining_open else Shift.Status.CONFIRMED,
            'is_open': remaining_open,
            'updated_at': timezone.now(),
        }
        if not remaining_open and int(shift.required_count or 1) == 1:
            updates['worker_id'] = worker.id
        Shift.objects.filter(pk=shift.pk).update(**updates)
        shift.notes = cleaned_notes
        shift.status = updates['status']
        shift.is_open = remaining_open
        if 'worker_id' in updates:
            shift.worker_id = worker.id

        payload_row = payload_by_id.get(str(shift.id))
        if payload_row is not None:
            payload_row['notes'] = _ASSIGNMENT_LINE_RE.sub('', str(payload_row.get('notes') or '')).strip()
            payload_row['worker_id'] = str(worker.id)
            payload_row['worker_name'] = worker.user.get_full_name() or worker.user.email

        notify_worker_shift_event(worker.user, shift, 'Schicht zugewiesen', 'ai-assignment')
        assigned += 1

    if assigned:
        package.payload = payload
        package.save(update_fields=['payload', 'updated_at'])
    return assigned


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def order_parse(request):
    raw_text = str(request.data.get('text') or '').strip()
    if not raw_text:
        return Response({'detail': 'Kein Auftragstext übergeben.'}, status=400)

    try:
        result = normalize_order_request(raw_text, parse_order_text(raw_text))
    except Exception as exc:
        # Explicit German shift instructions do not need to fail just because the
        # external AI provider is temporarily unavailable or interpreted fields
        # inconsistently. Deterministic parsing covers the common create-shift flow.
        result = deterministic_order_request(raw_text)
        if not result:
            return Response({'detail': str(exc)}, status=400)
        result = normalize_order_request(raw_text, result)

    if not result.get('shifts'):
        return Response({'detail': 'Im Text wurde keine vollständige Schicht erkannt.'}, status=400)
    try:
        _validate_roster_count(result)
        result, _ = _prepare_named_assignments(result, raw_text)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)

    contract_no = extract_request_id(raw_text, result)
    result['contract_no'] = contract_no
    result['request_id'] = contract_no or fallback_request_id(result, (result['shifts'][0].get('site_text') or ''))
    audit(request, 'order_automation.parsed', request.user, {
        'request_id': result.get('request_id'),
        'shift_count': sum(max(1, int(item.get('count') or 1)) for item in result.get('shifts', [])),
    })
    return Response(result)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def order_approve(request):
    raw_text = str(request.data.get('raw_text') or '').strip()
    parsed = normalize_order_request(raw_text, request.data.get('parsed') or {})
    if not parsed.get('shifts'):
        fallback = deterministic_order_request(raw_text)
        if fallback:
            parsed = normalize_order_request(raw_text, fallback)
    try:
        _validate_roster_count(parsed)
        parsed, workers_by_id = _prepare_named_assignments(parsed, raw_text)
        result = approve_order(
            parsed,
            raw_text,
            actor=request.user,
            client_id=request.data.get('client_id') or None,
        )
        assigned_count = _apply_named_assignments(result, workers_by_id)
        if assigned_count:
            result['assigned_count'] = assigned_count
            result['created_open_count'] = max(0, int(result.get('created_count') or 0) - assigned_count)
    except Exception as exc:
        return Response({'detail': str(exc)}, status=400)
    audit(request, 'order_automation.approved', request.user, result)
    return Response(result)
