"""Regression coverage for historic Lexware annual uploads and review."""
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from reportlab.pdfgen import canvas

from core.models import Document


def tiny_pdf(*page_titles):
    output = io.BytesIO()
    pdf = canvas.Canvas(output)
    for title in page_titles:
        pdf.drawString(50, 765, title)
        pdf.showPage()
    pdf.save()
    return output.getvalue()


@pytest.mark.django_db
def test_annual_lexware_pdfs_archive_without_extracting_301_page_lohnkonto(auth_admin, monkeypatch):
    def should_not_parse_annual(*args, **kwargs):
        raise AssertionError('Annual archival documents must not be parsed as payslips')

    monkeypatch.setattr('core.payroll_views.parse_lexware_pdf', should_not_parse_annual)
    annual = [
        'Lohnkonto(1).pdf',
        'Lohnkonto-UV_2025.pdf',
        'Lohnsteuerbescheinigungen_2025.pdf',
    ]
    result = auth_admin.post(
        '/api/working-time/lexware-import/',
        {
            'period': '2025-12',
            'files': [
                SimpleUploadedFile(name, tiny_pdf(
                    'Lohnkonto 2025',
                    'Abrechnung für Dezember 2025 - Muster Muster',
                ), content_type='application/pdf')
                for name in annual
            ],
        }, format='multipart',
    )
    assert result.status_code == 200, result.data
    assert result.data['status'] == 'ok'
    assert result.data['rows'] == 0
    assert result.data['archive_errors'] == []
    assert len(result.data['archived_documents']) == 3
    assert Document.objects.filter(folder='payroll', title__startswith='Lexware 2025-12').count() == 3


@pytest.mark.django_db
def test_archival_storage_error_is_reported_without_server_500(auth_admin, monkeypatch):
    def fails_storage(*args, **kwargs):
        raise OSError('simulated disk full')

    monkeypatch.setattr('core.payroll_views._archive_lexware_upload', fails_storage)
    response = auth_admin.post(
        '/api/working-time/lexware-import/',
        {
            'period': '2025-12',
            'files': [
                SimpleUploadedFile(
                    'Lohnkonto(1).pdf', tiny_pdf('Lohnkonto 2025'),
                    content_type='application/pdf',
                )
            ],
        }, format='multipart',
    )
    assert response.status_code == 200, response.data
    assert response.data['status'] == 'partial'
    assert response.data['archive_errors'][0]['file'] == 'Lohnkonto(1).pdf'
    assert response.data['archived_documents'] == []


@pytest.mark.django_db
def test_can_review_old_unmatched_worker_without_reimport(
    auth_admin, auth_worker, admin_user, worker_user,
):
    report = tiny_pdf(
        'Abrechnung für Dezember 2025 - Anna Becker',
        'Abrechnung für Dezember 2025 - Missing Employee',
    )
    Document.objects.create(
        title='Lexware 2025-12 · Lohnabrechnungen_2025-12.pdf',
        file=SimpleUploadedFile(
            'Lohnabrechnungen_2025-12.pdf', report,
            content_type='application/pdf',
        ),
        folder=Document.Folder.PAYROLL,
        visibility=Document.Visibility.ADMIN,
        uploaded_by=admin_user,
    )
    path = '/api/working-time/lexware-unmatched/?period=2025-12'
    assert auth_worker.get(path).status_code == 403
    response = auth_admin.get(path)
    assert response.status_code == 200, response.data
    assert response.data['evidence_files'] == 1
    assert response.data['scanned_rows'] == 2
    assert response.data['matched_rows'] == 1
    assert response.data['unmatched_rows'] == 1
    assert response.data['unmatched_unique_count'] == 1
    assert response.data['unmatched'][0]['employee_name'] == 'Missing Employee'
    assert auth_admin.get('/api/working-time/lexware-unmatched/?period=2025-13').status_code == 400



@pytest.mark.django_db
def test_review_counts_archived_short_name_as_assigned_without_guessing_new_names(
    auth_admin, admin_user, monkeypatch,
):
    from core.lexware_historical import reconcile_archive

    title = 'Lexware 2025-10 · Lohnabrechnungen_2025-10.pdf'
    long_name = {
        'kind': 'payslip', 'employee_name': 'Example Historical Complete',
        'personal_number': '8012', 'period': '2025-10',
        'gross_amount': '900.00', 'net_amount': '715.00', 'page': 1,
    }
    short_name = {
        'kind': 'payslip', 'employee_name': 'Example Historical',
        'personal_number': '8012', 'period': '2025-10',
        'gross_amount': '900.00', 'net_amount': '715.00', 'page': 2,
    }
    unrelated = {
        'kind': 'payslip', 'employee_name': 'Still Unverified Other',
        'personal_number': '8888', 'period': '2025-10',
        'gross_amount': '600.00', 'net_amount': '500.00', 'page': 3,
    }
    Document.objects.create(
        title=title,
        file=SimpleUploadedFile('Lohnabrechnungen_2025-10.pdf', tiny_pdf('test')),
        folder=Document.Folder.PAYROLL,
        visibility=Document.Visibility.ADMIN,
        uploaded_by=admin_user,
    )
    monkeypatch.setattr(
        'core.lexware_historical._evidence',
        lambda year, month: ([(title, long_name), (title, short_name)], 0),
    )
    restored = reconcile_archive(2025, 10, apply=True)
    assert restored['added_payroll_rows'] == 2
    monkeypatch.setattr(
        'core.payroll_views.parse_lexware_pdf',
        lambda data: ('lohnabrechnungen', [long_name, short_name, unrelated]),
    )

    response = auth_admin.get('/api/working-time/lexware-unmatched/?period=2025-10')
    assert response.status_code == 200, response.data
    assert response.data['scanned_rows'] == 3
    assert response.data['matched_rows'] == 2
    assert response.data['unmatched_rows'] == 1
    assert response.data['unmatched_unique_count'] == 1
    assert response.data['unmatched'][0]['employee_name'] == 'Still Unverified Other'
