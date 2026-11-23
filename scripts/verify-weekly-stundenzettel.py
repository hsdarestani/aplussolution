# Production verification; strictly read-only, with no employee names in logs.
from collections import Counter
from datetime import datetime, timedelta, timezone as utc_timezone
from decimal import Decimal
from io import BytesIO

from django.urls import resolve
from pypdf import PdfReader
from rest_framework.test import APIRequestFactory, force_authenticate

from core.models import Shift, TimeEntry, User
from core.mobile_schedule import mobile_schedule
from core.schedule_reports import _shift_groups
from core.stundenzettel import (
    BERLIN, GROUPS, TEMPLATE, decimal_hours,
    export_stundenzettel, parse_week, weekly_rows,
)

assert resolve('/api/reports/stundenzettel.pdf').func == export_stundenzettel
assert TEMPLATE.is_file() and not PdfReader(TEMPLATE).get_fields()

admin = User.objects.filter(role=User.Role.ADMIN, is_active=True).first()
assert admin is not None
factory = APIRequestFactory()
week = '2026-W46'
monday = parse_week(week)

request = factory.get(
    '/api/mobile/schedule/',
    {'date_from': str(monday), 'date_to': str(monday + timedelta(days=6))},
    HTTP_HOST='app.aplus-solution.de', secure=True,
)
force_authenticate(request, user=admin)
schedule = mobile_schedule(request)
assert schedule.status_code == 200

for group in GROUPS:
    hotels = weekly_rows(monday, group)
    rows = [row for records in hotels.values() for row in records]
    assert rows, f'No assigned shifts in {group} for chosen week'
    assert all(row['vorname'] != 'OpenShift' for row in rows)

    # Independent check: each output interval must come from the latest
    # finished employee TimeEntry for that shift, not from planned clock time.
    shifts = {
        str(shift.pk): shift for shift in Shift.objects.filter(
            pk__in=[row['shift_id'] for row in rows]
        )
    }
    time_entries = {}
    for entry in TimeEntry.objects.filter(
        shift_id__in=[s.pk for s in shifts.values()],
        clock_out__isnull=False,
    ).order_by('updated_at', 'pk'):
        if entry.clock_out <= entry.clock_in:
            continue
        first = entry.clock_in.astimezone(BERLIN).replace(second=0, microsecond=0)
        last = entry.clock_out.astimezone(BERLIN).replace(second=0, microsecond=0)
        minutes = int(
            (last.astimezone(utc_timezone.utc) -
             first.astimezone(utc_timezone.utc)).total_seconds() // 60
        )
        if minutes > 0:
            time_entries[(str(entry.shift_id), str(entry.worker_id))] = (first, last, minutes)

    for row in rows:
        shift = shifts[row['shift_id']]
        assert shift.status != Shift.Status.CANCELLED
        assert group in _shift_groups(shift)
        recorded = time_entries.get((row['shift_id'], row['worker_id']))
        if recorded is None:
            assert row['start'] == row['ende'] == row['stunden'] == ''
            assert row['minutes'] is None
        else:
            first, last, minutes = recorded
            assert row['datum'] == first.strftime('%d.%m.%Y')
            assert row['start'] == first.strftime('%H:%M')
            assert row['ende'] == last.strftime('%H:%M')
            assert row['stunden'] == decimal_hours(minutes)
            assert row['minutes'] == minutes

    request = factory.get(
        '/api/reports/stundenzettel.pdf', {'week': week, 'group': group},
    )
    force_authenticate(request, user=admin)
    response = export_stundenzettel(request)
    assert response.status_code == 200, (group, response.status_code)

    reader = PdfReader(BytesIO(response.content))
    fields = reader.get_fields()
    assert reader.pages and fields
    actual = []
    for name in fields:
        if '_datum_' in name:
            prefix, index = name.split('_datum_')
            actual.append(tuple(
                fields[f'{prefix}_{field}_{index}']['/V']
                for field in ('datum', 'vorname', 'nachname', 'start', 'ende', 'stunden')
            ))
    expected = [
        tuple(row[field] for field in (
            'datum', 'vorname', 'nachname', 'start', 'ende', 'stunden',
        )) for row in rows
    ]
    assert Counter(actual) == Counter(expected), (group, 'PDF differs from recorded worker hours')

    for page_no, page in enumerate(reader.pages, 1):
        ids = [name for name in fields if name.startswith(f'p{page_no}_stunden_')]
        page_sum = sum(
            (Decimal(str(fields[name]['/V'])) for name in ids
             if str(fields[name]['/V']).strip()), Decimal('0'),
        )
        assert Decimal(str(fields[f'p{page_no}_gesamt']['/V'])) == page_sum
        assert fields[f'p{page_no}_hotel']['/V']
        assert fields[f'p{page_no}_bereich']['/V'] == GROUPS[group][1]
        content = page.extract_text()
        assert 'Bestätigung Hotel' in content
        assert '(Unterschrift)' in content
    assert all(
        field['/V'] == 'bestätigt' for name, field in fields.items()
        if '_bestaetigung_' in name
    )
    assert all(
        not field['/V'] for name, field in fields.items()
        if '_stunden_' in name and not field['/V']
    )
    total = sum(Decimal(row['stunden']) for row in rows if row['stunden'])
    print(
        'LIVE_REPORTED_STUNDENZETTEL_MATCHES_EMPLOYEE_TIMES',
        group, 'week', week, 'rows', len(rows),
        'reported_rows', sum(bool(row['stunden']) for row in rows),
        'hours', str(total), 'pages', len(reader.pages),
    )
print('LIVE_REPORTED_STUNDENZETTEL_BOTH_DEPARTMENTS_VERIFIED')
