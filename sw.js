// Jednoduchý service worker: uloží „obal“ appky, aby se spouštěl rychle a ukázal hlášku i bez internetu.
const CACHE = "energie-obal-v1";
const SOUBORY = ["./", "index.html", "manifest.webmanifest", "ikona.svg", "ikona-192.png", "ikona-512.png",
                 "ikona-maskable-512.png", "apple-touch-icon.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SOUBORY)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((klice) => Promise.all(klice.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return;           // samotnou appku na Streamlitu necháme být
  e.respondWith(
    fetch(e.request)
      .then((odpoved) => {
        const kopie = odpoved.clone();
        caches.open(CACHE).then((c) => c.put(e.request, kopie));
        return odpoved;
      })
      .catch(() => caches.match(e.request, { ignoreSearch: true }).then((r) => r || caches.match("index.html")))
  );
});
