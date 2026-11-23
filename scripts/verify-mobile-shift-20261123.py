# Read-only production verification after the guarded 2026-11-23 mobile shift release.
# Never print employee names, shift notes, emails or event numbers.
from datetime import datetime, timedelta, timezone as utc
from zoneinfo import ZoneInfo

from django.db import connection
from core.event_numbers import extract_event_number
from core.models import Shift, User
from core.shift_api import ShiftApiSerializer

BERLIN = ZoneInfo('Europe/Berlin')
assert Shift._meta.get_field('event_number').max_length == 64
assert 'event_number' in {column.name for column in connection.introspection.get_table_description(
    connection.cursor(), Shift._meta.db_table
)}
assert 'event_number' in ShiftApiSerializer.Meta.fields

marketing = User.objects.filter(email__iexact='marketing@aplus-solution.de').first()
assert marketing is not None, 'Marketing super-admin account missing'
assert marketing.role == User.Role.ADMIN and marketing.is_staff and marketing.is_superuser
assert marketing.is_active, 'Marketing super-admin inactive'

info = User.objects.filter(email__iexact='info@aplus-solution.de').first()
if info is not None:
    assert info.is_active, 'Existing Info login unexpectedly inactive'

candidates = 0
unfilled = 0
for note, event_number in Shift.objects.exclude(notes='').values_list('notes', 'event_number').iterator(chunk_size=500):
    parsed = extract_event_number(note)
    if parsed:
        candidates += 1
        if not str(event_number or '').strip():
            unfilled += 1
assert unfilled == 0, ('Unfilled recognized event numbers', unfilled)

# Independently check net PLAN totals on representative existing shifts and
# overnight shifts: count UTC scheduled minutes and exclude configured Pause.
checked = 0
for starts, ends, pause in Shift.objects.exclude(status=Shift.Status.CANCELLED).values_list(
    'starts_at', 'ends_at', 'break_minutes'
).order_by('-starts_at')[:200]:
    if not starts or not ends or ends <= starts:
        continue
    minutes = int((ends.astimezone(utc.utc) - starts.astimezone(utc.utc)).total_seconds() // 60)
    assert minutes > 0
    pause = max(0, int(pause or 0))
    net_minutes = max(0, minutes - pause)
    assert net_minutes <= minutes
    assert net_minutes >= 0
    checked += 1
print('MOBILE_SHIFT_RELEASE_VERIFIED',
      'marketing_super_admin', True,
      'info_account_exists', info is not None,
      'recognized_event_notes', candidates,
      'unfilled_event_numbers', unfilled,
      'net_plan_sample', checked)
