from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from reportlab.pdfgen import canvas
from rest_framework.test import APIClient

from core.models import ClientCompany, Location, Position, Shift, User, WorkerProfile
from core.shift_plan_models import ShiftPlanAttachment, ShiftPlanDocument
from core.shift_slots import ShiftSlot


pytestmark = pytest.mark.django_db


def pdf_upload(name='10719 30_09_2026.pdf'):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(40, 800, 'Mi, 30. September 2026 09:30-16:30 Uhr')
    pdf.drawString(40, 780, 'Goethe-Universität Frankfurt Campus Westend PEG-Gebäude')
    pdf.drawString(40, 760, 'Konferenz 10719')
    pdf.drawString(40, 740, 'VA.Nr. 10719')
    pdf.drawString(40, 700, 'Personal')
    pdf.drawString(40, 680, '1x10,5 Servicekraft')
    pdf.drawString(40, 660, '08:30 Uhr bis 19:00 Uhr')
    pdf.showPage()
    pdf.drawString(40, 800, 'Do, 1. Oktober 2026 09:30-14:30 Uhr')
    pdf.drawString(40, 780, 'Goethe-Universität Frankfurt Campus Westend PEG-Gebäude')
    pdf.drawString(40, 760, 'Konferenz 10719')
    pdf.drawString(40, 700, 'Personal')
    pdf.drawString(40, 680, '1x8,5 Servicekraft')
    pdf.drawString(40, 660, '09:00 Uhr bis 17:30 Uhr')
    pdf.showPage()
    pdf.drawString(40, 800, 'Fr, 2. Oktober 2026 09:30-16:30 Uhr')
    pdf.drawString(40, 780, 'Goethe-Universität Frankfurt Campus Westend PEG-Gebäude')
    pdf.drawString(40, 760, 'Konferenz 10719')
    pdf.drawString(40, 700, 'Logistik')
    pdf.drawString(40, 680, '1x2,5 Logistiker')
    pdf.save()
    raw = buffer.getvalue()
    return SimpleUploadedFile(name, raw, content_type='application/pdf')


def setup_schedule():
    admin = User.objects.create_user(email='admin@example.com', password='pw', role=User.Role.ADMIN)
    client_user = User.objects.create_user(email='client@example.com', password='pw', role=User.Role.CLIENT)
    client = ClientCompany.objects.create(name='Goethe Universität', customer_number='G-1')
    client.contacts.add(client_user)
    location = Location.objects.create(
        client=client,
        name='Goethe Universität Frankfurt Campus Westend',
        address='Theodor-W.-Adorno-Platz 6, 60629 Frankfurt am Main',
    )
    position = Position.objects.create(name='Servicekraft')
    berlin = ZoneInfo('Europe/Berlin')
    shift1 = Shift.objects.create(
        client=client,
        location=location,
        position=position,
        starts_at=datetime(2026, 9, 30, 8, 30, tzinfo=berlin),
        ends_at=datetime(2026, 9, 30, 19, 0, tzinfo=berlin),
        notes='Konferenz / VA Nr. 10719',
        status=Shift.Status.CONFIRMED,
    )
    shift2 = Shift.objects.create(
        client=client,
        location=location,
        position=position,
        starts_at=datetime(2026, 10, 1, 9, 0, tzinfo=berlin),
        ends_at=datetime(2026, 10, 1, 17, 30, tzinfo=berlin),
        notes='Event 10719 Goethe Uni',
        status=Shift.Status.CONFIRMED,
    )
    other = Shift.objects.create(
        client=client,
        location=location,
        position=position,
        starts_at=datetime(2026, 10, 3, 9, 0, tzinfo=berlin),
        ends_at=datetime(2026, 10, 3, 17, 0, tzinfo=berlin),
        notes='Event 99999',
        status=Shift.Status.CONFIRMED,
    )
    return admin, client_user, client, shift1, shift2, other


def test_bulk_plan_matches_all_event_days_but_stays_with_same_customer():
    admin, _, client, shift1, shift2, other = setup_schedule()
    berlin = ZoneInfo('Europe/Berlin')

    # The third day intentionally has no event number in the shift note and no
    # Servicekraft block in the PDF. It should still inherit the established
    # event customer and position context.
    placeholder_location = Location.objects.create(
        client=client,
        name='Siehe Notiz',
        address='',
    )
    alternate_position = Position.objects.create(name='SK')
    shift3 = Shift.objects.create(
        client=client,
        location=placeholder_location,
        position=alternate_position,
        starts_at=datetime(2026, 10, 2, 9, 30, tzinfo=berlin),
        ends_at=datetime(2026, 10, 2, 16, 30, tzinfo=berlin),
        notes='Siehe Notiz',
        status=Shift.Status.CONFIRMED,
    )

    # Even an identical event number on another customer must not receive the
    # document when the PDF context points more strongly to the established
    # customer.
    foreign_client = ClientCompany.objects.create(name='Andere Firma', customer_number='O-2')
    foreign_location = Location.objects.create(
        client=foreign_client,
        name='Andere Location',
        address='Andere Straße 1, Frankfurt am Main',
    )
    foreign_shift = Shift.objects.create(
        client=foreign_client,
        location=foreign_location,
        position=shift1.position,
        starts_at=datetime(2026, 9, 30, 8, 30, tzinfo=berlin),
        ends_at=datetime(2026, 9, 30, 19, 0, tzinfo=berlin),
        notes='Konferenz / VA Nr. 10719',
        status=Shift.Status.CONFIRMED,
    )

    api = APIClient()
    api.force_authenticate(admin)
    response = api.post('/api/shift-plans/bulk-upload/', {'files': [pdf_upload()]}, format='multipart')

    assert response.status_code == 200
    assert response.data['matched_attachments'] == 3
    assert ShiftPlanDocument.objects.count() == 1
    assert ShiftPlanAttachment.objects.filter(shift=shift1).count() == 1
    assert ShiftPlanAttachment.objects.filter(shift=shift2).count() == 1
    assert ShiftPlanAttachment.objects.filter(shift=shift3).count() == 1
    assert ShiftPlanAttachment.objects.filter(shift=foreign_shift).count() == 0
    assert ShiftPlanAttachment.objects.filter(shift=other).count() == 0


def test_client_can_upload_directly_only_to_own_shift():
    _, client_user, client, shift1, _, _ = setup_schedule()
    other_client = ClientCompany.objects.create(name='Other', customer_number='O-1')
    other_location = Location.objects.create(client=other_client, name='Other Site', address='Other')
    other_shift = Shift.objects.create(
        client=other_client,
        location=other_location,
        position=shift1.position,
        starts_at=shift1.starts_at,
        ends_at=shift1.ends_at,
        status=Shift.Status.CONFIRMED,
    )
    api = APIClient()
    api.force_authenticate(client_user)

    allowed = api.post(f'/api/shifts/{shift1.id}/plans/', {'file': pdf_upload()}, format='multipart')
    denied = api.post(f'/api/shifts/{other_shift.id}/plans/', {'file': pdf_upload('10719-copy.pdf')}, format='multipart')

    assert allowed.status_code in {200, 201}
    assert denied.status_code == 403


def test_worker_can_download_plan_only_for_assigned_shift():
    admin, _, _, shift1, _, other = setup_schedule()
    worker_user = User.objects.create_user(email='worker@example.com', password='pw', role=User.Role.WORKER)
    worker = WorkerProfile.objects.create(user=worker_user, employee_number='E-1')
    slot = ShiftSlot.objects.create(shift=shift1, worker=worker, status=ShiftSlot.Status.CLAIMED, source='test')

    admin_api = APIClient()
    admin_api.force_authenticate(admin)
    uploaded = admin_api.post(f'/api/shifts/{shift1.id}/plans/', {'file': pdf_upload()}, format='multipart')
    attachment_id = uploaded.data['id']

    worker_api = APIClient()
    worker_api.force_authenticate(worker_user)
    allowed = worker_api.get(f'/api/shift-plans/attachments/{attachment_id}/download/')
    assert allowed.status_code == 200

    other_upload = admin_api.post(f'/api/shifts/{other.id}/plans/', {'file': pdf_upload('99999.pdf')}, format='multipart')
    denied = worker_api.get(f"/api/shift-plans/attachments/{other_upload.data['id']}/download/")
    assert denied.status_code == 403
