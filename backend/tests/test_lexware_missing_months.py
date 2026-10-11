"""Verify absent payroll months are restored without altering existing wages."""
from datetime import date

import pytest

from core.lexware_historical import reconcile_archive
from core.lexware_missing_months import complete_historical_months
from core.models import PayrollStatement, WorkerProfile, WorkingTimeAccountRecord


def archived(name, month, kind, **extra):
    suffix = 'Lohnabrechnungen' if kind == 'payslip' else 'Zahlungsliste'
    return (
        f'Lexware 2025-{month:02d} · {suffix}_2025-{month:02d}.pdf',
        {'kind': kind, 'employee_name': name, **extra},
    )


@pytest.mark.django_db
def test_complete_missing_historical_month_exact_evidence_without_fake_hours(monkeypatch):
    first = [archived('Archive Example Worker', 7, 'payslip',
                      personal_number='1021', period='2025-07',
                      gross_amount='800.00', net_amount='650.00')]
    monkeypatch.setattr('core.lexware_historical._evidence', lambda y, m: (first, 0))
    created = reconcile_archive(2025, 7, apply=True)
    assert created['created_inactive_profiles'] == 1
    worker = WorkerProfile.objects.get()
    assert PayrollStatement.objects.count() == 1

    august = [
        archived('Archive Example Worker', 8, 'payslip',
                 personal_number='1021', period='2025-08',
                 gross_amount='900.00', net_amount='710.00'),
        archived('Archive Example Worker', 8, 'payment',
                 amount='710.00', iban='DE00000000000000000000'),
    ]
    monkeypatch.setattr('core.lexware_missing_months._evidence',
                        lambda y, m: (august, 0) if m == 8 else ([], 0))

    dry = complete_historical_months(months=(8,))
    assert dry['missing_payroll_months'] == 1
    assert dry['missing_evidence_rows'] == 2
    assert dry['applied'] is False
    assert PayrollStatement.objects.count() == 1

    changed = complete_historical_months(months=(8,), apply=True)
    assert changed['created_payroll_months'] == 1
    assert changed['added_source_rows'] == 2
    record = PayrollStatement.objects.get(worker=worker, period=date(2025, 8, 1))
    assert str(record.gross_amount) == '900.00'
    assert str(record.net_amount) == '710.00'
    assert str(record.transferred_amount) == '710.00'
    assert len(record.raw_data) == 2
    assert record.source == 'lexware_historical_archive'
    original = PayrollStatement.objects.get(worker=worker, period=date(2025, 7, 1))
    assert str(original.gross_amount) == '800.00'
    assert WorkingTimeAccountRecord.objects.count() == 0

    repeated = complete_historical_months(months=(8,), apply=True)
    assert repeated['created_payroll_months'] == 0
    assert PayrollStatement.objects.count() == 2


@pytest.mark.django_db
def test_missing_month_does_not_guess_name_from_partial_identity(monkeypatch):
    first = [archived('Archive Example Worker', 7, 'payslip',
                      personal_number='1021', period='2025-07',
                      gross_amount='800.00', net_amount='650.00')]
    monkeypatch.setattr('core.lexware_historical._evidence', lambda y, m: (first, 0))
    reconcile_archive(2025, 7, apply=True)
    monthly = [archived('Archive Example', 8, 'payment', amount='700.00')]
    monkeypatch.setattr('core.lexware_missing_months._evidence',
                        lambda y, m: (monthly, 0))
    result = complete_historical_months(months=(8,), apply=True)
    assert result['created_payroll_months'] == 0
    assert PayrollStatement.objects.count() == 1


@pytest.mark.django_db
def test_existing_payroll_month_is_never_overwritten(monkeypatch):
    first = [archived('Archive Example Worker', 7, 'payslip',
                      personal_number='1021', period='2025-07',
                      gross_amount='800.00', net_amount='650.00')]
    monkeypatch.setattr('core.lexware_historical._evidence', lambda y, m: (first, 0))
    reconcile_archive(2025, 7, apply=True)
    monthly = [archived('Archive Example Worker', 7, 'payslip',
                        personal_number='1021', period='2025-07',
                        gross_amount='1800.00', net_amount='1650.00')]
    monkeypatch.setattr('core.lexware_missing_months._evidence', lambda y, m: (monthly, 0))
    result = complete_historical_months(months=(7,), apply=True)
    assert result['created_payroll_months'] == 0
    assert str(PayrollStatement.objects.get().gross_amount) == '800.00'
