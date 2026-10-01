import hashlib
import io
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfgen import canvas

from .models import (
    AuevSetting,
    ClientOrder,
    Contract,
    Location,
    Notification,
    Position,
    Shift,
    ShiftImportPackage,
    ShiftImportRevision,
    TimeEntry,
    User,
    WorkerProfile,
    WorkingTimeAccountRecord,
    WorkingTimeSetting,
    WorkingTimeSyncLog,
)
from .operational_notifications import notify_open_shift_available
from .order_automation import (
    _best_model_match,
    _parse_local_datetime,
    _validate_parsed,
    extract_request_id,
    fallback_request_id,
    payload_hash,
    resolve_client,
    seed_client_contract_template,
)
from .shift_slots import ShiftSlot
from .working_time import dec, ensure_settings, iter_months

TWO = Decimal('0.01')


def _package_local_shift_ids(payload: dict | None) -> list[str]:
    if not payload:
        return []
    result = []
    for item in payload.get('shifts', []):
        value = item.get('local_shift_id')
        if value:
            result.append(str(value))
    return result


def _package_legacy_wiw_ids(payload: dict | None) -> list[str]:
    if not payload:
        return []
    result = []
    for item in payload.get('shifts', []):
        if item.get('local_shift_id'):
            continue
        value = item.get('shift_id')
        if value:
            result.append(str(value))
    return result


def package_shifts(package: ShiftImportPackage):
    local_ids = _package_local_shift_ids(package.payload)
    legacy_ids = _package_legacy_wiw_ids(package.payload)
    query = Q(pk__in=local_ids)
    if legacy_ids:
        query |= Q(wiw_shift_id__in=legacy_ids)
    if not local_ids and not legacy_ids:
        return Shift.objects.none()
    return Shift.objects.filter(query).distinct()


def _resolve_location(client, shift_data):
    hint = str(shift_data.get('location_text') or shift_data.get('site_text') or client.name).strip()
    address = str(shift_data.get('site_address') or client.address or hint).strip()
    candidates = Location.objects.filter(active=True).filter(Q(client=client) | Q(client__isnull=True))
    exact = candidates.filter(name__iexact=hint).first()
    location = exact or _best_model_match(hint, candidates, threshold=0.55)
    if location and location.client_id in (None, client.id):
        if location.client_id is None:
            location.client = client
            location.save(update_fields=['client', 'updated_at'])
        return location
    return Location.objects.create(client=client, name=hint or client.name, address=address or hint or client.name)


def _resolve_position(role):
    name = str(role or 'Servicekraft').strip() or 'Servicekraft'
    exact = Position.objects.filter(name__iexact=name).first()
    if exact:
        if not exact.active:
            exact.active = True
            exact.save(update_fields=['active', 'updated_at'])
        return exact
    matched = _best_model_match(name, Position.objects.filter(active=True), threshold=0.72)
    return matched or Position.objects.create(name=name)


def _old_package_shifts_are_replaceable(package):
    rows = package_shifts(package).prefetch_related('slots')
    for shift in rows:
        if shift.time_entries.exists():
            return False, 'Mindestens eine bestehende Schicht hat bereits Zeiterfassungen.'
        if shift.slots.filter(status=ShiftSlot.Status.CLAIMED, worker__isnull=False).exists() or shift.worker_id:
            return False, 'Mindestens eine bestehende Schicht ist bereits besetzt.'
    return True, ''


def approve_order(parsed: dict, raw_text: str, actor=None, client_id=None) -> dict:
    """Approve parsed demand entirely inside A+ Workforce; no WIW write/read occurs."""
    parsed = _validate_parsed(parsed)
    client_hint = str(client_id or parsed['shifts'][0].get('site_text') or '')
    request_id = extract_request_id(raw_text, parsed) or fallback_request_id(parsed, client_hint)
    source_hash = payload_hash(parsed, client_hint, request_id)

    with transaction.atomic():
        existing = ShiftImportPackage.objects.select_for_update().filter(request_id=request_id).first()
        if existing and existing.source_hash == source_hash:
            return {
                'status': 'unchanged',
                'source': 'aplus',
                'request_id': request_id,
                'package_id': str(existing.id),
            }
        if existing:
            replaceable, reason = _old_package_shifts_are_replaceable(existing)
            if not replaceable:
                raise ValueError(
                    f'Der Auftrag kann nicht automatisch ersetzt werden: {reason} '
                    'Bitte die bereits laufende Planung direkt im Dienstplan ändern.'
                )

        client = resolve_client(parsed, client_id)
        prepared = []
        for item in parsed['shifts']:
            start = _parse_local_datetime(item['date'], item['start_time'])
            end = _parse_local_datetime(item['date'], item['end_time'])
            if end <= start:
                end += timedelta(days=1)
            prepared.append({
                **item,
                'start_dt': start,
                'end_dt': end,
                'location': _resolve_location(client, item),
                'position': _resolve_position(item.get('role')),
            })

        first_start = min(item['start_dt'] for item in prepared)
        last_end = max(item['end_dt'] for item in prepared)
        requested_staff = sum(max(1, int(item.get('count') or 1)) for item in prepared)
        functions = list(dict.fromkeys(item['position'].name for item in prepared))

        order = None
        if existing:
            order_id = (existing.payload or {}).get('order_id')
            if order_id:
                order = ClientOrder.objects.filter(pk=order_id).first()
        if not order:
            order = ClientOrder()
        order.client = client
        order.title = f'Auftrag {request_id}'
        order.description = raw_text
        order.location = prepared[0]['location']
        order.starts_at = first_start
        order.ends_at = last_end
        order.requested_staff = requested_staff
        order.functions = functions
        order.status = ClientOrder.Status.CONFIRMED
        if not order.created_by_id:
            order.created_by = actor
        order.save()

        old_payload = dict(existing.payload or {}) if existing else {}
        old_ids = _package_local_shift_ids(old_payload) or _package_legacy_wiw_ids(old_payload)
        if existing:
            package_shifts(existing).delete()

        now = timezone.now()
        created_shifts = []
        for item in prepared:
            notes = str(item.get('notes') or '').strip()
            notes = (notes + f'\nAuftrag: {request_id}\nManaged by A+ Workforce').strip()
            shift = Shift.objects.create(
                order=order,
                client=client,
                location=item['location'],
                position=item['position'],
                starts_at=item['start_dt'],
                ends_at=item['end_dt'],
                break_minutes=0,
                status=Shift.Status.PUBLISHED,
                is_open=True,
                notes=notes,
                required_count=max(1, int(item.get('count') or 1)),
                published_at=now,
            )
            created_shifts.append({
                'shift_id': str(shift.id),
                'local_shift_id': str(shift.id),
                'date': item['start_dt'].date().isoformat(),
                'start_time': item['start_dt'].strftime('%H:%M'),
                'end_time': item['end_dt'].strftime('%H:%M'),
                'role': item['position'].name,
                'location_id': str(item['location'].id),
                'location_name': item['location'].name,
                'position_id': str(item['position'].id),
                'required_count': shift.required_count,
                'notes': str(item.get('notes') or ''),
            })

        saved_payload = {
            'source_system': 'aplus',
            'request_id': request_id,
            'contract_no': extract_request_id(raw_text, parsed),
            'order_id': str(order.id),
            'site_name': client.name,
            'site_address': client.address or prepared[0]['location'].address,
            'client_type': 'company',
            'first_shift_time': first_start.isoformat(),
            'first_shift_end_time': last_end.isoformat(),
            'source_hash': source_hash,
            'shifts': created_shifts,
        }
        package, created = ShiftImportPackage.objects.update_or_create(
            request_id=request_id,
            defaults={
                'client': client,
                'site_name': client.name,
                'site_address': client.address or prepared[0]['location'].address,
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
            old_shift_ids=old_ids,
            new_shift_ids=[item['local_shift_id'] for item in created_shifts],
            old_payload=old_payload,
            new_payload=saved_payload,
        )

    for item in created_shifts:
        created_shift = Shift.objects.filter(pk=item['local_shift_id']).first()
        if created_shift:
            notify_open_shift_available(created_shift, 'ai-order')

    return {
        'status': 'ok',
        'source': 'aplus',
        'action': 'created' if created else 'updated',
        'version': version,
        'request_id': request_id,
        'package_id': str(package.id),
        'order_id': str(order.id),
        'shift_count': len(created_shifts),
        'created_count': requested_staff,
    }


def _claimed_workers(shift):
    slots = list(
        shift.slots.filter(status=ShiftSlot.Status.CLAIMED, worker__isnull=False)
        .select_related('worker__user')
        .order_by('created_at')
    )
    if slots:
        return [slot.worker for slot in slots]
    return [shift.worker] if shift.worker_id else []


AUEV_FALLBACKS = {
    'permit_date': date(2024, 4, 15),
    'framework_date': date(2024, 8, 26),
    'effective_date': None,
    'required_qualification': 'Serviceerfahrung in der Gastronomie',
    'intended_activity': 'Servicetätigkeiten – Eventcatering',
}


def _format_person_date(value):
    if not value:
        return '–'
    if hasattr(value, 'strftime'):
        return value.strftime('%d.%m.%Y')
    raw = str(value).strip()
    for fmt in ('%d.%m.%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(raw[:10], fmt).strftime('%d.%m.%Y')
        except ValueError:
            pass
    return raw


def _employee_rows(package: ShiftImportPackage):
    rows = []
    for shift in package_shifts(package).select_related('position', 'worker__user').prefetch_related('slots__worker__user').order_by('starts_at'):
        for worker in _claimed_workers(shift):
            master = getattr(worker, 'master_data', None)
            birth_date = _format_person_date((master.data or {}).get('birth_date', '') if master else '')
            last_name = (worker.user.last_name or '').strip()
            first_name = (worker.user.first_name or '').strip()
            if last_name or first_name:
                employee = ', '.join(value for value in (last_name, first_name) if value)
            else:
                employee = worker.user.get_full_name() or worker.user.email
            rows.append({
                'employee': f'{employee}, {birth_date}',
                'start': timezone.localtime(shift.starts_at).strftime('%H:%M'),
                'end': timezone.localtime(shift.ends_at).strftime('%H:%M'),
                'date': timezone.localtime(shift.starts_at).strftime('%d.%m.%Y'),
                'activity': shift.position.name,
            })
    return rows


def _auev_values(package: ShiftImportPackage):
    default_row = AuevSetting.objects.filter(client__isnull=True).order_by('created_at').first()
    client_row = AuevSetting.objects.filter(client=package.client).first() if package.client_id else None

    def pick(field):
        client_value = getattr(client_row, field, None) if client_row else None
        if client_value not in (None, ''):
            return client_value
        default_value = getattr(default_row, field, None) if default_row else None
        if default_value not in (None, ''):
            return default_value
        return AUEV_FALLBACKS[field]

    effective_date = pick('effective_date') or timezone.localtime(package.first_shift_time).date()
    return {
        'permit_date': _format_person_date(pick('permit_date')),
        'framework_date': _format_person_date(pick('framework_date')),
        'effective_date': _format_person_date(effective_date),
        'required_qualification': str(pick('required_qualification') or AUEV_FALLBACKS['required_qualification']),
        'intended_activity': str(pick('intended_activity') or AUEV_FALLBACKS['intended_activity']),
    }


def _fit_font_size(text, width, preferred=8.5, minimum=5.0, font='Helvetica'):
    size = preferred
    value = str(text or '')
    while size > minimum and pdfmetrics.stringWidth(value, font, size) > width:
        size -= 0.25
    return max(size, minimum)


def _draw_top(c, x, top_baseline, text, size=8.5, font='Helvetica'):
    c.setFont(font, size)
    c.setFillColor(colors.black)
    c.drawString(x, A4[1] - top_baseline, str(text))


def _draw_fitted_top(c, x, top_baseline, width, text, preferred=8.5, minimum=5.0, font='Helvetica'):
    value = str(text or '').replace('\n', ', ').strip()
    size = _fit_font_size(value, width, preferred, minimum, font)
    _draw_top(c, x, top_baseline, value, size=size, font=font)


def _draw_underlined(c, x, top_baseline, text, size=8.5):
    _draw_top(c, x, top_baseline, text, size=size)
    width = pdfmetrics.stringWidth(text, 'Helvetica', size)
    y = A4[1] - top_baseline - 1.6
    c.setLineWidth(0.45)
    c.line(x, y, x + width, y)


def build_client_contract_pdf(package: ShiftImportPackage) -> bytes:
    rows = _employee_rows(package)
    if not rows:
        raise ValueError('Für die Vertragsgenerierung muss mindestens ein Mitarbeiter einer Schicht zugeteilt sein.')
    if len(rows) > 10:
        raise ValueError('Die aktuelle ANÜ Vorlage bietet Platz für maximal 10 Mitarbeiter pro Vertrag.')

    values = _auev_values(package)
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4, pageCompression=1)
    c.setTitle(f'Einzelarbeitnehmerüberlassungsvertrag {package.request_id}')

    client_line = package.client.name if package.client_id else package.site_name
    client_address = package.client.address if package.client_id else package.site_address
    if client_address:
        client_line = f'{client_line}, {client_address}'
    client_line = f'{client_line} (Auftraggeber)'

    # Page 1 follows the supplied legal sample in wording, spacing and table geometry.
    _draw_top(c, 78, 142, 'Anhang 1: Einzelarbeitnehmerüberlassungsvertrag', size=11.2, font='Helvetica-Bold')
    _draw_top(c, 78, 164, 'Zwischen', size=8.5)
    _draw_fitted_top(c, 78, 174, 480, client_line, preferred=8.5, minimum=5.4)
    _draw_top(c, 78, 185, 'und', size=8.5)
    _draw_top(c, 78, 206, 'A+ Solution GmbH, Carl-Sonnenschein Straße 57, 65936 Frankfurt am Main (Personaldienstleister)', size=8.5)
    _draw_top(c, 78, 227, 'wird folgender Arbeitnehmerüberlassungsvertrag geschlossen:', size=8.5)

    _draw_top(c, 78, 248, '§ 1 Erlaubnis zur Arbeitnehmerüberlassung', size=8.5, font='Helvetica-Bold')
    _draw_top(c, 78, 261, 'Der Personaldienstleister erklärt, im Besitz einer befristeten Erlaubnis zur Arbeitnehmerüberlassung zu sein,', size=8.5)
    _draw_top(c, 78, 274, 'zuletzt erteilt und nicht widerrufen von der Bundesagentur für Arbeit, Agentur für Arbeit Düsseldorf am', size=8.5)
    _draw_top(c, 78, 287, f"{values['permit_date']} in Düsseldorf.", size=8.5)

    _draw_top(c, 78, 306, '§ 2 Rahmenvereinbarung', size=8.5, font='Helvetica-Bold')
    _draw_top(c, 78, 319, 'Die Rahmenvereinbarung zur Arbeitnehmerüberlassung vom', size=8.5)
    _draw_top(c, 350, 319, values['framework_date'], size=8.5)
    _draw_top(c, 403, 319, 'zwischen Auftraggeber und Perso-', size=8.5)
    _draw_top(c, 78, 332, 'naldienstleister findet auf diesen Arbeitnehmerüberlassungsvertrag Anwendung.', size=8.5)

    _draw_top(c, 78, 353, '§ 3 Gegenstand des Vertrages / Überlassungsbedingungen', size=8.5, font='Helvetica-Bold')
    _draw_top(c, 78, 366, 'Der Personaldienstleister überlässt mit Wirkung zum', size=8.5)
    _draw_top(c, 311, 366, values['effective_date'], size=8.5)
    _draw_top(c, 364, 366, 'an den Auftraggeber folgende Zeitarbeitneh-', size=8.5)
    _draw_top(c, 78, 379, 'mer an den in § 2 Absatz 2 der Rahmenvereinbarung festgelegten Betrieb.', size=8.5)

    _draw_underlined(c, 96, 400, 'Erforderliche Qualifikation:', size=8.5)
    _draw_fitted_top(c, 290, 400, 268, values['required_qualification'], preferred=8.5, minimum=5.5)
    _draw_underlined(c, 96, 426, 'Vorgesehene Tätigkeit:', size=8.5)
    _draw_fitted_top(c, 290, 426, 268, values['intended_activity'], preferred=8.5, minimum=5.5)

    _draw_underlined(c, 96, 517, 'Betriebliche Arbeitszeit in Stunden/MA:', size=8.5)
    _draw_top(c, 290, 517, '(S.u.)', size=8.5)

    x_lines = [78.48, 297.84, 340.32, 382.80, 446.64, 503.04, 559.68]
    y_lines_top = [527.28, 546.72, 566.16, 585.60, 605.28, 624.72, 644.16, 663.60, 683.28, 702.72, 722.16, 741.84]
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.45)
    for x in x_lines:
        c.line(x, A4[1] - y_lines_top[0], x, A4[1] - y_lines_top[-1])
    for y in y_lines_top:
        c.line(x_lines[0], A4[1] - y, x_lines[-1], A4[1] - y)

    _draw_top(c, 83.8, 545, 'Name, Vorname, Geburtsdatum', size=8.0, font='Helvetica-Bold')
    _draw_top(c, 303.1, 545, 'Start', size=8.0, font='Helvetica-Bold')
    _draw_top(c, 345.6, 545, 'Ende', size=8.0, font='Helvetica-Bold')
    _draw_top(c, 388.1, 545, 'Datum', size=8.0, font='Helvetica-Bold')
    _draw_top(c, 451.9, 545, 'Tätigkeit', size=8.0, font='Helvetica-Bold')

    row_baselines = [563, 582.5, 602, 621.5, 641, 660.5, 680, 699.5, 719, 738.5]
    for index, row in enumerate(rows):
        baseline = row_baselines[index]
        _draw_fitted_top(c, 82, baseline, 212, row['employee'], preferred=6.8, minimum=5.0)
        _draw_fitted_top(c, 301, baseline, 37, row['start'], preferred=6.8, minimum=5.5)
        _draw_fitted_top(c, 343, baseline, 38, row['end'], preferred=6.8, minimum=5.5)
        _draw_fitted_top(c, 386, baseline, 59, row['date'], preferred=6.4, minimum=5.0)
        _draw_fitted_top(c, 449, baseline, 52, row['activity'], preferred=6.2, minimum=4.6)

    _draw_top(c, 78, 773, '(    ) Konkretisierung zum aktuellen Zeitpunkt nicht Bekannt. Wird rechtzeitig per E-Mail mitgeteilt.', size=8.2)
    _draw_top(c, 555, 820, '1', size=8.0)
    c.showPage()

    # Page 2 of the supplied template.
    body = 8.4
    _draw_top(c, 78, 139, '(1)  Die namentliche Nennung und die Angabe des Geburtsdatums erfolgt ausschließlich hinsichtlich § 1 Abs.', size=body)
    _draw_top(c, 96, 152, '1 Satz 6 AÜG. Sollte die Person des Zeitarbeitnehmers im Zeitpunkt des Abschlusses des Einzelarbeit-', size=body)
    _draw_top(c, 96, 165, 'nehmerüberlassungsvertrages noch unbekannt sein, so ist der Zeitarbeitnehmer von Auftraggeber und', size=body)
    _draw_top(c, 96, 178, 'Personaldienstleister rechtzeitig vor Einsatzbeginn namentlich unter Angabe des Geburtsdatums einver-', size=body)
    _draw_top(c, 96, 191, 'nehmlich zu benennen (Konkretisierung).', size=body)

    _draw_top(c, 78, 217, '(2)  Die Überlassungsvergütung richtet sich nach der tatsächlichen Arbeitszeit der eingesetzten Arbeitnehmer,', size=body)
    _draw_top(c, 96, 230, 'mindestens aber nach der in Absatz 1 genannten betrieblichen Arbeitszeit.', size=body)
    _draw_top(c, 78, 264, '(4) Es werden folgende Zuschläge vereinbart:', size=body)

    _draw_top(c, 78, 317, '§ 4 Arbeitsschutz', size=8.5, font='Helvetica-Bold')
    _draw_top(c, 78, 335, '(1) Bitte Zutreffendes ankreuzen:', size=body)
    c.rect(96, A4[1] - 356, 7, 7, stroke=1, fill=0)
    _draw_top(c, 114, 356, 'Für den Einsatz der überlassenen Zeitarbeitnehmer sind keine arbeitsmedizinischen Vorsorgeunter-', size=body)
    _draw_top(c, 114, 369, 'suchungen erforderlich. (X)', size=body)
    c.rect(96, A4[1] - 388, 7, 7, stroke=1, fill=0)
    _draw_top(c, 114, 388, 'Für den Einsatz der überlassenen Zeitarbeitnehmer sind folgende arbeitsmedizinischen Vorsorgeun-', size=body)
    _draw_top(c, 114, 401, 'tersuchungen erforderlich:', size=body)
    _draw_top(c, 503, 401, '[Angabe]', size=body)
    _draw_top(c, 114, 414, 'Diese werden vom Personaldienstleister vor Überlassungsbeginn durchgeführt und dem Auftraggeber', size=body)
    _draw_top(c, 114, 427, 'nachgewiesen.', size=body)

    _draw_top(c, 78, 461, '§ 5 Befristung', size=8.5, font='Helvetica-Bold')
    contract_end = package.first_shift_end_time or package.first_shift_time
    end_date = timezone.localtime(contract_end).strftime('%d.%m.%Y')
    _draw_top(c, 78, 482, 'Dieser Einzelarbeitnehmerüberlassungsvertrag wird zunächst befristet bis zum', size=body)
    _draw_top(c, 429, 482, end_date, size=body)

    c.setLineWidth(0.55)
    c.line(78, A4[1] - 545, 242, A4[1] - 545)
    c.line(290, A4[1] - 545, 482, A4[1] - 545)
    _draw_top(c, 78, 566, '[Datum, Unterschrift Auftraggeber]', size=8.1)
    _draw_top(c, 290, 566, '[Datum, Unterschrift Personaldienstleister]', size=8.1)
    _draw_top(c, 555, 820, '2', size=8.0)

    c.save()
    return buffer.getvalue()


def generate_client_contract(package: ShiftImportPackage, actor=None) -> Contract:
    template = seed_client_contract_template()
    pdf_bytes = build_client_contract_pdf(package)
    contract = package.contract or Contract(
        template=template,
        client=package.client,
        title=f'Einzelarbeitnehmerüberlassungsvertrag {package.request_id}',
        source_system='aplus',
        created_by=actor,
    )
    contract.template = template
    contract.client = package.client
    contract.source_system = 'aplus'
    contract.starts_on = package.first_shift_time.date()
    contract.ends_on = (package.first_shift_end_time or package.first_shift_time).date()
    contract.reminder_date = max(timezone.localdate(), contract.starts_on - timedelta(days=1))
    local_ids = [str(shift.id) for shift in package_shifts(package)]
    contract.variables = {
        'request_id': package.request_id,
        'client_name': package.client.name,
        'client_address': package.client.address,
        'start_date': contract.starts_on.isoformat(),
        'end_date': contract.ends_on.isoformat(),
        'shift_ids': local_ids,
        'auev_settings': _auev_values(package),
        'portal_visible': False,
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
    for user in recipients.distinct():
        Notification.objects.get_or_create(
            user=user,
            kind=f'client-contract-generated-{package.id}',
            defaults={'title': 'Kundenvertrag erstellt', 'body': contract.title, 'action_url': '/contracts'},
        )
    return contract


def sync_packages_from_local_shifts(start_date: date, end_date: date, actor=None) -> dict:
    start_dt = timezone.make_aware(datetime.combine(start_date, time.min), timezone.get_current_timezone())
    end_dt = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min), timezone.get_current_timezone())
    referenced = set()
    for payload in ShiftImportPackage.objects.values_list('payload', flat=True):
        referenced.update(_package_local_shift_ids(payload))
    shifts = list(
        Shift.objects.filter(starts_at__gte=start_dt, starts_at__lt=end_dt)
        .exclude(status=Shift.Status.CANCELLED)
        .select_related('order', 'client', 'location', 'position')
        .order_by('starts_at')
    )
    shifts = [shift for shift in shifts if str(shift.id) not in referenced]
    grouped = defaultdict(list)
    for shift in shifts:
        key = f'order:{shift.order_id}' if shift.order_id else f'client:{shift.client_id}:{shift.starts_at.astimezone().date().isoformat()}'
        grouped[key].append(shift)

    created = 0
    for key, rows in grouped.items():
        first = min(row.starts_at for row in rows)
        last = max(row.ends_at for row in rows)
        order = rows[0].order
        request_id = f'LOCAL-{order.id}' if order else f'LOCAL-{rows[0].client.customer_number}-{first.date().isoformat()}'
        request_id = request_id[:120]
        shift_payload = [{
            'shift_id': str(row.id),
            'local_shift_id': str(row.id),
            'date': row.starts_at.astimezone().date().isoformat(),
            'start_time': row.starts_at.astimezone().strftime('%H:%M'),
            'end_time': row.ends_at.astimezone().strftime('%H:%M'),
            'role': row.position.name,
            'location_id': str(row.location_id),
            'location_name': row.location.name,
            'position_id': str(row.position_id),
            'required_count': row.required_count,
            'notes': row.notes,
        } for row in rows]
        payload = {
            'source_system': 'aplus',
            'request_id': request_id,
            'order_id': str(order.id) if order else None,
            'site_name': rows[0].client.name,
            'site_address': rows[0].client.address or rows[0].location.address,
            'first_shift_time': first.isoformat(),
            'first_shift_end_time': last.isoformat(),
            'shifts': shift_payload,
        }
        source_hash = hashlib.sha256(str(payload).encode('utf-8')).hexdigest()
        ShiftImportPackage.objects.create(
            request_id=request_id,
            client=rows[0].client,
            site_name=rows[0].client.name,
            site_address=rows[0].client.address or rows[0].location.address,
            first_shift_time=first,
            first_shift_end_time=last,
            raw_text=order.description if order else '',
            source_hash=source_hash,
            payload=payload,
            status=ShiftImportPackage.Status.PENDING,
            created_by=actor,
        )
        created += 1
    return {'created': created, 'updated': 0, 'unchanged': 0, 'source': 'aplus'}


def sync_working_time(start: date, end: date) -> WorkingTimeSyncLog:
    """Rebuild Arbeitszeitkonto exclusively from local A+ TimeEntry rows."""
    if end < start:
        raise ValueError('Das Enddatum muss nach dem Startdatum liegen.')
    ensure_settings()
    start_dt = timezone.make_aware(datetime.combine(start, time.min), timezone.get_current_timezone())
    end_dt = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), timezone.get_current_timezone())
    entries = list(
        TimeEntry.objects.filter(clock_in__gte=start_dt, clock_in__lt=end_dt, clock_out__isnull=False)
        .select_related('worker__user', 'shift')
        .order_by('clock_in')
    )
    workers = list(WorkerProfile.objects.select_related('user').filter(active=True))
    settings_map = {row.worker_id: row for row in WorkingTimeSetting.objects.select_related('worker').all()}
    grouped = defaultdict(list)
    hours_by_key = defaultdict(lambda: Decimal('0'))
    unapproved = 0
    for entry in entries:
        month = entry.clock_in.astimezone().date().replace(day=1)
        key = (str(entry.worker_id), month)
        worked_minutes = entry.worked_minutes
        hours_by_key[key] += Decimal(worked_minutes) / Decimal('60')
        if not entry.approved:
            unapproved += 1
        grouped[key].append({
            'id': str(entry.id),
            'worker_id': str(entry.worker_id),
            'shift_id': str(entry.shift_id) if entry.shift_id else None,
            'clock_in': entry.clock_in.isoformat(),
            'clock_out': entry.clock_out.isoformat() if entry.clock_out else None,
            'worked_minutes': worked_minutes,
            'approved': entry.approved,
            'source': 'aplus',
        })

    now = timezone.now()
    count = 0
    with transaction.atomic():
        for worker in workers:
            row_setting = settings_map.get(worker.id)
            if row_setting and (not row_setting.active or row_setting.excluded):
                continue
            monthly_limit = dec((row_setting.monthly_limit if row_setting else None) or worker.monthly_hours or settings.WORKING_TIME_DEFAULT_MONTHLY_LIMIT)
            hourly_rate = dec((row_setting.hourly_rate if row_setting else None) or worker.tariff_hourly_rate or settings.WORKING_TIME_DEFAULT_HOURLY_RATE)
            prior = WorkingTimeAccountRecord.objects.filter(worker=worker, year_month__lt=start.replace(day=1)).order_by('-year_month').first()
            carry = prior.saldo_cumulative if prior else Decimal('0.00')
            for month in iter_months(start, end):
                existing = WorkingTimeAccountRecord.objects.filter(worker=worker, year_month=month).first()
                ist = hours_by_key.get((str(worker.id), month), Decimal('0')).quantize(TWO)
                difference = (ist - monthly_limit).quantize(TWO)
                paid = existing.paid_hours if existing else Decimal('0')
                manual = existing.manual_adjustment if existing else Decimal('0')
                saldo = (carry + difference + manual - paid).quantize(TWO)
                gross = (ist * hourly_rate).quantize(TWO)
                WorkingTimeAccountRecord.objects.update_or_create(
                    worker=worker,
                    year_month=month,
                    defaults={
                        'ist_hours': ist,
                        'soll_hours': monthly_limit,
                        'difference_hours': difference,
                        'carryover_previous': carry,
                        'paid_hours': paid,
                        'manual_adjustment': manual,
                        'saldo_cumulative': saldo,
                        'hourly_rate': hourly_rate,
                        'gross_amount': gross,
                        'raw_entries': grouped.get((str(worker.id), month), []),
                        'source': 'aplus_time_entries',
                        'synced_at': now,
                    },
                )
                carry = saldo
                count += 1
        message = ''
        if unapproved:
            message = f'{unapproved} noch nicht freigegebene Zeiteinträge wurden in die Berechnung einbezogen.'
        log = WorkingTimeSyncLog.objects.create(
            range_start=start,
            range_end=end,
            status='warning' if unapproved else 'ok',
            message=message,
            records_count=count,
            metadata={'source': 'aplus_time_entries', 'entries': len(entries), 'unapproved_entries': unapproved},
        )
    return log
