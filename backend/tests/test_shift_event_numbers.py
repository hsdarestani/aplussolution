import pytest

from core.event_numbers import extract_event_number, normalize_event_number
from core.models import Shift
from core.shift_api import ShiftApiSerializer


@pytest.mark.parametrize('note,expected', [
    ('Event-Nr. 11211', '11211'),
    ('Veranstaltungsnummer: 11211', '11211'),
    ('Event #11211', '11211'),
    ('VA-Nr: 11211', '11211'),
    ('Nr. 11211\nBitte pünktlich sein', '11211'),
    ('Einlass 17:00\nEvent ID: EV-1254\nKontakt 01791234567', 'EV-1254'),
    ('Tel. 01791234567', ''),
    ('Einlass 17:00, Ende 21:00', ''),
    ('Event am 26.11.2026', ''),
    ('Notiz ohne Nummer', ''),
])
def test_conservative_event_number_extraction(note, expected):
    assert extract_event_number(note) == expected


def test_normalize_event_number():
    assert normalize_event_number(' abc-1254 ') == 'ABC-1254'
    assert normalize_event_number('') == ''
    assert normalize_event_number('x' * 65) == ''


@pytest.mark.django_db
def test_shift_api_fills_event_number_from_legacy_notes(shift):
    shift.event_number = ''
    shift.notes = 'Event-Nr. 12345, Aufbau um 9 Uhr'
    shift.save(update_fields=['event_number', 'notes'])
    serializer = ShiftApiSerializer(shift, data={'notes': shift.notes}, partial=True)
    serializer.is_valid(raise_exception=True)
    updated = serializer.save()
    assert updated.event_number == '12345'
    assert ShiftApiSerializer(updated).data['event_number'] == '12345'
    assert updated.notes == shift.notes


@pytest.mark.django_db
def test_explicit_number_overrides_note_and_can_be_cleared(shift):
    shift.notes = 'Event-Nr. 12345'
    shift.event_number = '12345'
    shift.save(update_fields=['notes', 'event_number'])
    serializer = ShiftApiSerializer(shift, data={'event_number': 'xyz-782'}, partial=True)
    serializer.is_valid(raise_exception=True)
    updated = serializer.save()
    assert updated.event_number == 'XYZ-782'
    serializer = ShiftApiSerializer(updated, data={'event_number': ''}, partial=True)
    serializer.is_valid(raise_exception=True)
    updated = serializer.save()
    assert updated.event_number == ''
