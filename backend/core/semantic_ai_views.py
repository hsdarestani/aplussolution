from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import ClientCompany, Location, Position, Shift, ShiftImportPackage, WorkerProfile
from .native_cutover import approve_order
from .operational_notifications import notify_worker_shift_event
from .permissions import IsAdminOrManager
from .services import audit
from .shift_rules import schedule_groups_for_position_name
from .shift_slots import ShiftSlot


SYNTHETIC_MIGRATION_EMAIL_SUFFIX = '@sync.invalid'


def _worker_label(worker: WorkerProfile) -> str:
    return worker.user.get_full_name() or worker.user.email or worker.employee_number


def _directory() -> dict[str, list[dict[str, str]]]:
    clients = ClientCompany.objects.filter(active=True).order_by('name')
    locations = (
        Location.objects.filter(active=True, client__active=True)
        .select_related('client')
        .order_by('client__name', 'name')
    )
    workers = (
        WorkerProfile.objects.filter(active=True, user__is_active=True)
        .exclude(user__email__iendswith=SYNTHETIC_MIGRATION_EMAIL_SUFFIX)
        .select_related('user')
        .order_by('user__first_name', 'user__last_name', 'employee_number')
    )
    positions = Position.objects.filter(active=True).order_by('name')
    return {
        'clients': [
            {'id': str(item.id), 'name': item.name, 'address': item.address or ''}
            for item in clients
        ],
        'locations': [
            {
                'id': str(item.id),
                'client_id': str(item.client_id),
                'name': item.name,
                'address': item.address or '',
            }
            for item in locations
        ],
        'workers': [
            {
                'id': str(item.id),
                'name': _worker_label(item),
                'employee_number': item.employee_number or '',
            }
            for item in workers
        ],
        'positions': [
            {'id': str(item.id), 'name': item.name}
            for item in positions
        ],
    }


def _system_prompt() -> str:
    return f"""You are the A+ Solution workforce planning AI.

Understand the user's request semantically. The user may write in ANY language, with any wording, abbreviations, typos, prose, lists, copied WhatsApp messages, or mixed languages. Do not depend on fixed phrases, line formats, separators, or keyword templates.

You receive the authoritative A+ directory together with the request. Resolve every mentioned business entity to that directory by meaning and context:
- client_id must be an existing client id from directory.clients.
- location_id must be an existing location id belonging to that client.
- position_id must be an existing position id.
- assignment_worker_id must be an existing worker id when the request assigns a person; otherwise use an empty string for an OpenShift.
- Never invent IDs or create a customer/location/worker/position from free text.
- Distinguish a job/position such as Front Office from a person's name.
- If one employee is said to handle all shifts, repeat that worker id on every relevant shift.
- If the request is ambiguous about a directory entity, leave its id empty instead of guessing; keep a short human-readable hint in the matching *_text/name field so the admin can choose from a dropdown.
- Preserve only genuine notes in notes. Do not copy worker/client/location/position names into notes merely because you could not map them.
- Convert dates to YYYY-MM-DD and times to 24-hour HH:MM. Overnight shifts keep the same start date and an end time earlier than the start time; the server will roll the end into the next day.
- Expand distinct requested dates/times into distinct shift rows. count is the number of parallel staff slots for that exact row, not the total number of rows.
- Extract a contract/order/event number only when the user actually supplied one; otherwise contract_no is an empty string.

Current local date: {timezone.localdate().isoformat()}
Timezone: {settings.TIME_ZONE}

Return ONLY one JSON object with this shape:
{{
  "contract_no": "",
  "shifts": [
    {{
      "date": "YYYY-MM-DD",
      "start_time": "HH:MM",
      "end_time": "HH:MM",
      "count": 1,
      "client_id": "",
      "site_text": "",
      "location_id": "",
      "location_text": "",
      "position_id": "",
      "role": "",
      "assignment_worker_id": "",
      "assignment_worker_name": "",
      "site_address": "",
      "notes": ""
    }}
  ]
}}
"""


def _call_ai(text: str, directory: dict[str, list[dict[str, str]]], session=None) -> dict:
    if not settings.WIW_OPENAI_KEY:
        raise ValueError('WIW_OPENAI_KEY ist nicht konfiguriert.')
    client = session or requests.Session()
    user_payload = json.dumps(
        {'directory': directory, 'request': text},
        ensure_ascii=False,
        separators=(',', ':'),
    )
    response = client.post(
        'https://api.openai.com/v1/chat/completions',
        headers={
            'Authorization': f'Bearer {settings.WIW_OPENAI_KEY}',
            'Content-Type': 'application/json',
        },
        json={
            'model': settings.WIW_OPENAI_MODEL,
            'response_format': {'type': 'json_object'},
            'messages': [
                {'role': 'system', 'content': _system_prompt()},
                {'role': 'user', 'content': user_payload},
            ],
            'temperature': 0,
        },
        timeout=settings.WIW_HTTP_TIMEOUT,
    )
    if not response.ok:
        raise ValueError(f'AI-Auftragsanalyse fehlgeschlagen ({response.status_code}).')
    body = response.json()
    content = (((body.get('choices') or [{}])[0].get('message') or {}).get('content'))
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError) as exc:
        raise ValueError('Die AI hat kein gültiges JSON zurückgegeben.') from exc
    if not isinstance(parsed, dict):
        raise ValueError('Die AI-Antwort hat ein ungültiges Format.')
    return parsed


def _clean_ai_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_rows = payload.get('shifts') if isinstance(payload, dict) else None
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError('Die AI hat keine vollständige Schicht erkannt.')
    rows = []
    for index, raw in enumerate(raw_rows, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f'Schicht {index} ist ungültig.')
        date_value = str(raw.get('date') or '').strip()
        start_time = str(raw.get('start_time') or '').strip()
        end_time = str(raw.get('end_time') or '').strip()
        if not date_value or not start_time or not end_time:
            raise ValueError(f'Für Schicht {index} fehlen Datum oder Uhrzeit.')
        try:
            count = max(1, int(raw.get('count') or 1))
        except (TypeError, ValueError):
            count = 1
        rows.append({
            'date': date_value,
            'start_time': start_time,
            'end_time': end_time,
            'count': count,
            'client_id': str(raw.get('client_id') or '').strip(),
            'site_text': str(raw.get('site_text') or '').strip(),
            'location_id': str(raw.get('location_id') or '').strip(),
            'location_text': str(raw.get('location_text') or '').strip(),
            'position_id': str(raw.get('position_id') or '').strip(),
            'role': str(raw.get('role') or '').strip(),
            'assignment_worker_id': str(raw.get('assignment_worker_id') or '').strip(),
            'assignment_worker_name': str(raw.get('assignment_worker_name') or '').strip(),
            'site_address': str(raw.get('site_address') or '').strip(),
            'notes': str(raw.get('notes') or '').strip(),
        })
    return {
        'contract_no': str(payload.get('contract_no') or '').strip(),
        'shifts': rows,
    }


def _canonicalize_ids(parsed: dict[str, Any], *, strict: bool) -> dict[str, Any]:
    for index, item in enumerate(parsed.get('shifts') or [], start=1):
        client = None
        if item.get('client_id'):
            client = ClientCompany.objects.filter(pk=item['client_id'], active=True).first()
        if client:
            item['client_id'] = str(client.id)
            item['site_text'] = client.name
            if client.address:
                item['site_address'] = client.address
        else:
            item['client_id'] = ''
            if strict:
                raise ValueError(f'Bitte für Schicht {index} einen bestehenden Kunden auswählen.')

        location = None
        if client and item.get('location_id'):
            location = Location.objects.filter(
                pk=item['location_id'], client=client, active=True,
            ).first()
        if location:
            item['location_id'] = str(location.id)
            item['location_text'] = location.name
            if location.address:
                item['site_address'] = location.address
        else:
            item['location_id'] = ''
            if strict:
                raise ValueError(f'Bitte für Schicht {index} einen bestehenden Standort auswählen.')

        position = None
        if item.get('position_id'):
            position = Position.objects.filter(pk=item['position_id'], active=True).first()
        if not position and item.get('role'):
            # Admin edits in the review UI may change the visible role text. Exact
            # directory equality is safe and does not interpret the user's prose.
            position = Position.objects.filter(name__iexact=item['role'], active=True).first()
        if position:
            item['position_id'] = str(position.id)
            item['role'] = position.name
        else:
            item['position_id'] = ''
            if strict:
                raise ValueError(f'Bitte für Schicht {index} eine bestehende Position auswählen.')

        worker = None
        if item.get('assignment_worker_id'):
            worker = (
                WorkerProfile.objects.filter(
                    pk=item['assignment_worker_id'], active=True, user__is_active=True,
                )
                .exclude(user__email__iendswith=SYNTHETIC_MIGRATION_EMAIL_SUFFIX)
                .select_related('user')
                .first()
            )
        if worker:
            item['assignment_worker_id'] = str(worker.id)
            item['assignment_worker_name'] = _worker_label(worker)
        else:
            item['assignment_worker_id'] = ''
            item['assignment_worker_name'] = ''
    return parsed


def _selected_client_id(parsed: dict[str, Any]) -> str:
    ids = {
        str(item.get('client_id') or '')
        for item in parsed.get('shifts') or []
        if item.get('client_id')
    }
    if len(ids) != 1:
        raise ValueError('Ein AI-Auftrag muss genau einem bestehenden Kunden zugeordnet sein.')
    return next(iter(ids))


def _approval_payload_with_assignment_markers(parsed: dict[str, Any]) -> dict[str, Any]:
    """Protect named AI assignments from transient OpenShift fan-out.

    Native order creation publishes the shift before the semantic assignment step
    claims its slot. The existing OpenShift notifier recognises an ``Übernommen
    von NAME`` line as a direct assignment and suppresses broad employee fan-out.
    Add that line only to the internal approval copy; the real note is restored
    immediately afterwards and is the only text the user ever keeps on the shift.
    """
    approval = deepcopy(parsed)
    for row in approval.get('shifts') or []:
        if not str(row.get('assignment_worker_id') or '').strip():
            continue
        worker_name = str(row.get('assignment_worker_name') or '').strip()
        if not worker_name:
            continue
        genuine_note = str(row.get('notes') or '').strip()
        marker = f'Übernommen von {worker_name}'
        row['notes'] = f'{genuine_note}\n{marker}'.strip()
    return approval


def _assign_workers(result: dict[str, Any], reviewed_rows: list[dict[str, Any]]) -> int:
    package_id = result.get('package_id')
    if not package_id:
        return 0
    package = ShiftImportPackage.objects.filter(pk=package_id).first()
    if not package:
        return 0
    payload = dict(package.payload or {})
    created_rows = payload.get('shifts') if isinstance(payload.get('shifts'), list) else []
    assigned = 0

    with transaction.atomic():
        for reviewed, created in zip(reviewed_rows, created_rows):
            worker_id = str(reviewed.get('assignment_worker_id') or '').strip()
            shift_id = str(created.get('local_shift_id') or created.get('shift_id') or '').strip()
            if not shift_id:
                continue
            shift = Shift.objects.filter(pk=shift_id).select_related('position').prefetch_related('slots').first()
            if not shift:
                continue

            # Keep only the note the admin/user actually supplied. Internal order
            # IDs, implementation markers and "Managed by A+ Workforce" belong in
            # package/order metadata, never in the visible shift note.
            genuine_note = str(reviewed.get('notes') or '').strip()
            shift.notes = genuine_note
            if not shift.schedule_groups:
                shift.schedule_groups = schedule_groups_for_position_name(shift.position.name)
            shift.save(update_fields=['notes', 'schedule_groups', 'updated_at'])
            created['notes'] = genuine_note
            created['schedule_groups'] = list(shift.schedule_groups or [])

            if not worker_id:
                continue
            worker = (
                WorkerProfile.objects.filter(pk=worker_id, active=True, user__is_active=True)
                .select_related('user')
                .first()
            )
            if not worker:
                continue

            slot = shift.slots.filter(
                status=ShiftSlot.Status.OPEN, worker__isnull=True,
            ).order_by('created_at').first()
            if slot:
                slot.worker = worker
                slot.status = ShiftSlot.Status.CLAIMED
                slot.source = 'ai_semantic_assignment'
                slot.claimed_at = timezone.now()
                slot.confirmation_status = ShiftSlot.ConfirmationStatus.CONFIRMED
                slot.save(update_fields=[
                    'worker', 'status', 'source', 'claimed_at',
                    'confirmation_status', 'updated_at',
                ])

            remaining_open = shift.slots.filter(
                status=ShiftSlot.Status.OPEN, worker__isnull=True,
            ).exists()
            shift.is_open = remaining_open
            shift.status = Shift.Status.PUBLISHED if remaining_open else Shift.Status.CONFIRMED
            if not remaining_open and int(shift.required_count or 1) == 1:
                shift.worker = worker
            shift.save(update_fields=['is_open', 'status', 'worker', 'updated_at'])

            created['worker_id'] = str(worker.id)
            created['worker_name'] = _worker_label(worker)
            created['assignment_worker_id'] = str(worker.id)
            created['assignment_worker_name'] = _worker_label(worker)
            notify_worker_shift_event(worker.user, shift, 'Schicht zugewiesen', 'ai-semantic-assignment')
            assigned += 1

        # Notes / Zeitplan metadata are updated for every AI-created shift, even
        # when it remains an OpenShift, so always persist the package payload.
        package.payload = payload
        package.save(update_fields=['payload', 'updated_at'])
    return assigned


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def order_metadata(request):
    return Response(_directory())


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def order_parse(request):
    raw_text = str(request.data.get('text') or '').strip()
    if not raw_text:
        return Response({'detail': 'Kein Auftragstext übergeben.'}, status=400)
    try:
        directory = _directory()
        parsed = _clean_ai_payload(_call_ai(raw_text, directory))
        parsed = _canonicalize_ids(parsed, strict=False)
    except Exception as exc:
        return Response({'detail': str(exc)}, status=400)

    audit(request, 'order_automation.semantic_parsed', request.user, {
        'shift_count': len(parsed.get('shifts') or []),
        'mapped_clients': sum(bool(item.get('client_id')) for item in parsed.get('shifts') or []),
        'mapped_locations': sum(bool(item.get('location_id')) for item in parsed.get('shifts') or []),
        'mapped_workers': sum(bool(item.get('assignment_worker_id')) for item in parsed.get('shifts') or []),
    })
    return Response(parsed)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def order_approve(request):
    raw_text = str(request.data.get('raw_text') or '').strip()
    incoming = request.data.get('parsed') or {}
    try:
        parsed = _clean_ai_payload(incoming)
        parsed = _canonicalize_ids(parsed, strict=True)
        client_id = _selected_client_id(parsed)
        approval_payload = _approval_payload_with_assignment_markers(parsed)
        result = approve_order(approval_payload, raw_text, actor=request.user, client_id=client_id)
        assigned_count = _assign_workers(result, parsed['shifts'])
        result['assigned_count'] = assigned_count
        result['created_open_count'] = max(0, int(result.get('created_count') or 0) - assigned_count)
    except Exception as exc:
        return Response({'detail': str(exc)}, status=400)

    audit(request, 'order_automation.semantic_approved', request.user, result)
    return Response(result)
