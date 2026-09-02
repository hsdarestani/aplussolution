import { useEffect } from 'react';
import { Capacitor } from '@capacitor/core';
import { LocalNotifications } from '@capacitor/local-notifications';
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

function showForegroundBanner(notification: PushNotificationSchema) {
  const existing = document.getElementById('aplus-foreground-push');
  existing?.remove();
  const banner = document.createElement('button');
  banner.id = 'aplus-foreground-push';
  banner.type = 'button';
  banner.setAttribute('aria-label', notification.title || 'Neue Benachrichtigung');
  Object.assign(banner.style, {
    position: 'fixed',
    zIndex: '2147483000',
    top: 'calc(env(safe-area-inset-top, 0px) + 12px)',
    left: '12px',
    right: '12px',
    border: '1px solid rgba(255,255,255,.18)',
    borderRadius: '18px',
    background: 'rgba(18, 35, 61, .96)',
    color: '#fff',
    padding: '13px 15px',
    boxShadow: '0 12px 38px rgba(15,23,42,.28)',
    textAlign: 'left',
    font: 'inherit',
  });
  const title = document.createElement('strong');
  title.textContent = notification.title || 'Neue Benachrichtigung';
  title.style.display = 'block';
  const body = document.createElement('span');
  body.textContent = notification.body || '';
  body.style.cssText = 'display:block;margin-top:3px;font-size:13px;line-height:1.35;opacity:.88;white-space:pre-line;';
  banner.append(title, body);
  banner.onclick = () => {
    banner.remove();
    openActionUrl(notificationActionUrl(notification));
  };
  document.body.appendChild(banner);
  window.setTimeout(() => banner.remove(), 5200);
}

async function presentForegroundNotification(notification: PushNotificationSchema) {
  showForegroundBanner(notification);
  try {
    let permission = await LocalNotifications.checkPermissions();
    if (permission.display === 'prompt') permission = await LocalNotifications.requestPermissions();
    if (permission.display !== 'granted') return;
    const id = Math.max(1, Math.floor(Date.now() % 2_000_000_000));
    await LocalNotifications.schedule({
      notifications: [{
        id,
        title: notification.title || 'A+ Solution',
        body: notification.body || '',
        schedule: { at: new Date(Date.now() + 80), allowWhileIdle: true },
        channelId: Capacitor.getPlatform() === 'android' ? 'aplus_updates' : undefined,
        extra: notification.data || {},
      }],
    });
  } catch (error) {
    // The in-app banner above is the fallback for old binaries where the local
    // notification plugin/channel has not been synced yet.
    console.warn('Foreground notification presentation failed', error);
  }
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

      handles.push(await PushNotifications.addListener('registrationError', (error: unknown) => {
        console.warn('Native push registration error', error);
      }));

      handles.push(await PushNotifications.addListener('pushNotificationReceived', (notification) => {
        window.dispatchEvent(new Event('aplus-notifications-refresh'));
        window.dispatchEvent(new CustomEvent('aplus:foreground-push', { detail: notification }));
        void presentForegroundNotification(notification);
      }));

      handles.push(await PushNotifications.addListener('pushNotificationActionPerformed', (event: ActionPerformed) => {
        openActionUrl(notificationActionUrl(event.notification));
      }));

      handles.push(await LocalNotifications.addListener('localNotificationActionPerformed', (event) => {
        const actionUrl = String(event.notification.extra?.action_url || event.notification.extra?.actionUrl || '');
        openActionUrl(actionUrl);
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
        if (Capacitor.getPlatform() === 'android') {
          await PushNotifications.createChannel({
            id: 'aplus_updates',
            name: 'A+ Solution Updates',
            description: 'Schichten, Verträge, Nachrichten und wichtige Änderungen',
            importance: 5,
            visibility: 1,
            sound: 'default',
            vibration: true,
          });
          try {
            await LocalNotifications.createChannel({
              id: 'aplus_updates',
              name: 'A+ Solution Updates',
              description: 'Schichten, Verträge, Nachrichten und wichtige Änderungen',
              importance: 5,
              visibility: 1,
              sound: 'default',
              vibration: true,
            });
          } catch {
            // PushNotifications already owns the channel on existing installs.
          }
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
