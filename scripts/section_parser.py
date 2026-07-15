#!/usr/bin/env python3
"""사업보고서 원문(XML)에서 "사업의 내용" 섹션만 구조적으로 추출 (Loop 3 PART 1).

★ 구조적 기준 — 특정 회사 하드코딩 0:
  - DART 사업보고서는 규제 서식(자본시장법)에 따라 최상위 섹션을 로마숫자 제목으로 나눈다:
    "I. 회사의 개요 / II. 사업의 내용 / III. 재무에 관한 사항 / ...".
  - 최상위 섹션 = 로마숫자 접두를 가진 <TITLE> (서식의 번호체계 = 구조 앵커).
  - 그 중 제목이 표준 섹션명(config: text_section_title)을 포함하는 섹션을,
    다음 최상위 섹션 직전까지 잘라낸다.
  섹션명·로마숫자는 규제 서식의 라벨이지 회사명·종목코드가 아니다.

★ 추출 실패는 결측(빈 문자열 + status) — 임의 대체 0.
순수 함수(파일 I/O 없음) — 테스트 가능.
"""
import re

_TITLE_RE = re.compile(r"<TITLE[^>]*>(.*?)</TITLE>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_ROMAN_RE = re.compile(r"^([IVXLCDM]+)\.\s*(.+)$")        # 로마숫자 + '.' 접두 = 최상위 섹션


def _clean(s):
    s = _TAG_RE.sub(" ", s).replace("&cr;", " ").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", s).strip()


def top_sections(raw):
    """최상위(로마숫자) <TITLE> 섹션들을 (문자오프셋, 정규화제목, 원제목)으로 반환."""
    tops = []
    for m in _TITLE_RE.finditer(raw):
        t = _clean(m.group(1))
        rm = _ROMAN_RE.match(t)
        if rm:
            tops.append((m.start(), rm.group(2).replace(" ", ""), t))
    return tops


def extract_section(raw, section_title):
    """raw XML에서 section_title 을 포함하는 최상위 섹션 텍스트를 추출.

    반환: (text, status). status ∈ {ok, no_titles, no_section, empty}.
    실패 시 text="" (결측). 임의 대체 없음.
    """
    if not raw:
        return "", "no_titles"
    tops = top_sections(raw)
    if not tops:
        return "", "no_titles"
    anchor = section_title.replace(" ", "")
    idx = next((i for i, (_, norm, _) in enumerate(tops) if anchor in norm), None)
    if idx is None:
        return "", "no_section"
    start = tops[idx][0]
    end = tops[idx + 1][0] if idx + 1 < len(tops) else len(raw)
    txt = _clean(raw[start:end])
    return (txt, "ok") if txt else ("", "empty")
