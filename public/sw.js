const CACHE_NAME = 'mukthiguru-core-v1';
const MEDITATION_CACHE = 'mukthiguru-meditation-v1';

const ASSETS_TO_CACHE = [
  '/',
  '/index.html',
  '/favicon.svg',
  '/placeholder.svg',
  '/robots.txt',
  '/sitemap.xml',
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
  const url = new URL(event.request.url);

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
            cache.put(event.request, networkResponse.clone());
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
            cache.put(event.request, networkResponse.clone());
            return networkResponse;
          }).catch(() => {
            // Offline fallback for crisis pages if network fails and not in cache
            loggerLog('Offline: Serving cached crisis/breathing page fallback');
          });
          return cachedResponse || fetchPromise;
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
        if (event.request.method === 'GET' && url.origin === self.location.origin) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      })
      .catch(() => {
        // Serve from cache if offline
        return caches.match(event.request).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }
          // If offline and request is for page, return index.html (SPA routing)
          if (event.request.headers.get('accept').includes('text/html')) {
            return caches.match('/index.html');
          }
        });
      })
  );
});

function loggerLog(message) {
  console.log(`[MukthiGuru SW] ${message}`);
}
