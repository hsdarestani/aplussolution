import io
from datetime import date

import fitz
import pytest
from django.core.files.base import ContentFile
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from core.document_engine import generate_contract_files
from core.models import Contract, ContractTemplate
from core.smart_pdf_overlay import analyse_pdf_template, render_smart_pdf_overlay


def _labelled_pdf(name_line_width=260):
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    pdf.setFont('Helvetica', 9)
    pdf.drawString(60, 760, 'Mitarbeiter')
    pdf.line(160, 758, 160 + name_line_width, 758)
    pdf.drawString(60, 720, 'Ort, Datum')
    pdf.line(160, 718, 420, 718)
    pdf.drawString(60, 680, 'Unveränderlicher Vertragstext')
    pdf.save()
    return output.getvalue()


def _fields():
    return [
        {'name': 'employee_name', 'label': 'Mitarbeiter', 'source': 'worker.full_name', 'required': True},
        {'name': 'signature_place', 'label': 'Ort', 'source': 'master.signature_place', 'required': False},
        {'name': 'signature_date', 'label': 'Datum', 'source': 'today', 'required': True},
    ]


def test_layout_analysis_detects_real_input_lines(tmp_path):
    source = tmp_path / 'contract.pdf'
    source.write_bytes(_labelled_pdf())

    analysis = analyse_pdf_template(source, _fields())

    assert analysis['engine'] == 'smartdocs-layout-v1'
    assert analysis['matched_count'] >= 2
    assert analysis['resolved_coordinates']['employee_name']['source'] == 'smartdocs-line'
    assert analysis['resolved_coordinates']['employee_name']['confidence'] >= 0.52
    assert analysis['resolved_coordinates']['signature_date']['label'] == 'Ort, Datum'


def test_overlay_places_values_on_detected_baselines_not_fixed_footer(tmp_path):
    source = tmp_path / 'contract.pdf'
    source.write_bytes(_labelled_pdf())
    data = {
        'employee_name': 'Anna Becker',
        'signature_place': 'Frankfurt am Main',
        'signature_date': date(2026, 8, 21),
    }
    analysis = analyse_pdf_template(source, _fields())

    pdf_bytes, layout = render_smart_pdf_overlay(
        source,
        _fields(),
        data,
        analysis=analysis,
        format_value=lambda value: value.strftime('%d.%m.%Y') if isinstance(value, date) else str(value),
    )

    document = fitz.open(stream=pdf_bytes, filetype='pdf')
    try:
        page = document[0]
        name_rects = page.search_for('Anna Becker')
        place_rects = page.search_for('Frankfurt am Main')
        date_rects = page.search_for('21.08.2026')
        assert name_rects and place_rects and date_rects
        # ReportLab y=758 becomes roughly y=84 in PyMuPDF's top-left coordinate system.
        # The value must stay at the detected form line, not at the old fixed footer.
        assert 150 <= name_rects[0].x0 <= 170
        assert 65 <= name_rects[0].y0 <= 90
        assert 150 <= place_rects[0].x0 <= 170
        assert 105 <= place_rects[0].y0 <= 130
        assert layout['unplaced_required'] == []
        assert 'employee_name' in layout['placed_fields']
        assert 'signature_place' in layout['placed_fields']
        assert 'signature_date' in layout['placed_fields']
    finally:
        document.close()


def test_long_value_is_shrunk_to_available_field_width(tmp_path):
    source = tmp_path / 'narrow.pdf'
    source.write_bytes(_labelled_pdf(name_line_width=120))
    fields = [{'name': 'employee_name', 'label': 'Mitarbeiter', 'source': 'worker.full_name', 'required': True}]
    long_name = 'Maximilian Alexander von Beispielhausen'
    analysis = analyse_pdf_template(source, fields)

    pdf_bytes, _ = render_smart_pdf_overlay(source, fields, {'employee_name': long_name}, analysis=analysis)

    document = fitz.open(stream=pdf_bytes, filetype='pdf')
    try:
        page = document[0]
        spans = [
            span
            for block in page.get_text('dict').get('blocks', []) if block.get('type') == 0
            for line in block.get('lines', [])
            for span in line.get('spans', [])
            if 'Maximilian' in str(span.get('text') or '')
        ]
        assert spans
        rect = fitz.Rect(spans[0]['bbox'])
        assert rect.x0 >= 150
        assert rect.x1 <= 286  # detected line ends at x=280, with small extraction tolerance
        assert float(spans[0]['size']) < 9
    finally:
        document.close()


@pytest.mark.django_db
def test_contract_generation_uses_smart_layout_and_caches_mapping(tmp_path, admin_user, worker_user, settings):
    settings.MEDIA_ROOT = tmp_path / 'media'
    template = ContractTemplate.objects.create(
        name='Smart Overlay Vertrag',
        slug='smart-overlay-regression',
        kind=ContractTemplate.Kind.DATA_SECRECY,
        source_format=ContractTemplate.SourceFormat.PDF_OVERLAY,
        schema={'fields': _fields(), 'signature_roles': ['employee'], 'overlay': {}},
        requires_signature=True,
    )
    template.source_file.save('smart-overlay.pdf', ContentFile(_labelled_pdf()), save=True)
    contract = Contract.objects.create(
        template=template,
        worker=worker_user.worker_profile,
        title='Smart Overlay Vertrag',
        variables={'signature_place': 'Frankfurt am Main'},
        created_by=admin_user,
    )

    generate_contract_files(contract)

    contract.refresh_from_db(); template.refresh_from_db()
    assert contract.pdf
    assert contract.status == Contract.Status.READY
    layout = template.schema['overlay']['smart_layout']
    assert layout['engine'] == 'smartdocs-layout-v1'
    assert layout['source_checksum'] == template.source_checksum
    assert 'employee_name' in layout['resolved_coordinates']
    contract.pdf.open('rb')
    try:
        generated = contract.pdf.read()
    finally:
        contract.pdf.close()
    document = fitz.open(stream=generated, filetype='pdf')
    try:
        text = document[0].get_text('text')
        assert 'Anna Becker' in text
        assert 'Frankfurt am Main' in text
    finally:
        document.close()
