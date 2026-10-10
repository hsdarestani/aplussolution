"""Backfill statutory Hessen holiday evidence without rebuilding paid balances.

Historical monthly attendance evidence is updated in place; the existing
IST, SOLL, Saldo, Lexware and gross salary values are never recalculated.
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import migrations

BERLIN = ZoneInfo('Europe/Berlin')
HOLIDAYS_2026 = {
    date(2026, 1, 1): ('Neujahr', 125),
    date(2026, 4, 3): ('Karfreitag', 125),
    date(2026, 4, 6): ('Ostermontag', 125),
    date(2026, 5, 1): ('Tag der Arbeit', 150),
    date(2026, 5, 14): ('Christi Himmelfahrt', 125),
    date(2026, 5, 25): ('Pfingstmontag', 125),
    date(2026, 6, 4): ('Fronleichnam', 125),
    date(2026, 10, 3): ('Tag der Deutschen Einheit', 125),
    date(2026, 12, 25): ('1. Weihnachtsfeiertag', 150),
    date(2026, 12, 26): ('2. Weihnachtsfeiertag', 150),
}


def _local_dt(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.astimezone(BERLIN) if result.tzinfo else result.replace(tzinfo=BERLIN)
    except (ValueError, TypeError):
        return None


def _holiday_fields(raw):
    local_start = _local_dt(raw.get('local_clock_in') or raw.get('clock_in'))
    local_end = _local_dt(raw.get('local_clock_out') or raw.get('clock_out'))
    if not local_start or not local_end or local_end <= local_start:
        return 0, []
    gross = max(0, int((local_end - local_start).total_seconds() // 60))
    net = max(0, int(raw.get('worked_minutes') or 0))
    factor = Decimal(net) / Decimal(gross) if gross else Decimal('0')
    total = 0
    details = []
    cursor = local_start.date()
    while cursor <= local_end.date():
        holiday = HOLIDAYS_2026.get(cursor)
        if holiday:
            day_start = datetime.combine(cursor, time.min, tzinfo=BERLIN)
            day_end = day_start + timedelta(days=1)
            overlap = max(0, int((min(local_end, day_end) - max(local_start, day_start)).total_seconds() // 60))
            if overlap:
                minutes = int((Decimal(overlap) * factor).quantize(Decimal('1')))
                total += minutes
                details.append({
                    'date': cursor.isoformat(),
                    'name': holiday[0],
                    'minutes': minutes,
                    'tax_exempt_ceiling_percent': holiday[1],
                })
        cursor += timedelta(days=1)
    return total, details


def backfill(apps, schema_editor):
    TimeEntry = apps.get_model('core', 'TimeEntry')
    Record = apps.get_model('core', 'WorkingTimeAccountRecord')
    # Imported WIW history remains read-only. Closed historical evidence requires no admin action.
    TimeEntry.objects.filter(
        wiw_time_id__isnull=False, clock_out__isnull=False, approved=False
    ).update(approved=True, approved_by=None)

    for row in Record.objects.filter(year_month__year=2026).iterator(chunk_size=200):
        old_entries = row.raw_entries or []
        changed = False
        updated = []
        for previous in old_entries:
            if not isinstance(previous, dict):
                updated.append(previous)
                continue
            entry = dict(previous)
            if 'holiday_minutes' not in entry:
                minutes, details = _holiday_fields(entry)
                entry['holiday_minutes'] = minutes
                entry['holiday_details'] = details
                entry['holiday_surcharge_percent'] = '0.00'
                entry['holiday_surcharge_amount'] = '0.00'
                changed = True
            updated.append(entry)
        if changed:
            Record.objects.filter(pk=row.pk).update(raw_entries=updated)


class Migration(migrations.Migration):
    dependencies = [('core', '0055_hessen_holiday_surcharge_setting')]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
