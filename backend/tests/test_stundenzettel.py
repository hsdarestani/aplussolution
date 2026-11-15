from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo
import pytest
from pypdf import PdfReader
from core.models import TimeEntry
from core.stundenzettel import parse_week, weekly_rows, render_pdf
BERLIN = ZoneInfo('Europe/Berlin')

def entry(worker_user, shift, start, end, **kwargs):
    return TimeEntry.objects.create(worker=worker_user.worker_profile, shift=shift,
        clock_in=datetime.fromisoformat(start).replace(tzinfo=BERLIN),
        clock_out=datetime.fromisoformat(end).replace(tzinfo=BERLIN), **kwargs)

@pytest.mark.django_db
def test_export_roles_and_validation(auth_admin, auth_worker, auth_client, api_client):
    path = '/api/reports/stundenzettel.pdf?week=2026-W45&group=housekeeping'
    for client in [auth_worker, auth_client, api_client]:
        assert client.get(path).status_code in (401, 403)
    for week in ['', '2026-W54', '2026-W00', 'nonsense', '2025-W53']:
        assert auth_admin.get(path.replace('2026-W45', week)).status_code == 400
    assert auth_admin.get(path.replace('housekeeping', 'service')).status_code == 400
    assert auth_admin.get(path).status_code == 404

@pytest.mark.django_db
def test_actual_hours_week_boundary_and_exact_emailed_form_wording(auth_admin, worker_user, shift, admin_user):
    shift.schedule_groups = ['front_office']; shift.save()
    entry(worker_user, shift, '2026-11-08T22:30', '2026-11-09T06:30', approved=True, approved_by=admin_user, break_minutes=30)
    entry(worker_user, shift, '2026-11-09T08:00', '2026-11-09T12:00', approved=True)
    entry(worker_user, shift, '2026-11-07T08:00', '2026-11-07T12:00', approved=False)
    entry(worker_user, shift, '2026-11-06T08:00', '2026-11-06T12:00', approved=False, wiw_time_id='historic', break_minutes=0)
    response = auth_admin.get('/api/reports/stundenzettel.pdf?week=2026-W45&group=front_office')
    assert response.status_code == 200
    assert 'KW45 - 2026' in response['Content-Disposition']
    assert response['Cache-Control'] == 'private, no-store'
    reader = PdfReader(BytesIO(response.content)); fields = reader.get_fields()
    for field, value in [('vorname','Anna'),('nachname','Becker'),('datum','08.11.2026'),('start','22:30'),('ende','06:30'),('stunden','7.5'),('bestaetigung','bestätigt')]:
        assert fields[f'p1_{field}_02']['/V'] == value
    assert len(fields) == 14
    assert fields['p1_bestaetigung_01']['/V'] == 'bestätigt'
    text = reader.pages[0].extract_text()
    assert all(value not in text for value in ['Summe Seite', 'Gesamt Hotel', 'KW ', 'Seite 1/'])
    assert 'Bestätigung Hotel' in text
    assert '(Unterschrift)' in text
    assert '11.5' in reader.pages[0].extract_text()
    assert 'Hotel Spenerhaus' not in reader.pages[0].extract_text()
    for widget in reader.pages[0]['/Annots']:
        assert widget.get_object()['/AP']['/N']

@pytest.mark.django_db
def test_pagination_hotel_isolation_and_dst(worker_user, shift):
    shift.schedule_groups = ['housekeeping']; shift.save()
    monday = parse_week('2026-W43')
    entry(worker_user, shift, '2026-10-25T01:30', '2026-10-25T03:30', approved=True, break_minutes=0)
    for index in range(14):
        entry(worker_user, shift, '2026-10-20T08:00', '2026-10-20T13:30', approved=True, break_minutes=0)
    hotels = weekly_rows(monday, 'housekeeping')
    assert [row['stunden'] for rows in hotels.values() for row in rows].count('3') == 1
    key = next(iter(hotels))
    hotels[('another-client', 'another-location', key[2])] = [next(iter(hotels.values()))[0]]
    reader = PdfReader(BytesIO(render_pdf(monday, 'housekeeping', hotels)))
    assert len(reader.pages) == 3
    assert len(reader.get_fields()) == 16 * 7
    assert 'HOUSEKEEPING' in reader.pages[0].extract_text()
    assert 'FRONT OFFICE' not in reader.pages[0].extract_text()
    assert 'Hotel Spenerhaus' not in reader.pages[0].extract_text()
