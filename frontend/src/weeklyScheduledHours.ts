/** Total scheduled (not clocked/approved) hours for every shift slot in a week. */
export type ScheduledShift = {
  starts_at?: string | null;
  ends_at?: string | null;
  break_minutes?: number | string | null;
  source?: string | null;
};

export function scheduledShiftHours(shift: ScheduledShift): number {
  const start = new Date(shift.starts_at || '').getTime();
  const end = new Date(shift.ends_at || '').getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return 0;
  // Admin Dienstplan totals show the full planned interval, never deduct Pause.
  return (end - start) / 3600000;
}

export function sumScheduledCardHours(cards: readonly { shift: ScheduledShift }[]): number {
  return cards.reduce((sum, card) => sum + scheduledShiftHours(card.shift), 0);
}

/**
 * Use the full weekly schedule rather than filtered/visible cards. One slot is
 * one scheduled shift: two employees on one backend shift count twice.
 * The live-dashboard WIW rows are supplementary OpenShift previews and must
 * not be added to the canonical week endpoint (avoids duplicate counting).
 */
export function sumAllWeeklyScheduledHours<T extends ScheduledShift>(
  shifts: readonly T[],
  weekDays: readonly string[],
  shiftDateKey: (iso: string) => string,
  slotCount: (shift: T) => number,
): number {
  const dates = new Set(weekDays);
  return shifts.reduce((sum, shift) => {
    if (!shift.starts_at || shift.source === 'wiw-live' || !dates.has(shiftDateKey(shift.starts_at))) return sum;
    const slots = Number(slotCount(shift));
    if (!Number.isFinite(slots) || slots <= 0) return sum;
    return sum + scheduledShiftHours(shift) * Math.floor(slots);
  }, 0);
}
