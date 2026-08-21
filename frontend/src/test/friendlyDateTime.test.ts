import { describe, expect, it } from 'vitest';
import {
  normalizePickerOutput,
  pickerKindFromType,
  quickPickerValue,
  toIonDatetimeValue,
} from '../friendlyDateTime';

describe('friendly date/time helpers', () => {
  const now = new Date(2026, 7, 21, 13, 4, 0);

  it('recognizes every native picker type we enhance', () => {
    expect(pickerKindFromType('date')).toBe('date');
    expect(pickerKindFromType('time')).toBe('time');
    expect(pickerKindFromType('datetime-local')).toBe('datetime-local');
    expect(pickerKindFromType('month')).toBe('month');
    expect(pickerKindFromType('week')).toBe('week');
    expect(pickerKindFromType('text')).toBeUndefined();
  });

  it('keeps backend-compatible values after choosing in IonDatetime', () => {
    expect(normalizePickerOutput('date', '2026-08-21T00:00:00')).toBe('2026-08-21');
    expect(normalizePickerOutput('time', '2026-08-21T14:35:00+02:00')).toBe('14:35');
    expect(normalizePickerOutput('datetime-local', '2026-08-21T14:35:00+02:00')).toBe('2026-08-21T14:35');
    expect(normalizePickerOutput('month', '2026-08-21T00:00:00')).toBe('2026-08');
    expect(normalizePickerOutput('week', '2026-08-21T00:00:00')).toBe('2026-W34');
  });

  it('maps existing HTML input values into IonDatetime values', () => {
    expect(toIonDatetimeValue('date', '2026-09-02', now)).toBe('2026-09-02');
    expect(toIonDatetimeValue('time', '09:15', now)).toBe('2026-08-21T09:15:00');
    expect(toIonDatetimeValue('datetime-local', '2026-09-02T18:45', now)).toBe('2026-09-02T18:45');
    expect(toIonDatetimeValue('month', '2026-11', now)).toBe('2026-11-01');
    expect(toIonDatetimeValue('week', '2026-W34', now)).toBe('2026-08-17');
  });

  it('provides useful quick selections without changing output contracts', () => {
    expect(quickPickerValue('date', 0, now)).toBe('2026-08-21');
    expect(quickPickerValue('date', 1, now)).toBe('2026-08-22');
    expect(quickPickerValue('datetime-local', 0, now)).toBe('2026-08-21T13:04');
    expect(quickPickerValue('month', 0, now)).toBe('2026-08-01');
  });
});
