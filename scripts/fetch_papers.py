#!/usr/bin/env python3
"""
KCI 소비자학 논문 수집 스크립트
KCI Open API로 소비자학 관련 논문을 수집하여 docs/papers.json에 저장합니다.

IP 화이트리스트 주의: KCI API는 등록된 IP에서만 호출 가능합니다.
  - KCI Open API 포털에서 신청한 IP로 실행하거나,
  - 자체 호스팅 GitHub Actions runner를 사용하세요.
  - 문의: 042-869-6736 (평일 09:00~18:00)
"""

import os
import json
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

KCI_API_KEY = os.environ.get("KCI_API_KEY", "53088312")
KCI_API_URL = "https://open.kci.go.kr/po/openapi/openApiArticleService.do"
KST = timezone(timedelta(hours=9))
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "papers.json")

SEARCH_KEYWORDS = [
    "소비자학",
    "소비자행동",
    "소비자만족",
    "소비자태도",
    "소비자정책",
    "소비자금융",
    "지속가능소비",
    "소비자연구",
    "소비자심리",
    "소비자피해",
]

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
    "구조방정식": ["구조방정식", "SEM", "PLS-SEM", "공분산구조", "경로분석"],
    "회귀분석": ["회귀분석", "regression", "로지스틱회귀", "다중회귀", "위계적 회귀"],
    "질적 연구": ["인터뷰", "질적연구", "내러티브", "현상학", "근거이론", "사례연구", "포커스그룹", "심층면접"],
    "실험연구": ["실험연구", "실험설계", "무작위배정", "실험집단", "통제집단", "처치효과"],
    "메타분석": ["메타분석", "meta-analysis", "체계적 문헌고찰"],
    "내용분석": ["내용분석", "텍스트분석", "빅데이터", "텍스트마이닝", "토픽모델링", "LDA"],
    "혼합연구": ["혼합연구", "혼합방법", "mixed method"],
    "설문조사": ["설문조사", "설문", "questionnaire", "질문지", "survey"],
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


def get_text(elem, *tags) -> str:
    for tag in tags:
        el = elem.find(tag)
        if el is not None and el.text:
            return el.text.strip()
    return ""


def parse_article(article_elem) -> dict | None:
    article_id = get_text(article_elem,
        "articleId", "ArticleId", "artiId", "article_id", "id")
    title = get_text(article_elem,
        "title", "Title", "ArticleName", "artiNm", "articleName")
    authors_raw = get_text(article_elem,
        "author", "Author", "AuthorName", "authors", "authorName")
    journal = get_text(article_elem,
        "journal", "Journal", "JournalName", "journalNm", "journalName")
    year_raw = get_text(article_elem,
        "year", "Year", "pubYear", "publishYear", "publicationYear")
    abstract = get_text(article_elem,
        "abstract", "Abstract", "artiAbstract", "abstractKo")
    keywords_raw = get_text(article_elem,
        "keyword", "Keyword", "keywords", "keywordKo")

    if not title:
        return None
    if not article_id:
        # id 없으면 제목으로 임시 id 생성
        article_id = "TEMP_" + str(abs(hash(title)))[:12]

    authors = [a.strip() for a in authors_raw.replace(";", ",").split(",") if a.strip()] if authors_raw else []
    keywords = [k.strip() for k in keywords_raw.replace(";", ",").split(",") if k.strip()] if keywords_raw else []

    try:
        year = int(str(year_raw).strip()[:4]) if year_raw else None
    except (ValueError, TypeError):
        year = None

    combined = f"{title} {abstract} {keywords_raw}"
    return {
        "id": article_id,
        "title": title,
        "authors": authors,
        "year": year,
        "journal": journal or "소비자학연구",
        "abstract": abstract[:600] if abstract else "",
        "keywords": keywords[:10],
        "topic": infer_topic(combined),
        "method": infer_method(combined),
    }


def fetch_keyword(keyword: str, max_pages: int = 5) -> list[dict]:
    papers = []
    for page in range(1, max_pages + 1):
        params = {
            "key": KCI_API_KEY,
            "apiCode": "articleSearch",
            "keyword": keyword,
            "startPage": page,
            "displayCount": 100,
        }
        try:
            resp = requests.get(KCI_API_URL, params=params, timeout=30)
            resp.raise_for_status()

            root = ET.fromstring(resp.content)

            # 총 건수
            total_el = (root.find(".//totalCount") or root.find(".//totCnt")
                        or root.find(".//total_count") or root.find(".//TotalCount"))
            total_count = int(total_el.text) if total_el is not None and total_el.text else 0

            # 논문 요소 탐색 (여러 태그명 시도)
            articles = (root.findall(".//Article") or root.findall(".//article")
                        or root.findall(".//item") or root.findall(".//Item"))

            if not articles:
                if page == 1:
                    print(f"  [{keyword}] 파싱 실패 — XML 구조:")
                    for ch in root:
                        print(f"    <{ch.tag}>")
                        for c2 in ch:
                            print(f"      <{c2.tag}>: {(c2.text or '')[:60]}")
                break

            new_count = 0
            for art in articles:
                parsed = parse_article(art)
                if parsed:
                    papers.append(parsed)
                    new_count += 1

            print(f"  [{keyword}] p{page}: +{new_count}건 (누적 {len(papers)}/{total_count})")

            if len(papers) >= total_count or len(articles) == 0:
                break
            time.sleep(0.5)

        except requests.HTTPError as e:
            print(f"  [{keyword}] HTTP 오류: {e.response.status_code} — {e.response.text[:200]}")
            break
        except Exception as e:
            print(f"  [{keyword}] 오류: {e}")
            break

    return papers


def main():
    print("=== KCI 소비자학 논문 수집 시작 ===\n")

    seen: dict[str, dict] = {}
    for kw in SEARCH_KEYWORDS:
        print(f"키워드: {kw}")
        for p in fetch_keyword(kw):
            if p["id"] not in seen:
                seen[p["id"]] = p
        print(f"  => 고유 논문 누적: {len(seen)}건\n")
        time.sleep(1)

    papers = sorted(seen.values(),
                    key=lambda p: (p.get("year") or 0, p.get("id", "")),
                    reverse=True)

    output = {
        "updated_at": datetime.now(KST).isoformat(),
        "total": len(papers),
        "papers": papers,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"=== 완료: {len(papers)}건 → docs/papers.json ===")


if __name__ == "__main__":
    main()
