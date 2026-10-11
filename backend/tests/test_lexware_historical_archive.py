"""Former staff must be inactive, evidence-backed and never invent attendance."""
from datetime import date
import pytest

from core.lexware_historical import reconcile_archive
from core.models import PayrollStatement, User, WorkerProfile, WorkingTimeAccountRecord


@pytest.mark.django_db
def test_recover_historic_staff_only_from_evidence_without_balance_changes(monkeypatch):
    source = [
        ('Lexware 2025-12 · Lohnabrechnungen_2025-12.pdf', {
            'kind': 'payslip', 'employee_name': 'Former Example Person',
            'personal_number': '5672', 'period': '2025-12',
            'gross_amount': '950.00', 'net_amount': '750.00',
            'page': 1,
        }),
        ('Lexware 2025-12 · Zahlungsliste_2025-12.pdf', {
            'kind': 'payment', 'employee_name': 'Former Example Person',
            'amount': '750.00', 'iban': 'DE00000000000000000000',
            'page': 1,
        }),
    ]
    monkeypatch.setattr('core.lexware_historical._evidence', lambda y, m: (source, 0))
    dry_run = reconcile_archive(2025, 12)
    assert dry_run['profiles_eligible'] == 1
    assert dry_run['applied'] is False
    assert WorkerProfile.objects.count() == 0

    result = reconcile_archive(2025, 12, apply=True)
    assert result['created_inactive_profiles'] == 1
    assert result['created_payroll_months'] == 1
    assert result['added_payroll_rows'] == 2
    worker = WorkerProfile.objects.get()
    assert worker.active is False
    assert worker.user.is_active is False
    assert not worker.user.has_usable_password()
    assert worker.user.email.endswith('@inactive.invalid')
    assert worker.master_data.data['lexware_personal_number'] == '5672'
    assert WorkingTimeAccountRecord.objects.count() == 0
    statement = PayrollStatement.objects.get(worker=worker, period=date(2025, 12, 1))
    assert str(statement.gross_amount) == '950.00'
    assert str(statement.net_amount) == '750.00'
    assert str(statement.transferred_amount) == '750.00'
    assert len(statement.raw_data) == 2

    repeat = reconcile_archive(2025, 12, apply=True)
    assert repeat['created_inactive_profiles'] == 0
    assert PayrollStatement.objects.count() == 1
    assert len(PayrollStatement.objects.get().raw_data) == 2


@pytest.mark.django_db
def test_short_vs_long_lexware_names_without_personnel_number_are_held(monkeypatch):
    files = [
        ('Lexware 2025-12 · Lohnabrechnungen_2025-12.pdf', {
            'kind': 'payslip', 'employee_name': 'Sample Partial', 'period': '2025-12', 'gross_amount': '800.00',
        }),
        ('Lexware 2025-12 · Lohnabrechnungen_2025-12.pdf', {
            'kind': 'payslip', 'employee_name': 'Sample Partial Longer Name', 'period': '2025-12', 'gross_amount': '900.00',
        }),
    ]
    monkeypatch.setattr('core.lexware_historical._evidence', lambda y, m: (files, 0))
    results = reconcile_archive(2025, 12, apply=True)
    assert results['ambiguous_groups_held'] == 2
    assert results['created_inactive_profiles'] == 0
    assert results['unresolved_rows'] == 2


@pytest.mark.django_db
def test_same_personnel_number_aliases_unify_verified_payslips(monkeypatch):
    files = [
        ('Lexware 2025-12 · Lohnabrechnungen_2025-12.pdf', {
            'kind': 'payslip', 'employee_name': 'Sample Long', 'personal_number': '1700',
            'period': '2025-12', 'gross_amount': '800.00', 'page': 1,
        }),
        ('Lexware 2025-12 · Lohnabrechnungen_2025-12.pdf', {
            'kind': 'payslip', 'employee_name': 'Sample Long Complete', 'personal_number': '1700',
            'period': '2025-12', 'gross_amount': '850.00', 'page': 2,
        }),
    ]
    monkeypatch.setattr('core.lexware_historical._evidence', lambda y, m: (files, 0))
    result = reconcile_archive(2025, 12, apply=True)
    assert result['created_inactive_profiles'] == 1
    assert result['added_payroll_rows'] == 2
    assert WorkerProfile.objects.count() == 1
    assert PayrollStatement.objects.count() == 1
    assert len(WorkerProfile.objects.get().master_data.data['lexware_source_names']) == 2

    # The short source name is not the created historical user's full name.
    # Despite that difference, the archived row has already been linked.
    # Subsequent read-only reviews must not report it as unresolved again.
    preview = reconcile_archive(2025, 12)
    assert preview['unmatched_source_rows'] == 0
    assert preview['unresolved_rows'] == 0
    assert preview['profiles_eligible'] == 0
