/**
 * Push-only service worker for AskMukthiGuru daily teachings.
 * - Does NOT cache or intercept fetch (per Lovable PWA skill: messaging workers
 *   are isolated from app-shell SWs).
 * - Handles `push` and `notificationclick` events only.
 */
/* eslint-disable no-restricted-globals */

// A push payload's url/deep_link is attacker-controllable if the admin/cron
// sender is ever compromised or misconfigured — validate it here as a second
// layer, independent of server-side validation. (OH-P1-06, 2026-08-24)
const SAFE_DEEP_LINK = /^\/(chat|practices|profile|notebooks|knowledge-graph)(\/[a-zA-Z0-9_-]*)?$/;
const sanitizeDeepLink = (url) => (typeof url === 'string' && SAFE_DEEP_LINK.test(url) ? url : '/chat');

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
      data: { url: sanitizeDeepLink(payload.url) },
    }),
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = sanitizeDeepLink(event.notification.data && event.notification.data.url);
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
