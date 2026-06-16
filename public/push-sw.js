/**
 * Push-only service worker for AskMukthiGuru daily teachings.
 * - Does NOT cache or intercept fetch (per Lovable PWA skill: messaging workers
 *   are isolated from app-shell SWs).
 * - Handles `push` and `notificationclick` events only.
 */
/* eslint-disable no-restricted-globals */

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('push', (event) => {
  let payload = {
    title: 'A teaching for you',
    body: 'Open AskMukthiGuru for today’s message.',
    url: '/chat',
  };
  try {
    if (event.data) payload = { ...payload, ...event.data.json() };
  } catch {
    // payload may be plain text
    if (event.data) payload.body = event.data.text();
  }

  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: '/favicon.svg',
      badge: '/favicon.svg',
      tag: 'daily-teaching',
      renotify: false,
      data: { url: payload.url || '/chat' },
    }),
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/chat';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((wins) => {
      for (const w of wins) {
        if ('focus' in w) {
          w.navigate(url).catch(() => {});
          return w.focus();
        }
      }
      if (self.clients.openWindow) return self.clients.openWindow(url);
    }),
  );
});
