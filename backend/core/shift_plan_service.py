import hashlib
import io
import json
import re
import unicodedata
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from pypdf import PdfReader

from .client_portal_access import get_client_portal_access
from .models import Shift, User
from .shift_plan_models import ShiftPlanAttachment, ShiftPlanDocument


PLAN_MAX_BYTES = 20 * 1024 * 1024
MAX_BULK_FILES = 50
AUTO_MATCH_THRESHOLD = 100

GERMAN_MONTHS = {
    'januar': 1,
    'februar': 2,
    'maerz': 3,
    'marz': 3,
    'april': 4,
    'mai': 5,
    'juni': 6,
    'juli': 7,
    'august': 8,
    'september': 9,
    'oktober': 10,
    'november': 11,
    'dezember': 12,
}

EVENT_PATTERNS = [
    re.compile(r'(?i)\bVA\.?\s*Nr\.?\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{2,})'),
    re.compile(r'(?i)\bKonferenz\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{2,})'),
    re.compile(
        r'(?i)\b(?:Event|Veranstaltung|Auftrag|Einsatz)\s*'
        r'(?:Nr\.?|Nummer|Number|No\.?|ID|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{2,})'
    ),
]
FULL_GERMAN_DATE = re.compile(
    r'(?i)\b(?:Mo|Di|Mi|Do|Fr|Sa|So)?\s*,?\s*(\d{1,2})\.\s*'
    r'(Januar|Februar|März|Maerz|Marz|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)'
    r'\s+(20\d{2})\b'
)
FILENAME_DATE = re.compile(r'(?<!\d)(\d{1,2})[._-](\d{1,2})[._-](20\d{2})(?!\d)')
SERVICE_WINDOW = re.compile(
    r'(?is)\b(?:Servicekraft|Logistiker|Mitarbeiter(?:in)?)\b.{0,260}?'
    r'(\d{1,2}:\d{2})\s*Uhr\s*bis\s*(\d{1,2}:\d{2})\s*Uhr'
)


def _ascii(value):
    return unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode('ascii')


def normalize_text(value):
    return ' '.join(re.findall(r'[a-z0-9]+', _ascii(value).lower()))


def normalize_identifier(value):
    return re.sub(r'[^a-z0-9]', '', _ascii(value).lower())


def _safe_event_value(value):
    raw = str(value or '').strip(' \t\r\n.,:;()[]{}')
    key = normalize_identifier(raw)
    if len(key) < 4:
        return ''
    # Avoid interpreting dates and times as event numbers.
    if re.fullmatch(r'\d{8}', key) or re.fullmatch(r'\d{4}', key):
        return ''
    return raw[:80]


def event_identifiers(text, filename=''):
    found = []
    seen = set()

    for source in (str(text or ''), Path(str(filename or '')).stem):
        for pattern in EVENT_PATTERNS:
            for match in pattern.finditer(source):
                raw = _safe_event_value(match.group(1))
                key = normalize_identifier(raw)
                if raw and key not in seen:
                    seen.add(key)
                    found.append(raw)

    # Event-plan filenames commonly start with the VA number, e.g.
    # "10719 30_09_2026.pdf". Only accept a standalone 4-10 digit token.
    stem = Path(str(filename or '')).stem
    for raw in re.findall(r'(?<!\d)(\d{4,10})(?!\d)', stem):
        value = _safe_event_value(raw)
        key = normalize_identifier(value)
        if value and key not in seen:
            seen.add(key)
            found.append(value)
    return found


def _page_date(text):
    head = str(text or '')[:350]
    match = FULL_GERMAN_DATE.search(head)
    if not match:
        return None
    day, month_name, year = match.groups()
    month = GERMAN_MONTHS.get(normalize_text(month_name).replace(' ', ''))
    if not month:
        return None
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def extract_event_dates(page_texts, filename=''):
    dates = []
    for text in page_texts:
        parsed = _page_date(text)
        if parsed and parsed not in dates:
            dates.append(parsed)
    if not dates:
        match = FILENAME_DATE.search(Path(str(filename or '')).stem)
        if match:
            try:
                dates.append(date(int(match.group(3)), int(match.group(2)), int(match.group(1))))
            except ValueError:
                pass
    return dates


def extract_service_windows(page_texts):
    windows = {}
    for text in page_texts:
        event_date = _page_date(text)
        if not event_date:
            continue
        key = event_date.isoformat()
        for match in SERVICE_WINDOW.finditer(text):
            pair = [match.group(1), match.group(2)]
            if pair not in windows.setdefault(key, []):
                windows[key].append(pair)
    return windows


def _read_pdf_text(raw):
    page_texts = []
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            result = reader.decrypt('')
            if not result:
                raise ValueError('Passwortgeschützte PDF-Dateien werden nicht unterstützt.')
        for page in reader.pages[:60]:
            try:
                page_texts.append(page.extract_text() or '')
            except Exception:
                page_texts.append('')
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('Die PDF-Datei konnte nicht gelesen werden.') from exc

    # PyMuPDF often recovers a text layer that pypdf cannot. This is not OCR.
    if len(normalize_text('\n'.join(page_texts))) < 20:
        try:
            import fitz

            recovered = []
            with fitz.open(stream=raw, filetype='pdf') as document:
                for page in document[:60]:
                    recovered.append(page.get_text('text') or '')
            if len(normalize_text('\n'.join(recovered))) > len(normalize_text('\n'.join(page_texts))):
                page_texts = recovered
        except Exception:
            pass
    return page_texts


def extract_pdf_payload(upload):
    if not upload:
        raise ValueError('Keine PDF-Datei erhalten.')
    name = Path(str(getattr(upload, 'name', '') or '')).name or 'Einsatzplan.pdf'
    if Path(name).suffix.lower() != '.pdf':
        raise ValueError('Nur PDF-Dateien sind erlaubt.')
    if int(getattr(upload, 'size', 0) or 0) > PLAN_MAX_BYTES:
        raise ValueError('Eine PDF-Datei darf maximal 20 MB groß sein.')

    try:
        upload.seek(0)
    except Exception:
        pass
    raw = upload.read()
    try:
        upload.seek(0)
    except Exception:
        pass

    if len(raw) > PLAN_MAX_BYTES:
        raise ValueError('Eine PDF-Datei darf maximal 20 MB groß sein.')
    if not raw.startswith(b'%PDF'):
        raise ValueError('Die Datei ist keine gültige PDF-Datei.')

    page_texts = _read_pdf_text(raw)
    full_text = '\n\n'.join(page_texts).strip()
    dates = extract_event_dates(page_texts, name)
    return {
        'raw': raw,
        'name': name,
        'checksum': hashlib.sha256(raw).hexdigest(),
        'page_texts': page_texts,
        'text': full_text,
        'event_numbers': event_identifiers(full_text, name),
        'event_dates': dates,
        'service_windows': extract_service_windows(page_texts),
    }


def _json_text(value):
    try:
        return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(value or '')


def shift_match_source(shift):
    parts = [
        shift.notes,
        shift.wiw_shift_id,
        _json_text(shift.wiw_payload),
        getattr(shift.order, 'title', '') if shift.order_id else '',
        getattr(shift.order, 'description', '') if shift.order_id else '',
        shift.client.name if shift.client_id else '',
        shift.location.name if shift.location_id else '',
        shift.location.address if shift.location_id else '',
        shift.position.name if shift.position_id else '',
    ]
    return '\n'.join(str(part or '') for part in parts)


def _identifier_present(source, value):
    raw = str(value or '').strip()
    if not raw:
        return False
    source_ascii = _ascii(source).lower()
    value_ascii = _ascii(raw).lower()
    if value_ascii.isdigit():
        return bool(re.search(rf'(?<!\d){re.escape(value_ascii)}(?!\d)', source_ascii))
    return normalize_identifier(value_ascii) in normalize_identifier(source_ascii)


def _note_similarity(shift_note, pdf_text):
    note = normalize_text(shift_note)
    full = normalize_text(pdf_text)
    if len(note) < 6:
        return 0, ''
    if len(note) >= 10 and note in full:
        return 45, 'Notiz wurde im Plan gefunden'

    # Compare only meaningful note tokens to the plan. Event numbers alone are
    # scored separately so they cannot inflate the note similarity.
    stop = {
        'event', 'veranstaltung', 'auftrag', 'einsatz', 'notiz', 'hinweis',
        'service', 'schicht', 'kunde', 'mitarbeiter', 'mitarbeiterin',
    }
    tokens = [token for token in note.split() if token not in stop and not token.isdigit()]
    if len(tokens) >= 2:
        present = sum(1 for token in tokens if token in full)
        overlap = present / len(tokens)
        if overlap >= 0.8:
            return 38, 'Notiz passt sehr gut zum Plan'
        if overlap >= 0.6:
            return 25, 'Notiz passt zum Plan'

    # Fallback for short free-text descriptions.
    plan_slice = full[:8000]
    ratio = SequenceMatcher(None, note[:600], plan_slice[:600]).ratio()
    if ratio >= 0.72:
        return 20, 'Notiz ist ähnlich zum Plan'
    return 0, ''


def _time_minutes(value):
    hour, minute = str(value).split(':', 1)
    return int(hour) * 60 + int(minute)


def score_shift_match(payload, shift):
    source = shift_match_source(shift)
    score = 0
    reasons = []
    event_match = False
    date_match = False
    time_match = False

    for event_number in payload.get('event_numbers') or []:
        if _identifier_present(source, event_number):
            score += 100
            event_match = True
            reasons.append(f'Event {event_number} stimmt überein')
            break

    local_start = timezone.localtime(shift.starts_at)
    local_end = timezone.localtime(shift.ends_at)
    shift_date = local_start.date()
    event_dates = payload.get('event_dates') or []
    if event_dates:
        if shift_date in event_dates:
            score += 35
            date_match = True
            reasons.append(f'Datum {shift_date:%d.%m.%Y} stimmt überein')
        else:
            score -= 70

    date_windows = (payload.get('service_windows') or {}).get(shift_date.isoformat(), [])
    if date_windows:
        start_minutes = local_start.hour * 60 + local_start.minute
        end_minutes = local_end.hour * 60 + local_end.minute
        for window_start, window_end in date_windows:
            try:
                if abs(start_minutes - _time_minutes(window_start)) <= 90 and abs(end_minutes - _time_minutes(window_end)) <= 120:
                    score += 25
                    time_match = True
                    reasons.append(f'Personalzeit {window_start} bis {window_end} passt')
                    break
            except Exception:
                continue

    pdf_text = payload.get('text') or ''
    location_name = normalize_text(shift.location.name if shift.location_id else '')
    location_address = normalize_text(shift.location.address if shift.location_id else '')
    normalized_pdf = normalize_text(pdf_text)
    if location_name and len(location_name) >= 5 and location_name in normalized_pdf:
        score += 15
        reasons.append('Einsatzort wurde im Plan gefunden')
    elif location_address and len(location_address) >= 8:
        address_tokens = [token for token in location_address.split() if len(token) >= 4]
        if address_tokens and sum(1 for token in address_tokens if token in normalized_pdf) / len(address_tokens) >= 0.6:
            score += 12
            reasons.append('Adresse passt zum Plan')

    note_points, note_reason = _note_similarity(shift.notes, pdf_text)
    score += note_points
    if note_reason:
        reasons.append(note_reason)

    # Event plans are allowed to map to several shifts/days, but when the PDF
    # contains explicit event dates an event-number match on another day is not
    # enough for automatic attachment.
    auto_eligible = bool(
        (event_match and (date_match or not event_dates))
        or (date_match and note_points >= 38 and score >= AUTO_MATCH_THRESHOLD)
    )
    return {
        'shift': shift,
        'score': max(0, score),
        'reason': ' · '.join(reasons)[:500],
        'event_match': event_match,
        'date_match': date_match,
        'time_match': time_match,
        'auto_eligible': auto_eligible,
    }


def _base_candidate_queryset():
    return Shift.objects.select_related('order', 'client', 'location', 'position').exclude(status=Shift.Status.CANCELLED)


def candidate_shifts_for_upload(user):
    qs = _base_candidate_queryset()
    if user.role in {User.Role.ADMIN, User.Role.MANAGER}:
        return qs
    if user.role == User.Role.CLIENT:
        access, company = get_client_portal_access(user)
        if access and access.read_only:
            return qs.none()
        qs = qs.filter(client=company)
        if access and access.location_scope_id:
            qs = qs.filter(location_id=access.location_scope_id)
        return qs
    return qs.none()


def can_view_shift_plan(user, shift):
    if user.role in {User.Role.ADMIN, User.Role.MANAGER}:
        return True
    if user.role == User.Role.CLIENT:
        access, company = get_client_portal_access(user)
        if shift.client_id != company.id:
            return False
        if access and access.location_scope_id and shift.location_id != access.location_scope_id:
            return False
        return True
    if user.role == User.Role.WORKER:
        try:
            worker = user.worker_profile
        except Exception:
            return False
        return shift.slots.filter(worker=worker, status='claimed').exists()
    return False


def can_upload_shift_plan(user, shift):
    if user.role in {User.Role.ADMIN, User.Role.MANAGER}:
        return True
    if user.role != User.Role.CLIENT:
        return False
    access, company = get_client_portal_access(user)
    if access and access.read_only:
        return False
    if shift.client_id != company.id:
        return False
    if access and access.location_scope_id and shift.location_id != access.location_scope_id:
        return False
    return True


def _candidate_queryset_for_payload(user, payload):
    qs = candidate_shifts_for_upload(user)
    dates = payload.get('event_dates') or []
    if dates:
        start = min(dates)
        end = max(dates)
        # Django evaluates __date using the active timezone. Europe/Berlin is the
        # production timezone, matching the event plans and schedule UI.
        qs = qs.filter(starts_at__date__gte=start, starts_at__date__lte=end)
    else:
        now = timezone.now()
        qs = qs.filter(starts_at__gte=now - timezone.timedelta(days=180), starts_at__lte=now + timezone.timedelta(days=365))
    return qs[:1500]


def rank_document_matches(user, payload):
    ranked = [score_shift_match(payload, shift) for shift in _candidate_queryset_for_payload(user, payload)]
    ranked.sort(key=lambda item: (-item['score'], item['shift'].starts_at, str(item['shift'].id)))
    return ranked


def shift_summary(shift):
    return {
        'id': str(shift.id),
        'client_name': shift.client.name,
        'location_name': shift.location.name,
        'position_name': shift.position.name,
        'starts_at': shift.starts_at,
        'ends_at': shift.ends_at,
        'notes': shift.notes or '',
    }


def document_payload(document):
    return {
        'id': str(document.id),
        'original_name': document.original_name,
        'event_numbers': document.extracted_event_numbers,
        'event_dates': document.extracted_event_dates,
        'created_at': document.created_at,
    }


@transaction.atomic
def save_plan_document(payload, user, client=None):
    document = ShiftPlanDocument.objects.filter(checksum=payload['checksum']).first()
    if document:
        return document, False

    document = ShiftPlanDocument(
        original_name=payload['name'][:255],
        checksum=payload['checksum'],
        extracted_event_numbers=payload.get('event_numbers') or [],
        extracted_event_dates=[value.isoformat() for value in payload.get('event_dates') or []],
        extracted_service_windows=payload.get('service_windows') or {},
        extracted_preview=(payload.get('text') or '')[:12000],
        client=client,
        uploaded_by=user,
    )
    document.file.save(payload['name'], ContentFile(payload['raw']), save=False)
    document.save()
    return document, True


def attach_document(document, shift, user, score=0, reason='', automatic=False):
    attachment, created = ShiftPlanAttachment.objects.get_or_create(
        shift=shift,
        document=document,
        defaults={
            'match_score': max(0, min(255, int(score or 0))),
            'match_reason': str(reason or '')[:500],
            'matched_automatically': bool(automatic),
            'attached_by': user,
        },
    )
    if not created and automatic and int(score or 0) > attachment.match_score:
        attachment.match_score = max(0, min(255, int(score or 0)))
        attachment.match_reason = str(reason or '')[:500]
        attachment.matched_automatically = True
        attachment.save(update_fields=['match_score', 'match_reason', 'matched_automatically'])
    return attachment, created


def process_bulk_pdf(upload, user):
    payload = extract_pdf_payload(upload)
    client = None
    if user.role == User.Role.CLIENT:
        _, client = get_client_portal_access(user)

    document, created_document = save_plan_document(payload, user, client=client)
    ranked = rank_document_matches(user, payload)

    automatic = [
        item for item in ranked
        if item['auto_eligible'] and item['score'] >= AUTO_MATCH_THRESHOLD
    ]

    attached = []
    for item in automatic:
        attachment, _ = attach_document(
            document,
            item['shift'],
            user,
            score=item['score'],
            reason=item['reason'],
            automatic=True,
        )
        attached.append({
            **shift_summary(item['shift']),
            'attachment_id': str(attachment.id),
            'score': item['score'],
            'reason': item['reason'],
        })

    candidates = [
        {
            **shift_summary(item['shift']),
            'score': item['score'],
            'reason': item['reason'],
        }
        for item in ranked[:5]
        if item['score'] > 0
    ]

    return {
        'document': document_payload(document),
        'created_document': created_document,
        'matched': attached,
        'candidates': candidates,
        'status': 'matched' if attached else 'needs_review',
    }
