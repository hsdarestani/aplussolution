import { beforeEach, expect, test, vi } from 'vitest';

const native = vi.hoisted(() => ({
  open: vi.fn(),
  isNative: vi.fn(() => true),
  platform: vi.fn(() => 'ios'),
}));
vi.mock('@capacitor/core', () => ({
  Capacitor: { isNativePlatform: native.isNative, getPlatform: native.platform },
  registerPlugin: () => ({ open: native.open }),
}));

import { openAppleCalendarSubscription } from '../appleCalendarSubscription';

beforeEach(() => {
  vi.clearAllMocks();
  native.isNative.mockReturnValue(true);
  native.platform.mockReturnValue('ios');
  native.open.mockResolvedValue(undefined);
});

test('iOS uses the native bridge rather than WebView navigation', async () => {
  await openAppleCalendarSubscription('webcal://app.aplus-solution.de/api/calendar/feed/a.ics');
  expect(native.open).toHaveBeenCalledWith({ url: 'webcal://app.aplus-solution.de/api/calendar/feed/a.ics' });
});
test('rejects untrusted protocols before native handoff', async () => {
  await expect(openAppleCalendarSubscription('javascript:alert(1)')).rejects.toThrow('Ungültiger Kalenderlink.');
  expect(native.open).not.toHaveBeenCalled();
});
test('propagates native open errors rather than silently succeeding', async () => {
  native.open.mockRejectedValueOnce(new Error('Kein Kalender Handler'));
  await expect(openAppleCalendarSubscription('webcal://app.aplus-solution.de/calendar.ics')).rejects.toThrow('Kein Kalender Handler');
});
