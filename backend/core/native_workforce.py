import hashlib
import io
from pathlib import Path

import fitz
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


AUEV_TEMPLATE_PATH = Path(__file__).resolve().parent / 'assets' / 'muster_einzelarbeitnehmerueberlassungsvertrag.pdf'
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


def _insert_fitted_line(page, rect, text, max_size=8.5, min_size=5.2):
    rect = fitz.Rect(*rect)
    value = str(text or '').replace('\n', ', ').strip()
    size = max_size
    while size > min_size and fitz.get_text_length(value, fontname='helv', fontsize=size) > rect.width:
        size -= 0.25
    page.insert_text((rect.x0, rect.y1 - 2), value, fontname='helv', fontsize=max(size, min_size), color=(0, 0, 0))


def build_client_contract_pdf(package: ShiftImportPackage) -> bytes:
    rows = _employee_rows(package)
    if not rows:
        raise ValueError('Für die Vertragsgenerierung muss mindestens ein Mitarbeiter einer Schicht zugeteilt sein.')
    if len(rows) > 10:
        raise ValueError('Die aktuelle ANÜ Vorlage bietet Platz für maximal 10 Mitarbeiter pro Vertrag.')
    if not AUEV_TEMPLATE_PATH.exists():
        raise ValueError('Die ANÜ PDF Vorlage ist auf dem Server nicht installiert.')

    values = _auev_values(package)
    document = fitz.open(AUEV_TEMPLATE_PATH)
    try:
        page = document[0]
        for rect in (
            (76, 275, 214, 290),
            (349.8, 307.5, 401.2, 321.5),
            (311.0, 354.5, 362.6, 369.0),
            (286, 388, 558, 403.2),
            (286, 414, 558, 429.2),
        ):
            page.add_redact_annot(fitz.Rect(*rect), fill=(1, 1, 1))
        page.apply_redactions()

        client_line = package.client.name if package.client_id else package.site_name
        client_address = package.client.address if package.client_id else package.site_address
        if client_address:
            client_line = f'{client_line}, {client_address}'
        _insert_fitted_line(page, (78, 162, 558, 175), f'{client_line} (Auftraggeber)', max_size=8.5, min_size=5.4)
        _insert_fitted_line(page, (78, 275, 214, 290), f"{values['permit_date']} in Düsseldorf.", max_size=8.5)
        _insert_fitted_line(page, (350.2, 307.5, 400.8, 321.5), values['framework_date'], max_size=8.5)
        _insert_fitted_line(page, (311.4, 354.5, 362.2, 369.0), values['effective_date'], max_size=8.5)
        _insert_fitted_line(page, (290, 388, 558, 403.2), values['required_qualification'], max_size=8.5, min_size=5.5)
        _insert_fitted_line(page, (290, 414, 558, 429.2), values['intended_activity'], max_size=8.5, min_size=5.5)

        row_tops = [546.96, 565.92, 585.36, 605.04, 624.48, 643.92, 663.36, 683.04, 702.48, 721.92]
        row_bottoms = [565.92, 585.36, 605.04, 624.48, 643.92, 663.36, 683.04, 702.48, 721.92, 741.60]
        for index, row in enumerate(rows):
            top, bottom = row_tops[index], row_bottoms[index]
            _insert_fitted_line(page, (82, top + 2, 295, bottom - 2), row['employee'], max_size=6.8, min_size=5.0)
            _insert_fitted_line(page, (301, top + 2, 338, bottom - 2), row['start'], max_size=6.8, min_size=5.5)
            _insert_fitted_line(page, (343, top + 2, 381, bottom - 2), row['end'], max_size=6.8, min_size=5.5)
            _insert_fitted_line(page, (386, top + 2, 445, bottom - 2), row['date'], max_size=6.4, min_size=5.0)
            _insert_fitted_line(page, (449, top + 2, 501, bottom - 2), row['activity'], max_size=6.2, min_size=4.6)

        second_page = document[1]
        second_page.add_redact_annot(fitz.Rect(426.5, 470.0, 491.0, 484.0), fill=(1, 1, 1))
        second_page.apply_redactions()
        contract_end = package.first_shift_end_time or package.first_shift_time
        _insert_fitted_line(
            second_page,
            (429, 470, 491, 484),
            timezone.localtime(contract_end).strftime('%d.%m.%Y'),
            max_size=8.5,
        )
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()


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
