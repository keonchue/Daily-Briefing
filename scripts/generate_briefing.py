import anthropic, json, os, time, re
import urllib.request
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET

KST = timezone(timedelta(hours=9))
today = datetime.now(KST).strftime("%Y년 %m월 %d일")
today_iso = datetime.now(KST).strftime("%Y-%m-%d")

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
AV_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DailyBriefingBot/1.0)"}

RSS_FEEDS = {
    "econ": [
        {"name": "구글뉴스 경제①", "url": "https://news.google.com/rss/search?q=한국경제+금리+환율&hl=ko&gl=KR&ceid=KR:ko"},
        {"name": "구글뉴스 경제②", "url": "https://news.google.com/rss/search?q=소비+물가+유통&hl=ko&gl=KR&ceid=KR:ko"},
    ],
    "politics": [
        {"name": "구글뉴스 정치①", "url": "https://news.google.com/rss/search?q=한국정치+사회이슈&hl=ko&gl=KR&ceid=KR:ko"},
        {"name": "구글뉴스 정치②", "url": "https://news.google.com/rss/search?q=한국사회+정책&hl=ko&gl=KR&ceid=KR:ko"},
    ],
    "consumer": [
        {"name": "소비자평가", "url": "https://www.iconsumer.or.kr/rss/allArticle.xml"},
        {"name": "마케팅조선", "url": "https://marketing.chosun.com/rss/allArticle.xml"},
        {"name": "한국소비자원", "url": "https://www.kca.go.kr/rss/news.xml"},
        {"name": "매일경제 소비", "url": "https://www.mk.co.kr/rss/50200011/"},
        {"name": "한국경제 소비자", "url": "https://www.hankyung.com/feed/consumer"},
        {"name": "연합뉴스 경제", "url": "https://www.yna.co.kr/rss/economy.xml"},
        {"name": "머니투데이", "url": "https://rss.mt.co.kr/mt_news/sec_list.xml?code=0020"},
    ],
}


def parse_rss(feed_url, source_name, limit=4):
    try:
        req = urllib.request.Request(feed_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as res:
            content = res.read()
        root = ET.fromstring(content)
        items = []
        entries = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
        for entry in entries[:limit]:
            title = (entry.findtext("title") or entry.findtext("{http://www.w3.org/2005/Atom}title") or "")
            link = (entry.findtext("link") or (entry.find("{http://www.w3.org/2005/Atom}link") or entry).get("href", "") or "")
            desc = (entry.findtext("description") or entry.findtext("{http://www.w3.org/2005/Atom}summary") or "")
            title = re.sub(r'<[^>]+>|\[CDATA\[|\]\]', '', title).strip()
            desc = re.sub(r'<[^>]+>|\[CDATA\[|\]\]', '', desc).strip()[:150]
            if title:
                items.append({"title": title, "url": link.strip(), "desc": desc, "source": source_name})
        print(f"     v {source_name}: {len(items)}건")
        return items
    except Exception as e:
        print(f"     x {source_name} 실패: {e}")
        return []


def fetch_section_news(section):
    news = []
    for feed in RSS_FEEDS[section]:
        limit = feed.get("limit", 4)
        news.extend(parse_rss(feed["url"], feed["name"], limit=limit))
        time.sleep(0.5)
    return news[:6]


def score_consumer_articles(articles):
    """소비자학 관련도 1~10점 평가, 7점 이상만 반환"""
    if not articles:
        return []

    articles_text = "\n".join(
        [f"A{i}: [{a['source']}] {a['title']}" for i, a in enumerate(articles)]
    )

    prompt = f"""다음 기사들의 소비자학 관련도를 1~10점으로 평가하세요.

평가 기준:
- 소비자 행동: 구매 결정, 소비 패턴, 브랜드 선택, 소비자 심리 등
- 마케팅 전략: 가격 정책, 유통 전략, 광고·홍보, 제품 전략 등
- 소비 트렌드: 새로운 소비 문화, 라이프스타일 변화, MZ세대 소비 등
- 소비자 정책: 소비자 보호법, 규제, 소비자 권리·피해 구제 등
- 시장 구조: 경쟁 환경, 독과점, 유통채널 변화, 플랫폼 경제 등

기사 목록:
{articles_text}

반드시 아래 형식으로만 응답. JSON만 출력:
{{"scores":[{{"id":"A0","score":8}},{{"id":"A1","score":5}}]}}

규칙: 모든 기사에 점수 부여. 문자열 안에 큰따옴표 금지."""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    result = parse_json_safe(response.content[0].text)
    passing_ids = {
        item["id"] for item in result.get("scores", [])
        if item.get("score", 0) >= 7
    }
    filtered = [
        articles[int(aid[1:])]
        for aid in sorted(passing_ids)
        if aid.startswith("A") and aid[1:].isdigit() and int(aid[1:]) < len(articles)
    ]
    print(f"     v 소비자학 관련도 평가: {len(articles)}건 → {len(filtered)}건 (7점 이상)")
    return filtered


def fetch_consumer_news():
    """소비자 섹션: 전체 수집 후 소비자학 관련도 필터링"""
    news = []
    for feed in RSS_FEEDS["consumer"]:
        limit = feed.get("limit", 4)
        news.extend(parse_rss(feed["url"], feed["name"], limit=limit))
        time.sleep(0.5)
    print(f"     -> 소비자학 관련도 평가 중... ({len(news)}건)")
    return score_consumer_articles(news)


def fetch_bok_indicators():
    indicators = {"rate": "2.50%", "exchange": "알 수 없음", "kospi": "알 수 없음"}
    try:
        req = urllib.request.Request("https://open.er-api.com/v6/latest/USD", headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read())
        krw = data.get("rates", {}).get("KRW", 0)
        if krw:
            indicators["exchange"] = f"{krw:,.0f}"
    except Exception as e:
        print(f"     x 환율 조회 실패: {e}")

    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EKS11?interval=1d&range=2d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read())
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        last, prev = closes[-1], closes[-2] if len(closes) > 1 else closes[-1]
        change = ((last - prev) / prev * 100) if prev else 0
        arrow = "▲" if change >= 0 else "▼"
        indicators["kospi"] = f"{last:,.2f} ({arrow}{abs(change):.2f}%)"
    except Exception as e:
        print(f"     x KOSPI 조회 실패: {e}")

    return indicators


def fetch_kospi_history():
    """Yahoo Finance에서 KOSPI 30거래일 히스토리 가져오기"""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EKS11?interval=1d&range=45d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read())
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        pairs = [(ts, c) for ts, c in zip(timestamps, closes) if c is not None]
        pairs = pairs[-30:]
        history = [
            {"date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"), "close": round(c, 2)}
            for ts, c in pairs
        ]
        current = history[-1]["close"]
        prev = history[-2]["close"] if len(history) > 1 else current
        change_pct = round((current - prev) / prev * 100, 2) if prev else 0
        print(f"     v KOSPI 히스토리: {len(history)}일, 현재 {current:,.2f} ({change_pct:+.2f}%)")
        return {"current": round(current, 2), "change_pct": change_pct, "history": history}
    except Exception as e:
        print(f"     x KOSPI 히스토리 조회 실패: {e}")
        return None


def fetch_nasdaq_history():
    """Yahoo Finance에서 NASDAQ 지수(^IXIC) 30거래일 히스토리 가져오기"""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EIXIC?interval=1d&range=45d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read())
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        pairs = [(ts, c) for ts, c in zip(timestamps, closes) if c is not None]
        pairs = pairs[-30:]
        history = [
            {"date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"), "close": round(c, 2)}
            for ts, c in pairs
        ]
        current = history[-1]["close"]
        prev = history[-2]["close"] if len(history) > 1 else current
        change_pct = round((current - prev) / prev * 100, 2) if prev else 0
        print(f"     v NASDAQ(^IXIC) 히스토리: {len(history)}일, 현재 {current:,.2f} ({change_pct:+.2f}%)")
        return {"current": round(current, 2), "change_pct": change_pct, "history": history}
    except Exception as e:
        print(f"     x NASDAQ 히스토리 조회 실패: {e}")
        return None


def parse_json_safe(raw):
    raw = re.sub(r'```json|```', '', raw).strip()
    start = raw.find('{')
    end = raw.rfind('}')
    if start == -1 or end == -1:
        raise ValueError("JSON 없음")
    json_str = raw[start:end + 1]
    for attempt in [
        lambda s: json.loads(s),
        lambda s: json.loads(re.sub(r'\n\s*', ' ', s)),
        lambda s: json.loads(re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', s)),
    ]:
        try:
            return attempt(json_str)
        except json.JSONDecodeError:
            continue
    raise ValueError("JSON 파싱 실패")


def call_claude_section(section_name, news_list, extra_context=""):
    """섹션별로 따로 Claude 호출 — 짧고 안전"""
    url_map = {f"N{i}": {"title": n["source"], "url": n["url"]} for i, n in enumerate(news_list)}
    news_text = "\n".join([f"N{i}: [{n['source']}] {n['title']}" for i, n in enumerate(news_list)])

    prompt = f"""{today} 기준 뉴스로 소비자학과 브리핑 카드 3개를 JSON으로 작성하세요.

{extra_context}
뉴스 목록:
{news_text}

반드시 아래 형식으로만 응답. 코드블록 없이 JSON만 출력:
{{"summary":"2문장요약","cards":[{{"tag":"태그","headline":"제목","body":"설명","insight":"소비자학관점","source_ids":["N0"]}}]}}

규칙: cards 정확히 3개. 문자열안에 큰따옴표 금지. source_ids는 위 N번호만 사용."""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}]
    )
    result = parse_json_safe(response.content[0].text)

    # source_ids → 실제 URL 변환
    for card in result.get("cards", []):
        ids = card.pop("source_ids", [])
        card["sources"] = [url_map[sid] for sid in ids if sid in url_map]

    return result


def main():
    print(f"[{today}] 브리핑 생성 시작...")

    print("  -> 경제 지표 수집 중...")
    bok = fetch_bok_indicators()
    print(f"     환율: {bok['exchange']}원 | KOSPI: {bok['kospi']}")

    print("  -> 시장 차트 데이터 수집 중...")
    market_charts = {}
    kospi_hist = fetch_kospi_history()
    if kospi_hist:
        market_charts["kospi"] = kospi_hist
    nasdaq_hist = fetch_nasdaq_history()
    if nasdaq_hist:
        market_charts["nasdaq"] = nasdaq_hist

    print("  -> 경제 뉴스 수집 중...")
    econ_news = fetch_section_news("econ")
    time.sleep(1)
    print("  -> 정치·사회 뉴스 수집 중...")
    politics_news = fetch_section_news("politics")
    time.sleep(1)
    print("  -> 소비자 뉴스 수집 및 관련도 평가 중...")
    consumer_news = fetch_consumer_news()

    sections = {}

    econ_context = f"경제지표: 기준금리 {bok['rate']}, 원달러환율 {bok['exchange']}원, KOSPI {bok['kospi']}\n첫번째 카드 body에 반드시 KOSPI와 환율 수치를 포함하세요."

    consumer_context = "소비자학 관련도 7점 이상으로 선정된 기사입니다. 소비자 행동, 마케팅 전략, 소비 트렌드, 소비자 정책 관점에서 분석하세요.\n"

    for key, news, ctx in [
        ("econ", econ_news, econ_context),
        ("politics", politics_news, ""),
        ("consumer", consumer_news, consumer_context),
    ]:
        print(f"  -> {key} Claude 분석 중...")
        try:
            sections[key] = call_claude_section(key, news, ctx)
            print(f"  v {key} 완료")
        except Exception as e:
            print(f"  x {key} 실패: {e}")
            sections[key] = {"summary": "오류 발생", "cards": []}
        time.sleep(30)

    briefing = {
        "date": today_iso,
        "date_kr": today,
        "market_charts": market_charts,
        "sections": sections,
    }
    os.makedirs("docs", exist_ok=True)
    with open("docs/briefing.json", "w", encoding="utf-8") as f:
        json.dump(briefing, f, ensure_ascii=False, indent=2)

    # 아카이브 저장
    os.makedirs("docs/archive", exist_ok=True)
    with open(f"docs/archive/{today_iso}.json", "w", encoding="utf-8") as f:
        json.dump(briefing, f, ensure_ascii=False, indent=2)

    # 아카이브 인덱스 업데이트
    index_path = "docs/archive/index.json"
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            idx = json.load(f)
        dates = idx.get("dates", [])
    else:
        dates = []
    if today_iso not in dates:
        dates.append(today_iso)
        dates.sort()
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"dates": dates}, f, ensure_ascii=False)

    print("완료!")


if __name__ == "__main__":
    main()
