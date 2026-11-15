from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo
import pytest
from pypdf import PdfReader
from core.models import Shift, TimeEntry
from core.shift_slots import ShiftSlot
from core.stundenzettel import parse_week, weekly_rows, render_pdf
BERLIN = ZoneInfo('Europe/Berlin')

def stamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=BERLIN)

def plan(shift, start, end, group='front_office', **changes):
    shift.pk = None
    shift.wiw_shift_id = None
    shift.starts_at = stamp(start)
    shift.ends_at = stamp(end)
    shift.schedule_groups = [group]
    shift.break_minutes = 0
    for name, value in changes.items():
        setattr(shift, name, value)
    shift.save()
    if shift.worker_id:
        shift.slots.update(worker=shift.worker, status=ShiftSlot.Status.CLAIMED)
    return shift

@pytest.mark.django_db
def test_export_roles_and_validation(auth_admin, auth_worker, auth_client, api_client):
    path = '/api/reports/stundenzettel.pdf?week=2026-W45&group=housekeeping'
    for client in [auth_worker, auth_client, api_client]:
        assert client.get(path).status_code in (401, 403)
    for week in ['', '2026-W54', '2026-W00', 'nonsense', '2025-W53']:
        assert auth_admin.get(path.replace('2026-W45', week)).status_code == 400
    assert auth_admin.get(path.replace('housekeeping', 'service')).status_code == 400
    response = auth_admin.get(path)
    assert response.status_code == 404
    assert 'geplanten Schichten' in response.json()['detail']

@pytest.mark.django_db
def test_all_planned_shifts_even_without_or_with_pending_conflicting_time(auth_admin, worker_user, shift):
    sunday = plan(shift, '2026-11-08T22:30', '2026-11-09T06:45', break_minutes=30)
    TimeEntry.objects.create(worker=worker_user.worker_profile, shift=sunday,
        clock_in=stamp('2026-11-08T23:00'), clock_out=stamp('2026-11-09T04:00'), approved=True)
    # A second entry cannot duplicate or override the planned card.
    TimeEntry.objects.create(worker=worker_user.worker_profile, shift=sunday,
        clock_in=stamp('2026-11-08T22:00'), approved=False)
    no_time = plan(shift, '2026-11-06T14:30', '2026-11-06T22:45', status=Shift.Status.PUBLISHED, break_minutes=30)
    no_time.slots.update(confirmation_status=ShiftSlot.ConfirmationStatus.PENDING)
    plan(shift, '2026-11-09T08:00', '2026-11-09T13:00')
    plan(shift, '2026-11-07T08:00', '2026-11-07T13:00', status=Shift.Status.CANCELLED)
    response = auth_admin.get('/api/reports/stundenzettel.pdf?week=2026-W45&group=front_office')
    assert response.status_code == 200
    assert 'KW45 - 2026' in response['Content-Disposition']
    assert response['Cache-Control'] == 'private, no-store'
    reader = PdfReader(BytesIO(response.content)); fields = reader.get_fields()
    for field, value in [('vorname','Anna'),('nachname','Becker'),('datum','08.11.2026'),('start','22:30'),('ende','06:45'),('stunden','7.75'),('bestaetigung','bestätigt')]:
        assert fields[f'p1_{field}_02']['/V'] == value
    assert len(fields) == 14
    assert fields['p1_bestaetigung_01']['/V'] == 'bestätigt'
    text = reader.pages[0].extract_text()
    assert all(value not in text for value in ['Summe Seite', 'Gesamt Hotel', 'KW ', 'Seite 1/'])
    assert 'Bestätigung Hotel' in text and '(Unterschrift)' in text
    assert '15.5' in text
    for widget in reader.pages[0]['/Annots']:
        assert widget.get_object()['/AP']['/N']

@pytest.mark.django_db
def test_active_slot_cards_include_all_workers_and_open_places_without_stale_mirror(shift, second_worker):
    planned = plan(shift, '2026-11-11T08:00', '2026-11-11T13:00', group='housekeeping')
    old_slot = planned.slots.get()
    old_slot.status = ShiftSlot.Status.CANCELLED; old_slot.save()
    ShiftSlot.objects.create(shift=planned, worker=second_worker, status=ShiftSlot.Status.CLAIMED,
        confirmation_status=ShiftSlot.ConfirmationStatus.PENDING)
    ShiftSlot.objects.create(shift=planned, status=ShiftSlot.Status.OPEN)
    rows = [r for hotel in weekly_rows(parse_week('2026-W46'), 'housekeeping').values() for r in hotel]
    assert len(rows) == 2
    assert {r['vorname'] for r in rows} == {'Lukas', 'OpenShift'}
    assert sum(r['minutes'] for r in rows) == 600
    planned.slots.update(status=ShiftSlot.Status.CANCELLED)
    assert not weekly_rows(parse_week('2026-W46'), 'housekeeping')

@pytest.mark.django_db
def test_pagination_hotel_isolation_and_planned_dst(shift):
    monday = parse_week('2026-W43')
    plan(shift, '2026-10-25T01:30', '2026-10-25T03:30', group='housekeeping')
    for index in range(14):
        plan(shift, '2026-10-20T08:00', '2026-10-20T13:30', group='housekeeping')
    hotels = weekly_rows(monday, 'housekeeping')
    assert [r['stunden'] for rows in hotels.values() for r in rows].count('3') == 1
    key = next(iter(hotels))
    hotels[('another-client', 'another-location', key[2])] = [next(iter(hotels.values()))[0]]
    reader = PdfReader(BytesIO(render_pdf(monday, 'housekeeping', hotels)))
    assert len(reader.pages) == 3
    assert len(reader.get_fields()) == 16 * 7
    assert 'HOUSEKEEPING' in reader.pages[0].extract_text()
    assert 'FRONT OFFICE' not in reader.pages[0].extract_text()
