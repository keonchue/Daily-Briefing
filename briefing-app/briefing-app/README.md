# 소비자 데일리 브리핑 PWA

서울대학교 소비자학과 학생을 위한 매일 아침 자동 브리핑 앱입니다.

## 구조

```
briefing-app/
├── .github/
│   └── workflows/
│       └── daily_briefing.yml   ← 매일 오전 7시 자동 실행
├── scripts/
│   └── generate_briefing.py     ← 브리핑 생성 Python 스크립트
└── pwa/
    ├── index.html               ← 메인 웹앱
    ├── manifest.json            ← PWA 설정
    ├── sw.js                    ← Service Worker (알림/캐시)
    └── briefing.json            ← 생성된 브리핑 데이터 (자동 업데이트)
```

## 설치 방법 (5분)

### 1단계 — GitHub 저장소 만들기
1. [github.com](https://github.com) → **New repository**
2. 이름: `daily-briefing` (Public으로 설정)
3. 이 폴더의 파일을 모두 업로드

### 2단계 — Anthropic API 키 등록
1. [console.anthropic.com](https://console.anthropic.com) → API Keys에서 키 발급
2. GitHub 저장소 → **Settings → Secrets → Actions**
3. **New secret** → 이름: `ANTHROPIC_API_KEY`, 값: 발급받은 키

### 3단계 — GitHub Pages 활성화
1. GitHub 저장소 → **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` / Folder: `/pwa`
4. Save → 잠시 후 `https://[유저명].github.io/daily-briefing/` 로 접속 가능

### 4단계 — 폰에서 홈 화면에 추가
- **iPhone (Safari)**: 공유 버튼 → "홈 화면에 추가"
- **Android (Chrome)**: 메뉴 → "홈 화면에 추가" 또는 설치 팝업

### 5단계 — 첫 브리핑 즉시 생성하기
GitHub 저장소 → **Actions** 탭 → `소비자 데일리 브리핑 생성` → **Run workflow**

이후 매일 오전 7시(한국 시간)에 자동으로 브리핑이 생성됩니다.

## 동작 방식

```
매일 오전 7시
    ↓
GitHub Actions 실행
    ↓
generate_briefing.py → Anthropic API (웹 검색 포함)
    ↓
briefing.json 업데이트 → Git 자동 커밋·푸시
    ↓
GitHub Pages 자동 배포
    ↓
PWA 앱에서 최신 브리핑 표시 + 푸시 알림
```

## 비용

- GitHub Actions: **무료** (월 2,000분 무료)
- GitHub Pages: **무료**
- Anthropic API: 브리핑 1회 생성 약 **$0.01~0.03** 수준
