import { Capacitor, registerPlugin } from '@capacitor/core';

interface NativeCalendarSubscription {
  open(options: { url: string }): Promise<void>;
}

const nativeCalendar = registerPlugin<NativeCalendarSubscription>('APlusCalendarSubscription');

export function isAllowedCalendarHandoff(value: string): boolean {
  try {
    const uri = new URL(value);
    if (uri.hostname.toLowerCase() !== 'app.aplus-solution.de') return false;
    if (uri.username || uri.password || uri.port || uri.hash) return false;

    if (uri.protocol === 'https:') {
      return /^\/calendar\/subscribe\/[A-Za-z0-9_~:-]+$/.test(uri.pathname) && uri.search === '';
    }
    // Legacy workflow retained for links used by earlier app versions.
    return uri.protocol === 'webcal:' && /^\/(?:calendar\/[^/]+|api\/calendar\/feed\/[^/]+)\.ics$/.test(uri.pathname);
  } catch {
    return false;
  }
}

/**
 * On iOS the HTTPS subscribe page is intentionally opened in the system
 * browser, where a real user gesture can hand the webcal link to Calendar.
 * Old webcal deep links are still supported for backwards compatibility.
 * Returning from UIApplication.open is not proof the user subscribed.
 */
export async function openAppleCalendarSubscription(url: string): Promise<void> {
  if (!isAllowedCalendarHandoff(url)) {
    throw new Error('Ungültiger Kalenderlink.');
  }

  if (Capacitor.isNativePlatform() && Capacitor.getPlatform() === 'ios') {
    await nativeCalendar.open({ url });
    return;
  }

  window.location.assign(url);
}
