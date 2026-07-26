import hashlib
import io
import json
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import (
    ClientCompany,
    Contract,
    ContractTemplate,
    Location,
    Notification,
    Position,
    Shift,
    ShiftImportPackage,
    ShiftImportRevision,
    User,
    WorkerProfile,
)
from .wiw import WhenIWorkClient, WhenIWorkError

REQUEST_PATTERNS = [
    r'(?:vertragsnummer|vertrags-nr\.?|vertrag\s*nr\.?|contract\s*no\.?)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9/\-_.]{2,})',
    r'(?:auftragsnummer|auftrags-nr\.?|auftrag\s*nr\.?|order\s*no\.?)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9/\-_.]{2,})',
    r'(?:veranstaltungsnummer|veranstaltungs-nr\.?|veranstaltung\s*nr\.?|event\s*no\.?)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9/\-_.]{2,})',
    r'(?:bestellnummer|bestell-nr\.?)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9/\-_.]{2,})',
]

CLIENT_CONTRACT_HTML = """
<h1>Einzelarbeitnehmerüberlassungsvertrag</h1>
<h2>Auftraggeber</h2>
{{ client_name }}<br/>{{ client_address }}
<h2>Personaldienstleister</h2>
{{ company_name }}<br/>{{ company_address }}
<h2>Einsatz</h2>
Vertragsnummer: {{ request_id }}<br/>Einsatzbeginn: {{ start_date }}<br/>Einsatzende: {{ end_date }}
"""


def normalize_name(value: Any) -> str:
    text = str(value or '').lower().strip()
    text = re.sub(r'\(\d+\)', '', text)
    text = re.sub(r'^\s*\d+\s*[-.)]?\s*', '', text)
    text = re.sub(r'[^a-z0-9äöüß\s]', ' ', text, flags=re.I)
    return re.sub(r'\s+', ' ', text).strip()


def similarity(left: str, right: str) -> float:
    a, b = normalize_name(left), normalize_name(right)
    if not a or not b:
        return 0.0
    if a == b or a in b or b in a:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def normalize_request_id(value: Any) -> str:
    value = re.sub(r'[^A-Z0-9\-/_\.]', '-', str(value or '').upper().strip())
    return re.sub(r'-+', '-', value).strip('-')[:120]


def extract_request_id(raw_text: str, parsed: dict | None = None) -> str:
    parsed = parsed or {}
    for key in ('contract_no', 'contract_number', 'order_no', 'auftrag_nr', 'veranstaltungs_nr', 'event_no', 'request_id'):
        candidate = normalize_request_id(parsed.get(key))
        if candidate and not re.match(r'^(REQ|AUTO)-', candidate, flags=re.I):
            return candidate
    for pattern in REQUEST_PATTERNS:
        match = re.search(pattern, raw_text or '', flags=re.I)
        if match:
            return normalize_request_id(match.group(1))
    return ''


def fallback_request_id(parsed: dict, client_hint: str = '') -> str:
    first = (parsed.get('shifts') or [{}])[0]
    basis = '|'.join(str(value or '') for value in (
        client_hint,
        first.get('site_text'),
        first.get('location_text'),
        first.get('date'),
        first.get('notes'),
    ))
    return 'AUTO-' + hashlib.md5(basis.encode('utf-8')).hexdigest()[:16].upper()


def payload_hash(parsed: dict, client_hint: str, request_id: str) -> str:
    payload = {'request_id': request_id, 'client': client_hint, 'shifts': parsed.get('shifts') or []}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _parse_local_datetime(day_value: Any, clock_value: Any) -> datetime:
    day_text = str(day_value or '').strip()
    clock_text = str(clock_value or '').strip()
    if not day_text or not clock_text:
        raise ValueError('Datum und Uhrzeit sind erforderlich.')
    combined = f'{day_text} {clock_text}'
    parsed = None
    for fmt in ('%Y-%m-%d %H:%M', '%d.%m.%Y %H:%M', '%Y-%m-%dT%H:%M'):
        try:
            parsed = datetime.strptime(combined, fmt)
            break
        except ValueError:
            continue
    if not parsed:
        raise ValueError(f'Ungültiges Datum/Uhrzeit: {combined}')
    return timezone.make_aware(parsed, timezone.get_current_timezone())


def _validate_parsed(payload: dict) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get('shifts'), list) or not payload['shifts']:
        raise ValueError('Die Auftragsanalyse enthält keine Schichten.')
    clean = {'contract_no': str(payload.get('contract_no') or ''), 'shifts': []}
    for index, shift in enumerate(payload['shifts'], start=1):
        if not isinstance(shift, dict):
            raise ValueError(f'Schicht {index} ist ungültig.')
        count = max(1, int(shift.get('count') or 1))
        start = _parse_local_datetime(shift.get('date'), shift.get('start_time'))
        end = _parse_local_datetime(shift.get('date'), shift.get('end_time'))
        if end <= start:
            end += timedelta(days=1)
        clean['shifts'].append({
            'role': str(shift.get('role') or 'Servicekraft').strip(),
            'date': start.date().isoformat(),
            'start_time': start.strftime('%H:%M'),
            'end_time': end.strftime('%H:%M'),
            'count': count,
            'location_text': str(shift.get('location_text') or '').strip(),
            'site_text': str(shift.get('site_text') or '').strip(),
            'site_address': str(shift.get('site_address') or '').strip(),
            'notes': str(shift.get('notes') or '').strip(),
        })
    return clean


def parse_order_text(text: str, session=None) -> dict:
    text = str(text or '').strip()
    if not text:
        raise ValueError('Kein Auftragstext übergeben.')
    if not settings.WIW_OPENAI_KEY:
        raise ValueError('WIW_OPENAI_KEY ist nicht konfiguriert.')
    prompt = """Du bist eine Workforce-Automation für A+ Solution GmbH. Analysiere den deutschen Auftragstext und zerlege ihn in einzelne Schichten. Extrahiere eine vorhandene Vertrags-, Auftrags- oder Veranstaltungsnummer exakt und erfinde keine Nummer. Antworte ausschließlich als JSON mit contract_no und shifts. Jede Schicht benötigt role, date (YYYY-MM-DD), start_time (HH:MM), end_time (HH:MM), count, location_text, site_text, site_address und notes."""
    client = session or requests.Session()
    response = client.post(
        'https://api.openai.com/v1/chat/completions',
        headers={'Authorization': f'Bearer {settings.WIW_OPENAI_KEY}', 'Content-Type': 'application/json'},
        json={
            'model': settings.WIW_OPENAI_MODEL,
            'response_format': {'type': 'json_object'},
            'messages': [{'role': 'system', 'content': prompt}, {'role': 'user', 'content': text}],
            'temperature': 0.1,
        },
        timeout=settings.WIW_HTTP_TIMEOUT,
    )
    if not response.ok:
        raise ValueError(f'OpenAI-Auftragsanalyse fehlgeschlagen ({response.status_code}).')
    body = response.json()
    content = (((body.get('choices') or [{}])[0].get('message') or {}).get('content'))
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError) as exc:
        raise ValueError('OpenAI hat kein gültiges JSON zurückgegeben.') from exc
    parsed = _validate_parsed(parsed)
    contract_key = extract_request_id(text, parsed)
    parsed['contract_no'] = contract_key
    parsed['request_id'] = contract_key or fallback_request_id(parsed)
    return parsed


def _best_model_match(name: str, queryset, attr='name', threshold=0.5):
    best = None
    score = threshold
    for item in queryset:
        current = similarity(name, getattr(item, attr, ''))
        if current >= score:
            best, score = item, current
    return best


def resolve_client(parsed: dict, client_id=None):
    if client_id:
        return ClientCompany.objects.get(pk=client_id)
    first = parsed['shifts'][0]
    hint = first.get('site_text') or first.get('location_text')
    client = _best_model_match(hint, ClientCompany.objects.filter(active=True), threshold=0.45)
    if client:
        return client
    location = _best_model_match(hint, Location.objects.select_related('client').filter(active=True), threshold=0.55)
    if location and location.client_id:
        return location.client
    name = str(hint or 'Unbekannter Auftraggeber').strip()
    address = first.get('site_address') or ''
    number = 'AUTO-' + hashlib.md5(normalize_name(name).encode()).hexdigest()[:12].upper()
    client, _ = ClientCompany.objects.get_or_create(customer_number=number, defaults={'name': name, 'address': address})
    if address and not client.address:
        client.address = address
        client.save(update_fields=['address', 'updated_at'])
    return client


def _extract_item(payload: dict, singular: str) -> dict:
    if not isinstance(payload, dict):
        return {}
    value = payload.get(singular)
    if isinstance(value, dict):
        return value
    value = payload.get('data')
    if isinstance(value, dict):
        return value
    return payload


def _wiw_match(name: str, items: list[dict], threshold=0.45):
    best = None
    best_score = threshold
    for item in items:
        score = similarity(name, item.get('name') or item.get('label') or '')
        if score >= best_score:
            best, best_score = item, score
    return best


def overlap_minutes(a_start, a_end, b_start, b_end) -> int:
    seconds = (min(a_end, b_end) - max(a_start, b_start)).total_seconds()
    return max(0, int(seconds // 60))


def _remote_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed.astimezone(timezone.get_current_timezone())
    except ValueError:
        return None


def _shift_ids(payload: dict | None) -> list[str]:
    if not payload:
        return []
    return [str(item.get('shift_id')) for item in payload.get('shifts', []) if item.get('shift_id')]


def approve_order(parsed: dict, raw_text: str, actor=None, client_id=None, wiw_client=None) -> dict:
    parsed = _validate_parsed(parsed)
    client_hint = str(client_id or parsed['shifts'][0].get('site_text') or '')
    request_id = extract_request_id(raw_text, parsed) or fallback_request_id(parsed, client_hint)
    source_hash = payload_hash(parsed, client_hint, request_id)
    existing = ShiftImportPackage.objects.filter(request_id=request_id).first()
    if existing and existing.source_hash == source_hash:
        return {'status': 'unchanged', 'request_id': request_id, 'package_id': str(existing.id)}

    client_company = resolve_client(parsed, client_id)
    wiw = wiw_client or WhenIWorkClient()
    locations = wiw.collection('locations', optional=True).items
    positions = wiw.collection('positions', optional=True).items
    sites = wiw.collection('sites', optional=True).items
    first_shift = parsed['shifts'][0]
    site_name = client_company.name
    site_address = client_company.address or first_shift.get('site_address') or ''
    site_match = _wiw_match(site_name, sites, 0.5)
    if site_match:
        site_id = str(site_match.get('id') or site_match.get('site_id') or '')
    else:
        created = _extract_item(wiw.post('/sites', {'name': site_name, 'address': site_address}), 'site')
        site_id = str(created.get('id') or created.get('site_id') or '')

    prepared = []
    for shift in parsed['shifts']:
        start = _parse_local_datetime(shift['date'], shift['start_time'])
        end = _parse_local_datetime(shift['date'], shift['end_time'])
        if end <= start:
            end += timedelta(days=1)
        location_match = _wiw_match(shift.get('location_text'), locations, 0.45)
        position_match = _wiw_match(shift.get('role'), positions, 0.45)
        location_id = str((location_match or {}).get('id') or (location_match or {}).get('location_id') or settings.WIW_DEFAULT_LOCATION_ID or '')
        position_id = str((position_match or {}).get('id') or (position_match or {}).get('position_id') or '')
        if not location_id:
            raise ValueError(f'Kein WIW-Standort für „{shift.get("location_text") or site_name}“ gefunden.')
        if not position_id:
            raise ValueError(f'Keine WIW-Position für „{shift.get("role")}“ gefunden.')
        prepared.append({**shift, 'start_dt': start, 'end_dt': end, 'location_id': location_id, 'position_id': position_id, 'site_id': site_id})

    created_remote = []
    try:
        for shift in prepared:
            for _ in range(shift['count']):
                payload = {
                    'location_id': int(shift['location_id']),
                    'position_id': int(shift['position_id']),
                    'site_id': int(shift['site_id']) if shift['site_id'] else None,
                    'start_time': shift['start_dt'].strftime('%Y-%m-%dT%H:%M:%S'),
                    'end_time': shift['end_dt'].strftime('%Y-%m-%dT%H:%M:%S'),
                    'notes': (shift.get('notes') + f'\nContract: {request_id}\nManaged by A+ Workforce').strip(),
                    'published': True,
                    'notice': True,
                    'notify': True,
                    'is_biddable': True,
                }
                result = _extract_item(wiw.post('/shifts', payload), 'shift')
                shift_id = result.get('id') or result.get('shift_id')
                if not shift_id:
                    raise WhenIWorkError('WIW hat keine Shift-ID zurückgegeben.')
                try:
                    wiw.post(f'/shifts/{shift_id}/notify', {'notice': True})
                except WhenIWorkError:
                    pass
                created_remote.append({
                    'shift_id': str(shift_id),
                    'date': shift['start_dt'].date().isoformat(),
                    'start_time': shift['start_dt'].strftime('%H:%M'),
                    'end_time': shift['end_dt'].strftime('%H:%M'),
                    'role': shift['role'],
                    'site_id': shift['site_id'],
                    'location_id': shift['location_id'],
                    'position_id': shift['position_id'],
                    'notes': shift.get('notes') or '',
                })
    except Exception:
        for item in created_remote:
            try:
                wiw.delete(f'/shifts/{item["shift_id"]}')
            except Exception:
                pass
        raise

    # Remove shifts from the previous version only after the new set exists.
    old_payload = existing.payload if existing else {}
    deleted_old = []
    failed_old = []
    for shift_id in _shift_ids(old_payload):
        try:
            wiw.delete(f'/shifts/{shift_id}')
            deleted_old.append(shift_id)
        except WhenIWorkError:
            failed_old.append(shift_id)

    # Remove external overlaps matching position and site/location, excluding newly created shifts.
    new_ids = {item['shift_id'] for item in created_remote}
    deleted_overlaps = []
    range_start = min(item['start_dt'] for item in prepared).date().isoformat()
    range_end = (max(item['end_dt'] for item in prepared).date() + timedelta(days=1)).isoformat()
    remote_shifts = wiw.collection('shifts', params={'start': range_start, 'end': range_end}, optional=True).items
    for remote in remote_shifts:
        remote_id = str(remote.get('id') or remote.get('shift_id') or '')
        if not remote_id or remote_id in new_ids or remote_id in set(_shift_ids(old_payload)):
            continue
        remote_start = _remote_datetime(remote.get('start_time') or remote.get('start'))
        remote_end = _remote_datetime(remote.get('end_time') or remote.get('end'))
        if not remote_start or not remote_end:
            continue
        for target in prepared:
            same_position = not remote.get('position_id') or str(remote.get('position_id')) == str(target['position_id'])
            same_place = (target['site_id'] and str(remote.get('site_id') or '') == str(target['site_id'])) or str(remote.get('location_id') or '') == str(target['location_id'])
            if same_position and same_place and overlap_minutes(target['start_dt'], target['end_dt'], remote_start, remote_end) >= 15:
                try:
                    wiw.delete(f'/shifts/{remote_id}')
                    deleted_overlaps.append(remote_id)
                except WhenIWorkError:
                    pass
                break

    first_start = min(item['start_dt'] for item in prepared)
    last_end = max(item['end_dt'] for item in prepared)
    saved_payload = {
        'request_id': request_id,
        'contract_no': extract_request_id(raw_text, parsed),
        'site_name': site_name,
        'site_address': site_address,
        'client_type': 'company',
        'first_shift_time': first_start.isoformat(),
        'first_shift_end_time': last_end.isoformat(),
        'source_hash': source_hash,
        'deleted_old_shift_ids': deleted_old,
        'failed_delete_shift_ids': failed_old,
        'external_deleted_shift_ids': deleted_overlaps,
        'shifts': created_remote,
    }
    with transaction.atomic():
        package, created = ShiftImportPackage.objects.update_or_create(
            request_id=request_id,
            defaults={
                'client': client_company,
                'site_name': site_name,
                'site_address': site_address,
                'first_shift_time': first_start,
                'first_shift_end_time': last_end,
                'raw_text': raw_text,
                'source_hash': source_hash,
                'payload': saved_payload,
                'status': ShiftImportPackage.Status.PENDING,
                'created_by': actor,
            },
        )
        version = (package.revisions.order_by('-version').values_list('version', flat=True).first() or 0) + 1
        ShiftImportRevision.objects.create(
            package=package,
            version=version,
            action='created' if created else 'updated',
            old_shift_ids=_shift_ids(old_payload),
            new_shift_ids=list(new_ids),
            old_payload=old_payload or {},
            new_payload=saved_payload,
        )
        # Keep the local app immediately usable while the regular WIW sync catches up.
        local_location = Location.objects.filter(wiw_site_id=site_id).first() or Location.objects.filter(client=client_company).first()
        if not local_location:
            local_location = Location.objects.create(client=client_company, name=site_name, address=site_address or site_name, wiw_site_id=site_id or None)
        for item in created_remote:
            position = Position.objects.filter(wiw_position_id=item['position_id']).first() or Position.objects.filter(name__iexact=item['role']).first()
            if not position:
                position = Position.objects.create(name=item['role'], wiw_position_id=item['position_id'])
            start = _parse_local_datetime(item['date'], item['start_time'])
            end = _parse_local_datetime(item['date'], item['end_time'])
            if end <= start:
                end += timedelta(days=1)
            Shift.objects.update_or_create(
                wiw_shift_id=item['shift_id'],
                defaults={
                    'client': client_company,
                    'location': local_location,
                    'position': position,
                    'starts_at': start,
                    'ends_at': end,
                    'status': Shift.Status.PUBLISHED,
                    'is_open': True,
                    'notes': item['notes'],
                    'wiw_payload': item,
                    'wiw_synced_at': timezone.now(),
                },
            )
    return {
        'status': 'ok',
        'action': 'created' if created else 'updated',
        'version': version,
        'request_id': request_id,
        'package_id': str(package.id),
        'created_count': len(created_remote),
        'deleted_old_shift_ids': deleted_old,
        'external_deleted_shift_ids': deleted_overlaps,
        'failed_delete_shift_ids': failed_old,
    }


def seed_client_contract_template() -> ContractTemplate:
    template, _ = ContractTemplate.objects.get_or_create(
        slug='einzelarbeitnehmerueberlassung',
        defaults={
            'name': 'Einzelarbeitnehmerüberlassungsvertrag',
            'kind': ContractTemplate.Kind.CLIENT_AUEV,
            'audience': ContractTemplate.Audience.CLIENT,
            'version': 'A+ 2026.1',
            'schema': {'signature_roles': ['client', 'employer']},
            'html_template': CLIENT_CONTRACT_HTML,
            'source_format': ContractTemplate.SourceFormat.HTML,
            'requires_signature': True,
            'required_document': False,
        },
    )
    return template


def _employee_rows(package: ShiftImportPackage):
    rows = []
    local_shifts = Shift.objects.filter(wiw_shift_id__in=_shift_ids(package.payload)).select_related('worker__user', 'position').order_by('starts_at')
    for shift in local_shifts:
        if not shift.worker_id:
            continue
        master = getattr(shift.worker, 'master_data', None)
        birth_date = (master.data or {}).get('birth_date', '') if master else ''
        rows.append([
            shift.worker.user.get_full_name() or shift.worker.user.email,
            birth_date or '–',
            shift.starts_at.astimezone().strftime('%d.%m.%Y %H:%M'),
            shift.ends_at.astimezone().strftime('%d.%m.%Y %H:%M'),
            shift.position.name,
        ])
    return rows


def build_client_contract_pdf(package: ShiftImportPackage) -> bytes:
    rows = _employee_rows(package)
    if not rows:
        raise ValueError('Für die Vertragsgenerierung muss mindestens ein Mitarbeiter einer Schicht zugeteilt sein.')
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=15 * mm, bottomMargin=15 * mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='CenteredTitle', parent=styles['Title'], alignment=TA_CENTER, fontSize=16, leading=20, spaceAfter=14))
    styles.add(ParagraphStyle(name='Clause', parent=styles['BodyText'], fontSize=9, leading=13, spaceAfter=8))
    story = [Paragraph('Einzelarbeitnehmerüberlassungsvertrag', styles['CenteredTitle'])]
    story += [
        Paragraph(f'<b>Auftraggeber:</b> {package.client.name}<br/>{package.client.address or package.site_address}', styles['Clause']),
        Paragraph(f'<b>Personaldienstleister:</b> {settings.COMPANY_NAME}<br/>{settings.COMPANY_ADDRESS}', styles['Clause']),
        Paragraph('Zwischen den Parteien wird folgender Arbeitnehmerüberlassungsvertrag geschlossen:', styles['Clause']),
        Paragraph('<b>§ 1 Erlaubnis zur Arbeitnehmerüberlassung</b>', styles['Heading3']),
        Paragraph(f'Der Personaldienstleister erklärt, im Besitz einer Erlaubnis zur Arbeitnehmerüberlassung zu sein, erteilt durch {settings.AUEG_LICENSE_AUTHORITY or "die zuständige Bundesagentur für Arbeit"} am {settings.AUEG_LICENSE_DATE or "–"}.', styles['Clause']),
        Paragraph('<b>§ 2 Einsatz und Konkretisierung</b>', styles['Heading3']),
        Paragraph(f'Der Einsatz erfolgt auf Grundlage des Auftrags {package.request_id}. Die nachfolgend genannten Arbeitnehmer werden vor Einsatzbeginn konkretisiert.', styles['Clause']),
    ]
    table_data = [['Mitarbeiter', 'Geburtsdatum', 'Beginn', 'Ende', 'Tätigkeit'], *rows]
    table = Table(table_data, colWidths=[52 * mm, 25 * mm, 35 * mm, 35 * mm, 33 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#102a63')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.35, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f7fb')]),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    story += [table, PageBreak()]
    story += [
        Paragraph('<b>§ 3 Vergütung und Arbeitszeit</b>', styles['Heading3']),
        Paragraph('Die Überlassungsvergütung richtet sich nach der tatsächlichen Arbeitszeit der eingesetzten Arbeitnehmer sowie den zwischen den Parteien vereinbarten Konditionen.', styles['Clause']),
        Paragraph('<b>§ 4 Arbeitsschutz</b>', styles['Heading3']),
        Paragraph('Auftraggeber und Personaldienstleister erfüllen ihre gesetzlichen Pflichten zum Arbeits- und Gesundheitsschutz. Der Auftraggeber unterweist die eingesetzten Arbeitnehmer vor Tätigkeitsbeginn.', styles['Clause']),
        Paragraph('<b>§ 5 Laufzeit</b>', styles['Heading3']),
        Paragraph(f'Dieser Einzelarbeitnehmerüberlassungsvertrag gilt für den Zeitraum {package.first_shift_time:%d.%m.%Y} bis {(package.first_shift_end_time or package.first_shift_time):%d.%m.%Y}.', styles['Clause']),
        Spacer(1, 25 * mm),
        Table([
            ['_____________________________', '_____________________________'],
            ['Auftraggeber', 'A+ Solution GmbH'],
            ['Ort, Datum, Unterschrift', 'Ort, Datum, Unterschrift'],
        ], colWidths=[85 * mm, 85 * mm], style=TableStyle([('FONTSIZE', (0, 0), (-1, -1), 9), ('VALIGN', (0, 0), (-1, -1), 'TOP')])),
    ]
    doc.build(story)
    return buffer.getvalue()


def generate_client_contract(package: ShiftImportPackage, actor=None) -> Contract:
    template = seed_client_contract_template()
    pdf_bytes = build_client_contract_pdf(package)
    contract = package.contract or Contract(
        template=template,
        client=package.client,
        title=f'Einzelarbeitnehmerüberlassungsvertrag {package.request_id}',
        source_system='wiw',
        created_by=actor,
    )
    contract.template = template
    contract.client = package.client
    contract.starts_on = package.first_shift_time.date()
    contract.ends_on = (package.first_shift_end_time or package.first_shift_time).date()
    contract.reminder_date = max(timezone.localdate(), contract.starts_on - timedelta(days=1))
    contract.variables = {
        'request_id': package.request_id,
        'client_name': package.client.name,
        'client_address': package.client.address,
        'start_date': contract.starts_on.isoformat(),
        'end_date': contract.ends_on.isoformat(),
        'shift_ids': _shift_ids(package.payload),
    }
    contract.data_snapshot = contract.variables
    contract.generated_at = timezone.now()
    contract.status = Contract.Status.READY
    contract.pdf.save(f'auev-{package.request_id}.pdf', ContentFile(pdf_bytes), save=False)
    contract.save()
    package.contract = contract
    package.pdf.save(f'auev-{package.request_id}.pdf', ContentFile(pdf_bytes), save=False)
    package.status = ShiftImportPackage.Status.GENERATED
    package.save(update_fields=['contract', 'pdf', 'status', 'updated_at'])
    recipients = User.objects.filter(role__in=[User.Role.ADMIN, User.Role.MANAGER], is_active=True)
    recipients = recipients | package.client.contacts.filter(is_active=True)
    for user in recipients.distinct():
        Notification.objects.get_or_create(
            user=user,
            kind=f'client-contract-generated-{package.id}',
            defaults={'title': 'Kundenvertrag erstellt', 'body': contract.title, 'action_url': '/contracts'},
        )
    return contract


def generate_due_client_contracts(now=None) -> dict:
    now = now or timezone.now()
    packages = ShiftImportPackage.objects.filter(
        status=ShiftImportPackage.Status.PENDING,
        first_shift_time__lte=now + timedelta(hours=24),
        first_shift_time__gte=now - timedelta(days=1),
        client__isnull=False,
    )
    generated, skipped, errors = 0, 0, []
    for package in packages:
        try:
            generate_client_contract(package)
            generated += 1
        except ValueError as exc:
            skipped += 1
            errors.append({'package': str(package.id), 'error': str(exc)})
    return {'generated': generated, 'skipped': skipped, 'errors': errors}


def sync_packages_from_local_shifts(start_date: date, end_date: date, actor=None) -> dict:
    start_dt = timezone.make_aware(datetime.combine(start_date, time.min), timezone.get_current_timezone())
    end_dt = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min), timezone.get_current_timezone())
    shifts = Shift.objects.filter(starts_at__gte=start_dt, starts_at__lt=end_dt, wiw_shift_id__isnull=False).select_related('client', 'location', 'position', 'worker__user')
    grouped: dict[str, list[Shift]] = {}
    for shift in shifts:
        key = f'{shift.client_id}|{shift.starts_at.astimezone().date().isoformat()}'
        grouped.setdefault(key, []).append(shift)
    created = updated = unchanged = 0
    for rows in grouped.values():
        rows.sort(key=lambda item: item.starts_at)
        first = rows[0]
        request_id = f'SYNC-{first.client.customer_number}-{first.starts_at.astimezone().date().isoformat()}'[:120]
        payload = {
            'request_id': request_id,
            'site_name': first.client.name,
            'site_address': first.client.address,
            'client_type': 'company',
            'first_shift_time': first.starts_at.isoformat(),
            'first_shift_end_time': max(row.ends_at for row in rows).isoformat(),
            'shifts': [{
                'shift_id': row.wiw_shift_id,
                'date': row.starts_at.astimezone().date().isoformat(),
                'start_time': row.starts_at.astimezone().strftime('%H:%M'),
                'end_time': row.ends_at.astimezone().strftime('%H:%M'),
                'role': row.position.name,
                'employee_name': row.worker.user.get_full_name() if row.worker_id else 'Unassigned',
                'location_id': row.location.wiw_location_id,
                'site_id': row.location.wiw_site_id,
                'position_id': row.position.wiw_position_id,
            } for row in rows],
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        existing = ShiftImportPackage.objects.filter(request_id=request_id).first()
        if existing and existing.source_hash == digest:
            unchanged += 1
            continue
        package, was_created = ShiftImportPackage.objects.update_or_create(
            request_id=request_id,
            defaults={
                'client': first.client,
                'site_name': first.client.name,
                'site_address': first.client.address,
                'first_shift_time': first.starts_at,
                'first_shift_end_time': max(row.ends_at for row in rows),
                'source_hash': digest,
                'payload': payload,
                'status': ShiftImportPackage.Status.PENDING,
                'created_by': actor,
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1
    return {'status': 'ok', 'created': created, 'updated': updated, 'unchanged': unchanged, 'total_customer_packages': len(grouped)}
