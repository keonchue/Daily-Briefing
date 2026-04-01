const CACHE = "briefing-v1";
self.addEventListener("install", e => { self.skipWaiting(); });
self.addEventListener("activate", e => { self.clients.claim(); });
self.addEventListener("fetch", e => {
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
self.addEventListener("push", e => {
  const data = e.data?.json() ?? {};
  e.waitUntil(self.registration.showNotification(data.title || "소비자 데일리 브리핑", {
    body: data.body || "오늘의 브리핑이 준비되었습니다!", icon: "/icon-192.png", tag: "daily-briefing"
  }));
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  e.waitUntil(clients.openWindow("/"));
});
