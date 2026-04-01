import anthropic, json, os
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
today = datetime.now(KST).strftime("%Y년 %m월 %d일")
today_iso = datetime.now(KST).strftime("%Y-%m-%d")

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM = f"""당신은 서울대학교 소비자학과 학생을 위한 데일리 브리핑 어시스턴트입니다.
웹 검색으로 {today} 기준 최신 정보를 수집하세요.
반드시 순수 JSON만 반환하세요. 마크다운 코드블록이나 설명 없이 JSON만 출력하세요.
모든 내용은 한국어로 작성하세요."""

SECTIONS = {
    "econ": f"""{today} 기준 한국 경제 상황을 웹 검색으로 조사하고 아래 JSON만 반환하세요:
{{"summary":"2문장 요약","cards":[{{"tag":"카테고리","headline":"제목","body":"2-3문장. 구체적 수치 포함.","insight":"소비자학 관점 시사점 1-2문장"}}]}}
cards 3-4개. 한국은행 기준금리 / USD/KRW 환율 / KOSPI / 거시경제 흐름 각각 다루기.""",
    "politics": f"""{today} 기준 주요 정치·사회 이슈를 웹 검색으로 조사하고 아래 JSON만 반환하세요:
{{"summary":"2문장 요약","cards":[{{"tag":"카테고리","headline":"제목","body":"2-3문장 설명.","insight":"소비자·시장 영향 1-2문장"}}]}}
cards 3-4개. 국내외 주요 이슈 포함.""",
    "consumer": f"""{today} 기준 소비자 트렌드·마케팅 이슈를 웹 검색으로 조사하고 아래 JSON만 반환하세요:
{{"summary":"2문장 요약","cards":[{{"tag":"카테고리","headline":"제목","body":"2-3문장. 소비자학 맥락 포함.","insight":"소비자학 이론 연결 1-2문장"}}]}}
cards 3-4개. 마케팅 전략 / MZ소비 / ESG / 유통 트렌드 포함."""
}

def fetch_section(prompt):
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1500,
        system=SYSTEM,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )
    raw = "\n".join(block.text for block in response.content if hasattr(block, "text"))
    start = min((raw.find(c) for c in ["{", "["] if raw.find(c) != -1), default=-1)
    if start == -1:
        return {"summary": "데이터를 불러오지 못했습니다.", "cards": []}
    end = max(raw.rfind("}"), raw.rfind("]"))
    return json.loads(raw[start:end + 1])

def main():
    print(f"[{today}] 브리핑 생성 시작...")
    briefing = {"date": today_iso, "date_kr": today, "sections": {}}
    for key, prompt in SECTIONS.items():
        print(f"  -> {key} 수집 중...")
        try:
            briefing["sections"][key] = fetch_section(prompt)
            print(f"  v {key} 완료")
        except Exception as e:
            print(f"  x {key} 실패: {e}")
            briefing["sections"][key] = {"summary": "오류 발생", "cards": []}
    os.makedirs("pwa", exist_ok=True)
    with open("pwa/briefing.json", "w", encoding="utf-8") as f:
        json.dump(briefing, f, ensure_ascii=False, indent=2)
    print("완료!")

if __name__ == "__main__":
    main()
