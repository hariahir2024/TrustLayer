const CACHE_NAME = 'bsb-cache-v1';
const urlsToCache = [
  '/bank',
  '/static/css/style.css',
  '/static/js/sdk.js',
  '/static/js/bank.js',
  '/static/manifest.json'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => response || fetch(event.request))
  );
});
