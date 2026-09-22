// Retire legacy A+ service-worker registrations without reloading open clients.
// The previous self-destroying Workbox worker navigated every controlled client
// during activation, which could make the iOS Capacitor WebView appear to restart.
self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    try {
      await self.registration.unregister();
    } catch {
      // Best-effort cleanup only.
    }

    try {
      const cacheNames = await caches.keys();
      await Promise.all(cacheNames.map((cacheName) => caches.delete(cacheName)));
    } catch {
      // Cache cleanup must never trigger client navigation or block the app.
    }
  })());
});
