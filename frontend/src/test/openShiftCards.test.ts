import { describe, expect, it } from 'vitest';
import { expandOpenShiftCards } from '../openShiftCards';

describe('OpenShift slot cards', () => {
  const shift = {
    id: 'shift-1',
    starts_at: '2026-10-20T08:30:00+02:00',
    ends_at: '2026-10-20T13:00:00+02:00',
    status: 'published',
    required_count: 2,
    open_count: 2,
    filled_count: 0,
    slot_cards: [
      { id: 'slot-a', status: 'open', is_open: true },
      { id: 'slot-b', status: 'open', is_open: true },
    ],
  };

  it('shows the two actual places while retaining the parent id for claim', () => {
    const rows = expandOpenShiftCards([shift]);
    expect(rows).toHaveLength(2);
    expect(rows.map((row) => row._open_slot_id)).toEqual(['slot-a', 'slot-b']);
    expect(rows.every((row) => row.id === 'shift-1')).toBe(true);
    expect(rows.every((row) => row.source_shift_id === 'shift-1')).toBe(true);
  });

  it('shows only available slots on partially claimed shifts', () => {
    const rows = expandOpenShiftCards([{
      ...shift,
      open_count: 1,
      filled_count: 1,
      slot_cards: [
        { id: 'slot-a', status: 'claimed', is_open: false },
        { id: 'slot-b', status: 'open', is_open: true },
      ],
    }]);
    expect(rows).toHaveLength(1);
    expect(rows[0]._open_slot_id).toBe('slot-b');
  });

  it('supports older API responses that return just open_count', () => {
    expect(expandOpenShiftCards([{ id: 'legacy', open_count: 3 }]).map((row) => row._open_slot_id))
      .toEqual(['open-0', 'open-1', 'open-2']);
  });
});
