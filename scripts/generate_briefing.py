import anthropic, json, os, time, re
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
today = datetime.now(KST).strftime("%Y년 %m월 %d일")
today_iso = datetime.now(KST).strftime("%Y-%m-%d")

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM = f"""당신은 서울대학교 소비자학과 학생을 위한 데일리 브리핑 어시스턴트입니다.
웹 검색으로 {today} 기준 최신 정보를 수집하세요.
반드시 순수 JSON만 반환하세요. 마크다운 코드블록이나 설명 없이 JSON만 출력하세요.
모든 내용은 한국어로 작성하세요.
JSON 문자열 안에 큰따옴표(")를 절대 사용하지 마세요. 작은따옴표나 다른 표현을 사용하세요."""

SECTIONS = {
    "econ": f"""{today} 기준 한국 경제 상황을 웹 검색으로 조사하고 아래 JSON 형식으로만 반환하세요.
{{"summary":"2문장 요약","cards":[{{"tag":"카테고리","headline":"제목","body":"설명","insight":"소비자학 관점","sources":[{{"title":"출처명","url":"URL"}}]}}]}}
cards 3개. 기준금리, 환율, 주가 각각 다루기. 각 카드 sources에 실제 참고 URL 포함.""",
    "politics": f"""{today} 기준 주요 정치·사회 이슈를 웹 검색으로 조사하고 아래 JSON 형식으로만 반환하세요.
{{"summary":"2문장 요약","cards":[{{"tag":"카테고리","headline":"제목","body":"설명","insight":"소비자 영향","sources":[{{"title":"출처명","url":"URL"}}]}}]}}
cards 3개. 국내외 주요 이슈. 각 카드 sources에 실제 참고 URL 포함.""",
    "consumer": f"""{today} 기준 소비자 트렌드·마케팅 이슈를 웹 검색으로 조사하고 아래 JSON 형식으로만 반환하세요.
{{"summary":"2문장 요약","cards":[{{"tag":"카테고리","headline":"제목","body":"설명","insight":"소비자학 이론 연결","sources":[{{"title":"출처명","url":"URL"}}]}}]}}
cards 3개. 마케팅/MZ소비/ESG/유통 트렌드. 각 카드 sources에 실제 참고 URL 포함."""
}


def safe_parse_json(raw: str) -> dict:
    """JSON을 안전하게 파싱합니다."""
    # 코드블록 제거
    raw = re.sub(r'```json|```', '', raw).strip()

    # 첫 번째 { 부터 마지막 } 까지 추출
    start = raw.find('{')
    end = raw.rfind('}')
    if start == -1 or end == -1:
        raise ValueError("JSON 구조를 찾을 수 없음")

    json_str = raw[start:end + 1]

    # 파싱 시도
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # 제어문자 제거 후 재시도
        json_str = re.sub(r'[\x00-\x1f\x7f]', ' ', json_str)
        return json.loads(json_str)


def fetch_section(prompt: str) -> dict:
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2000,
        system=SYSTEM,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )
    raw = "\n".join(
        block.text for block in response.content if hasattr(block, "text")
    )
    print(f"    응답 길이: {len(raw)}자")
    return safe_parse_json(raw)


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
        time.sleep(60)

    os.makedirs("docs", exist_ok=True)
    with open("docs/briefing.json", "w", encoding="utf-8") as f:
        json.dump(briefing, f, ensure_ascii=False, indent=2)
    print("완료!")


if __name__ == "__main__":
    main()
