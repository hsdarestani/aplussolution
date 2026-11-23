import { describe, expect, it } from 'vitest';
import { canViewAdminShiftExtraRows } from './adminScheduleVisibility';

describe('Info admin shift-card visibility', () => {
  it('hides direct assignment, card-count and Zeitlog summaries for Info', () => {
    expect(canViewAdminShiftExtraRows('info@aplus-solution.de')).toBe(false);
    expect(canViewAdminShiftExtraRows(' INFO@APLUS-SOLUTION.DE ')).toBe(false);
  });
  it('shows the full rows for marketing super-admin and other admins', () => {
    expect(canViewAdminShiftExtraRows('marketing@aplus-solution.de')).toBe(true);
    expect(canViewAdminShiftExtraRows('admin@example.com')).toBe(true);
  });
  it('does not reveal extra rows while identity is pending', () => {
    expect(canViewAdminShiftExtraRows('')).toBe(false);
    expect(canViewAdminShiftExtraRows(undefined)).toBe(false);
  });
});
