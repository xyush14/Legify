/* Headnote service worker.
 *
 * Deliberately minimal. The app ships new HTML/JS several times a day and every
 * static/app response is served `no-cache`, so we do NOT cache app shell or API
 * responses — that would risk serving users a stale, broken build. This worker
 * exists only to (a) satisfy PWA installability (a fetch handler + manifest) so
 * the site qualifies as an installable app and a clean Trusted Web Activity
 * wrap, and (b) show a friendly offline card instead of the browser dino.
 */
const OFFLINE_URL = "/static/offline.html";
const CACHE = "headnote-shell-v1";
const PRECACHE = [OFFLINE_URL, "/static/icons/icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  // Only handle top-level navigations; everything else goes straight to network.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).catch(() => caches.match(OFFLINE_URL))
    );
    return;
  }
  // Non-navigation requests: network, fall back to cache only for precached assets.
  event.respondWith(fetch(req).catch(() => caches.match(req)));
});
