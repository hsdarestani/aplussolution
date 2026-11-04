/** Keep the end clock time anchored to the nearest valid day when start changes. */
export function endAfterChangingStart(start: number, previousAbsoluteEnd: number): number {
  const endClock = ((previousAbsoluteEnd % 1440) + 1440) % 1440;
  if (endClock > start) return endClock;
  if (endClock < start) return endClock + 1440;
  return endClock; // Equal start/end is invalid and must not create a 24h shift.
}

/** This mobile form must never accidentally save a 29/30 hour housekeeping shift. */
export function shiftDurationIsValid(start: number, absoluteEnd: number): boolean {
  return Number.isFinite(start) && Number.isFinite(absoluteEnd)
    && absoluteEnd > start && absoluteEnd - start <= 1440;
}
