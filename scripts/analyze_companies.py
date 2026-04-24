#!/usr/bin/env python3
"""기업 분석 자동 생성 스크립트 (Claude API 사용)"""

import os
import json
import anthropic
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "companies.json")

INDUSTRIES = [
    {"id": "bigtech", "name": "빅테크"},
    {"id": "retail",  "name": "유통"},
    {"id": "adtech",  "name": "광고/마케팅"},
]

COMPANIES = [
    {"id": "apple",   "name": "Apple",           "name_ko": "애플",  "ticker": "AAPL", "country": "미국", "industry_id": "bigtech"},
    {"id": "coupang", "name": "Coupang",          "name_ko": "쿠팡",  "ticker": "CPNG", "country": "한국", "industry_id": "retail"},
    {"id": "meta",    "name": "Meta Platforms",   "name_ko": "메타",  "ticker": "META", "country": "미국", "industry_id": "adtech"},
]


def analyze_company(client: anthropic.Anthropic, company: dict) -> dict:
    industry_name = next(i["name"] for i in INDUSTRIES if i["id"] == company["industry_id"])
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
    industry_map = {ind["id"]: {**ind, "companies": []} for ind in INDUSTRIES}

    for company in COMPANIES:
        print(f"분석 중: {company['name_ko']} ({company['name']})...")
        try:
            analysis = analyze_company(client, company)
            company_data = {
                **company,
                **analysis,
                "updated_at": datetime.now(KST).strftime("%Y-%m-%d"),
            }
            del company_data["industry_id"]
            industry_map[company["industry_id"]]["companies"].append(company_data)
            print(f"  완료 ✓")
        except Exception as e:
            print(f"  오류: {e}")
            industry_map[company["industry_id"]]["companies"].append({
                **company,
                "updated_at": datetime.now(KST).strftime("%Y-%m-%d"),
                "overview": "분석 데이터를 불러올 수 없습니다.",
                "swot": {"strengths": [], "weaknesses": [], "opportunities": [], "threats": []},
                "consumer_strategy": "",
                "recent_issues": [],
            })

    today = datetime.now(KST).strftime("%Y-%m-%d")
    output = {
        "updated_at": datetime.now(KST).isoformat(),
        "date": today,
        "industries": list(industry_map.values()),
    }

    # 실제 분석이 하나라도 성공했는지 확인
    all_companies = [c for ind in output["industries"] for c in ind["companies"]]
    has_valid = any(
        c.get("overview") and c["overview"] != "분석 데이터를 불러올 수 없습니다."
        for c in all_companies
    )

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    if has_valid:
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"완료: docs/companies.json 저장됨")
    else:
        print("경고: 모든 기업 분석이 실패했습니다. 기존 companies.json 유지.")
        # 기존 파일이 없을 때만 저장 (최초 실행 시 빈 파일보다는 오류 데이터라도)
        if not os.path.exists(OUTPUT_PATH):
            with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            print("  (기존 파일 없어 저장)")
        return

    # 아카이브 저장
    archive_dir = os.path.join(os.path.dirname(OUTPUT_PATH), "companies-archive")
    os.makedirs(archive_dir, exist_ok=True)

    archive_path = os.path.join(archive_dir, f"{today}.json")
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"아카이브 저장됨: companies-archive/{today}.json")

    # 아카이브 인덱스 업데이트
    index_path = os.path.join(archive_dir, "index.json")
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
        dates = index.get("dates", [])
    else:
        dates = []
    if today not in dates:
        dates.append(today)
        dates.sort()
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"dates": dates}, f, ensure_ascii=False)
    print(f"인덱스 업데이트됨: {len(dates)}개 항목")


if __name__ == "__main__":
    main()
