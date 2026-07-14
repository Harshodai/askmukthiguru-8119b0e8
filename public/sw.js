const CACHE_NAME = 'mukthiguru-core-v1';
const MEDITATION_CACHE = 'mukthiguru-meditation-v1';

const ASSETS_TO_CACHE = [
  '/',
  '/index.html',
  '/favicon.svg',
  '/placeholder.svg',
  '/robots.txt',
  '/sitemap.xml',
  '/icon-192.png',
  '/icon-512.png',
];

// Install Event: pre-cache static core assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      loggerLog('Pre-caching core app shell assets');
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
  self.skipWaiting();
});

// Activate Event: clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME && key !== MEDITATION_CACHE) {
            loggerLog(`Deleting obsolete cache: ${key}`);
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// Fetch Event: handle offline caching policies
self.addEventListener('fetch', (event) => {
  // Only intercept GET requests
  if (event.request.method !== 'GET') {
    return;
  }

  const url = new URL(event.request.url);

  // Only intercept http/https schemes (bypass chrome-extension, etc.)
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    return;
  }

  // 1. Caching Policy for Meditation Audio and Media Assets (Cache-First)
  if (
    url.pathname.includes('/meditation/') || 
    url.pathname.includes('/assets/meditation') ||
    url.pathname.endsWith('.mp3') ||
    url.pathname.endsWith('.wav')
  ) {
    event.respondWith(
      caches.open(MEDITATION_CACHE).then((cache) => {
        return cache.match(event.request).then((cachedResponse) => {
          if (cachedResponse) {
            loggerLog(`Serving cached meditation asset: ${url.pathname}`);
            return cachedResponse;
          }
          return fetch(event.request).then((networkResponse) => {
            if (networkResponse.status === 200) {
              cache.put(event.request, networkResponse.clone());
            }
            return networkResponse;
          });
        });
      })
    );
    return;
  }

  // 2. Caching Policy for Crisis Support and Breathing Pages (Stale-While-Revalidate)
  if (
    url.pathname.includes('/crisis') || 
    url.pathname.includes('/breathing') || 
    url.pathname.includes('/practices')
  ) {
    event.respondWith(
      caches.open(CACHE_NAME).then((cache) => {
        return cache.match(event.request).then((cachedResponse) => {
          const fetchPromise = fetch(event.request).then((networkResponse) => {
            if (networkResponse.status === 200) {
              cache.put(event.request, networkResponse.clone());
            }
            return networkResponse;
          });
          return cachedResponse || fetchPromise;
        }).catch((err) => {
          loggerLog(`Stale-while-revalidate error: ${err}`);
          return new Response('Service Offline', { status: 503 });
        });
      })
    );
    return;
  }

  // 3. General App Shell Cache Policy (Network-First with Cache Fallback)
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Cache successful GET requests for same origin
        if (url.origin === self.location.origin && response.status === 200) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      })
      .catch((err) => {
        loggerLog(`Network-first fetch failed, trying cache: ${err}`);
        // Serve from cache if offline
        return caches.match(event.request).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }
          // If offline and request is for page, return index.html (SPA routing)
          const acceptHeader = event.request.headers.get('accept') || '';
          if (acceptHeader.includes('text/html')) {
            return caches.match('/index.html');
          }
          // Offline fallback for API calls
          if (event.request.url.includes('/api/chat')) {
            return new Response(
              JSON.stringify({
                content: "Namaste. I am currently offline, but you can still access guided meditations. Tap the Serene Mind button below.",
                intent: "CASUAL",
                offline: true,
              }),
              { headers: { 'Content-Type': 'application/json' } }
            );
          }
          // Default offline response for other assets
          return new Response('Offline / Resource Unavailable', {
            status: 503,
            statusText: 'Service Offline',
            headers: new Headers({ 'Content-Type': 'text/plain' })
          });
        });
      })
  );
});

function loggerLog(message) {
  console.log(`[MukthiGuru SW] ${message}`);
}
