import { describe, expect, it } from 'vitest';
import { endAfterChangingStart, shiftDurationIsValid } from '../shiftTimeValidation';

describe('shift time boundaries', () => {
  it('fixes the 29h hotel shift when moving start to 08:00 but end shows 13:00 next day', () => {
    expect(endAfterChangingStart(8 * 60, 1440 + 13 * 60)).toBe(13 * 60);
    expect(shiftDurationIsValid(8 * 60, 13 * 60)).toBe(true);
  });
  it('still supports real overnight shifts', () => {
    expect(endAfterChangingStart(22 * 60, 1440 + 6 * 60)).toBe(1440 + 6 * 60);
    expect(shiftDurationIsValid(22 * 60, 1440 + 6 * 60)).toBe(true);
  });
  it('rejects same start and end and accidental 29 or 30 hour shifts', () => {
    expect(shiftDurationIsValid(480, 480)).toBe(false);
    expect(shiftDurationIsValid(480, 1440 + 780)).toBe(false);
    expect(shiftDurationIsValid(420, 1440 + 780)).toBe(false);
  });
});
