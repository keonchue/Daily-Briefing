#!/usr/bin/env python3
"""KCI 소비자학연구 논문 수집 스크립트 (학술지 기반)"""

import os
import json
import re as _re
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

KCI_API_KEY = os.environ.get("KCI_API_KEY") or "53088312"
KCI_API_URL = "https://open.kci.go.kr/po/openapi/openApiSearch.kci"
JOURNAL_NAME = "소비자학연구"
KST = timezone(timedelta(hours=9))
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "papers.json")

TOPIC_MAP = {
    "구매 의사결정": ["구매의사결정", "구매결정", "의사결정", "구매의도", "충동구매", "쇼핑", "선택행동"],
    "마케팅 전략": ["마케팅전략", "마케팅 전략", "광고전략", "프로모션", "포지셔닝", "세분화", "타겟팅", "마케팅믹스"],
    "소비자 만족/불만족": ["소비자만족", "고객만족", "소비자불만", "불만족", "충성도", "재구매의도", "서비스품질"],
    "온라인/디지털 소비": ["온라인", "디지털", "인터넷", "SNS", "소셜미디어", "모바일", "이커머스", "플랫폼", "유튜브", "인플루언서", "핀테크"],
    "지속가능 소비/윤리적 소비": ["지속가능", "친환경", "녹색소비", "탄소", "ESG", "환경", "재활용", "공정무역", "윤리적소비", "윤리적 소비"],
    "브랜드 태도": ["브랜드태도", "브랜드 태도", "브랜드신뢰", "브랜드충성", "브랜드이미지", "브랜드자산", "브랜드정체성"],
    "소비자 정보처리": ["정보처리", "정보탐색", "정보활용", "인지", "심리", "동기", "감정", "정서", "자아개념", "지각"],
    "가격 지각": ["가격지각", "가격 지각", "가격공정성", "지불의사", "가격민감성", "할인", "가격태도", "준거가격"],
    "소비자 복지/정책": ["소비자복지", "소비자정책", "정책", "법률", "규제", "제도", "보호", "피해구제", "공정거래", "취약계층", "청소년소비자", "노인소비자"],
}

METHOD_MAP = {
    "메타분석": ["메타분석", "meta-analysis", "체계적 문헌고찰", "systematic review"],
    "빅데이터/텍스트마이닝": ["빅데이터", "텍스트마이닝", "머신러닝", "딥러닝", "인공지능", "자연어처리", "NLP", "sentiment", "word2vec", "BERT", "토픽모델링", "LDA"],
    "패널데이터/종단연구": ["패널데이터", "종단연구", "종단적", "longitudinal", "panel data", "패널조사", "추적조사"],
    "질적연구(인터뷰/FGI)": ["심층면접", "포커스그룹", "FGI", "FGD", "focus group", "인터뷰", "질적연구", "내러티브", "현상학", "근거이론", "사례연구"],
    "실험연구": ["실험연구", "실험설계", "무작위배정", "실험집단", "통제집단", "처치효과", "피험자", "시나리오"],
    "내용분석": ["내용분석", "텍스트분석", "content analysis"],
    "혼합연구방법": ["혼합연구", "혼합방법", "mixed method"],
    "문헌연구/이론연구": ["문헌연구", "이론연구", "문헌고찰", "이론적 고찰", "개념적 모형", "theoretical", "conceptual framework", "문헌 검토"],
    "설문조사": ["설문조사", "설문", "questionnaire", "survey", "질문지", "구조방정식", "SEM", "회귀분석", "regression"],
}


def infer_topic(text: str) -> str:
    text_lower = text.lower()
    for topic, keywords in TOPIC_MAP.items():
        if any(kw.lower() in text_lower for kw in keywords):
            return topic
    return "소비자 행동"


def infer_method(text: str) -> str:
    text_lower = text.lower()
    for method, keywords in METHOD_MAP.items():
        if any(kw.lower() in text_lower for kw in keywords):
            return method
    return "설문조사"


def _elem_text(elem) -> str:
    return (elem.text or "").strip() if elem is not None else ""


def parse_record(record_elem) -> dict | None:
    article_info = record_elem.find("articleInfo")
    if article_info is None:
        return None

    article_id = article_info.get("article-id", "")

    title_el = article_info.find(".//article-title[@lang='original']")
    title = _elem_text(title_el)
    if not title:
        return None

    if not article_id:
        article_id = "TEMP_" + str(abs(hash(title)))[:12]

    raw_authors = [_elem_text(a) for a in article_info.findall(".//author")]
    authors = [_re.sub(r"\(.*?\)", "", a).strip() for a in raw_authors if a]

    # 소속기관 파싱 (가능한 경우)
    aff_els = article_info.findall(".//aff") or record_elem.findall(".//aff")
    affiliations = list({_re.sub(r"\s+", " ", _elem_text(a)).strip() for a in aff_els if _elem_text(a)})
    affiliations = [a for a in affiliations if a and len(a) > 2][:5]

    journal_el = record_elem.find(".//journal-name")
    journal = _elem_text(journal_el) or JOURNAL_NAME

    year_raw = _elem_text(record_elem.find(".//pub-year"))
    try:
        year = int(year_raw[:4]) if year_raw else None
    except (ValueError, TypeError):
        year = None

    month_raw = _elem_text(record_elem.find(".//pub-mon"))
    try:
        pub_month = int(month_raw) if month_raw else None
    except (ValueError, TypeError):
        pub_month = None

    abstract_el = article_info.find(".//abstract[@lang='original']")
    abstract = _elem_text(abstract_el)

    keywords = [_elem_text(k) for k in article_info.findall(".//kwd") if _elem_text(k)]

    citation_el = article_info.find(".//citation-count") or record_elem.find(".//citation-count")
    try:
        citation_count = int(_elem_text(citation_el)) if citation_el is not None else 0
    except (ValueError, TypeError):
        citation_count = 0

    view_el = article_info.find(".//view-count") or record_elem.find(".//view-count") \
              or article_info.find(".//download-count") or record_elem.find(".//download-count")
    try:
        view_count = int(_elem_text(view_el)) if view_el is not None else 0
    except (ValueError, TypeError):
        view_count = 0

    combined = f"{title} {abstract} {' '.join(keywords)}"
    result = {
        "id": article_id,
        "title": title,
        "authors": authors,
        "year": year,
        "pub_month": pub_month,
        "journal": journal,
        "abstract": abstract[:600],
        "keywords": keywords[:10],
        "citation_count": citation_count,
        "view_count": view_count,
        "topic": infer_topic(combined),
        "method": infer_method(combined),
    }
    if affiliations:
        result["affiliations"] = affiliations
    return result


def _api_call(params: dict, label: str) -> list:
    """KCI API 호출 (3회 재시도). 성공 시 (records, total_count) 반환."""
    for attempt in range(3):
        try:
            resp = requests.get(KCI_API_URL, params=params, timeout=30)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            total_el = root.find(".//result/total") or root.find(".//total")
            total_count = int(total_el.text) if total_el is not None and total_el.text else 0
            records = root.findall(".//record")
            return records, total_count
        except Exception as e:
            print(f"  {label} 오류 (시도 {attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(2)
    return [], 0


def fetch_year(year: int, seen_ids: set, papers: list) -> int:
    """특정 연도 논문을 페이지네이션으로 전량 수집. 추가된 건수 반환."""
    added = 0
    page = 1
    consecutive_empty = 0

    while True:
        params = {
            "key": KCI_API_KEY,
            "apiCode": "articleSearch",
            "journal": JOURNAL_NAME,
            "startYear": year,
            "endYear": year,
            "page": page,
            "displayCount": 10,
        }
        records, total_count = _api_call(params, f"{year} p{page}")

        if not records:
            consecutive_empty += 1
            if consecutive_empty >= 3:
                break
            page += 1
            time.sleep(0.3)
            continue

        consecutive_empty = 0
        for rec in records:
            parsed = parse_record(rec)
            if parsed and parsed["id"] not in seen_ids:
                seen_ids.add(parsed["id"])
                papers.append(parsed)
                added += 1

        if total_count > 0 and added >= total_count:
            break
        page += 1
        time.sleep(0.3)

    return added


def fetch_journal() -> list[dict]:
    papers = []
    seen_ids: set[str] = set()

    # 전체 총 건수 확인 (연도 필터 없이 첫 페이지만)
    _, grand_total = _api_call({
        "key": KCI_API_KEY,
        "apiCode": "articleSearch",
        "journal": JOURNAL_NAME,
        "page": 1,
        "displayCount": 10,
    }, "총계 조회")
    print(f"  API 전체 총 건수: {grand_total}건\n")

    current_year = datetime.now(KST).year
    # 소비자학연구 창간: 1990년
    for year in range(current_year, 1989, -1):
        before = len(papers)
        added = fetch_year(year, seen_ids, papers)
        if added > 0:
            print(f"  {year}년: +{added}건 (누적 {len(papers)}/{grand_total})")
        time.sleep(0.2)

    return papers


def main():
    print(f"=== KCI [{JOURNAL_NAME}] 논문 수집 시작 ===\n")

    papers = fetch_journal()

    papers.sort(key=lambda p: (p.get("year") or 0, p.get("pub_month") or 0), reverse=True)

    output = {
        "updated_at": datetime.now(KST).isoformat(),
        "total": len(papers),
        "papers": papers,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n=== 완료: {len(papers)}건 → docs/papers.json ===")


if __name__ == "__main__":
    main()
