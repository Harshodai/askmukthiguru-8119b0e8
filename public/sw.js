/*
 * Privacy-safe service worker.
 *
 * This worker caches only immutable public application assets. It never caches
 * API, authenticated, personalised, safety, logistics or conversation requests,
 * and it never simulates an answer while offline. Those responses must always
 * come from the live, capability-aware backend.
 */
const CACHE_NAME = 'askmukthiguru-static-v2';

const PRE_CACHE_ASSETS = [
  '/favicon.svg',
  '/placeholder.svg',
  '/icon-192.png',
  '/icon-512.png',
];

const STATIC_ASSET_PATTERN = /\.(?:css|js|mjs|map|png|jpe?g|gif|svg|webp|avif|woff2?|ttf|eot)$/i;

function isCacheableStaticAsset(request, url) {
  if (request.method !== 'GET' || url.origin !== self.location.origin) return false;
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/functions/')) return false;
  return url.pathname.startsWith('/assets/') || PRE_CACHE_ASSETS.includes(url.pathname) || STATIC_ASSET_PATTERN.test(url.pathname);
}

function mayStore(response) {
  if (!response || !response.ok || response.type !== 'basic') return false;
  const cacheControl = response.headers.get('Cache-Control') || '';
  return !/no-store|private/i.test(cacheControl);
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRE_CACHE_ASSETS)),
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys
        .filter((key) => key !== CACHE_NAME && /^(askmukthiguru|mukthiguru)-/.test(key))
        .map((key) => caches.delete(key)),
    )),
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (!isCacheableStaticAsset(event.request, url)) return;

  event.respondWith(
    caches.open(CACHE_NAME).then(async (cache) => {
      const cached = await cache.match(event.request);
      if (cached) return cached;

      const response = await fetch(event.request);
      if (mayStore(response)) await cache.put(event.request, response.clone());
      return response;
    }),
  );
});
