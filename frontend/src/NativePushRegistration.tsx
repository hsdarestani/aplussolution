import { useEffect } from 'react';
import { Capacitor } from '@capacitor/core';
import { PushNotifications, type ActionPerformed, type PushNotificationSchema, type Token } from '@capacitor/push-notifications';

import { api } from './api';

const APP_ID = 'de.aplussolution.workforce';
let nativePushStarted = false;

function openActionUrl(actionUrl?: string) {
  if (!actionUrl) return;
  const route = actionUrl.replace(/^\/+/, '').split(/[?#]/)[0];
  const viewMap: Record<string, string> = {
    messages: 'messages',
    contracts: 'contracts',
    documents: 'documents',
    schedule: 'schedule',
    shifts: 'schedule',
    orders: 'orders',
    people: 'people',
    operations: 'operations',
  };
  const view = viewMap[route];
  if (!view) {
    window.location.href = actionUrl;
    return;
  }
  const url = new URL(window.location.href);
  url.pathname = '/';
  url.searchParams.set('view', view);
  window.history.pushState({ view }, '', `${url.pathname}${url.search}${url.hash}`);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

function notificationActionUrl(notification?: PushNotificationSchema) {
  const data = notification?.data || {};
  return String(data.action_url || data.actionUrl || '');
}

export default function NativePushRegistration() {
  useEffect(() => {
    if (!Capacitor.isNativePlatform() || nativePushStarted) return;
    nativePushStarted = true;
    let disposed = false;
    let authTimer = 0;
    const handles: Array<{ remove: () => Promise<void> }> = [];

    const addListeners = async () => {
      handles.push(await PushNotifications.addListener('registration', async (token: Token) => {
        if (disposed || !token.value) return;
        localStorage.setItem('aplus_push_token', token.value);
        try {
          await api('push/devices/register/', {
            method: 'POST',
            body: JSON.stringify({
              token: token.value,
              platform: Capacitor.getPlatform(),
              app_id: APP_ID,
              device_name: `${Capacitor.getPlatform()} native app`,
            }),
          });
        } catch (error) {
          console.warn('Push token registration failed', error);
        }
      }));

      handles.push(await PushNotifications.addListener('registrationError', (error: any) => {
        console.warn('Native push registration error', error);
      }));

      handles.push(await PushNotifications.addListener('pushNotificationReceived', () => {
        window.dispatchEvent(new Event('aplus-notifications-refresh'));
      }));

      handles.push(await PushNotifications.addListener('pushNotificationActionPerformed', (event: ActionPerformed) => {
        openActionUrl(notificationActionUrl(event.notification));
      }));
    };

    const registerWhenAuthenticated = async () => {
      if (disposed) return;
      if (!localStorage.getItem('access')) {
        authTimer = window.setTimeout(() => void registerWhenAuthenticated(), 1200);
        return;
      }
      try {
        let permission = await PushNotifications.checkPermissions();
        if (permission.receive === 'prompt') {
          permission = await PushNotifications.requestPermissions();
        }
        if (permission.receive !== 'granted') {
          console.info('Native push permission not granted.');
          return;
        }
        await PushNotifications.register();
      } catch (error) {
        console.warn('Native push setup failed', error);
      }
    };

    void addListeners().then(registerWhenAuthenticated);

    return () => {
      disposed = true;
      if (authTimer) window.clearTimeout(authTimer);
      handles.forEach((handle) => void handle.remove());
      nativePushStarted = false;
    };
  }, []);

  return null;
}
