/**
 * Admin Dienstplan renders one card per ShiftSlot. Worker OpenShifts must
 * preserve the same card count, rather than collapsing an N-person demand
 * into one parent Shift row. The real Shift ID is never replaced.
 */
export function expandOpenShiftCards<T extends Record<string, any>>(
  shifts: T[],
): Array<T & { source_shift_id: string; _open_slot_id: string; _available_open_slot: boolean }> {
  return shifts.flatMap((shift) => {
    const slots = Array.isArray(shift.slot_cards)
      ? shift.slot_cards.filter((slot: any) => slot?.status === 'open' && slot?.is_open)
      : [];
    // If the server returned slot_cards, it is authoritative. Never invent
    // an open card when every slot is already claimed or closed.
    const fallbackCount = Math.max(0, Math.min(100, Math.trunc(Number(shift.open_count) || 0)));
    const openSlots: any[] = Array.isArray(shift.slot_cards)
      ? slots
      : Array.from({ length: fallbackCount }, (_, index) => ({ id: `open-${index}` }));

    return openSlots.map((slot: any, index: number) => ({
      ...shift,
      source_shift_id: shift.source_shift_id || shift.id,
      _open_slot_id: String(slot.id || `open-${index}`),
      _available_open_slot: true,
    }));
  });
}
