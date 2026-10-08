import csv
import hashlib
import io
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Document, EmployeeMasterData, PayrollStatement, User, WorkerProfile, WorkingTimeAccountRecord, WorkingTimeSetting
from .permissions import IsAdminOrManager
from .serializers import PayrollStatementSerializer
from .services import audit
from .working_time import dec, settings_rows, update_record
from .lexware_pdf import parse_lexware_pdf
from .lexware_aliases import aliases_for_target, canonical_target
from .wiw_sync import calculate_completeness


class PayrollViewSet(viewsets.ModelViewSet):
    queryset = PayrollStatement.objects.select_related('worker__user').all()
    serializer_class = PayrollStatementSerializer
    permission_classes = [IsAuthenticated]
    manager_mutations = {'create', 'update', 'partial_update', 'destroy'}

    def get_permissions(self):
        if getattr(self, 'action', None) in self.manager_mutations:
            return [IsAdminOrManager()]
        return super().get_permissions()

    def get_queryset(self):
        user = self.request.user
        if user.role in {User.Role.ADMIN, User.Role.MANAGER}:
            return self.queryset
        if user.role == User.Role.WORKER:
            return self.queryset.filter(worker__user=user)
        return self.queryset.none()

    def perform_create(self, serializer):
        obj = serializer.save()
        audit(self.request, 'payrollstatement.created', obj)

    def perform_update(self, serializer):
        obj = serializer.save()
        audit(self.request, 'payrollstatement.updated', obj)


@api_view(['GET', 'POST'])
@permission_classes([IsAdminOrManager])
def worktime_settings(request):
    if request.method == 'GET':
        return Response({
            'default_monthly_limit': str(settings.WORKING_TIME_DEFAULT_MONTHLY_LIMIT),
            'default_hourly_rate': str(settings.WORKING_TIME_DEFAULT_HOURLY_RATE),
            'default_break_minutes': settings.WORKING_TIME_DEFAULT_BREAK_MINUTES,
            'employees': settings_rows(),
        })

    employees = request.data.get('employees') or []
    saved = 0
    for row in employees:
        worker = get_object_or_404(WorkerProfile, pk=row.get('worker_id'))
        monthly_limit = max(Decimal('0'), dec(row.get('monthly_limit')))
        hourly_rate = max(Decimal('0'), dec(row.get('hourly_rate')))

        setting, _ = WorkingTimeSetting.objects.get_or_create(worker=worker)
        setting.monthly_limit = monthly_limit
        setting.hourly_rate = hourly_rate
        setting.night_surcharge_percent = max(Decimal('0'), dec(row.get('night_surcharge_percent')))
        setting.saturday_surcharge_percent = max(Decimal('0'), dec(row.get('saturday_surcharge_percent')))
        setting.sunday_surcharge_percent = max(Decimal('0'), dec(row.get('sunday_surcharge_percent')))
        setting.active = bool(row.get('active', True))
        setting.excluded = bool(row.get('excluded', False))
        setting.notes = str(row.get('notes') or '')
        setting.save()

        worker.monthly_hours = monthly_limit
        worker.tariff_hourly_rate = hourly_rate
        worker.save(update_fields=['monthly_hours', 'tariff_hourly_rate', 'updated_at'])
        saved += 1

    audit(request, 'working_time.settings_saved', request.user, {'saved': saved})
    return Response({'status': 'ok', 'saved': saved, 'employees': settings_rows()})


def _norm(value) -> str:
    text = unicodedata.normalize('NFKD', str(value or '').replace('ß', 'ss').replace('ẞ', 'SS'))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()


def _parse_money(value) -> Decimal | None:
    text = str(value or '').strip()
    if not text:
        return None
    text = text.replace('\xa0', '').replace('EUR', '').replace('€', '').replace(' ', '')
    if ',' in text and '.' in text:
        if text.rfind(',') > text.rfind('.'):
            text = text.replace('.', '').replace(',', '.')
        else:
            text = text.replace(',', '')
    elif ',' in text:
        text = text.replace('.', '').replace(',', '.')
    try:
        return Decimal(text)
    except Exception:
        return None


def _parse_bank_date(value, payroll_period=None):
    text = str(value or '').strip()
    if not text:
        return None
    for fmt in ('%d.%m.%Y', '%d.%m.%y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    if payroll_period and re.fullmatch(r'\d{4}', text):
        day = int(text[:2])
        month = int(text[2:])
        year = payroll_period.year
        if month < payroll_period.month - 6:
            year += 1
        elif month > payroll_period.month + 6:
            year -= 1
        try:
            return payroll_period.replace(year=year, month=month, day=day)
        except ValueError:
            return None
    return None


def _read_csv(name: str, payload: bytes) -> list[dict]:
    decoded = None
    for encoding in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            decoded = payload.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if decoded is None:
        return []

    # DATEV files start with an EXTF metadata line before the real column header.
    # Lexware Office uses DATEV CSV for bank exports of Giro accounts.
    lines = decoded.splitlines()
    header_index = 0
    for index, line in enumerate(lines[:30]):
        normalized = _norm(line)
        if (
            ('umsatz ohne soll haben kz' in normalized and 'buchungstext' in normalized)
            or ('buchungsdatum' in normalized and ('betrag' in normalized or 'umsatz' in normalized))
            or ('datum' in normalized and 'betrag' in normalized)
        ):
            header_index = index
            break
    decoded_table = '\n'.join(lines[header_index:])

    sample = decoded_table[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=';,\t,')
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ';'
    reader = csv.DictReader(io.StringIO(decoded_table), dialect=dialect)
    rows = []
    for row in reader:
        clean = {str(key or '').strip(): value for key, value in row.items()}
        clean['_source_file'] = name
        rows.append(clean)
    return rows


def _bank_rows(upload) -> list[dict]:
    payload = upload.read()
    name = str(getattr(upload, 'name', '') or 'lexware.csv')
    if name.lower().endswith('.zip') or payload[:4] == b'PK\x03\x04':
        rows = []
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for item in archive.namelist():
                if item.lower().endswith('.csv') and not item.endswith('/'):
                    rows.extend(_read_csv(item, archive.read(item)))
        return rows
    return _read_csv(name, payload)



def _xml_local_name(element) -> str:
    return str(getattr(element, 'tag', '') or '').rsplit('}', 1)[-1]


def _xml_child(node, name):
    if node is None:
        return None
    for child in list(node):
        if _xml_local_name(child) == name:
            return child
    return None


def _xml_path_text(node, *path) -> str:
    current = node
    for name in path:
        current = _xml_child(current, name)
        if current is None:
            return ''
    return str(current.text or '').strip()


def _sepa_rows(name: str, payload: bytes) -> list[dict]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return []

    rows = []
    for payment_info in root.iter():
        if _xml_local_name(payment_info) != 'PmtInf':
            continue
        execution_date = _xml_path_text(payment_info, 'ReqdExctnDt', 'Dt')
        for tx in list(payment_info):
            if _xml_local_name(tx) != 'CdtTrfTxInf':
                continue
            employee_name = _xml_path_text(tx, 'Cdtr', 'Nm')
            iban = _xml_path_text(tx, 'CdtrAcct', 'Id', 'IBAN')
            amount = _xml_path_text(tx, 'Amt', 'InstdAmt')
            purpose = _xml_path_text(tx, 'RmtInf', 'Ustrd')
            if not employee_name or not amount:
                continue
            rows.append({
                'employee_name': employee_name,
                'amount': amount,
                'iban': iban,
                'purpose': purpose,
                'payment_date': execution_date or None,
                '_source_file': name,
            })
    return rows


def _archive_lexware_upload(upload, period_text: str, user) -> str | None:
    name = str(getattr(upload, 'name', '') or 'Lexware Datei').strip()
    title = f'Lexware {period_text} · {name}'[:250]
    if Document.objects.filter(title=title, folder=Document.Folder.PAYROLL).exists():
        return None
    try:
        upload.seek(0)
        Document.objects.create(
            title=title,
            file=upload,
            folder=Document.Folder.PAYROLL,
            visibility=Document.Visibility.ADMIN,
            uploaded_by=user,
        )
        return title
    finally:
        try:
            upload.seek(0)
        except Exception:
            pass


def _row_value(row: dict, candidates: tuple[str, ...]):
    normalized = {_norm(key): value for key, value in row.items() if not key.startswith('_')}
    for candidate in candidates:
        value = normalized.get(_norm(candidate))
        if value not in (None, ''):
            return value
    return None


def _employee_matchers():
    matchers = []
    # Historical payroll uploads must also match former/inactive employees.
    for worker in WorkerProfile.objects.select_related('user').all():
        first = _norm(worker.user.first_name)
        last = _norm(worker.user.last_name)
        full = _norm(worker.user.get_full_name())
        aliases = {alias for alias in (
            full,
            _norm(f'{worker.user.first_name} {worker.user.last_name}'),
            _norm(f'{worker.user.last_name} {worker.user.first_name}'),
            _norm(worker.employee_number),
        ) if alias}
        if first and last:
            aliases.add(f'{first} {last}')
            aliases.add(f'{last} {first}')
        canonical_keys = {alias for alias in aliases if alias}
        for canonical_key in canonical_keys:
            aliases.update(aliases_for_target(canonical_key))
        matchers.append((worker, sorted(aliases, key=len, reverse=True)))
    return matchers


def _find_worker(row: dict, matchers):
    text = _norm(' '.join(str(value or '') for key, value in row.items() if not key.startswith('_')))
    employee_name = _norm(row.get('employee_name') or '')
    canonical_name = canonical_target(employee_name) if employee_name else ''
    if canonical_name and canonical_name != employee_name:
        exact_candidates = []
        canonical_tokens = set(canonical_name.split())
        for worker, aliases in matchers:
            if any(set(alias.split()).issuperset(canonical_tokens) for alias in aliases if alias):
                exact_candidates.append(worker)
        unique = {worker.id: worker for worker in exact_candidates}
        if len(unique) == 1:
            return next(iter(unique.values()))

        first_token = canonical_name.split()[0] if canonical_name.split() else ''
        if first_token:
            first_name_candidates = {}
            for worker, aliases in matchers:
                if any(first_token in alias.split() for alias in aliases if alias):
                    first_name_candidates[worker.id] = worker
            if len(first_name_candidates) == 1:
                return next(iter(first_name_candidates.values()))

    # Match whole normalized aliases, never arbitrary substrings of IBANs or
    # reference numbers. Ambiguous names require manual reconciliation.
    haystack = f' {text} '
    candidates = []
    for worker, aliases in matchers:
        hits = [
            alias for alias in aliases
            if len(alias) >= 4 and not alias.isdigit() and f' {alias} ' in haystack
        ]
        if hits:
            candidates.append((max(map(len, hits)), worker))
    if not candidates:
        return None
    max_length = max(length for length, _ in candidates)
    winners = [worker for length, worker in candidates if length == max_length]
    return winners[0] if len(winners) == 1 else None


def _expand_lexware_package_uploads(uploads):
    """Expand a Lexware year/package ZIP containing PDFs/XMLs.

    Bank-export ZIPs that contain only CSV files are left untouched and continue
    through the existing bank CSV parser.
    """
    expanded = []
    for upload in uploads:
        name = str(getattr(upload, 'name', '') or 'lexware')
        if not name.lower().endswith('.zip'):
            expanded.append(upload)
            continue
        try:
            payload = upload.read()
            upload.seek(0)
            if payload[:4] != b'PK\x03\x04':
                expanded.append(upload)
                continue
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                members = [item for item in archive.namelist() if not item.endswith('/')]
                package_members = [
                    item for item in members
                    if item.lower().endswith(('.pdf', '.xml'))
                ]
                if not package_members:
                    expanded.append(upload)
                    continue
                for member in package_members:
                    data = archive.read(member)
                    filename = member.rsplit('/', 1)[-1]
                    expanded.append(SimpleUploadedFile(
                        filename,
                        data,
                        content_type='application/pdf' if filename.lower().endswith('.pdf') else 'application/xml',
                    ))
        except Exception:
            try:
                upload.seek(0)
            except Exception:
                pass
            expanded.append(upload)
    return expanded


def _filename_period(name: str) -> str:
    match = re.search(r'(20[0-9]{2})[-_](0[1-9]|1[0-2])', str(name or ''))
    return f'{match.group(1)}-{match.group(2)}' if match else ''


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
@parser_classes([MultiPartParser, FormParser])
def lexware_bank_import(request):
    """Import Lexware evidence for one payroll period.

    Supported evidence:
    - bank CSV/ZIP exports
    - Lexware SEPA XML payment instructions
    - Lexware Zahlungsliste PDF
    - Lexware Lohnabrechnungen PDF

    The selected payroll period remains authoritative. Payment-list amounts are
    treated as actual payout evidence. Payslips provide gross/net and, for
    hourly Lohn rows, paid hours and the historical hourly rate. A fixed Gehalt
    is never converted into hours automatically.
    """
    uploads = request.FILES.getlist('files')
    if not uploads:
        single = request.FILES.get('file')
        uploads = [single] if single else []
    if not uploads:
        return Response({'detail': 'Bitte Lexware PDF, CSV, ZIP oder SEPA XML auswählen.'}, status=400)

    uploads = _expand_lexware_package_uploads(uploads)

    period_text = str(request.data.get('period') or '').strip()
    auto_period = period_text.lower() == 'auto'
    requested_year = str(request.data.get('year') or '').strip()
    if requested_year and not re.fullmatch(r'20[0-9]{2}', requested_year):
        return Response({'detail': 'Jahr muss im Format JJJJ angegeben werden.'}, status=400)

    period = None
    if not auto_period:
        if not re.fullmatch(r'\d{4}-\d{2}', period_text):
            return Response({'detail': 'Abrechnungsmonat muss im Format JJJJ-MM angegeben werden.'}, status=400)
        try:
            period = datetime.strptime(period_text, '%Y-%m').date().replace(day=1)
        except ValueError:
            return Response({'detail': 'Ungültiger Abrechnungsmonat.'}, status=400)

    detected_periods = {
        detected for detected in (
            _filename_period(str(getattr(upload, 'name', '') or ''))
            for upload in uploads
        )
        if detected
    }
    if not auto_period and len(detected_periods) > 1:
        return Response({
            'detail': 'Die ausgewählten Lexware Dateien gehören zu unterschiedlichen Abrechnungsmonaten.',
            'detected_periods': sorted(detected_periods),
        }, status=400)
    if not auto_period and detected_periods and period_text not in detected_periods:
        detected = next(iter(detected_periods))
        return Response({
            'detail': f'Die Lexware Datei gehört zu {detected}, ausgewählt ist aber {period_text}. Bitte den Abrechnungsmonat korrigieren.',
            'detected_period': detected,
        }, status=400)
    if auto_period and not requested_year and detected_periods:
        years = {value[:4] for value in detected_periods}
        if len(years) == 1:
            requested_year = next(iter(years))

    matchers = _employee_matchers()
    grouped = defaultdict(list)
    source_files = defaultdict(set)
    unmatched = []
    parsed_rows = 0
    archived_documents = []
    archived_only = []
    skipped_historical_corrections = []

    for upload in uploads:
        name = str(getattr(upload, 'name', '') or 'lexware')
        lower_name = name.lower()
        file_period_text = _filename_period(name) or (period_text if not auto_period else '')
        file_period = (
            datetime.strptime(file_period_text, '%Y-%m').date().replace(day=1)
            if re.fullmatch(r'\d{4}-\d{2}', file_period_text)
            else None
        )
        archive_period_label = file_period_text or requested_year or 'ohne Zeitraum'

        if lower_name.endswith('.xml') or 'xml' in str(getattr(upload, 'content_type', '')).lower():
            payload = upload.read()
            sepa_rows = _sepa_rows(name, payload)
            parsed_rows += len(sepa_rows)
            if not file_period_text or file_period is None:
                unmatched.append({'file': name, 'text': 'Abrechnungsmonat für SEPA Datei nicht erkennbar'})
                archived_title = _archive_lexware_upload(upload, archive_period_label, request.user)
                if archived_title:
                    archived_documents.append(archived_title)
                continue
            if not sepa_rows:
                unmatched.append({'file': name, 'text': 'SEPA XML konnte nicht gelesen werden'})
            for row in sepa_rows:
                worker = _find_worker({'employee_name': row.get('employee_name', '')}, matchers)
                amount = _parse_money(row.get('amount'))
                if not worker or amount in (None, Decimal('0')):
                    unmatched.append({
                        'file': name,
                        'text': str(row.get('employee_name') or 'Unbekannter Mitarbeiter')[:180],
                    })
                    continue
                payment_date = _parse_bank_date(row.get('payment_date'), file_period)
                amount = abs(amount).quantize(Decimal('0.01'))
                key_source = f"{name}|{file_period_text}|sepa|{row.get('employee_name')}|{row.get('iban')}|{amount}|{payment_date}"
                grouped[(worker.id, file_period_text)].append({
                    'kind': 'payment',
                    'key': hashlib.sha256(key_source.encode('utf-8')).hexdigest(),
                    'amount': str(amount),
                    'payment_date': payment_date.isoformat() if payment_date else None,
                    'recipient': row.get('employee_name') or '',
                    'purpose': row.get('purpose') or '',
                    'iban': row.get('iban') or '',
                    'source_file': name,
                    'source_type': 'lexware_sepa_xml',
                })
                source_files[(worker.id, file_period_text)].add(name)
            archived_title = _archive_lexware_upload(upload, archive_period_label, request.user)
            if archived_title:
                archived_documents.append(archived_title)
            continue

        if lower_name.endswith('.pdf') or str(getattr(upload, 'content_type', '')).lower() == 'application/pdf':
            payload = upload.read()
            try:
                document_type, pdf_rows = parse_lexware_pdf(payload)
            except Exception as exc:
                unmatched.append({'file': name, 'text': f'PDF konnte nicht gelesen werden: {exc}'[:180]})
                continue

            if document_type == 'unknown':
                archived_title = _archive_lexware_upload(upload, archive_period_label, request.user)
                if archived_title:
                    archived_documents.append(archived_title)
                archived_only.append(name)
                continue

            parsed_rows += len(pdf_rows)
            for row in pdf_rows:
                worker = _find_worker({'employee_name': row.get('employee_name', '')}, matchers)
                if not worker:
                    unmatched.append({
                        'file': name,
                        'text': str(row.get('employee_name') or 'Unbekannter Mitarbeiter')[:180],
                    })
                    continue

                item = dict(row)
                item['source_file'] = name
                item['source_type'] = (
                    'lexware_payslip_pdf'
                    if row.get('kind') == 'payslip'
                    else 'lexware_zahlungsliste_pdf'
                )
                target_period_text = (
                    str(row.get('period') or '').strip()
                    if row.get('kind') == 'payslip'
                    else file_period_text
                ) or file_period_text
                if not re.fullmatch(r'\d{4}-\d{2}', target_period_text):
                    unmatched.append({'file': name, 'text': 'Abrechnungsmonat nicht erkennbar'})
                    continue
                if (
                    auto_period
                    and requested_year
                    and not target_period_text.startswith(f'{requested_year}-')
                ):
                    skipped_historical_corrections.append({
                        'file': name,
                        'employee_name': row.get('employee_name') or '',
                        'period': target_period_text,
                    })
                    continue
                key_source = '|'.join([
                    name,
                    target_period_text,
                    str(row.get('kind') or ''),
                    str(row.get('employee_name') or ''),
                    str(row.get('personal_number') or ''),
                    str(row.get('amount') or ''),
                    str(row.get('gross_amount') or ''),
                    str(row.get('payout_amount') or ''),
                    str(row.get('is_correction') or ''),
                ])
                item['key'] = hashlib.sha256(key_source.encode('utf-8')).hexdigest()
                grouped[(worker.id, target_period_text)].append(item)
                source_files[(worker.id, target_period_text)].add(name)
            archived_title = _archive_lexware_upload(upload, archive_period_label, request.user)
            if archived_title:
                archived_documents.append(archived_title)
            continue

        try:
            rows = _bank_rows(upload)
        except Exception as exc:
            unmatched.append({'file': name, 'text': f'Datei konnte nicht gelesen werden: {exc}'[:180]})
            continue

        parsed_rows += len(rows)
        for row in rows:
            worker = _find_worker(row, matchers)
            amount = _parse_money(_row_value(row, (
                'Betrag', 'Umsatz', 'Umsatz (ohne Soll/Haben-Kz)', 'Basis-Umsatz',
                'Amount', 'Betrag EUR', 'Wert', 'Transaction amount',
            )))
            if not worker or amount in (None, Decimal('0')):
                if any(str(value or '').strip() for value in row.values()):
                    unmatched.append({
                        'file': row.get('_source_file', name),
                        'text': str(_row_value(row, ('Verwendungszweck', 'Buchungstext', 'Beschreibung', 'Text')) or '')[:180],
                    })
                continue

            payment_date = _parse_bank_date(_row_value(row, (
                'Buchungsdatum', 'Belegdatum', 'Datum', 'Wertstellung', 'Date', 'Transaction date',
            )), period)
            purpose = str(_row_value(row, (
                'Verwendungszweck', 'Buchungstext', 'Beschreibung', 'Text', 'Purpose',
                'Auftraggeber/Empfänger', 'Zahlungspflichtiger/Zahlungsempfänger',
            )) or '')
            recipient = str(_row_value(row, (
                'Empfänger', 'Zahlungsempfänger', 'Begünstigter', 'Name', 'Recipient',
                'Auftraggeber/Empfänger', 'Zahlungspflichtiger/Zahlungsempfänger',
            )) or '')
            amount = abs(amount).quantize(Decimal('0.01'))
            key_source = f'{row.get("_source_file",name)}|{payment_date}|{amount}|{recipient}|{purpose}'
            grouped[(worker.id, period_text)].append({
                'kind': 'payment',
                'key': hashlib.sha256(key_source.encode('utf-8')).hexdigest(),
                'amount': str(amount),
                'payment_date': payment_date.isoformat() if payment_date else None,
                'recipient': recipient,
                'purpose': purpose,
                'source_file': row.get('_source_file', name),
                'source_type': 'lexware_bank_export',
            })
            source_files[(worker.id, file_period_text)].add(name)

        archived_title = _archive_lexware_upload(upload, archive_period_label, request.user)
        if archived_title:
            archived_documents.append(archived_title)

    imported = []
    for (worker_id, statement_period_text), items in grouped.items():
        worker = WorkerProfile.objects.select_related('user').get(pk=worker_id)
        statement_period = datetime.strptime(statement_period_text, '%Y-%m').date().replace(day=1)
        statement, _ = PayrollStatement.objects.get_or_create(
            worker=worker,
            period=statement_period,
            defaults={'source': 'lexware_import'},
        )
        existing = list(statement.raw_data or [])
        by_key = {str(item.get('key')): item for item in existing if item.get('key')}
        for item in items:
            by_key[item['key']] = item
        merged = list(by_key.values())

        payment_items = [
            item for item in merged
            if item.get('kind') == 'payment'
            or (not item.get('kind') and item.get('amount') is not None)
        ]
        payslip_items = [item for item in merged if item.get('kind') == 'payslip']
        latest_payslip = payslip_items[-1] if payslip_items else None

        # Do not double count the same salary when several Lexware payment
        # evidences are imported. Prefer actual bank export, then SEPA order,
        # then the Lexware payment list.
        payment_items_by_source = defaultdict(list)
        for item in payment_items:
            payment_items_by_source[str(item.get('source_type') or 'legacy')].append(item)
        preferred_payment_items = []
        for source_type in (
            'lexware_bank_export',
            'lexware_sepa_xml',
            'lexware_zahlungsliste_pdf',
            'legacy',
        ):
            if payment_items_by_source.get(source_type):
                preferred_payment_items = payment_items_by_source[source_type]
                break

        if preferred_payment_items:
            total = sum(
                (dec(item.get('amount')) for item in preferred_payment_items),
                Decimal('0.00'),
            ).quantize(Decimal('0.01'))
            statement.transferred_amount = total
        dates = [
            _parse_bank_date(item.get('payment_date'), statement_period)
            for item in preferred_payment_items if item.get('payment_date')
        ]
        dates = [value for value in dates if value]
        if dates:
            statement.payment_date = max(dates)

        if latest_payslip:
            statement.gross_amount = _parse_money(latest_payslip.get('gross_amount'))
            statement.net_amount = _parse_money(latest_payslip.get('net_amount'))

        source_types = {str(item.get('source_type') or '') for item in merged}
        if 'lexware_bank_export' in source_types:
            statement.source = 'lexware_bank_export'
        elif 'lexware_sepa_xml' in source_types:
            statement.source = 'lexware_sepa_bundle' if 'lexware_payslip_pdf' in source_types else 'lexware_sepa_xml'
        elif 'lexware_payslip_pdf' in source_types and 'lexware_zahlungsliste_pdf' in source_types:
            statement.source = 'lexware_pdf_bundle'
        elif 'lexware_payslip_pdf' in source_types:
            statement.source = 'lexware_payslip_pdf'
        elif 'lexware_zahlungsliste_pdf' in source_types:
            statement.source = 'lexware_zahlungsliste_pdf'
        else:
            statement.source = 'lexware_import'

        current_refs = sorted(source_files.get((worker_id, statement_period_text)) or [])
        if current_refs:
            statement.source_reference = ', '.join(current_refs)[:255]
        statement.raw_data = merged
        statement.save(update_fields=[
            'gross_amount', 'net_amount', 'transferred_amount', 'payment_date',
            'source', 'source_reference', 'raw_data', 'updated_at',
        ])

        auto_paid_hours = None
        lexware_hourly_rate = None
        compensation_type = ''
        payout_amount = None
        supplements = []
        if latest_payslip:
            compensation_type = str(latest_payslip.get('compensation_type') or '')
            payout_amount = latest_payslip.get('payout_amount')
            supplements = latest_payslip.get('supplements') or []

            master, _ = EmployeeMasterData.objects.get_or_create(worker=worker)
            master_data = dict(master.data or {})
            source_map = dict(master.source_map or {})
            observed = {
                'lexware_personal_number': latest_payslip.get('personal_number'),
                'compensation_type': compensation_type,
                'lexware_monthly_salary': latest_payslip.get('monthly_salary'),
                'hourly_rate': latest_payslip.get('hourly_rate'),
                'lexware_supplements': supplements,
            }
            current_latest_period = str(master_data.get('lexware_latest_payroll_period') or '')
            if not current_latest_period or statement_period_text >= current_latest_period:
                observed['lexware_latest_payroll_period'] = statement_period_text
            for key, value in observed.items():
                if value not in (None, '', []):
                    master_data[key] = value
                    source_map[key] = 'lexware_payslip'
            completeness, missing = calculate_completeness(master_data)
            master.data = master_data
            master.source_map = source_map
            master.completeness = completeness
            master.missing_fields = missing
            master.save()

            setting, _ = WorkingTimeSetting.objects.get_or_create(worker=worker)
            setting_fields = []
            for supplement in supplements:
                label = str(supplement.get('label') or '').lower()
                percent = max(Decimal('0'), dec(supplement.get('percent')))
                if percent <= 0:
                    continue
                if 'nacht' in label:
                    setting.night_surcharge_percent = percent
                    setting_fields.append('night_surcharge_percent')
                elif 'sonntag' in label:
                    setting.sunday_surcharge_percent = percent
                    setting_fields.append('sunday_surcharge_percent')
                elif 'samstag' in label:
                    setting.saturday_surcharge_percent = percent
                    setting_fields.append('saturday_surcharge_percent')

            if compensation_type == 'hourly' and latest_payslip.get('quantity') is not None:
                auto_paid_hours = max(Decimal('0'), dec(latest_payslip.get('quantity')))
                lexware_hourly_rate = max(Decimal('0'), dec(latest_payslip.get('hourly_rate')))
                if lexware_hourly_rate > 0:
                    worker.tariff_hourly_rate = lexware_hourly_rate
                    worker.save(update_fields=['tariff_hourly_rate'])
                    setting.hourly_rate = lexware_hourly_rate
                    setting_fields.append('hourly_rate')
                record = WorkingTimeAccountRecord.objects.filter(
                    worker=worker,
                    year_month=statement_period,
                ).first()
                if record:
                    update_record(record, paid_total_hours=auto_paid_hours)

            if setting_fields:
                setting.save(update_fields=list(dict.fromkeys(setting_fields)))

        imported.append({
            'worker_id': str(worker.id),
            'employee_name': str(worker.user),
            'period': statement_period_text,
            'transferred_amount': str(statement.transferred_amount) if statement.transferred_amount is not None else None,
            'gross_amount': str(statement.gross_amount) if statement.gross_amount is not None else None,
            'net_amount': str(statement.net_amount) if statement.net_amount is not None else None,
            'payout_amount': payout_amount,
            'compensation_type': compensation_type,
            'paid_hours': str(auto_paid_hours) if auto_paid_hours is not None else None,
            'hourly_rate': str(lexware_hourly_rate) if lexware_hourly_rate is not None else None,
            'supplements': supplements,
            'evidence_items': len(merged),
        })

    audit(request, 'payroll.lexware_imported', request.user, {
        'period': period_text,
        'employees': len(imported),
        'rows': parsed_rows,
        'files': len(uploads),
        'unmatched': len(unmatched),
    })
    return Response({
        'status': 'ok',
        'period': period_text,
        'files': len(uploads),
        'rows': parsed_rows,
        'employees': imported,
        'unmatched_count': len(unmatched),
        'unmatched_preview': unmatched[:20],
        'archived_documents': archived_documents,
    })

