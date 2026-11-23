from datetime import datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

import pytest
from pypdf import PdfReader

from core.models import Shift, TimeEntry
from core.shift_slots import ShiftSlot
from core.stundenzettel import (
    displayed_total, parse_week, render_pdf, weekly_rows,
)

BERLIN = ZoneInfo('Europe/Berlin')


def stamp(value, fold=0):
    return datetime.fromisoformat(value).replace(tzinfo=BERLIN, fold=fold)


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
    for client in (auth_worker, auth_client, api_client):
        assert client.get(path).status_code in (401, 403)
    for week in ('', '2026-W54', '2026-W00', 'nonsense', '2025-W53'):
        assert auth_admin.get(path.replace('2026-W45', week)).status_code == 400
    assert auth_admin.get(path.replace('housekeeping', 'service')).status_code == 400
    response = auth_admin.get(path)
    assert response.status_code == 404
    assert 'geplanten Schichten' in response.json()['detail']


@pytest.mark.django_db
def test_uses_employee_entered_time_not_plan_even_if_pending(auth_admin, worker_user, shift):
    sunday = plan(shift, '2026-11-08T22:30', '2026-11-09T06:45', break_minutes=30)
    TimeEntry.objects.create(
        worker=worker_user.worker_profile, shift=sunday,
        clock_in=stamp('2026-11-08T23:00'), clock_out=stamp('2026-11-09T04:00'),
        break_minutes=45, approved=False,
    )
    # An unfinished timer must not override the actual completed submission.
    TimeEntry.objects.create(
        worker=worker_user.worker_profile, shift=sunday,
        clock_in=stamp('2026-11-08T23:15'), approved=False,
    )
    no_time = plan(
        shift, '2026-11-06T14:30', '2026-11-06T22:45',
        status=Shift.Status.PUBLISHED, break_minutes=30,
    )
    no_time.slots.update(confirmation_status=ShiftSlot.ConfirmationStatus.PENDING)
    plan(shift, '2026-11-09T08:00', '2026-11-09T13:00')
    plan(shift, '2026-11-07T08:00', '2026-11-07T13:00', status=Shift.Status.CANCELLED)

    response = auth_admin.get('/api/reports/stundenzettel.pdf?week=2026-W45&group=front_office')
    assert response.status_code == 200
    assert 'KW45 - 2026' in response['Content-Disposition']
    assert response['Cache-Control'] == 'private, no-store'
    reader = PdfReader(BytesIO(response.content))
    fields = reader.get_fields()
    assert len(fields) == 17
    assert fields['p1_bereich']['/V'] == 'FRONT OFFICE'
    assert fields['p1_hotel']['/V']

    # The no-report shift retains an employee row but never masquerades as
    # the planned 14:30-22:45 working time.
    assert fields['p1_datum_01']['/V'] == '06.11.2026'
    assert [fields[f'p1_{field}_01']['/V'] for field in ('start', 'ende', 'stunden')] == ['', '', '']

    for field, value in (
        ('vorname', 'Anna'), ('nachname', 'Becker'),
        ('datum', '08.11.2026'), ('start', '23:00'),
        ('ende', '04:00'), ('stunden', '5'), ('bestaetigung', 'bestätigt'),
    ):
        assert fields[f'p1_{field}_02']['/V'] == value
    assert fields['p1_gesamt']['/V'] == '5'
    assert fields['p1_gesamt'].get('/Ff', 0) & 1 == 0
    annot = next(
        ref.get_object() for ref in reader.pages[0]['/Annots']
        if ref.get_object().get('/T') == 'p1_start_02'
    )
    assert '/Bl' in annot['/AA']
    assert 'getField' in annot['/AA']['/Bl']['/JS']
    text = reader.pages[0].extract_text()
    assert all(value not in text for value in ('Summe Seite', 'Gesamt Hotel', 'KW ', 'Seite 1/'))
    assert 'Bestätigung Hotel' in text and '(Unterschrift)' in text
    assert all(item.get_object()['/AP']['/N'] for item in reader.pages[0]['/Annots'])


@pytest.mark.django_db
def test_slots_only_actual_workers_no_openshift_but_keep_recorded_released_worker(
    worker_user, shift, second_worker,
):
    planned = plan(shift, '2026-11-11T08:00', '2026-11-11T13:00', group='housekeeping')
    old_slot = planned.slots.get()
    old_slot.status = ShiftSlot.Status.CANCELLED
    old_slot.save()
    ShiftSlot.objects.create(
        shift=planned, worker=second_worker, status=ShiftSlot.Status.CLAIMED,
        confirmation_status=ShiftSlot.ConfirmationStatus.PENDING,
    )
    ShiftSlot.objects.create(shift=planned, status=ShiftSlot.Status.OPEN)
    monday = parse_week('2026-W46')
    rows = [row for hotel in weekly_rows(monday, 'housekeeping').values() for row in hotel]
    assert len(rows) == 1
    assert rows[0]['vorname'] == 'Lukas'
    assert rows[0]['stunden'] == ''
    assert rows[0]['start'] == ''
    assert all(row['vorname'] != 'OpenShift' for row in rows)

    # A completed submitted time is evidence, even after the assignment was
    # released; the cancelled slot's unrecorded mirror alone is not evidence.
    TimeEntry.objects.create(
        worker=worker_user.worker_profile, shift=planned,
        clock_in=stamp('2026-11-11T08:15'), clock_out=stamp('2026-11-11T12:45'),
        approved=True,
    )
    rows = [row for hotel in weekly_rows(monday, 'housekeeping').values() for row in hotel]
    assert len(rows) == 2
    assert {row['vorname'] for row in rows} == {'Lukas', 'Anna'}
    assert next(row for row in rows if row['vorname'] == 'Anna')['stunden'] == '4.5'
    planned.slots.update(status=ShiftSlot.Status.CANCELLED)
    rows = [row for hotel in weekly_rows(monday, 'housekeeping').values() for row in hotel]
    assert len(rows) == 1 and rows[0]['vorname'] == 'Anna'


@pytest.mark.django_db
def test_pagination_hotel_isolation_and_reported_dst(shift):
    monday = parse_week('2026-W43')
    dst = plan(shift, '2026-10-25T01:30', '2026-10-25T03:30', group='housekeeping')
    TimeEntry.objects.create(
        worker=dst.worker, shift=dst,
        clock_in=stamp('2026-10-25T01:30'), clock_out=stamp('2026-10-25T03:30'),
        approved=False, break_minutes=60,
    )
    for _ in range(14):
        plan(shift, '2026-10-20T08:00', '2026-10-20T13:30', group='housekeeping')
    hotels = weekly_rows(monday, 'housekeeping')
    assert [r['stunden'] for rows in hotels.values() for r in rows].count('3') == 1
    key = next(iter(hotels))
    hotels[('another-client', 'another-location', key[2])] = [next(iter(hotels.values()))[0]]
    reader = PdfReader(BytesIO(render_pdf(monday, 'housekeeping', hotels)))
    assert len(reader.pages) == 3
    assert len(reader.get_fields()) == 16 * 7 + 3 * 3
    assert reader.get_fields()['p1_bereich']['/V'] == 'HOUSEKEEPING'
    assert 'FRONT OFFICE' not in reader.pages[0].extract_text()


@pytest.mark.django_db
def test_employee_entered_rounded_hhmm_gross_hours_and_no_break_deduction(shift):
    monday = parse_week('2026-W46')
    planned = plan(
        shift, '2026-11-10T08:00', '2026-11-10T17:00',
        group='housekeeping', break_minutes=60,
    )
    TimeEntry.objects.create(
        worker=planned.worker, shift=planned,
        clock_in=stamp('2026-11-10T08:15').replace(second=40),
        clock_out=stamp('2026-11-10T16:45').replace(second=2),
        break_minutes=60, approved=False,
    )
    hotels = weekly_rows(monday, 'housekeeping')
    rows = [row for group in hotels.values() for row in group]
    assert len(rows) == 1
    assert rows[0]['start'] == '08:15'
    assert rows[0]['ende'] == '16:45'
    assert rows[0]['stunden'] == '8.5'
    assert rows[0]['minutes'] == 510
    fields = PdfReader(BytesIO(render_pdf(monday, 'housekeeping', hotels))).get_fields()
    assert fields['p1_start_01']['/V'] == '08:15'
    assert fields['p1_ende_01']['/V'] == '16:45'
    assert fields['p1_stunden_01']['/V'] == '8.5'
    assert fields['p1_gesamt']['/V'] == '8.5'


@pytest.mark.django_db
def test_uses_latest_completed_submission_without_duplicating_shift(shift):
    monday = parse_week('2026-W46')
    planned = plan(shift, '2026-11-10T08:00', '2026-11-10T17:00')
    earlier = TimeEntry.objects.create(
        shift=planned, worker=planned.worker,
        clock_in=stamp('2026-11-10T08:00'), clock_out=stamp('2026-11-10T17:00'),
        approved=True,
    )
    earlier.updated_at = stamp('2026-11-11T08:00')
    earlier.save(update_fields=['updated_at'])
    later = TimeEntry.objects.create(
        shift=planned, worker=planned.worker,
        clock_in=stamp('2026-11-10T09:00'), clock_out=stamp('2026-11-10T15:00'),
        approved=False,
    )
    later.updated_at = stamp('2026-11-12T08:00')
    later.save(update_fields=['updated_at'])
    rows = [row for group in weekly_rows(monday, 'front_office').values() for row in group]
    assert len(rows) == 1
    assert rows[0]['stunden'] == '6'
    assert rows[0]['start'] == '09:00'


def test_editable_total_matches_visible_rounded_rows():
    entries = [{'stunden': '1.33'}, {'stunden': '1.33'}, {'stunden': '1.33'}]
    assert displayed_total(entries) == '3.99'
