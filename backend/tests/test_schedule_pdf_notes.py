from io import BytesIO

import pytest
from django.utils import timezone
from pypdf import PdfReader


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
