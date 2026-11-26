// Jungle House AI service worker: phone / browser notifications only
// ("AI answer is ready", 2026-11-26). It does NOT cache or intercept any page
// or API request, so the site behaves exactly as without it.

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = {};
  }
  // Always show something: browsers (Safari especially) turn notifications
  // off for sites that receive a push without showing one.
  event.waitUntil(self.registration.showNotification(data.title || 'Jungle House AI', {
    body: data.body || '',
    tag: data.tag || 'jh-ai',
    renotify: true,
    icon: '/icons/icon-192.png',
    badge: '/icons/badge-96.png',
    data: { url: data.url, kind: data.kind, sessionId: data.sessionId },
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const { url, kind, sessionId } = event.notification.data || {};
  // Only paths on this site; never an address from outside.
  const target = typeof url === 'string' && url.startsWith('/') && !url.startsWith('//') ? url : '/chat';
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    const open = windows.find((client) => new URL(client.url).origin === self.location.origin);
    if (open) {
      open.postMessage({ type: 'jh-open-ai-task', kind, sessionId });
      return open.focus();
    }
    return self.clients.openWindow(target);
  })());
});
