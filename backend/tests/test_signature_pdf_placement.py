import io

from PIL import Image, ImageDraw

from core.models import ContractSignature
from core import signature_pdf


def test_signature_canvas_is_cropped_to_visible_ink():
    canvas = Image.new('RGBA', (600, 240), (255, 255, 255, 0))
    draw = ImageDraw.Draw(canvas)
    draw.line((220, 105, 380, 130), fill=(25, 25, 25, 255), width=6)
    raw = io.BytesIO()
    canvas.save(raw, format='PNG')

    cropped = signature_pdf._trim_signature_image(raw.getvalue())
    with Image.open(io.BytesIO(cropped)) as image:
        assert image.width < 260
        assert image.height < 100
        assert image.width > 120
        assert image.height > 20


def test_smartdocs_does_not_use_plain_worker_label_as_signature_target(monkeypatch):
    monkeypatch.setattr(
        signature_pdf,
        'analyse_pdf_template',
        lambda _path, _fields: {
            'resolved_coordinates': {
                'signature_employee': {
                    'label': 'Mitarbeiter',
                    'page': 1,
                    'position': {'x': 0.55, 'y': 0.50, 'width': 0.30, 'height': 0.05},
                    'confidence': 0.98,
                    'source': 'smartdocs-inline',
                }
            }
        },
    )

    placements = signature_pdf._smartdocs_placements(b'not-a-real-pdf', [ContractSignature.Role.EMPLOYEE])
    assert placements == {}


def test_smartdocs_accepts_explicit_signature_anchor(monkeypatch):
    monkeypatch.setattr(
        signature_pdf,
        'analyse_pdf_template',
        lambda _path, _fields: {
            'resolved_coordinates': {
                'signature_employee': {
                    'label': 'Unterschrift Arbeitnehmer',
                    'page': 6,
                    'position': {'x': 0.17, 'y': 0.50, 'width': 0.32, 'height': 0.05},
                    'confidence': 0.91,
                    'source': 'smartdocs-line',
                }
            }
        },
    )

    placements = signature_pdf._smartdocs_placements(b'not-a-real-pdf', [ContractSignature.Role.EMPLOYEE])
    assert placements[ContractSignature.Role.EMPLOYEE]['page'] == 6
    assert placements[ContractSignature.Role.EMPLOYEE]['source'] == 'smartdocs-line'
