import io
from datetime import datetime
from types import SimpleNamespace

import fitz
from PIL import Image, ImageDraw
from django.utils import timezone

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


def test_dgb_signature_caption_prints_entered_name_role_and_date():
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    signed_at = timezone.make_aware(datetime(2026, 9, 6, 12, 30))
    signature = SimpleNamespace(
        signer_name='Max Mustermann',
        role=ContractSignature.Role.EMPLOYEE,
        signed_at=signed_at,
    )
    template = SimpleNamespace(slug='arbeitsvertrag-dgb-gvp')
    slot = fitz.Rect(80, 100, 300, 140)

    assert signature_pdf._stamp_signature_caption(page, slot, signature, template) is True
    text = page.get_text()
    assert 'Max Mustermann' in text
    assert 'Arbeitnehmer' in text
    assert '06.09.2026' in text
    document.close()
