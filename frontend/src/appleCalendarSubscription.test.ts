import { describe, expect, it } from 'vitest';
import { isAllowedCalendarHandoff } from './appleCalendarSubscription';

describe('secure iOS calendar setup handoff', () => {
  const token = 'c97-3~signed_token_123';
  it('allows the signed HTTPS setup URL and legacy webcal feeds on the production host', () => {
    expect(isAllowedCalendarHandoff(`https://app.aplus-solution.de/calendar/subscribe/${token}`)).toBe(true);
    expect(isAllowedCalendarHandoff(`webcal://app.aplus-solution.de/calendar/${token}.ics`)).toBe(true);
    expect(isAllowedCalendarHandoff(`webcal://app.aplus-solution.de/api/calendar/feed/${token}.ics`)).toBe(true);
  });

  it('never opens an arbitrary host, insecure setup page, or exfiltration URL', () => {
    expect(isAllowedCalendarHandoff(`http://app.aplus-solution.de/calendar/subscribe/${token}`)).toBe(false);
    expect(isAllowedCalendarHandoff('https://evil.example/calendar/subscribe/secret')).toBe(false);
    expect(isAllowedCalendarHandoff('https://app.aplus-solution.de.evil.example/calendar/subscribe/secret')).toBe(false);
    expect(isAllowedCalendarHandoff('https://user:pass@app.aplus-solution.de/calendar/subscribe/secret')).toBe(false);
    expect(isAllowedCalendarHandoff('https://app.aplus-solution.de/calendar/subscribe/secret?redirect=https://evil.example')).toBe(false);
    expect(isAllowedCalendarHandoff('javascript:alert(1)')).toBe(false);
  });
});
