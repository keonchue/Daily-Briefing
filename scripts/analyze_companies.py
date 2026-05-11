#!/usr/bin/env python3
"""기업 분석 자동 생성 — 네이버 뉴스 기반 팩트 분석"""

import os
import json
import re
import html as html_mod
import urllib.request
import urllib.parse
import anthropic
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "companies.json")
ARCHIVE_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "companies-archive")
NAVER_NEWS_API = "https://openapi.naver.com/v1/search/news.json"


# ── 유틸리티 ──────────────────────────────────────────────────────────────────

def strip_html(text):
    return html_mod.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def fetch_news(query, display=15):
    """네이버 뉴스 검색 API"""
    naver_id = os.environ.get("NAVER_CLIENT_ID")
    naver_secret = os.environ.get("NAVER_CLIENT_SECRET")
    if not naver_id or not naver_secret:
        print(f"  [경고] 네이버 API 키 없음 — '{query}' 검색 건너뜀")
        return []
    params = urllib.parse.urlencode({"query": query, "display": display, "sort": "date"})
    req = urllib.request.Request(f"{NAVER_NEWS_API}?{params}")
    req.add_header("X-Naver-Client-Id", naver_id)
    req.add_header("X-Naver-Client-Secret", naver_secret)
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read().decode("utf-8"))
        return [
            {"title": strip_html(item["title"]),
             "desc": strip_html(item["description"]),
             "link": item["link"]}
            for item in data.get("items", [])
        ]
    except Exception as e:
        print(f"  [오류] 뉴스 검색 실패 ({query}): {e}")
        return []


def parse_json_response(text):
    """Claude 응답에서 JSON 추출"""
    text = text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.split("```")[0].strip()
    return json.loads(text)


# ── 아카이브 ──────────────────────────────────────────────────────────────────

def get_recent_companies(weeks=8):
    """최근 N주간 분석한 기업명 목록"""
    index_path = os.path.join(ARCHIVE_DIR, "index.json")
    if not os.path.exists(index_path):
        return []
    with open(index_path, encoding="utf-8") as f:
        dates = json.load(f).get("dates", [])
    recent = []
    for d in sorted(dates, reverse=True)[:weeks]:
        path = os.path.join(ARCHIVE_DIR, f"{d}.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for ind in data.get("industries", []):
            for c in ind.get("companies", []):
                name = c.get("name_ko") or c.get("name", "")
                if name and name not in recent:
                    recent.append(name)
    return recent


# ── 1단계: 트렌딩 뉴스 기반 기업 선정 ────────────────────────────────────────

def pick_companies(client, recent_names):
    """최신 뉴스 헤드라인을 참고해 Claude가 기업 3개 선정"""
    search_keywords = [
        "소비자 트렌드 기업", "마케팅 전략 브랜드",
        "유통 이커머스", "신제품 출시", "IT 플랫폼 서비스",
    ]
    headlines = []
    for kw in search_keywords:
        for a in fetch_news(kw, display=10):
            if a["title"] not in headlines:
                headlines.append(a["title"])

    headlines_text = "\n".join(f"- {h}" for h in headlines[:50])
    exclude = ""
    if recent_names:
        exclude = f"\n\n최근 분석한 기업 (반드시 제외하세요): {', '.join(recent_names)}"

    prompt = f"""당신은 소비자학 연구자입니다. 아래는 최근 한국 뉴스 헤드라인입니다.

=== 최근 뉴스 헤드라인 ===
{headlines_text}
========================

위 뉴스를 참고하여, 이번 주 '기업 분석' 코너에 실을 기업 3개를 선정해주세요.

선정 기준:
- 위 뉴스에서 주목받고 있거나, 소비자 관점에서 분석할 가치가 있는 B2C 기업
- 3개 기업은 반드시 서로 다른 업종이어야 함
- 한국 기업과 글로벌 기업을 적절히 섞을 것
- 실제로 존재하는 기업만 선정할 것{exclude}

아래 JSON 배열로만 응답하세요 (다른 텍스트 없이):
[
  {{"id": "영문소문자", "name": "English Name", "name_ko": "한국어명", "ticker": "상장티커 또는 비상장", "country": "국가", "industry_id": "영문소문자", "industry_name": "업종 (한국어, 간결하게)"}},
  {{"id": "...", "name": "...", "name_ko": "...", "ticker": "...", "country": "...", "industry_id": "...", "industry_name": "..."}},
  {{"id": "...", "name": "...", "name_ko": "...", "ticker": "...", "country": "...", "industry_id": "...", "industry_name": "..."}}
]"""

    print(f"  뉴스 헤드라인 {len(headlines)}개 수집 완료")
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    picks = parse_json_response(message.content[0].text)
    if not isinstance(picks, list) or len(picks) < 1:
        raise ValueError("기업 선정 결과가 비어 있음")
    return picks[:3]


# ── 2단계: 뉴스 기반 기업 분석 ────────────────────────────────────────────────

def analyze_company(client, company, industry_name, articles):
    """실제 뉴스 기사를 근거로 기업 분석"""
    articles_text = "\n\n".join(
        f"[기사 {i+1}] {a['title']}\n{a['desc']}"
        for i, a in enumerate(articles[:15])
    )

    prompt = f"""당신은 소비자학 연구자입니다. 아래 실제 뉴스 기사를 바탕으로 기업을 소비자 관점에서 분석해주세요.

기업: {company['name_ko']} ({company['name']}, {company['ticker']})
업계: {industry_name}
기준일: {datetime.now(KST).strftime('%Y년 %m월')}

=== 최근 뉴스 기사 ({len(articles)}건) ===
{articles_text}
========================================

분석 규칙:
- 위 기사의 내용만을 근거로 분석하세요
- 기사에서 확인할 수 없는 내용은 절대 추측하거나 지어내지 마세요
- 구체적 수치, 사실관계는 기사에 있는 것만 인용하세요
- recent_issues는 위 기사에서 실제로 보도된 이슈만 작성하세요

아래 JSON 형식으로만 응답 (다른 텍스트 없이):
{{
  "overview": "기업 개요 3–4문장 (기사 내용 기반, 소비자학·마케팅 관점)",
  "swot": {{
    "strengths":     ["강점 1 (기사 근거)", "강점 2", "강점 3"],
    "weaknesses":    ["약점 1 (기사 근거)", "약점 2", "약점 3"],
    "opportunities": ["기회 1 (기사 근거)", "기회 2", "기회 3"],
    "threats":       ["위협 1 (기사 근거)", "위협 2", "위협 3"]
  }},
  "consumer_strategy": "소비자 전략 3–4문장 (기사에서 확인되는 실제 전략·움직임 중심)",
  "recent_issues": [
    {{"title": "기사 기반 이슈 제목", "content": "기사 내용 요약 2–3문장"}},
    {{"title": "기사 기반 이슈 제목", "content": "기사 내용 요약 2–3문장"}},
    {{"title": "기사 기반 이슈 제목", "content": "기사 내용 요약 2–3문장"}}
  ]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return parse_json_response(message.content[0].text)


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY 환경변수가 필요합니다.")

    client = anthropic.Anthropic(api_key=api_key)

    # 1) 최근 분석 기업 확인
    recent = get_recent_companies(weeks=8)
    print(f"최근 8주 분석 기업 ({len(recent)}개): {', '.join(recent) if recent else '없음'}")

    # 2) 트렌딩 뉴스 기반 기업 선정
    print("\n[1단계] 기업 선정 중...")
    picks = pick_companies(client, recent)
    for p in picks:
        print(f"  ✓ {p['name_ko']} ({p['name']}) — {p['industry_name']}")

    # 3) 업종 맵 구성
    industry_map = {}
    for p in picks:
        iid = p["industry_id"]
        if iid not in industry_map:
            industry_map[iid] = {"id": iid, "name": p["industry_name"], "companies": []}

    # 4) 각 기업별 뉴스 수집 + 분석
    for p in picks:
        name_ko = p["name_ko"]
        industry_name = p["industry_name"]

        # 뉴스 검색: 기업명 + 소비자 키워드
        print(f"\n[2단계] {name_ko} 뉴스 수집 중...")
        articles = fetch_news(f"{name_ko} 소비자", display=15)
        if len(articles) < 5:
            articles += fetch_news(name_ko, display=15)
        # 중복 제거
        seen_titles = set()
        unique = []
        for a in articles:
            if a["title"] not in seen_titles:
                seen_titles.add(a["title"])
                unique.append(a)
        articles = unique[:15]
        print(f"  기사 {len(articles)}건 확보")

        if not articles:
            print(f"  [경고] 기사를 찾지 못해 건너뜀")
            industry_map[p["industry_id"]]["companies"].append({
                "id": p["id"], "name": p["name"], "name_ko": name_ko,
                "ticker": p["ticker"], "country": p["country"],
                "updated_at": datetime.now(KST).strftime("%Y-%m-%d"),
                "overview": "관련 뉴스를 찾지 못해 분석을 생성할 수 없습니다.",
                "swot": {"strengths": [], "weaknesses": [], "opportunities": [], "threats": []},
                "consumer_strategy": "", "recent_issues": [],
            })
            continue

        print(f"[3단계] {name_ko} 분석 중...")
        try:
            analysis = analyze_company(client, p, industry_name, articles)
            company_data = {
                "id": p["id"], "name": p["name"], "name_ko": name_ko,
                "ticker": p["ticker"], "country": p["country"],
                **analysis,
                "updated_at": datetime.now(KST).strftime("%Y-%m-%d"),
            }
            industry_map[p["industry_id"]]["companies"].append(company_data)
            print(f"  완료 ✓")
        except Exception as e:
            print(f"  오류: {e}")
            industry_map[p["industry_id"]]["companies"].append({
                "id": p["id"], "name": p["name"], "name_ko": name_ko,
                "ticker": p["ticker"], "country": p["country"],
                "updated_at": datetime.now(KST).strftime("%Y-%m-%d"),
                "overview": "분석 데이터를 불러올 수 없습니다.",
                "swot": {"strengths": [], "weaknesses": [], "opportunities": [], "threats": []},
                "consumer_strategy": "", "recent_issues": [],
            })

    # 5) 결과 저장
    today_str = datetime.now(KST).strftime("%Y-%m-%d")
    output = {
        "updated_at": datetime.now(KST).isoformat(),
        "date": today_str,
        "industries": list(industry_map.values()),
    }

    all_companies = [c for ind in output["industries"] for c in ind["companies"]]
    has_valid = any(
        c.get("overview") and c["overview"] not in (
            "분석 데이터를 불러올 수 없습니다.",
            "관련 뉴스를 찾지 못해 분석을 생성할 수 없습니다.",
        )
        for c in all_companies
    )

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    if has_valid:
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n완료: docs/companies.json 저장됨")
    else:
        print("\n경고: 모든 기업 분석이 실패했습니다. 기존 companies.json 유지.")
        if not os.path.exists(OUTPUT_PATH):
            with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
        return

    # 6) 아카이브 저장
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    archive_path = os.path.join(ARCHIVE_DIR, f"{today_str}.json")
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"아카이브 저장됨: companies-archive/{today_str}.json")

    index_path = os.path.join(ARCHIVE_DIR, "index.json")
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            dates = json.load(f).get("dates", [])
    else:
        dates = []
    if today_str not in dates:
        dates.append(today_str)
        dates.sort()
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"dates": dates}, f, ensure_ascii=False)
    print(f"인덱스 업데이트됨: {len(dates)}개 항목")


if __name__ == "__main__":
    main()
