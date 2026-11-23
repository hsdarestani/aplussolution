import { describe, expect, it } from 'vitest';
import { formatScheduledHours, scheduledShiftHours, sumAllWeeklyScheduledHours, sumScheduledCardHours } from './weeklyScheduledHours';

const weekDays = ['2026-11-16', '2026-11-17', '2026-11-18', '2026-11-19', '2026-11-20', '2026-11-21', '2026-11-22'];
const day = (iso: string) => iso.slice(0, 10);
const slotCount = (shift: any) =>
  shift.slot_cards?.length || ((shift.assigned_workers?.length || 0) + (shift.open_count || 0)) || 1;

describe('scheduled hours in manager Dienstplan', () => {
  it('displays quarter-hour totals without one-decimal drift', () => {
    expect(formatScheduledHours(8.25)).toBe('8,25');
    expect(formatScheduledHours(8.75)).toBe('8,75');
    expect(formatScheduledHours(9)).toBe('9');
  });
  it('adds the gross scheduled duration once for EACH person/slot, even if unapproved', () => {
    const shifts = [
      {
        starts_at: '2026-11-16T08:00:00+01:00', ends_at: '2026-11-16T13:00:00+01:00',
        break_minutes: 0, slot_cards: [{ id: 1, approved: false }, { id: 2, approved: true }],
      },
      {
        starts_at: '2026-11-17T08:30:00+01:00', ends_at: '2026-11-17T17:30:00+01:00',
        break_minutes: 30, slot_cards: [{ id: 3, status: 'pending' }],
      },
    ];
    expect(sumAllWeeklyScheduledHours(shifts, weekDays, day, slotCount)).toBe(19);
  });

  it('includes open and draft shifts but never adds the supplementary live WIW preview twice', () => {
    const base = {
      starts_at: '2026-11-18T12:00:00+01:00', ends_at: '2026-11-18T18:00:00+01:00',
      break_minutes: 30, open_count: 1,
    };
    const shifts = [
      { ...base, id: 'local', status: 'draft' },
      { ...base, id: 'live', source: 'wiw-live', status: 'published' },
    ];
    expect(sumAllWeeklyScheduledHours(shifts, weekDays, day, slotCount)).toBe(6);
  });

  it('only counts shifts in the selected Monday–Sunday week, not neighboring weeks', () => {
    const shifts = [
      { starts_at: '2026-11-15T10:00:00+01:00', ends_at: '2026-11-15T14:00:00+01:00' },
      { starts_at: '2026-11-22T22:30:00+01:00', ends_at: '2026-11-23T06:30:00+01:00', break_minutes: 30 },
      { starts_at: '2026-11-23T10:00:00+01:00', ends_at: '2026-11-23T14:00:00+01:00' },
    ];
    expect(sumAllWeeklyScheduledHours(shifts, weekDays, day, slotCount)).toBe(8);
  });

  it('uses exactly the same shift-hour math for day headings and the week footer', () => {
    const shifts = [
      { starts_at: '2026-11-16T08:00:00+01:00', ends_at: '2026-11-16T13:00:00+01:00', break_minutes: 0 },
      { starts_at: '2026-11-16T08:00:00+01:00', ends_at: '2026-11-16T13:00:00+01:00', break_minutes: 0 },
      { starts_at: '2026-11-17T09:00:00+01:00', ends_at: '2026-11-17T17:15:00+01:00', break_minutes: 30 },
    ];
    const cards = shifts.map((shift) => ({ shift }));
    expect(sumScheduledCardHours(cards)).toBe(18.25);
    expect(sumAllWeeklyScheduledHours(shifts, weekDays, day, () => 1)).toBe(sumScheduledCardHours(cards));
  });

  it('guards invalid or reversed times and never produces negative hours', () => {
    expect(scheduledShiftHours({ starts_at: 'bad', ends_at: 'bad' })).toBe(0);
    expect(scheduledShiftHours({ starts_at: '2026-11-16T13:00:00+01:00', ends_at: '2026-11-16T08:00:00+01:00' })).toBe(0);

    expect(scheduledShiftHours({ starts_at: '2026-11-16T08:00:00+01:00', ends_at: '2026-11-16T09:00:00+01:00', break_minutes: 120 })).toBe(1);
  });
});
