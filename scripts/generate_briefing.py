import anthropic, json, os, time, re
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET

KST = timezone(timedelta(hours=9))
today = datetime.now(KST).strftime("%Y년 %m월 %d일")
today_iso = datetime.now(KST).strftime("%Y-%m-%d")

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DailyBriefingBot/1.0)"}

RSS_FEEDS = {
    "econ": [
        {"name": "매일경제", "url": "https://www.mk.co.kr/rss/40300001/"},
        {"name": "한국경제", "url": "https://www.hankyung.com/feed/economy"},
    ],
    "politics": [
        {"name": "연합뉴스", "url": "https://www.yna.co.kr/rss/politics.xml"},
        {"name": "KBS뉴스", "url": "https://news.kbs.co.kr/rss/rss.do?cid=1"},
    ],
    "consumer": [
        {"name": "소비자평가", "url": "https://www.iconsumer.or.kr/rss/allArticle.xml"},
        {"name": "마케팅조선", "url": "https://marketing.chosun.com/rss/allArticle.xml"},
        {"name": "한국소비자원", "url": "https://www.kca.go.kr/rss/news.xml"},
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
            desc = re.sub(r'<[^>]+>|\[CDATA\[|\]\]', '', desc).strip()[:200]
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
        news.extend(parse_rss(feed["url"], feed["name"]))
        time.sleep(0.5)
    return news[:8]


def fetch_bok_indicators():
    indicators = {"rate": "2.50% (2026년 2월 동결)", "news": [], "exchange": "알 수 없음", "kospi": "알 수 없음"}
    try:
        bok_rss = "https://www.bok.or.kr/portal/bbs/P0000559/list.do?menuNo=200690&rssYn=Y"
        req = urllib.request.Request(bok_rss, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as res:
            root = ET.fromstring(res.read())
        for item in root.findall(".//item")[:3]:
            title = re.sub(r'<[^>]+>', '', item.findtext("title", "")).strip()
            link = item.findtext("link", "").strip()
            if title:
                indicators["news"].append({"title": title, "url": link, "source": "한국은행"})
        print(f"     v 한국은행: {len(indicators['news'])}건")
    except Exception as e:
        print(f"     x 한국은행 RSS 실패: {e}")

    try:
        req = urllib.request.Request("https://open.er-api.com/v6/latest/USD", headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read())
        krw = data.get("rates", {}).get("KRW", 0)
        if krw:
            indicators["exchange"] = f"1달러 = {krw:,.0f}원"
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


def parse_json_safe(raw):
    """JSON을 안전하게 파싱 (4단계 시도)"""
    raw = re.sub(r'```json|```', '', raw).strip()
    start = raw.find('{')
    end = raw.rfind('}')
    if start == -1 or end == -1:
        raise ValueError("JSON 구조를 찾을 수 없음")
    json_str = raw[start:end + 1]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    try:
        return json.loads(re.sub(r'\n\s*', ' ', json_str))
    except json.JSONDecodeError:
        pass

    try:
        return json.loads(re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', json_str))
    except json.JSONDecodeError:
        pass

    try:
        fixed = re.sub(r'(?<=: ")(.*?)(?="(?:\s*[,}\]]))',
                       lambda m: m.group(0).replace('"', "'"), json_str)
        return json.loads(fixed)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 파싱 최종 실패: {e}")


def generate_with_claude(bok, econ_news, politics_news, consumer_news):
    def index_news(news_list, prefix):
        return [{"id": f"{prefix}{i}", "title": n["title"], "desc": n["desc"], "source": n["source"]}
                for i, n in enumerate(news_list)]

    econ_indexed = index_news(econ_news, "E")
    politics_indexed = index_news(politics_news, "P")
    consumer_indexed = index_news(consumer_news, "C")

    url_map = {}
    for i, n in enumerate(econ_news):
        url_map[f"E{i}"] = {"title": n["source"], "url": n["url"]}
    for i, n in enumerate(politics_news):
        url_map[f"P{i}"] = {"title": n["source"], "url": n["url"]}
    for i, n in enumerate(consumer_news):
        url_map[f"C{i}"] = {"title": n["source"], "url": n["url"]}

    prompt = f"""아래는 {today} 기준 실제 수집된 뉴스입니다.
서울대 소비자학과 학생을 위한 브리핑 JSON을 작성하세요.

=== 경제 지표 (반드시 econ 카드에 포함할것) ===
한국은행 기준금리: {bok['rate']}
원달러환율: {bok['exchange']}
KOSPI지수: {bok['kospi']}

=== 경제 뉴스 (ID: E0~E7) ===
{json.dumps(econ_indexed, ensure_ascii=False)}

=== 정치·사회 뉴스 (ID: P0~P7) ===
{json.dumps(politics_indexed, ensure_ascii=False)}

=== 소비자·마케팅 뉴스 (ID: C0~C7) ===
{json.dumps(consumer_indexed, ensure_ascii=False)}

아래 JSON 형식으로만 응답하세요. 코드블록 없이 JSON만:
{{
  "econ": {{
    "summary": "2문장 요약",
    "cards": [
      {{"tag": "태그", "headline": "제목", "body": "2-3문장 설명. 수치 포함.", "insight": "소비자학 관점", "source_ids": ["E0", "E1"]}}
    ]
  }},
  "politics": {{
    "summary": "2문장 요약",
    "cards": [
      {{"tag": "태그", "headline": "제목", "body": "2-3문장 설명.", "insight": "소비자 시장 영향", "source_ids": ["P0"]}}
    ]
  }},
  "consumer": {{
    "summary": "2문장 요약",
    "cards": [
      {{"tag": "태그", "headline": "제목", "body": "2-3문장 설명.", "insight": "소비자학 이론 연결", "source_ids": ["C0", "C1"]}}
    ]
  }}
}}
규칙:
1. 각 섹션 cards 정확히 3개
2. source_ids에는 위 ID만 사용
3. body와 insight 문장에 큰따옴표 절대 사용 금지
4. 숫자와 단위 사이 공백 없이 붙여쓰기 (예: 5377.30포인트, 1510원, 2.50%)
5. econ 첫번째 카드 body에 반드시 KOSPI 수치와 환율 수치를 포함할것
   예시: KOSPI는 5377.30으로 상승했으며 원달러환율은 1510원을 기록했다."""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )

    result = parse_json_safe(response.content[0].text)

    # source_ids → 실제 URL로 변환 (핵심: parse 후 바로 실행)
    for section in ["econ", "politics", "consumer"]:
        for card in result.get(section, {}).get("cards", []):
            ids = card.pop("source_ids", [])
            existing = card.pop("sources", [])
            mapped = [url_map[sid] for sid in ids if sid in url_map]
            card["sources"] = mapped if mapped else existing

    return result


def main():
    print(f"[{today}] 브리핑 생성 시작...")

    print("  -> 한국은행 지표 수집 중...")
    bok = fetch_bok_indicators()

    print("  -> 경제 뉴스 수집 중 (매일경제, 한국경제)...")
    econ_news = fetch_section_news("econ")

    print("  -> 정치·사회 뉴스 수집 중 (연합뉴스, KBS)...")
    politics_news = fetch_section_news("politics")

    print("  -> 소비자 뉴스 수집 중 (소비자평가, 마케팅조선, 한국소비자원)...")
    consumer_news = fetch_section_news("consumer")

    print("  -> Claude Haiku 분석 중 (1회 호출)...")
    try:
        sections = generate_with_claude(bok, econ_news, politics_news, consumer_news)
        print("  v 분석 완료!")
    except Exception as e:
        print(f"  x 분석 실패: {e}")
        sections = {
            "econ": {"summary": "오류 발생", "cards": []},
            "politics": {"summary": "오류 발생", "cards": []},
            "consumer": {"summary": "오류 발생", "cards": []}
        }

    briefing = {"date": today_iso, "date_kr": today, "sections": sections}
    os.makedirs("docs", exist_ok=True)
    with open("docs/briefing.json", "w", encoding="utf-8") as f:
        json.dump(briefing, f, ensure_ascii=False, indent=2)
    print("완료!")


if __name__ == "__main__":
    main()
