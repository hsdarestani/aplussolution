from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


ROLE_PATTERNS = (
    (r'\bserviceleit(?:ung|er|erin|ungen)?\b', 'Serviceleitung'),
    (r'\bservicekr(?:a|ä)ft(?:e|en)?\b|\bservicekraft\b', 'Servicekraft'),
    (r'\bfront[\s-]*office\b|\brezeption\b|\breception\b', 'Front Office'),
    (r'\bhouse[\s-]*keeping\b|\bhousekeeping\b', 'Housekeeping'),
    (r'\bbar(?:kraft|kräfte|kraefte)?\b', 'Bar'),
)

INLINE_ASSIGNMENT_LINE_RE = re.compile(
    r'^\s*(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b'
    r'(?=[^\n]*\b(?:dienst|schicht)\b)[^\n]*?\s[-–—]\s*'
    r'([A-Za-zÄÖÜäöüßÀ-ÿ][A-Za-zÄÖÜäöüßÀ-ÿ\'’ .-]{1,79})\s*$',
    flags=re.I | re.M,
)


def _first(pattern: str, text: str, flags=re.I | re.M):
    match = re.search(pattern, text or '', flags=flags)
    return match.groups() if match else None


def _date(text: str) -> str:
    match = _first(r'\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b', text)
    if match:
        day, month, year = map(int, match)
        return f'{year:04d}-{month:02d}-{day:02d}'
    match = _first(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b', text)
    if match:
        year, month, day = map(int, match)
        return f'{year:04d}-{month:02d}-{day:02d}'
    return ''


def _times(text: str) -> tuple[str, str]:
    match = _first(
        r'\bvon\s+(\d{1,2})(?::(\d{1,2}))?\s*(?:uhr\s*)?(?:-|–|—|bis)\s*(\d{1,2})(?::(\d{1,2}))?\s*(?:uhr)?\b',
        text,
    )
    if not match:
        return '', ''
    start_h, start_m, end_h, end_m = match
    return f'{int(start_h):02d}:{int(start_m or 0):02d}', f'{int(end_h):02d}:{int(end_m or 0):02d}'


def _total_count(text: str) -> int | None:
    match = re.search(r'\b(?:insgesamt|gesamt)\s+(\d+)\s+(?:offene\s+)?schicht(?:en)?\b', text or '', flags=re.I)
    return max(1, int(match.group(1))) if match else None


def _count(text: str) -> int | None:
    # "Erstelle 5 Schichten ..." means five identical slots and is intentionally
    # represented by one descriptor with count=5. By contrast, "insgesamt 15
    # Schichten" is a total for a detailed roster and must never overwrite every
    # parsed row with count=15.
    match = re.search(r'\b(\d+)\s+(?:offene\s+)?schicht(?:en)?\b', text or '', flags=re.I)
    if not match:
        return None
    prefix = (text or '')[max(0, match.start() - 24):match.start()]
    if re.search(r'\b(?:insgesamt|gesamt)\s*$', prefix, flags=re.I):
        return None
    return max(1, int(match.group(1)))


def _role(text: str) -> str:
    for pattern, role in ROLE_PATTERNS:
        if re.search(pattern, text or '', flags=re.I):
            return role
    return ''


def _site_and_location(text: str) -> tuple[str, str]:
    # Covers natural input such as:
    # "Servicekräfte für Marthas in der Akademie als Standort."
    match = re.search(
        r'\bf(?:ü|ue)r\s+([^\n.,;]+?)\s+in\s+(?:(?:der|dem|den)\s+)?([^\n.,;]+?)\s+als\s+standort\b',
        text or '',
        flags=re.I,
    )
    if match:
        return match.group(1).strip(' -'), match.group(2).strip(' -')

    location = _first(r'\bstandort\s*:?[ \t]*([^\n.,;]+)', text)
    client = _first(r'\b(?:kunde|auftraggeber)\s*:?[ \t]*([^\n.,;]+)', text)
    return (client[0].strip() if client else ''), (location[0].strip() if location else '')


def _note(text: str) -> str:
    match = re.search(r'^\s*notiz\s*:?[ \t]*(.+?)\s*$', text or '', flags=re.I | re.M)
    return match.group(1).strip() if match else ''


def _assignment_key(value: str) -> str:
    return re.sub(r'[^a-z0-9äöüß]+', ' ', str(value or '').casefold()).strip()


def _inline_assignments(text: str) -> dict[str, str]:
    """Extract per-date assignments written as e.g. ``24.10.2026 Nachtdienst - Solomon``.

    The model sometimes places the trailing employee name into ``notes`` instead
    of returning it as an assignment. Treat the explicit roster syntax as the
    authoritative source, but only when a date has one unambiguous name.
    """
    by_date: dict[str, list[str]] = {}
    for day, month, year, raw_name in INLINE_ASSIGNMENT_LINE_RE.findall(text or ''):
        name = raw_name.strip(' -–—')
        if not name:
            continue
        date_key = f'{int(year):04d}-{int(month):02d}-{int(day):02d}'
        by_date.setdefault(date_key, []).append(name)

    result: dict[str, str] = {}
    for date_key, names in by_date.items():
        unique: dict[str, str] = {}
        for name in names:
            unique.setdefault(_assignment_key(name), name)
        if len(unique) == 1:
            result[date_key] = next(iter(unique.values()))
    return result


def normalize_order_request(raw_text: str, parsed: dict[str, Any] | None = None) -> dict[str, Any]:
    """Overlay explicit German instructions on top of the LLM result.

    A simple instruction such as "Erstelle 5 Schichten für den 10.10..." keeps
    one descriptor with ``count=5``. A detailed roster with an aggregate phrase
    such as "insgesamt 15 Schichten" keeps all individually parsed rows so the
    admin can inspect every shift before approval.
    """
    source = deepcopy(parsed or {}) if isinstance(parsed, dict) else {}
    existing = source.get('shifts') if isinstance(source.get('shifts'), list) else []

    date_value = _date(raw_text)
    start_time, end_time = _times(raw_text)
    count_value = _count(raw_text)
    total_count = _total_count(raw_text)
    role_value = _role(raw_text)
    site_value, location_value = _site_and_location(raw_text)
    note_value = _note(raw_text)
    inline_assignments = _inline_assignments(raw_text)

    explicit_shift = bool(date_value and start_time and end_time)
    # Collapse repeated LLM rows only for an explicit "N identical shifts"
    # instruction. Never collapse a detailed roster merely because the text also
    # mentions one date/time or an aggregate total.
    if explicit_shift and count_value is not None and total_count is None:
        base = dict(existing[0]) if existing and isinstance(existing[0], dict) else {}
        rows = [base]
    else:
        rows = [dict(item) for item in existing if isinstance(item, dict)]

    if not rows:
        source['shifts'] = []
        if total_count is not None:
            source['expected_shift_count'] = total_count
            source['shift_count_mismatch'] = True
        return source

    normalized = []
    complete_detailed_roster = total_count is not None and len(rows) == total_count
    for row in rows:
        # For a detailed multi-row roster, the row-specific date/time/role/site
        # from the AI parser wins. Global values are only overlays for the simple
        # one-descriptor command handled above.
        detailed_roster = total_count is not None or len(rows) > 1
        if date_value and not detailed_roster:
            row['date'] = date_value
        if start_time and not detailed_roster:
            row['start_time'] = start_time
        if end_time and not detailed_roster:
            row['end_time'] = end_time
        if complete_detailed_roster:
            # "insgesamt N Schichten" means N individually reviewable shift rows,
            # not N employees on each of those rows.
            row['count'] = 1
        elif count_value is not None and not detailed_roster:
            row['count'] = count_value
        else:
            row['count'] = max(1, int(row.get('count') or 1))
        if role_value and not detailed_roster:
            row['role'] = role_value
        else:
            row['role'] = str(row.get('role') or role_value or 'Servicekraft').strip()
        if site_value and not detailed_roster:
            row['site_text'] = site_value
        else:
            row['site_text'] = str(row.get('site_text') or site_value or '').strip()
        if location_value and not detailed_roster:
            row['location_text'] = location_value
        else:
            row['location_text'] = str(row.get('location_text') or location_value or '').strip()
        if note_value and not detailed_roster:
            row['notes'] = note_value
        else:
            row['notes'] = str(row.get('notes') or note_value or '').strip()
        row['site_address'] = str(row.get('site_address') or '').strip()

        # Explicit ``date + Dienst - Mitarbeiter`` roster lines must win over an
        # LLM that incorrectly copied the employee name into the note field.
        assignment_name = inline_assignments.get(str(row.get('date') or '').strip())
        if assignment_name:
            row['assignment_worker_name'] = assignment_name
            worker_key = _assignment_key(assignment_name)
            note_key = _assignment_key(row.get('notes') or '')
            if note_key in {
                worker_key,
                f'mitarbeiter {worker_key}',
                f'worker {worker_key}',
                f'zugewiesen {worker_key}',
            }:
                row['notes'] = ''

        normalized.append(row)

    source['shifts'] = normalized
    if total_count is not None:
        source['expected_shift_count'] = total_count
        source['shift_count_mismatch'] = len(normalized) != total_count
    else:
        source.pop('expected_shift_count', None)
        source.pop('shift_count_mismatch', None)
    return source


def deterministic_order_request(raw_text: str) -> dict[str, Any] | None:
    """Return a complete parsed order when the user's text is unambiguous.

    This is also the safe fallback when the external AI parser is unavailable.
    """
    date_value = _date(raw_text)
    start_time, end_time = _times(raw_text)
    if not (date_value and start_time and end_time):
        return None
    site_value, location_value = _site_and_location(raw_text)
    parsed = {
        'contract_no': '',
        'shifts': [{
            'role': _role(raw_text) or 'Servicekraft',
            'date': date_value,
            'start_time': start_time,
            'end_time': end_time,
            'count': _count(raw_text) or 1,
            'location_text': location_value,
            'site_text': site_value,
            'site_address': '',
            'notes': _note(raw_text),
        }],
    }
    return parsed