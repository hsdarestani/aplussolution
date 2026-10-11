"""Complete absent historical payroll months from already-archived Lexware evidence.

Strictly ADDITIVE: Only creates a missing PayrollStatement for verified,
disabled historical workers. Never modifies an existing statement, any
working-time record, or a salary/Saldo calculation.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal
import re

from django.db import transaction

from .lexware_historical import _evidence, _personnel_number, _row_key
from .models import AuditLog, PayrollStatement, WorkerProfile
from .payroll_views import _employee_matchers, _find_worker, _norm


def complete_historical_months(*, year=2025, months=(7, 8, 9, 10, 11), apply=False):
    if not 2000 <= year <= 2100 or any(month < 1 or month > 12 for month in months):
        raise ValueError("Invalid year or month")
    matchers = _employee_matchers()
    missing = defaultdict(list)
    errors = 0
    skipped_ambiguous = 0
    reviewed_historical_rows = 0
    existing_rows_preserved = 0

    for month in months:
        lines, errors_this_month = _evidence(year, month)
        errors += errors_this_month
        for source, row in lines:
            person = _find_worker(
                {'employee_name': str(row.get('employee_name') or '')}, matchers,
            )
            if person is None or person.employment_type != WorkerProfile.EmploymentType.HISTORICAL:
                continue
            if person.active or person.user.is_active:
                skipped_ambiguous += 1
                continue
            name = _norm(row.get('employee_name') or '')
            master = getattr(person, 'master_data', None)
            data = master.data if master else {}
            saved_names = {_norm(person.user.get_full_name())}
            saved_names.update(_norm(alias) for alias in data.get('lexware_source_names', []))
            personnel = _personnel_number(row)
            saved_personnel = str(data.get('lexware_personal_number') or '').replace(' ', '').upper()

            # Accept only a previously evidenced exact full-name/alias match,
            # or a matching Lexware Personalnummer. Matching by a short
            # first-name substring alone is NOT sufficient for payroll.
            number_matches = bool(personnel and saved_personnel and personnel == saved_personnel)
            if personnel and saved_personnel and personnel != saved_personnel:
                skipped_ambiguous += 1
                continue
            if not number_matches and name not in saved_names:
                skipped_ambiguous += 1
                continue
            destination = (
                str(row.get('period') or '')
                if row.get('kind') == 'payslip' else f'{year:04d}-{month:02d}'
            )
            if not re.fullmatch(r'20\d\d-(0[1-9]|1[0-2])', destination):
                continue
            dy, dm = (int(piece) for piece in destination.split('-'))
            if dy != year or dm not in months:
                continue
            reviewed_historical_rows += 1
            period = date(dy, dm, 1)
            if PayrollStatement.objects.filter(worker_id=person.pk, period=period).exists():
                existing_rows_preserved += 1
                continue
            missing[(person.pk, period)].append((source, dict(row)))

    report = {
        'year': year,
        'months': list(months),
        'parse_errors': errors,
        'verified_historical_evidence_rows': reviewed_historical_rows,
        'existing_rows_preserved': existing_rows_preserved,
        'uncertain_rows_held': skipped_ambiguous,
        'missing_payroll_months': len(missing),
        'missing_evidence_rows': sum(len(rows) for rows in missing.values()),
        'created_payroll_months': 0,
        'added_source_rows': 0,
        'applied': apply,
    }
    if errors:
        raise ValueError('Unable to read all archived payroll evidence')
    if not apply:
        return report

    with transaction.atomic():
        for (person_id, period), rows in sorted(missing.items(), key=lambda item: (item[0][1], str(item[0][0]))):
            evidence = []
            seen = set()
            for title, row in rows:
                key = _row_key(title, row, period.strftime('%Y-%m'))
                if key in seen:
                    continue
                seen.add(key)
                evidence.append({
                    **row,
                    'key': key,
                    'source_file': title,
                    'source_type': (
                        'lexware_payslip_pdf'
                        if row.get('kind') == 'payslip'
                        else 'lexware_zahlungsliste_pdf'
                    ),
                })
            payslips = [r for r in evidence if r.get('kind') == 'payslip']
            payments = [r for r in evidence if r.get('kind') == 'payment' and r.get('amount') is not None]
            values = {
                'source': 'lexware_historical_archive',
                'raw_data': evidence,
            }
            if payslips:
                latest = sorted(payslips, key=lambda r: bool(r.get('is_correction')))[-1]
                for source_field, field in [('gross_amount', 'gross_amount'), ('net_amount', 'net_amount')]:
                    if latest.get(source_field) not in (None, ''):
                        values[field] = Decimal(str(latest[source_field]))
            if payments:
                values['transferred_amount'] = sum(
                    (Decimal(str(row['amount'])) for row in payments), Decimal('0.00')
                )
            _statement, created = PayrollStatement.objects.get_or_create(
                worker_id=person_id, period=period, defaults=values,
            )
            if not created:
                continue
            report['created_payroll_months'] += 1
            report['added_source_rows'] += len(evidence)
            AuditLog.objects.create(
                actor=None, action='payroll.historical_month_completed',
                object_type='PayrollStatement',
                object_id=str(_statement.pk),
                metadata={'period': period.strftime('%Y-%m'), 'evidence_count': len(evidence)},
            )
    return report
