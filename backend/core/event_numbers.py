"""Conservative extraction of a Veranstaltungsnummer from legacy shift notes.

Do not treat phone numbers, dates or unrelated free-form text as event IDs.
"""
import re

EVENT_REFERENCE = re.compile(
    r'\b(?:event(?:\s*[-/.]?\s*(?:nr\.?|nummer|number|no\.?|id))?'
    r'|veranstaltung(?:s(?:nummer|nr\.?)|\s*(?:nr\.?|nummer|id))?'
    r'|va\s*[-/.]?\s*(?:nr\.?|nummer|id)'
    r'|auftrags?\s*[-/.]?\s*(?:nr\.?|nummer)'
    r'|evt\s*[-/.]?\s*(?:nr\.?|id)?)'
    r'\s*[:#=\-]?\s*#?\s*([A-Z]{0,5}[-/]?\d{2,12}(?:[-/]\d{1,5})?)\b',
    re.IGNORECASE,
)
NUMBER_REFERENCE = re.compile(
    r'(?:^|[\r\n])\s*(?:nr|nummer)\.?\s*[:#=\-]?\s*#?\s*(\d{2,12})\b',
    re.IGNORECASE | re.MULTILINE,
)
NUMBER_ONLY_NOTE = re.compile(r'^\s*#?\s*(\d{3,12})\s*$')


def normalize_event_number(value):
    cleaned = str(value or '').strip().upper().replace(' ', '')
    if not cleaned or len(cleaned) > 64:
        return ''
    return cleaned


def extract_event_number(note):
    if not isinstance(note, str) or not note.strip():
        return ''
    match = (EVENT_REFERENCE.search(note)
             or NUMBER_REFERENCE.search(note)
             or NUMBER_ONLY_NOTE.fullmatch(note))
    if not match:
        return ''
    value = normalize_event_number(match.group(1))
    if re.fullmatch(r'\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?', value):
        return ''
    return value
