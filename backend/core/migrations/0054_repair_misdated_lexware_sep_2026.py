from datetime import date
from decimal import Decimal

from django.db import migrations


SOURCE_FILES = {
    'Lohnabrechnungen_2026-09.pdf',
    'Zahlungsliste_2026-09.pdf',
}
SOURCE_PERIOD = date(2026, 10, 1)
TARGET_PERIOD = date(2026, 9, 1)


def _dec(value):
    try:
        return Decimal(str(value or '0'))
    except Exception:
        return Decimal('0')


def _recompute_statement(statement, items):
    payment_items = [
        item for item in items
        if item.get('kind') == 'payment'
        or (not item.get('kind') and item.get('amount') is not None)
    ]
    payslip_items = [item for item in items if item.get('kind') == 'payslip']
    latest_payslip = payslip_items[-1] if payslip_items else None

    statement.transferred_amount = (
        sum((_dec(item.get('amount')) for item in payment_items), Decimal('0.00'))
        if payment_items else None
    )
    statement.gross_amount = _dec(latest_payslip.get('gross_amount')) if latest_payslip and latest_payslip.get('gross_amount') is not None else None
    statement.net_amount = _dec(latest_payslip.get('net_amount')) if latest_payslip and latest_payslip.get('net_amount') is not None else None

    source_types = {str(item.get('source_type') or '') for item in items}
    if 'lexware_payslip_pdf' in source_types and 'lexware_zahlungsliste_pdf' in source_types:
        statement.source = 'lexware_pdf_bundle'
    elif 'lexware_payslip_pdf' in source_types:
        statement.source = 'lexware_payslip_pdf'
    elif 'lexware_zahlungsliste_pdf' in source_types:
        statement.source = 'lexware_zahlungsliste_pdf'
    elif 'lexware_bank_export' in source_types:
        statement.source = 'lexware_bank_export'
    else:
        statement.source = 'manual'

    refs = sorted({str(item.get('source_file') or '') for item in items if item.get('source_file')})
    statement.source_reference = ', '.join(refs)[:255]
    statement.raw_data = items


def _recompute_time_chain(WorkingTimeAccountRecord, worker_id):
    previous = (
        WorkingTimeAccountRecord.objects
        .filter(worker_id=worker_id, year_month__lt=TARGET_PERIOD)
        .order_by('-year_month')
        .first()
    )
    carry = previous.saldo_cumulative if previous else Decimal('0.00')
    rows = (
        WorkingTimeAccountRecord.objects
        .filter(worker_id=worker_id, year_month__gte=TARGET_PERIOD)
        .order_by('year_month')
    )
    for row in rows:
        row.carryover_previous = carry
        paid_total = (
            row.paid_total_hours
            if row.paid_total_hours is not None
            else (_dec(row.soll_hours) + _dec(row.paid_hours))
        )
        row.saldo_cumulative = (
            carry
            + _dec(row.ist_hours)
            + _dec(row.manual_adjustment)
            - _dec(paid_total)
        ).quantize(Decimal('0.01'))
        row.save(update_fields=['carryover_previous', 'saldo_cumulative'])
        carry = row.saldo_cumulative


def repair_misdated_lexware_import(apps, schema_editor):
    PayrollStatement = apps.get_model('core', 'PayrollStatement')
    WorkingTimeAccountRecord = apps.get_model('core', 'WorkingTimeAccountRecord')

    source_statements = list(PayrollStatement.objects.filter(period=SOURCE_PERIOD))
    for source in source_statements:
        worker_id = worker_id
        raw_items = list(source.raw_data or [])
        moved = [
            item for item in raw_items
            if str(item.get('source_file') or '') in SOURCE_FILES
        ]
        if not moved:
            continue

        remaining = [
            item for item in raw_items
            if str(item.get('source_file') or '') not in SOURCE_FILES
        ]

        target, _ = PayrollStatement.objects.get_or_create(
            worker_id=worker_id,
            period=TARGET_PERIOD,
            defaults={'source': 'lexware_import'},
        )
        existing_target = list(target.raw_data or [])
        by_key = {
            str(item.get('key')): item
            for item in existing_target
            if item.get('key')
        }
        for item in moved:
            key = str(item.get('key') or '')
            if key:
                by_key[key] = item
            else:
                existing_target.append(item)
        merged_target = existing_target + list(by_key.values())
        # De-duplicate any pre-key legacy rows while preserving order.
        seen = set()
        deduped_target = []
        for item in merged_target:
            marker = str(item.get('key') or repr(sorted(item.items())))
            if marker in seen:
                continue
            seen.add(marker)
            deduped_target.append(item)

        _recompute_statement(target, deduped_target)
        target.save()

        if remaining:
            _recompute_statement(source, remaining)
            source.save()
        else:
            source.delete()

        payslips = [item for item in moved if item.get('kind') == 'payslip']
        latest_payslip = payslips[-1] if payslips else None
        if latest_payslip and latest_payslip.get('compensation_type') == 'hourly':
            quantity = _dec(latest_payslip.get('quantity'))
            september_record = WorkingTimeAccountRecord.objects.filter(
                worker_id=worker_id,
                year_month=TARGET_PERIOD,
            ).first()
            october_record = WorkingTimeAccountRecord.objects.filter(
                worker_id=worker_id,
                year_month=SOURCE_PERIOD,
            ).first()

            if september_record and _dec(september_record.paid_total_hours) == Decimal('0'):
                september_record.paid_total_hours = quantity
                september_record.save(update_fields=['paid_total_hours'])

            if october_record and _dec(october_record.paid_total_hours) == quantity:
                october_record.paid_total_hours = Decimal('0.00')
                october_record.save(update_fields=['paid_total_hours'])

        _recompute_time_chain(WorkingTimeAccountRecord, worker_id)


def noop_reverse(apps, schema_editor):
    # This repairs a known one-off production import mistake. Reversing would
    # intentionally re-create invalid October payroll evidence, so no-op.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0053_payroll_audit_ledger'),
    ]

    operations = [
        migrations.RunPython(repair_misdated_lexware_import, noop_reverse),
    ]
