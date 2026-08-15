import { Capacitor } from '@capacitor/core';
import { PushNotifications } from '@capacitor/push-notifications';
import { api } from './api';

let initialized = false;

export async function initNativePush() {
  if (initialized || !Capacitor.isNativePlatform()) return;
  initialized = true;
  try {
    let permission = await PushNotifications.checkPermissions();
    if (permission.receive === 'prompt') permission = await PushNotifications.requestPermissions();
    if (permission.receive !== 'granted') return;

    await PushNotifications.addListener('registration', async token => {
      try {
        await api('push-devices/', {
          method: 'POST',
          body: JSON.stringify({
            token: token.value,
            platform: Capacitor.getPlatform(),
            device_name: navigator.userAgent.slice(0, 150),
            app_version: import.meta.env.VITE_APP_VERSION || '1.0.0',
          }),
        });
      } catch {
        // Device registration can retry on the next authenticated app start.
      }
    });

    await PushNotifications.addListener('pushNotificationActionPerformed', event => {
      const data: any = event.notification.data || {};
      window.dispatchEvent(new CustomEvent('aplus-communications-open', { detail: data }));
    });

    await PushNotifications.addListener('pushNotificationReceived', () => {
      window.dispatchEvent(new Event('aplus-communications-refresh'));
    });

    await PushNotifications.register();
  } catch {
    initialized = false;
  }
}
