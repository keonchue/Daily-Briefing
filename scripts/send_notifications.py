"""
Firebase Cloud Messaging 알림 발송 스크립트
GitHub Actions daily_briefing.yml에서 브리핑 생성 후 호출됩니다.

필요한 GitHub Secrets:
  FIREBASE_SERVICE_ACCOUNT  - Firebase 서비스 계정 JSON (전체 내용)
  FIREBASE_DB_URL           - Realtime Database URL
                              예) https://PROJECT_ID-default-rtdb.firebaseio.com
  PAGES_URL                 - GitHub Pages 배포 URL
                              예) https://username.github.io/Daily-Briefing
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta

import firebase_admin
from firebase_admin import credentials, messaging, db

# ── 환경 변수 로드 ────────────────────────────────────────────────────────────
sa_json      = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "")
db_url       = os.environ.get("FIREBASE_DB_URL", "")
pages_url    = os.environ.get("PAGES_URL", "").rstrip("/")

if not sa_json or not db_url:
    print("[알림 발송 건너뜀] FIREBASE_SERVICE_ACCOUNT 또는 FIREBASE_DB_URL이 설정되지 않았습니다.")
    sys.exit(0)

# ── Firebase 초기화 ───────────────────────────────────────────────────────────
try:
    sa_dict = json.loads(sa_json)
    cred = credentials.Certificate(sa_dict)
    firebase_admin.initialize_app(cred, {"databaseURL": db_url})
except Exception as e:
    print(f"[오류] Firebase 초기화 실패: {e}")
    sys.exit(1)

# ── 오늘 브리핑 데이터 읽기 ───────────────────────────────────────────────────
try:
    with open("docs/briefing.json", encoding="utf-8") as f:
        briefing = json.load(f)
except FileNotFoundError:
    print("[오류] docs/briefing.json 파일이 없습니다.")
    sys.exit(1)

date_kr = briefing.get("date_kr", "오늘")
econ_summary = briefing.get("sections", {}).get("econ", {}).get("summary", "")
notif_body = (econ_summary[:90] + "…") if len(econ_summary) > 90 else econ_summary
if not notif_body:
    notif_body = "오늘의 브리핑이 준비되었습니다!"

# ── FCM 토큰 목록 조회 ────────────────────────────────────────────────────────
try:
    tokens_data = db.reference("/fcm_tokens").get() or {}
except Exception as e:
    print(f"[오류] 토큰 조회 실패: {e}")
    sys.exit(1)

tokens = [
    v["token"]
    for v in tokens_data.values()
    if isinstance(v, dict) and v.get("token")
]

if not tokens:
    print("등록된 FCM 토큰이 없습니다. 알림 발송을 건너뜁니다.")
    sys.exit(0)

print(f"[알림 발송] {len(tokens)}개 토큰 대상 → {date_kr}")

# ── 메시지 발송 (500개 배치) ──────────────────────────────────────────────────
icon_url = f"{pages_url}/snu_ui_download.png" if pages_url else None
click_url = pages_url + "/" if pages_url else "/"

invalid_tokens: list[str] = []
total_success = 0

for i in range(0, len(tokens), 500):
    batch = tokens[i : i + 500]
    msg = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=f"📰 {date_kr} 브리핑",
            body=notif_body,
        ),
        webpush=messaging.WebpushConfig(
            notification=messaging.WebpushNotification(
                icon=icon_url,
                tag="daily-briefing",
                require_interaction=False,
            ),
            fcm_options=messaging.WebpushFCMOptions(link=click_url),
        ),
        tokens=batch,
    )

    try:
        resp = messaging.send_each_for_multicast(msg)
    except Exception as e:
        print(f"[오류] 배치 {i//500 + 1} 발송 실패: {e}")
        continue

    total_success += resp.success_count
    print(f"  배치 {i//500 + 1}: 성공 {resp.success_count} / 실패 {resp.failure_count}")

    # 무효 토큰 수집
    invalid_codes = {"registration-token-not-registered", "invalid-registration-token"}
    for j, r in enumerate(resp.responses):
        if not r.success and hasattr(r.exception, "code") and r.exception.code in invalid_codes:
            invalid_tokens.append(batch[j])

# ── 무효 토큰 정리 ────────────────────────────────────────────────────────────
if invalid_tokens:
    print(f"[정리] 무효 토큰 {len(invalid_tokens)}개 삭제 중...")
    token_to_key = {
        v["token"]: k
        for k, v in tokens_data.items()
        if isinstance(v, dict) and v.get("token")
    }
    for token in invalid_tokens:
        key = token_to_key.get(token)
        if key:
            try:
                db.reference(f"/fcm_tokens/{key}").delete()
            except Exception:
                pass

KST = timezone(timedelta(hours=9))
print(f"[완료] {total_success}/{len(tokens)} 발송 성공 — {datetime.now(KST).strftime('%H:%M:%S KST')}")
