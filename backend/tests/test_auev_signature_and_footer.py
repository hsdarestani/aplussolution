import io
import zipfile
from datetime import date

from django.test import SimpleTestCase
from docx import Document
from PIL import Image

from core.auev_builder import _classic_docx, _new_docx, _week_footer


def _signature_png():
    buffer = io.BytesIO()
    Image.new('RGBA', (90, 42), (0, 0, 0, 255)).save(buffer, 'PNG')
    return buffer.getvalue()


def _data(signature):
    return {
        'sequence_number': 415,
        'week_footer': '42-43',
        'provider_signature': signature,
        'signature_date_de': '15.10.2026',
        'first_shift_date_de': '17.10.2026',
        'last_shift_date_de': '24.10.2026',
        'settings': {
            'client_contract_text': 'Marthas Finest GmbH, Frankfurt',
            'permit_date_de': '20.04.2025',
            'framework_date_de': '26.08.2024',
            'effective_date_de': '17.10.2026',
            'intended_activity': 'Servicekraft',
        },
        'rows': [{
            'name_birth': 'Mustermann, Max, 01.01.2000',
            'start': '08:30', 'end': '15:30', 'date': '17.10.2026',
            'activity': 'Servicekraft',
        }],
    }


class AuevSignatureAndFooterTests(SimpleTestCase):
    def test_footer_uses_iso_week_values_and_not_document_sequence(self):
        self.assertEqual(_week_footer([date(2026, 10, 17), date(2026, 10, 24)]), '42-43')
        self.assertEqual(_week_footer([date(2026, 12, 31), date(2027, 1, 4)]), '53/2026-1/2027')

    def test_both_templates_embed_signature_and_display_week_footer(self):
        for build in (_classic_docx, _new_docx):
            with self.subTest(template=build.__name__):
                docx_bytes = build(_data(_signature_png()))
                rendered = Document(io.BytesIO(docx_bytes))
                self.assertEqual(rendered.sections[0].footer.paragraphs[0].text, '42-43')
                self.assertNotIn('415', rendered.sections[0].footer.paragraphs[0].text)
                with zipfile.ZipFile(io.BytesIO(docx_bytes)) as contents:
                    self.assertTrue(any(path.startswith('word/media/') for path in contents.namelist()))

    def test_unapproved_signature_is_not_embedded(self):
        for build in (_classic_docx, _new_docx):
            with self.subTest(template=build.__name__):
                docx_bytes = build(_data(None))
                with zipfile.ZipFile(io.BytesIO(docx_bytes)) as contents:
                    self.assertFalse(any(path.startswith('word/media/') for path in contents.namelist()))
