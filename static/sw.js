const CACHE_NAME = 'workpulse-v1';

self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
    // Basic network-first strategy for dynamic API and cached assets
    event.respondWith(
        fetch(event.request).catch(() => caches.match(event.request))
    );
});
