#!/usr/bin/env python3
"""기업 분석 자동 생성 스크립트 — 매주 Claude가 새로운 기업을 선정·분석"""

import os
import json
import anthropic
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "companies.json")
ARCHIVE_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "companies-archive")


def get_recent_companies(weeks=8):
    """최근 N주간 분석한 기업명 목록을 아카이브에서 읽어옴"""
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


def pick_companies(client, recent_names):
    """Claude에게 이번 주 분석할 기업 3개를 선정하게 함"""
    exclude = ""
    if recent_names:
        exclude = f"\n\n최근 분석한 기업 (반드시 제외): {', '.join(recent_names)}"

    prompt = f"""당신은 소비자학 연구자입니다. 이번 주 기업 분석 코너에 실을 기업 3개를 선정해주세요.

조건:
- 소비자와 밀접한 B2C 기업 (한국 또는 글로벌)
- 3개 기업은 서로 다른 업종이어야 함 (예: 테크, 유통, 식품, 뷰티, 금융, 모빌리티, 엔터테인먼트, 패션 등)
- 한국 기업과 글로벌 기업을 적절히 섞을 것
- 소비자 관점에서 흥미로운 전략을 펼치거나, 최근 주목할 만한 움직임이 있는 기업 우선
- 대기업뿐 아니라 성장 중인 중견·스타트업도 포함 가능{exclude}

아래 JSON 배열로만 응답 (코드블록이나 다른 텍스트 없이 JSON만):
[
  {{"id": "영문소문자id", "name": "English Name", "name_ko": "한국어명", "ticker": "티커 또는 비상장", "country": "국가", "industry_id": "영문소문자id", "industry_name": "업종명 (한국어, 간결하게)"}},
  {{"id": "...", "name": "...", "name_ko": "...", "ticker": "...", "country": "...", "industry_id": "...", "industry_name": "..."}},
  {{"id": "...", "name": "...", "name_ko": "...", "ticker": "...", "country": "...", "industry_id": "...", "industry_name": "..."}}
]"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    content = message.content[0].text.strip()
    if "```" in content:
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.split("```")[0].strip()

    picks = json.loads(content)
    if not isinstance(picks, list) or len(picks) < 1:
        raise ValueError("기업 선정 결과가 비어 있음")
    return picks[:3]


def analyze_company(client, company, industry_name):
    """선정된 기업 1개를 소비자 관점에서 분석"""
    prompt = f"""당신은 소비자학 연구자입니다. 다음 기업을 소비자 관점에서 분석해주세요.

기업: {company['name_ko']} ({company['name']}, {company['ticker']})
업계: {industry_name}
기준일: {datetime.now(KST).strftime('%Y년 %m월')}

아래 JSON 형식으로만 응답해주세요 (코드블록이나 다른 텍스트 없이 JSON만):

{{
  "overview": "기업 개요 3–4문장 (소비자학·마케팅 관점, 시장 내 포지션과 소비자와의 관계 중심)",
  "swot": {{
    "strengths":     ["강점 항목 1", "강점 항목 2", "강점 항목 3"],
    "weaknesses":    ["약점 항목 1", "약점 항목 2", "약점 항목 3"],
    "opportunities": ["기회 항목 1", "기회 항목 2", "기회 항목 3"],
    "threats":       ["위협 항목 1", "위협 항목 2", "위협 항목 3"]
  }},
  "consumer_strategy": "소비자 전략 3–4문장 (핵심 소비자 가치 제안·차별화 전략·충성도 프로그램 등)",
  "recent_issues": [
    {{"title": "이슈 제목 (간결하게)", "content": "이슈 내용 2–3문장"}},
    {{"title": "이슈 제목 (간결하게)", "content": "이슈 내용 2–3문장"}},
    {{"title": "이슈 제목 (간결하게)", "content": "이슈 내용 2–3문장"}}
  ]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    content = message.content[0].text.strip()
    if "```" in content:
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.split("```")[0].strip()

    return json.loads(content)


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY 환경변수가 필요합니다.")

    client = anthropic.Anthropic(api_key=api_key)

    # 1) 최근 분석 기업 확인
    recent = get_recent_companies(weeks=8)
    print(f"최근 8주 분석 기업 ({len(recent)}개): {', '.join(recent) if recent else '없음'}")

    # 2) Claude가 이번 주 기업 3개 선정
    print("\n기업 선정 중...")
    picks = pick_companies(client, recent)
    for p in picks:
        print(f"  → {p['name_ko']} ({p['name']}) [{p['industry_name']}]")

    # 3) 업종 맵 구성 (선정 결과에서 동적 생성)
    industry_map = {}
    for p in picks:
        iid = p["industry_id"]
        if iid not in industry_map:
            industry_map[iid] = {"id": iid, "name": p["industry_name"], "companies": []}

    # 4) 각 기업 분석
    for p in picks:
        name_ko = p["name_ko"]
        industry_name = p["industry_name"]
        print(f"\n분석 중: {name_ko} ({p['name']})...")
        try:
            analysis = analyze_company(client, p, industry_name)
            company_data = {
                "id": p["id"],
                "name": p["name"],
                "name_ko": name_ko,
                "ticker": p["ticker"],
                "country": p["country"],
                **analysis,
                "updated_at": datetime.now(KST).strftime("%Y-%m-%d"),
            }
            industry_map[p["industry_id"]]["companies"].append(company_data)
            print(f"  완료 ✓")
        except Exception as e:
            print(f"  오류: {e}")
            industry_map[p["industry_id"]]["companies"].append({
                "id": p["id"],
                "name": p["name"],
                "name_ko": name_ko,
                "ticker": p["ticker"],
                "country": p["country"],
                "updated_at": datetime.now(KST).strftime("%Y-%m-%d"),
                "overview": "분석 데이터를 불러올 수 없습니다.",
                "swot": {"strengths": [], "weaknesses": [], "opportunities": [], "threats": []},
                "consumer_strategy": "",
                "recent_issues": [],
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
        c.get("overview") and c["overview"] != "분석 데이터를 불러올 수 없습니다."
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
