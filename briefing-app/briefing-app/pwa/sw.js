const CACHE = "briefing-v1";
const FILES = ["/", "/index.html", "/manifest.json"];

// 설치: 정적 파일 캐싱
self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(FILES))
  );
  self.skipWaiting();
});

// 활성화: 오래된 캐시 삭제
self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// 네트워크 우선, 실패 시 캐시
self.addEventListener("fetch", e => {
  e.respondWith(
    fetch(e.request)
      .then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});

// 푸시 알림 수신
self.addEventListener("push", e => {
  const data = e.data?.json() ?? {};
  e.waitUntil(
    self.registration.showNotification(data.title || "소비자 데일리 브리핑", {
      body: data.body || "오늘의 브리핑이 준비되었습니다! 탭해서 확인하세요.",
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      tag: "daily-briefing",
      requireInteraction: false,
      data: { url: "/" }
    })
  );
});

// 알림 클릭 시 앱 열기
self.addEventListener("notificationclick", e => {
  e.notification.close();
  e.waitUntil(
    clients.matchAll({ type: "window" }).then(list => {
      if (list.length) return list[0].focus();
      return clients.openWindow("/");
    })
  );
});
