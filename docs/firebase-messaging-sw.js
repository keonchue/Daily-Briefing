// Firebase Messaging 백그라운드 핸들러
// 주의: 아래 설정값을 Firebase 콘솔에서 복사한 값으로 교체하세요.
importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey:            "AIzaSyAijGdIJXGidRLUZTMYb2A-4LFvunFMUDo",
  authDomain:        "consumer-briefing.firebaseapp.com",
  projectId:         "consumer-briefing",
  storageBucket:     "consumer-briefing.appspot.com",
  messagingSenderId: "579742111110",
  appId:             "1:579742111110:web:26a7408aac887c4b0b8807"
});

const messaging = firebase.messaging();

// 앱이 백그라운드/종료 상태일 때 수신
messaging.onBackgroundMessage(payload => {
  const n = payload.notification || {};
  const baseUrl = self.location.href.replace('firebase-messaging-sw.js', '');
  self.registration.showNotification(n.title || '소비자 데일리 브리핑', {
    body:  n.body  || '오늘의 브리핑이 준비되었습니다!',
    icon:  baseUrl + 'snu_ui_download.png',
    badge: baseUrl + 'snu_ui_download.png',
    tag:   'daily-briefing',
    requireInteraction: false,
    data:  { url: baseUrl }
  });
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = e.notification.data?.url || '/';
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      for (const c of list) {
        if (c.url.startsWith(url) && 'focus' in c) return c.focus();
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});
