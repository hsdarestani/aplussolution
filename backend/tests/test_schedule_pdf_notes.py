from datetime import timedelta
from io import BytesIO

import pytest
from django.utils import timezone
from pypdf import PdfReader

from core.models import Shift
from core.schedule_reports import _report_rows


@pytest.mark.django_db
def test_schedule_pdf_shows_shift_notes_and_hides_pause(auth_admin, shift):
    shift.notes = 'Testnotiz 12345\nBitte Seiteneingang nutzen'
    shift.break_minutes = 30
    shift.save(update_fields=['notes', 'break_minutes', 'updated_at'])

    day = timezone.localtime(shift.starts_at).date().isoformat()
    response = auth_admin.get(f'/api/reports/schedule.pdf?date_from={day}&date_to={day}')

    assert response.status_code == 200
    assert response['Content-Type'] == 'application/pdf'

    reader = PdfReader(BytesIO(response.content))
    text = '\n'.join(page.extract_text() or '' for page in reader.pages)

    assert 'Testnotiz 12345' in text
    assert 'Bitte Seiteneingang nutzen' in text
    assert 'Pause 30 Min' not in text
    assert 'Pause' not in text


@pytest.mark.django_db
def test_schedule_pdf_rows_repeat_openshift_for_every_free_capacity(company, location, position):
    start = timezone.now() + timedelta(days=7)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=start,
        ends_at=start + timedelta(hours=6),
        status=Shift.Status.PUBLISHED,
        required_count=2,
    )

    rows = _report_rows({
        'start': timezone.localtime(shift.starts_at).date(),
        'end': timezone.localtime(shift.starts_at).date(),
        'workers': [],
        'clients': [],
        'locations': [],
        'groups': [],
    })

    row = next(item for item in rows if item['date'] == timezone.localtime(shift.starts_at).date())
    assert row['worker_labels'].count('OpenShift') == 2
