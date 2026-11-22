import { describe, expect, it } from 'vitest';
import { extractShiftEventNumber, groupDayScheduleCards } from '../scheduleEventGrouping';

const rank = (name?: string) => name === "Martha's Finest" ? 0 : 1;
const makeCard = (id: number, time: string, notes: string, venue: string, client = 1) => ({
  key: String(id),
  shift: {
    id, client, client_name: client === 1 ? "Martha's Finest" : 'Other',
    location: venue === 'Dominikankloster' ? 10 : 20,
    location_name: venue, notes, starts_at: '2026-11-26T' + time + ':00+01:00',
  },
  worker: { name: 'Worker ' + id },
});

describe('event number from shift notes', () => {
  it.each([
    ['Event-Nr. 11211', '11211'],
    ['Eventnummer: 11211', '11211'],
    ['Event #11211', '11211'],
    ['Veranstaltungsnummer: 11211', '11211'],
    ['VA-Nr: 11211', '11211'],
    ['Nr. 11211\nBitte pünktlich sein', '11211'],
    ['#11211', '11211'],
    ['Einlass 17:00\nEvent ID: EV-1254\nKontakt 01791234567', 'EV-1254'],
  ])('detects %s', (note, expected) => {
    expect(extractShiftEventNumber(note)).toBe(expected);
  });

  it.each([
    'Start 07:00, Ende 15:30',
    '26.11.2026 / 12 Mitarbeitende',
    'Tel. 01791234567',
    'Event am 26.11.2026',
    'Nur Schichtnotiz',
    '',
  ])('does not invent an event number from %s', (note) => {
    expect(extractShiftEventNumber(note)).toBeNull();
  });
});

describe('mobile admin day grouping', () => {
  it('keeps one event together across different locations and sorts its shifts by time', () => {
    const cards = [
      makeCard(1, '07:00', 'Event-Nr. 222', 'Dominikankloster'),
      makeCard(2, '08:00', 'Event-Nr. 333', 'Evangelische Akademie'),
      makeCard(3, '09:00', 'Event-Nr. 222', 'Evangelische Akademie'),
      makeCard(4, '07:30', 'Event-Nr. 333', 'Dominikankloster'),
    ];
    const original = cards.map((card) => card.key);
    const grouped = groupDayScheduleCards(cards, rank);
    expect(grouped.map((g) => g.cards.map((c) => c.key))).toEqual([['1', '3'], ['4', '2']]);
    expect(grouped.map((g) => g.stripe)).toEqual(['#259B58', '#E8AD00']);
    expect(grouped.map((g) => g.title)).toEqual(['Event 222', 'Event 333']);
    expect(cards.map((card) => card.key)).toEqual(original);
  });

  it('separates different events in the same venue', () => {
    const groups = groupDayScheduleCards([
      makeCard(1, '08:00', 'Event: 100', 'Dominikankloster'),
      makeCard(2, '09:00', 'Event: 200', 'Dominikankloster'),
    ], rank);
    expect(groups).toHaveLength(2);
    expect(groups.every((group) => group.hasSiblingGroups)).toBe(true);
  });

  it('uses the location when notes lack an event number', () => {
    const groups = groupDayScheduleCards([
      makeCard(1, '07:00', '', 'Dominikankloster'),
      makeCard(2, '07:30', 'Dienstbeginn', 'Dominikankloster'),
      makeCard(3, '08:00', '', 'Evangelische Akademie'),
    ], rank);
    expect(groups.map((g) => g.cards.length)).toEqual([2, 1]);
    expect(groups.map((g) => g.title)).toEqual(['Dominikankloster', 'Evangelische Akademie']);
  });

  it('does not merge matching event numbers across different customers', () => {
    const groups = groupDayScheduleCards([
      makeCard(1, '08:00', 'Event #999', 'Dominikankloster', 1),
      makeCard(2, '08:00', 'Event #999', 'Dominikankloster', 2),
    ], rank);
    expect(groups).toHaveLength(2);
    expect(groups.every((g) => g.stripe === null)).toBe(true);
  });

  it('keeps multiple employee slots of one shift together', () => {
    const first = makeCard(1, '08:00', 'Event #100', 'Dominikankloster');
    const second = { ...first, key: '1:another-slot' };
    expect(groupDayScheduleCards([first, second], rank)[0].cards).toHaveLength(2);
  });
});
