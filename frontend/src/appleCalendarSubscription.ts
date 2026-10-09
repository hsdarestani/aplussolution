import { Capacitor, registerPlugin } from '@capacitor/core';

interface NativeCalendarSubscription {
  open(options: { url: string }): Promise<void>;
}

const nativeCalendar = registerPlugin<NativeCalendarSubscription>('APlusCalendarSubscription');

/**
 * webcal:// initiates a *subscription*, not a one-time ICS import.
 * WKWebView may silently swallow this custom scheme, so iOS must hand it
 * to UIApplication.shared.open through our registered native bridge.
 */
export async function openAppleCalendarSubscription(url: string): Promise<void> {
  if (!/^webcal:\/\/[a-z0-9.-]+\//i.test(url)) {
    throw new Error('Ungültiger Kalenderlink.');
  }

  if (Capacitor.isNativePlatform() && Capacitor.getPlatform() === 'ios') {
    await nativeCalendar.open({ url });
    return;
  }

  // Safari can handle webcal links directly; native iOS cannot use this path.
  window.location.assign(url);
}
