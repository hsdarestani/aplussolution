import re

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .ai_shift_normalizer import deterministic_order_request, normalize_order_request
from .models import Shift, ShiftImportPackage, WorkerProfile
from .native_cutover import approve_order
from .native_workforce import package_shifts
from .operational_notifications import notify_worker_shift_event
from .order_automation import extract_request_id, fallback_request_id, normalize_name, parse_order_text, similarity
from .permissions import IsAdminOrManager
from .services import audit
from .shift_slots import ShiftSlot


_ASSIGNMENT_LINE_RE = re.compile(r'^\s*(?:übernommen|uebernommen)\s+von\s+([^\n,.;]+?)\s*$', re.I | re.M)
_PLACEHOLDER_EMPLOYEE_PREFIXES = ('LOCAL-', 'WIW-', 'AUTO-', 'TEMP-', 'MIG-')


def _assignment_from_note(notes: str) -> str:
    match = _ASSIGNMENT_LINE_RE.search(str(notes or ''))
    return match.group(1).strip() if match else ''


def _clean_assignment_note(notes: str) -> str:
    cleaned = _ASSIGNMENT_LINE_RE.sub('', str(notes or ''))
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


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


def _worker_label(worker: WorkerProfile) -> str:
    return worker.user.get_full_name() or worker.user.email or worker.employee_number


def _placeholder_email(email: str) -> bool:
    value = str(email or '').strip().lower()
    return not value or value.endswith('.invalid') or value.endswith('@example.com')


def _placeholder_employee_number(value: str) -> bool:
    number = str(value or '').strip().upper()
    return not number or number.startswith(_PLACEHOLDER_EMPLOYEE_PREFIXES)


def _worker_quality_score(worker: WorkerProfile, wanted: str, match_score: float) -> float:
    """Prefer the real/login worker when duplicate directory rows share a name.

    Duplicate WIW/local placeholders can have exactly the same display name as the
    employee account that is actually used in the app. Name similarity therefore
    cannot be the only deciding factor. Prefer operational identities: real email,
    completed onboarding, real employee number, an active push device and existing
    claimed-shift history. A near-identical real account can beat an exact shadow
    row, but only after candidates have already passed the name-similarity gate.
    """
    email = str(worker.user.email or '').strip()
    employee_number = str(worker.employee_number or '').strip()
    exact = normalize_name(wanted) == normalize_name(_worker_label(worker))
    has_push = any(bool(getattr(device, 'active', False)) for device in worker.user.push_devices.all())
    claimed_history = worker.shift_slots.filter(
        status=ShiftSlot.Status.CLAIMED,
        worker__isnull=False,
    ).count()

    score = match_score * 100.0
    score += 3.0 if exact else 0.0
    score += 35.0 if not _placeholder_email(email) else 0.0
    score += 18.0 if bool(worker.user.is_onboarded) else 0.0
    score += 12.0 if not _placeholder_employee_number(employee_number) else 0.0
    score += 6.0 if employee_number.isdigit() else 0.0
    score += 8.0 if has_push else 0.0
    score += min(12.0, claimed_history * 0.5)
    score += 4.0 if bool(worker.wiw_user_id) else 0.0
    return score


def _worker_by_name(name: str) -> WorkerProfile | None:
    wanted = str(name or '').strip()
    if not wanted:
        return None

    candidates: list[tuple[WorkerProfile, float]] = []
    workers = (
        WorkerProfile.objects.filter(active=True, user__is_active=True)
        .select_related('user')
        .prefetch_related('user__push_devices')
    )
    for worker in workers:
        score = similarity(wanted, _worker_label(worker))
        if score >= 0.72:
            candidates.append((worker, score))
    if not candidates:
        return None

    # Keep only identities close to the strongest name match, then use account
    # quality to pick the canonical/real worker among duplicate or typo variants.
    best_name_score = max(score for _, score in candidates)
    finalists = [item for item in candidates if item[1] >= max(0.72, best_name_score - 0.12)]
    ranked = sorted(
        finalists,
        key=lambda item: (
            _worker_quality_score(item[0], wanted, item[1]),
            -item[0].created_at.timestamp() if item[0].created_at else 0.0,
            str(item[0].id),
        ),
        reverse=True,
    )
    return ranked[0][0]


def _worker_by_id(worker_id: str) -> WorkerProfile | None:
    if not worker_id:
        return None
    return (
        WorkerProfile.objects.filter(pk=worker_id, active=True, user__is_active=True)
        .select_related('user')
        .first()
    )


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


def _prepare_named_assignments(
    parsed: dict,
    raw_text: str,
    *,
    embed_assignment_note: bool = False,
) -> tuple[dict, dict[str, WorkerProfile]]:
    night_name, other_name = _assignment_rules(raw_text)
    workers_by_id: dict[str, WorkerProfile] = {}

    for item in parsed.get('shifts') or []:
        notes = str(item.get('notes') or '').strip()
        note_name = _assignment_from_note(notes)
        explicit_worker_id = str(item.get('assignment_worker_id') or '').strip()
        explicit_worker_name = str(item.get('assignment_worker_name') or '').strip()
        assignment_worker_override = bool(item.get('assignment_worker_override'))

        worker = _worker_by_id(explicit_worker_id)
        name = explicit_worker_name or note_name
        if not worker:
            if not name and not assignment_worker_override:
                name = night_name if _is_night_shift(item) else other_name
            if name:
                worker = _worker_by_name(name)
        if not worker:
            if name:
                raise ValueError(f'Der Mitarbeiter „{name}“ wurde nicht eindeutig gefunden. Bitte Namen prüfen.')
            if assignment_worker_override:
                item['assignment_worker_id'] = ''
                item['assignment_worker_name'] = ''
                item['notes'] = _clean_assignment_note(notes)
            continue

        canonical_name = _worker_label(worker)
        workers_by_id[str(worker.id)] = worker
        item['assignment_worker_id'] = str(worker.id)
        item['assignment_worker_name'] = canonical_name

        # The parsed preview must never misuse the employee name as a public note.
        # During approval only, keep a short temporary line because the existing
        # OpenShift notification guard and post-create assignment step use it. The
        # line is removed again immediately after the real WorkerProfile is claimed.
        notes = _clean_assignment_note(notes)
        if embed_assignment_note:
            notes = (notes + f'\nÜbernommen von {canonical_name}').strip()
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
        cleaned_notes = _clean_assignment_note(shift.notes)
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
            payload_row['notes'] = _clean_assignment_note(str(payload_row.get('notes') or ''))
            payload_row['worker_id'] = str(worker.id)
            payload_row['worker_name'] = canonical_name = _worker_label(worker)
            payload_row['assignment_worker_id'] = str(worker.id)
            payload_row['assignment_worker_name'] = canonical_name

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
        result, _ = _prepare_named_assignments(result, raw_text, embed_assignment_note=False)
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
    incoming = request.data.get('parsed') or {}
    admin_reviewed = bool(request.data.get('admin_reviewed') or (incoming.get('admin_reviewed') if isinstance(incoming, dict) else False))
    parsed = normalize_order_request(raw_text, incoming)

    if admin_reviewed:
        # Once an admin has edited/deleted rows in the confirmation screen, the
        # reviewed rows become authoritative. Do not resurrect deleted rows from
        # the raw order text or reject the deliberate row count change.
        parsed['admin_reviewed'] = True
        parsed['expected_shift_count'] = len(parsed.get('shifts') or [])
        parsed['shift_count_mismatch'] = False

    if not parsed.get('shifts'):
        if admin_reviewed:
            return Response({'detail': 'Mindestens eine geprüfte Schicht muss zur Erstellung übrig bleiben.'}, status=400)
        fallback = deterministic_order_request(raw_text)
        if fallback:
            parsed = normalize_order_request(raw_text, fallback)
    try:
        if not admin_reviewed:
            _validate_roster_count(parsed)
        parsed, workers_by_id = _prepare_named_assignments(parsed, raw_text, embed_assignment_note=True)
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
