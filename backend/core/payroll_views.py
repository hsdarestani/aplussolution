import csv
import hashlib
import io
import re
import unicodedata
import zipfile
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import PayrollStatement, User, WorkerProfile, WorkingTimeAccountRecord, WorkingTimeSetting
from .permissions import IsAdminOrManager
from .serializers import PayrollStatementSerializer
from .services import audit
from .working_time import dec, settings_rows, update_record
from .lexware_pdf import parse_lexware_pdf


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
    text = unicodedata.normalize('NFKD', str(value or ''))
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
        matchers.append((worker, sorted(aliases, key=len, reverse=True)))
    return matchers


def _find_worker(row: dict, matchers):
    text = _norm(' '.join(str(value or '') for key, value in row.items() if not key.startswith('_')))
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


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
@parser_classes([MultiPartParser, FormParser])
def lexware_bank_import(request):
    """One-time Lexware Office bank export import.

    The selected payroll period is authoritative because salary payments can be
    booked in a later calendar month than the payroll period they belong to.
    """
    upload = request.FILES.get('file')
    if not upload:
        return Response({'detail': 'Bitte Lexware CSV oder ZIP auswählen.'}, status=400)

    period_text = str(request.data.get('period') or '').strip()
    if not re.fullmatch(r'\d{4}-\d{2}', period_text):
        return Response({'detail': 'Abrechnungsmonat muss im Format JJJJ-MM angegeben werden.'}, status=400)
    try:
        period = datetime.strptime(period_text, '%Y-%m').date().replace(day=1)
    except ValueError:
        return Response({'detail': 'Ungültiger Abrechnungsmonat.'}, status=400)

    rows = _bank_rows(upload)
    matchers = _employee_matchers()
    grouped = defaultdict(list)
    unmatched = []

    for row in rows:
        worker = _find_worker(row, matchers)
        amount = _parse_money(_row_value(row, (
            'Betrag', 'Umsatz', 'Umsatz (ohne Soll/Haben-Kz)', 'Basis-Umsatz',
            'Amount', 'Betrag EUR', 'Wert', 'Transaction amount',
        )))
        if not worker or amount in (None, Decimal('0')):
            if any(str(value or '').strip() for value in row.values()):
                unmatched.append({
                    'file': row.get('_source_file', ''),
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
        key_source = f'{row.get("_source_file","")}|{payment_date}|{amount}|{recipient}|{purpose}'
        grouped[worker.id].append({
            'key': hashlib.sha256(key_source.encode('utf-8')).hexdigest(),
            'amount': str(amount),
            'payment_date': payment_date.isoformat() if payment_date else None,
            'recipient': recipient,
            'purpose': purpose,
            'source_file': row.get('_source_file', ''),
        })

    imported = []
    for worker_id, items in grouped.items():
        worker = WorkerProfile.objects.select_related('user').get(pk=worker_id)
        statement, _ = PayrollStatement.objects.get_or_create(
            worker=worker,
            period=period,
            defaults={'source': 'lexware_bank_export'},
        )
        existing = list(statement.raw_data or [])
        by_key = {str(item.get('key')): item for item in existing if item.get('key')}
        for item in items:
            by_key[item['key']] = item
        merged = list(by_key.values())
        total = sum((dec(item.get('amount')) for item in merged), Decimal('0.00')).quantize(Decimal('0.01'))
        dates = [
            _parse_bank_date(item.get('payment_date'), period)
            for item in merged if item.get('payment_date')
        ]
        statement.transferred_amount = total
        statement.payment_date = max((value for value in dates if value), default=statement.payment_date)
        statement.source = 'lexware_bank_export'
        statement.source_reference = str(getattr(upload, 'name', '') or '')[:255]
        statement.raw_data = merged
        statement.save(update_fields=[
            'transferred_amount', 'payment_date', 'source', 'source_reference',
            'raw_data', 'updated_at',
        ])
        imported.append({
            'worker_id': str(worker.id),
            'employee_name': str(worker.user),
            'period': period_text,
            'transferred_amount': str(total),
            'transactions': len(merged),
        })

    audit(request, 'payroll.lexware_bank_imported', request.user, {
        'period': period_text,
        'employees': len(imported),
        'rows': len(rows),
        'unmatched': len(unmatched),
    })
    return Response({
        'status': 'ok',
        'period': period_text,
        'rows': len(rows),
        'employees': imported,
        'unmatched_count': len(unmatched),
        'unmatched_preview': unmatched[:20],
    })
