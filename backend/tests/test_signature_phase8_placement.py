import io
from types import SimpleNamespace

from reportlab.pdfgen import canvas

from core.models import ContractSignature
from core.signature_pdf import _resolve_signature_placements


def _sample_pdf():
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=(595, 842))
    pdf.setFont('Helvetica', 10)
    pdf.drawString(350, 650, 'Arbeitgeber Unterschrift')
    pdf.line(345, 625, 540, 625)
    pdf.showPage()
    pdf.setFont('Helvetica', 10)
    pdf.drawString(55, 250, 'Arbeitnehmer Unterschrift')
    pdf.line(50, 225, 245, 225)
    pdf.save()
    return output.getvalue()


def test_signature_layout_follows_different_pdf_fields_by_role():
    source = _sample_pdf()
    template = SimpleNamespace(schema={})
    placements = _resolve_signature_placements(
        source,
        template,
        [ContractSignature.Role.EMPLOYER, ContractSignature.Role.EMPLOYEE],
    )

    employer = placements[ContractSignature.Role.EMPLOYER]
    employee = placements[ContractSignature.Role.EMPLOYEE]
    assert employer['page'] == 1
    assert employee['page'] == 2
    assert employer['source'] != 'legacy-fallback'
    assert employee['source'] != 'legacy-fallback'
    assert employer['position']['x'] > employee['position']['x']


def test_template_signature_coordinates_override_pdf_detection():
    source = _sample_pdf()
    template = SimpleNamespace(schema={
        'signature_placements': {
            ContractSignature.Role.EMPLOYEE: {
                'page': 1,
                'x': 0.66,
                'y': 0.22,
                'width': 0.25,
                'height': 0.06,
            },
        },
    })
    placements = _resolve_signature_placements(source, template, [ContractSignature.Role.EMPLOYEE])
    employee = placements[ContractSignature.Role.EMPLOYEE]
    assert employee['page'] == 1
    assert employee['source'] == 'template'
    assert employee['position']['x'] == 0.66
    assert employee['position']['y'] == 0.22
