import React from 'react';
import { render, waitFor } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import NativePushRegistration from '../NativePushRegistration';

const mocks = vi.hoisted(() => ({
  register: vi.fn().mockResolvedValue(undefined),
  localListener: vi.fn().mockRejectedValue(new Error('LocalNotifications is not implemented')),
  listeners: {} as Record<string, (value: any) => void>,
}));
vi.mock('@capacitor/core', () => ({ Capacitor: { isNativePlatform: () => true, getPlatform: () => 'ios' } }));
vi.mock('../api', () => ({ api: vi.fn().mockResolvedValue({}) }));
vi.mock('@capacitor/local-notifications', () => ({ LocalNotifications: {
  addListener: mocks.localListener,
  checkPermissions: vi.fn().mockRejectedValue(new Error('Unavailable')),
} }));
vi.mock('@capacitor/push-notifications', () => ({ PushNotifications: {
  addListener: vi.fn(async (event: string, callback: (value: any) => void) => {
    mocks.listeners[event] = callback;
    return { remove: vi.fn().mockResolvedValue(undefined) };
  }),
  checkPermissions: vi.fn().mockResolvedValue({ receive: 'granted' }),
  register: mocks.register,
} }));

test('an old binary without local notifications still registers push and displays a foreground banner', async () => {
  localStorage.setItem('access', 'test-token');
  const warning = vi.spyOn(console, 'warn').mockImplementation(() => {});
  const view = render(<NativePushRegistration />);
  await waitFor(() => expect(mocks.register).toHaveBeenCalledOnce());
  mocks.listeners.pushNotificationReceived({ title: 'Neue Schicht', body: 'Heute um 14:00', data: { action_url: '/schedule/' } });
  expect(document.getElementById('aplus-foreground-push')).toHaveTextContent('Neue SchichtHeute um 14:00');
  document.getElementById('aplus-foreground-push')?.remove();
  view.unmount();
  await Promise.resolve();
  warning.mockRestore();
});
