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


def _count(text: str) -> int | None:
    match = _first(r'\b(\d+)\s+(?:offene\s+)?schicht(?:en)?\b', text)
    return max(1, int(match[0])) if match else None


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


def normalize_order_request(raw_text: str, parsed: dict[str, Any] | None = None) -> dict[str, Any]:
    """Overlay explicit German instructions on top of the LLM result.

    Explicit count/date/time/site/location/note values are authoritative. When a
    single instruction asks for N identical shifts, keep one shift descriptor with
    ``count=N`` so approval creates exactly N slots instead of multiplying an LLM
    list of N one-count rows by N again.
    """
    source = deepcopy(parsed or {}) if isinstance(parsed, dict) else {}
    existing = source.get('shifts') if isinstance(source.get('shifts'), list) else []

    date_value = _date(raw_text)
    start_time, end_time = _times(raw_text)
    count_value = _count(raw_text)
    role_value = _role(raw_text)
    site_value, location_value = _site_and_location(raw_text)
    note_value = _note(raw_text)

    explicit_shift = bool(date_value and start_time and end_time)
    if explicit_shift:
        base = dict(existing[0]) if existing and isinstance(existing[0], dict) else {}
        rows = [base]
    else:
        rows = [dict(item) for item in existing if isinstance(item, dict)]

    if not rows:
        source['shifts'] = []
        return source

    normalized = []
    for row in rows:
        if date_value:
            row['date'] = date_value
        if start_time:
            row['start_time'] = start_time
        if end_time:
            row['end_time'] = end_time
        if count_value is not None:
            row['count'] = count_value
        else:
            row['count'] = max(1, int(row.get('count') or 1))
        if role_value:
            row['role'] = role_value
        else:
            row['role'] = str(row.get('role') or 'Servicekraft').strip()
        if site_value:
            row['site_text'] = site_value
        else:
            row['site_text'] = str(row.get('site_text') or '').strip()
        if location_value:
            row['location_text'] = location_value
        else:
            row['location_text'] = str(row.get('location_text') or '').strip()
        if note_value:
            row['notes'] = note_value
        else:
            row['notes'] = str(row.get('notes') or '').strip()
        row['site_address'] = str(row.get('site_address') or '').strip()
        normalized.append(row)

    source['shifts'] = normalized
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
