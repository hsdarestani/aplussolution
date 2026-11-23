/**
 * Presentation-only grouping for the admin mobile Dienstplan.
 * Never change a Shift's identity, dates or backend data.
 */
export type EventShift = {
  id?: string | number | null;
  client?: string | number | null;
  client_name?: string | null;
  location?: string | number | null;
  location_name?: string | null;
  notes?: string | null;
  event_number?: string | null;
  starts_at?: string | null;
};

export type EventCard<T extends EventShift = EventShift> = {
  shift: T;
  key?: string;
  worker?: { name?: string };
};

export type DayEventGroup<T> = {
  key: string;
  clientKey: string;
  cards: T[];
  eventNumber: string | null;
  title: string;
  // Only override the existing customer-colored stripe when that customer
  // has multiple distinct events/locations on this day.
  stripe: string | null;
  hasSiblingGroups: boolean;
};

const EVENT_STRIPES = [
  '#259B58', // green
  '#E8AD00', // yellow
  '#3478D4', // blue
  '#8B5CF6', // violet
  '#E56D34', // orange
  '#008F91', // teal
  '#C74F92', // pink
  '#876447', // brown
];

// Be conservative: ordinary dates, times, phone numbers and staff counts in
// the free-text note are NOT event identifiers.
const EVENT_REFERENCE = /\b(?:event(?:\s*[-/.]?\s*(?:nr\.?|nummer|number|no\.?|id))?|veranstaltung(?:s(?:nummer|nr\.?)|\s*(?:nr\.?|nummer|id))?|va\s*[-/.]?\s*(?:nr\.?|nummer|id)|auftrags?\s*[-/.]?\s*(?:nr\.?|nummer)|evt\s*[-/.]?\s*(?:nr\.?|id)?)\s*[:#=\-]?\s*#?\s*([A-Z]{0,5}[-/]?\d{2,12}(?:[-/]\d{1,5})?)\b/i;
const NUMBER_REFERENCE = /(?:^|[\r\n])\s*(?:nr|nummer)\.?\s*[:#=\-]?\s*#?\s*(\d{2,12})\b/im;
const NUMBER_ONLY_NOTE = /^\s*#?\s*(\d{3,12})\s*$/;

export function extractShiftEventNumber(note: unknown): string | null {
  if (typeof note !== 'string' || !note.trim()) return null;
  const candidate = EVENT_REFERENCE.exec(note)?.[1]
    || NUMBER_REFERENCE.exec(note)?.[1]
    || NUMBER_ONLY_NOTE.exec(note)?.[1];
  if (!candidate) return null;
  const value = candidate.replace(/\s+/g, '').toUpperCase();
  // Do not mistake an explicitly written event date for an event number.
  if (/^\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?$/.test(value)) return null;
  return value;
}

const normalize = (value: unknown) =>
  String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('de-DE').replace(/ß/g, 'ss').replace(/[^a-z0-9]/g, '');

function clientIdentity(shift: EventShift): string {
  // A stable backend client id takes precedence over a human-readable alias.
  return shift.client != null && shift.client !== ''
    ? 'id:' + shift.client
    : 'name:' + (normalize(shift.client_name) || 'unbekannt');
}

function eventIdentity(shift: EventShift): { key: string; number: string | null; title: string } {
  const number = String(shift.event_number || '').trim().toUpperCase()
    || extractShiftEventNumber(shift.notes);
  if (number) return { key: 'event:' + number, number, title: 'Event ' + number };
  // Notes without an identifiable event number must not be interpreted as
  // another event number. Keep different locations visibly separate instead.
  const venue = String(shift.location_name || '').trim();
  if (shift.location != null && shift.location !== '') {
    return { key: 'location:' + shift.location, number: null, title: venue || 'Standort' };
  }
  if (venue) return { key: 'venue:' + normalize(venue), number: null, title: venue };
  // If nothing is known, don't silently combine unrelated shifts.
  return { key: 'shift:' + (shift.id ?? 'unbekannt'), number: null, title: 'Event-Nr. fehlt' };
}

function startValue(shift: EventShift): number {
  const value = new Date(shift.starts_at || '').getTime();
  return Number.isFinite(value) ? value : Number.MAX_SAFE_INTEGER;
}

export function groupDayScheduleCards<T extends EventCard>(
  dayCards: readonly T[],
  clientRank: (name?: string) => number,
): DayEventGroup<T>[] {
  const groups = new Map<string, DayEventGroup<T>>();
  for (const card of dayCards) {
    const clientKey = clientIdentity(card.shift);
    const identity = eventIdentity(card.shift);
    const key = clientKey + '\u0000' + identity.key;
    const existing = groups.get(key);
    if (existing) existing.cards.push(card);
    else groups.set(key, {
      key, clientKey, cards: [card], eventNumber: identity.number,
      title: identity.title, stripe: null, hasSiblingGroups: false,
    });
  }

  const sorted = [...groups.values()].sort((a, b) => {
    const first = a.cards[0].shift;
    const second = b.cards[0].shift;
    return clientRank(first.client_name || undefined) - clientRank(second.client_name || undefined)
      || String(first.client_name || '').localeCompare(String(second.client_name || ''), 'de')
      || Math.min(...a.cards.map((card) => startValue(card.shift))) - Math.min(...b.cards.map((card) => startValue(card.shift)))
      || a.key.localeCompare(b.key, 'de', { numeric: true });
  });

  const clientCounts = new Map<string, number>();
  for (const group of sorted) clientCounts.set(group.clientKey, (clientCounts.get(group.clientKey) || 0) + 1);
  const colorIndex = new Map<string, number>();
  for (const group of sorted) {
    group.cards.sort((a, b) =>
      startValue(a.shift) - startValue(b.shift)
      || String(a.worker?.name || '').localeCompare(String(b.worker?.name || ''), 'de')
      || String(a.key || '').localeCompare(String(b.key || ''), 'de')
    );
    group.hasSiblingGroups = (clientCounts.get(group.clientKey) || 0) > 1;
    if (group.hasSiblingGroups) {
      const index = colorIndex.get(group.clientKey) || 0;
      group.stripe = EVENT_STRIPES[index % EVENT_STRIPES.length];
      colorIndex.set(group.clientKey, index + 1);
    }
  }
  return sorted;
}
