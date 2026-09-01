import io
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from reportlab.pdfgen import canvas

from core.models import ClientOrder, Shift
from core.order_file_import import approve_document_orders, extract_order_document, parse_order_document


def _two_page_pdf():
    output = io.BytesIO()
    pdf = canvas.Canvas(output)
    pdf.drawString(50, 800, 'Datum: Dienstag, 1. September 2026')
    pdf.drawString(50, 780, 'Veranstaltungs - Nr.: 11173')
    pdf.drawString(50, 760, 'Status: Definitiv')
    pdf.drawString(50, 740, 'Personal')
    pdf.drawString(50, 720, '2 Servicekraft pro Stunde vor Ort 14:00 - 21:00 Uhr (14 Std.)')
    pdf.showPage()
    pdf.drawString(50, 800, 'Datum: Samstag, 19. September 2026')
    pdf.drawString(50, 780, 'Veranstaltungs - Nr.: 11223')
    pdf.drawString(50, 760, 'Status: Option')
    pdf.drawString(50, 740, 'Personal')
    pdf.drawString(50, 720, '2 Servicekraft pro Stunde vor Ort 09:00 - 17:00 Uhr (16 Std.)')
    pdf.save()
    return output.getvalue()


class _FakeResponse:
    ok = True
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return {
            'choices': [
                {'message': {'content': json.dumps(self.payload)}}
            ]
        }


class _FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return _FakeResponse(self.payload)


def test_pdf_extraction_keeps_pages_separate():
    upload = SimpleUploadedFile('september.pdf', _two_page_pdf(), content_type='application/pdf')
    document = extract_order_document(upload)
    assert len(document['pages']) == 2
    assert '11173' in document['pages'][0]
    assert '11223' in document['pages'][1]
    assert '[[SEITE 1]]' in document['text']
    assert '[[SEITE 2]]' in document['text']


@override_settings(WIW_OPENAI_KEY='test-key', WIW_OPENAI_MODEL='gpt-4o-mini', WIW_HTTP_TIMEOUT=30)
def test_ai_document_parser_keeps_event_numbers_and_source_statuses():
    document = {
        'name': 'september.pdf',
        'pages': [
            'Veranstaltungs - Nr.: 11173\nStatus: Definitiv\nPersonal\n2 Servicekraft 14:00 - 21:00',
            'Veranstaltungs - Nr.: 11223\nStatus: Option\nPersonal\n2 Servicekraft 09:00 - 17:00',
        ],
        'text': '[[SEITE 1]] ... [[SEITE 2]] ...',
    }
    session = _FakeSession({
        'orders': [
            {
                'source_page': 1,
                'contract_no': '11173',
                'source_status': 'Definitiv',
                'title': 'Abendessen',
                'organizer': 'Deutsch-Koreanisches Forum e.V.',
                'shifts': [{
                    'role': 'Servicekraft', 'date': '2026-09-01', 'start_time': '14:00', 'end_time': '21:00',
                    'count': 2, 'location_text': 'Evangelische Akademie Frankfurt', 'site_text': 'Evangelische Akademie Frankfurt',
                    'site_address': 'Römerberg 9, 60311 Frankfurt am Main', 'notes': 'vor Ort',
                }],
            },
            {
                'source_page': 2,
                'contract_no': '11223',
                'source_status': 'Option',
                'title': 'Veranstaltung',
                'organizer': 'Stadtbild Deutschland e.V.',
                'shifts': [{
                    'role': 'Servicekraft', 'date': '2026-09-19', 'start_time': '09:00', 'end_time': '17:00',
                    'count': 2, 'location_text': 'Evangelische Akademie Frankfurt', 'site_text': 'Evangelische Akademie Frankfurt',
                    'site_address': 'Römerberg 9, 60311 Frankfurt am Main', 'notes': 'vor Ort',
                }],
            },
        ]
    })
    result = parse_order_document(document, session=session)
    assert result['order_count'] == 2
    assert result['staff_slots'] == 4
    assert [item['request_id'] for item in result['orders']] == ['11173', '11223']
    assert result['orders'][0]['source_status'] == 'Definitiv'
    assert result['orders'][1]['source_status'] == 'Option'
    assert result['orders'][1]['raw_text'].startswith('Veranstaltungs - Nr.: 11223')
    assert session.calls


@pytest.mark.django_db
def test_batch_import_publishes_definitive_and_keeps_option_as_draft(admin_user, company, location, position):
    orders = [
        {
            'request_id': 'FILE-DEF-1',
            'contract_no': 'FILE-DEF-1',
            'source_status': 'Definitiv',
            'raw_text': 'Veranstaltungs-Nr.: FILE-DEF-1\nStatus: Definitiv',
            'shifts': [{
                'role': position.name,
                'date': '2026-09-10',
                'start_time': '10:00',
                'end_time': '14:00',
                'count': 2,
                'location_text': location.name,
                'site_text': location.name,
                'site_address': location.address,
                'notes': '',
            }],
        },
        {
            'request_id': 'FILE-OPT-1',
            'contract_no': 'FILE-OPT-1',
            'source_status': 'Option',
            'raw_text': 'Veranstaltungs-Nr.: FILE-OPT-1\nStatus: Option',
            'shifts': [{
                'role': position.name,
                'date': '2026-09-19',
                'start_time': '09:00',
                'end_time': '17:00',
                'count': 3,
                'location_text': location.name,
                'site_text': location.name,
                'site_address': location.address,
                'notes': '',
            }],
        },
    ]
    result = approve_document_orders(orders, actor=admin_user, client_id=str(company.id))
    assert result['status'] == 'ok'
    assert result['published_orders'] == 1
    assert result['draft_orders'] == 1
    assert result['created_staff_slots'] == 5

    definitive_order = ClientOrder.objects.get(title__contains='FILE-DEF-1')
    option_order = ClientOrder.objects.get(title__contains='FILE-OPT-1')
    assert definitive_order.status == ClientOrder.Status.CONFIRMED
    assert option_order.status == ClientOrder.Status.PLANNING
    assert definitive_order.shifts.get().status == Shift.Status.PUBLISHED
    assert definitive_order.shifts.get().required_count == 2
    assert option_order.shifts.get().status == Shift.Status.DRAFT
    assert option_order.shifts.get().required_count == 3
