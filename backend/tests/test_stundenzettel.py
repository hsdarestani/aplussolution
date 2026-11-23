from datetime import datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from pypdf import PdfReader

from core.models import Shift, TimeEntry
from core.shift_slots import ShiftSlot
from core.stundenzettel import (
    _rounded_recorded_interval, displayed_total, parse_week, render_pdf, weekly_rows,
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

    # No completed employee time: exact unrounded PLAN appears, explicitly
    # marked as a plan estimate rather than verified employee attendance.
    assert fields['p1_datum_01']['/V'] == '06.11.2026'
    assert [fields[f'p1_{field}_01']['/V'] for field in ('start', 'ende', 'stunden')] == [
        '14:30', '22:45', '8.25',
    ]
    assert fields['p1_bestaetigung_01']['/V'] == 'PLAN (nicht erfasst)'

    for field, value in (
        ('vorname', 'Anna'), ('nachname', 'Becker'),
        ('datum', '08.11.2026'), ('start', '23:00'),
        ('ende', '04:00'), ('stunden', '5'), ('bestaetigung', 'bestätigt'),
    ):
        assert fields[f'p1_{field}_02']['/V'] == value
    assert fields['p1_gesamt']['/V'] == '13.25'
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
    assert rows[0]['stunden'] == '5'
    assert rows[0]['start'] == '08:00'
    assert rows[0]['ende'] == '13:00'
    assert rows[0]['source'] == 'PLAN'
    assert rows[0]['bestaetigung'] == 'PLAN (nicht erfasst)'
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
    assert next(row for row in rows if row['vorname'] == 'Anna')['source'] == 'IST'
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
    assert rows[0]['source'] == 'IST'
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
    TimeEntry.objects.filter(pk=earlier.pk).update(updated_at=stamp('2026-11-11T08:00'))
    later = TimeEntry.objects.create(
        shift=planned, worker=planned.worker,
        clock_in=stamp('2026-11-10T09:00'), clock_out=stamp('2026-11-10T15:00'),
        approved=False,
    )
    TimeEntry.objects.filter(pk=later.pk).update(updated_at=stamp('2026-11-12T08:00'))
    rows = [row for group in weekly_rows(monday, 'front_office').values() for row in group]
    assert len(rows) == 1
    assert rows[0]['stunden'] == '6'
    assert rows[0]['start'] == '09:00'
    assert rows[0]['source'] == 'IST'


def test_editable_total_matches_visible_rounded_rows():
    entries = [{'stunden': '1.33'}, {'stunden': '1.33'}, {'stunden': '1.33'}]
    assert displayed_total(entries) == '3.99'
    assert displayed_total(entries + [{'stunden': ''}]) == '3.99'
    assert displayed_total([{'stunden': ''}]) == '0'


@pytest.mark.parametrize(
    'started,ended,start_label,end_label,expected_minutes',
    [
        ('2026-11-10T11:10', '2026-11-10T12:10', '11:00', '12:15', 75),
        ('2026-11-10T11:00', '2026-11-10T11:15', '11:00', '11:15', 15),
        ('2026-11-10T11:20', '2026-11-10T11:40', '11:15', '11:45', 30),
        ('2026-11-10T11:59', '2026-11-10T12:01', '11:45', '12:15', 30),
        ('2026-11-10T23:58', '2026-11-11T00:02', '23:45', '00:15', 30),
        ('2026-03-29T01:50', '2026-03-29T03:10', '01:45', '03:15', 30),
    ],
)
def test_outward_quarter_rounding_preserves_full_interval(
    started, ended, start_label, end_label, expected_minutes,
):
    entry = SimpleNamespace(clock_in=stamp(started), clock_out=stamp(ended))
    start, end, minutes = _rounded_recorded_interval(entry)
    assert (start.strftime('%H:%M'), end.strftime('%H:%M'), minutes) == (
        start_label, end_label, expected_minutes,
    )
    assert start.astimezone(ZoneInfo('UTC')) <= entry.clock_in.astimezone(ZoneInfo('UTC'))
    assert end.astimezone(ZoneInfo('UTC')) >= entry.clock_out.astimezone(ZoneInfo('UTC'))


def test_quarter_rounding_dst_fold_uses_real_elapsed_time():
    entry = SimpleNamespace(
        clock_in=stamp('2026-10-25T02:10', fold=0),
        clock_out=stamp('2026-10-25T02:10', fold=1),
    )
    first, last, minutes = _rounded_recorded_interval(entry)
    assert (first.strftime('%H:%M'), last.strftime('%H:%M')) == ('02:00', '02:15')
    assert minutes == 75


@pytest.mark.django_db
def test_report_rounds_submitted_hhmm_outwards_without_changing_timeentry(shift):
    monday = parse_week('2026-W46')
    planned = plan(shift, '2026-11-10T08:00', '2026-11-10T17:00', group='housekeeping')
    entry = TimeEntry.objects.create(
        worker=planned.worker, shift=planned,
        clock_in=stamp('2026-11-10T08:10'), clock_out=stamp('2026-11-10T17:10'),
        break_minutes=60, approved=False,
    )
    hotels = weekly_rows(monday, 'housekeeping')
    row = next(iter(hotels.values()))[0]
    assert [row[key] for key in ('start', 'ende', 'stunden', 'minutes')] == [
        '08:00', '17:15', '9.25', 555,
    ]
    fields = PdfReader(BytesIO(render_pdf(monday, 'housekeeping', hotels))).get_fields()
    assert fields['p1_start_01']['/V'] == '08:00'
    assert fields['p1_ende_01']['/V'] == '17:15'
    assert fields['p1_stunden_01']['/V'] == '9.25'
    assert fields['p1_gesamt']['/V'] == '9.25'
    entry.refresh_from_db()
    assert entry.clock_in.astimezone(BERLIN).strftime('%H:%M') == '08:10'
    assert entry.clock_out.astimezone(BERLIN).strftime('%H:%M') == '17:10'
    pdf = PdfReader(BytesIO(render_pdf(monday, 'housekeeping', hotels)))
    widget = next(
        item.get_object() for item in pdf.pages[0]['/Annots']
        if item.get_object().get('/T') == 'p1_start_01'
    )
    script = str(widget['/AA']['/Bl']['/JS'])
    assert 'Math.floor(a/15)' in script
    assert 'Math.ceil(b/15)' in script
    assert r'\d{1,2}' in script


@pytest.mark.django_db
def test_no_submitted_ist_uses_exact_plan_for_each_department_and_sums(shift):
    monday = parse_week('2026-W46')
    planned = plan(
        shift, '2026-11-10T08:07', '2026-11-10T17:11',
        group='housekeeping', break_minutes=60,
    )
    TimeEntry.objects.create(
        shift=planned, worker=planned.worker,
        clock_in=stamp('2026-11-10T08:30'), clock_out=None,
        approved=False,
    )  # a running but incomplete timer is NOT a valid completed IST record

    rows = [r for group in weekly_rows(monday, 'housekeeping').values() for r in group]
    assert len(rows) == 1
    assert [rows[0][key] for key in ('start', 'ende', 'stunden', 'source', 'minutes')] == [
        '08:07', '17:11', '9.07', 'PLAN', 544,
    ]
    assert rows[0]['bestaetigung'] == 'PLAN (nicht erfasst)'
    fields = PdfReader(BytesIO(
        render_pdf(monday, 'housekeeping', weekly_rows(monday, 'housekeeping'))
    )).get_fields()
    assert fields['p1_start_01']['/V'] == '08:07'
    assert fields['p1_ende_01']['/V'] == '17:11'
    assert fields['p1_stunden_01']['/V'] == '9.07'
    assert fields['p1_gesamt']['/V'] == '9.07'
    assert fields['p1_bestaetigung_01']['/V'] == 'PLAN (nicht erfasst)'
    original_shift_id = planned.pk

    # The second department uses the same fallback rule; the original
    # employee time and shift schedule are never modified.
    another = plan(
        shift, '2026-11-11T09:05', '2026-11-11T15:05',
        group='front_office', break_minutes=30,
    )
    front = [r for group in weekly_rows(monday, 'front_office').values() for r in group]
    assert len(front) == 1
    assert front[0]['source'] == 'PLAN'
    assert (front[0]['start'], front[0]['ende'], front[0]['stunden']) == ('09:05', '15:05', '6')
    assert TimeEntry.objects.filter(shift=another).count() == 0
    assert TimeEntry.objects.filter(shift_id=original_shift_id, clock_out__isnull=True).count() == 1


@pytest.mark.django_db
def test_mixed_ist_and_plan_rows_only_round_ist_and_total_both(shift, second_worker):
    monday = parse_week('2026-W46')
    scheduled = plan(
        shift, '2026-11-10T08:07', '2026-11-10T17:11', group='front_office',
        break_minutes=60,
    )
    ShiftSlot.objects.create(
        shift=scheduled, worker=second_worker,
        status=ShiftSlot.Status.CLAIMED,
    )
    TimeEntry.objects.create(
        shift=scheduled, worker=scheduled.worker,
        clock_in=stamp('2026-11-10T08:10'), clock_out=stamp('2026-11-10T17:10'),
        break_minutes=60, approved=False,
    )
    hotels = weekly_rows(monday, 'front_office')
    rows = [r for group in hotels.values() for r in group]
    assert len(rows) == 2
    by_name = {row['vorname']: row for row in rows}
    assert (by_name['Anna']['start'], by_name['Anna']['ende'],
            by_name['Anna']['stunden'], by_name['Anna']['source']) == (
        '08:00', '17:15', '9.25', 'IST')
    assert (by_name['Lukas']['start'], by_name['Lukas']['ende'],
            by_name['Lukas']['stunden'], by_name['Anna']['source']) == (
        '08:07', '17:11', '9.07', 'PLAN')
    assert displayed_total(rows) == '18.32'
    reader = PdfReader(BytesIO(render_pdf(monday, 'front_office', hotels)))
    fields = reader.get_fields()
    assert fields['p1_gesamt']['/V'] == '18.32'
    assert sorted(fields[f'p1_bestaetigung_{i:02}']['/V'] for i in (1, 2)) == [
        'PLAN (nicht erfasst)', 'bestätigt',
    ]
