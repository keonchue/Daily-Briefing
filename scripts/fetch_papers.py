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
    "디지털·온라인": ["온라인", "디지털", "인터넷", "SNS", "소셜미디어", "모바일", "이커머스", "플랫폼", "유튜브", "인플루언서"],
    "금융·보험": ["금융", "보험", "투자", "신용", "대출", "연금", "부채", "저축", "핀테크", "주식", "가계부채"],
    "지속가능 소비": ["지속가능", "친환경", "녹색소비", "탄소", "ESG", "환경", "재활용", "공정무역", "윤리적소비"],
    "식품·건강": ["식품", "건강", "의료", "영양", "음식", "의약품", "건강기능식품", "다이어트", "안전"],
    "패션·뷰티": ["패션", "의류", "뷰티", "화장품", "의복", "피부"],
    "소비자 정책": ["정책", "법률", "규제", "제도", "보호", "권리", "피해구제", "공정거래"],
    "서비스·만족": ["서비스", "만족", "충성도", "신뢰", "품질", "고객", "서비스품질"],
    "취약계층": ["청소년", "노인", "고령", "장애", "저소득", "취약", "아동", "시니어"],
    "구매 행동": ["구매", "의사결정", "선택", "충동구매", "쇼핑", "구매의도"],
    "소비자 심리": ["심리", "인식", "지각", "동기", "감정", "정서", "인지", "자아개념"],
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

    citation_el = article_info.find(".//citation-count")
    try:
        citation_count = int(_elem_text(citation_el)) if citation_el is not None else 0
    except (ValueError, TypeError):
        citation_count = 0

    combined = f"{title} {abstract} {' '.join(keywords)}"
    return {
        "id": article_id,
        "title": title,
        "authors": authors,
        "year": year,
        "pub_month": pub_month,
        "journal": journal,
        "abstract": abstract[:600],
        "keywords": keywords[:10],
        "citation_count": citation_count,
        "topic": infer_topic(combined),
        "method": infer_method(combined),
    }


def fetch_journal(max_pages: int = 20) -> list[dict]:
    papers = []
    seen_ids: set[str] = set()

    for page in range(1, max_pages + 1):
        params = {
            "key": KCI_API_KEY,
            "apiCode": "articleSearch",
            "journal": JOURNAL_NAME,
            "page": page,
            "displayCount": 100,
        }
        try:
            resp = requests.get(KCI_API_URL, params=params, timeout=30)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)

            total_el = root.find(".//result/total") or root.find(".//total")
            total_count = int(total_el.text) if total_el is not None and total_el.text else 0

            records = root.findall(".//record")
            if not records:
                result_msg = _elem_text(root.find(".//resultMsg"))
                print(f"  p{page}: 결과 없음 ({result_msg or 'no records'})")
                break

            new_count = 0
            for rec in records:
                parsed = parse_record(rec)
                if parsed and parsed["id"] not in seen_ids:
                    seen_ids.add(parsed["id"])
                    papers.append(parsed)
                    new_count += 1

            print(f"  p{page}: +{new_count}건 (누적 {len(papers)}/{total_count})")

            if len(papers) >= total_count or len(records) == 0:
                break
            time.sleep(0.5)

        except requests.HTTPError as e:
            print(f"  HTTP 오류: {e.response.status_code}")
            break
        except Exception as e:
            print(f"  오류: {e}")
            break

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
