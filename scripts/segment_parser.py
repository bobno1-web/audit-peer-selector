#!/usr/bin/env python3
"""부문별 매출 → '집중도 프로필' 구조적 추출 (Loop 4 PART 1). 순수 함수 — 테스트 가능.

★ 구조적 기준 — 특정 회사 하드코딩 0:
  - '사업의 내용' 섹션 안의 <TABLE> 중, 헤더가 규제 서식 라벨(매출액 + 비율/비중/사업부문/매출유형/품목)을
    포함하는 표 = 부문별 매출실적 표. (라벨은 서식의 표준어이지 회사명·코드가 아니다.)
  - 그 표의 데이터 행에서 '매출액'(행 내 최대 화폐성 숫자)을 부문 매출로 본다. 합계/소계 행은 제외.
  - 부문 매출 → 비중 → **집중도 프로필**(부문수 n, 최대비중 top_share, HHI=Σ비중²).

★ 정보 차단벽: 부문별 '매출 비중'만 쓴다(사업 구성). 부문별 '이익률'은 만들지 않는다(채점비율 누출 방지).
★ 공통 축 정규화(O7): 기업마다 부문 분류가 달라 부문명 택소노미는 못 맞춘다. 대신 **택소노미-불요**
  스칼라(n, top_share, HHI)로 환원 → 전 기업 비교가능(집중형 vs 분산형). 엔진에서 표준화 거리로 유사도.
★ 추출 실패는 결측(None) — 임의 대체 0.
"""
import re

_TITLE_RE = re.compile(r"<TITLE[^>]*>(.*?)</TITLE>", re.S)
_ROMAN_RE = re.compile(r"^([IVXLCDM]+)\.\s*(.+)$")
_TABLE_RE = re.compile(r"<TABLE[ >].*?</TABLE>", re.I | re.S)
_ROW_RE = re.compile(r"<TR[ >].*?</TR>", re.I | re.S)
_CELL_RE = re.compile(r"<T[DEHU][ >].*?</T[DEHU]>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_NUM_RE = re.compile(r"^\(?-?(\d{1,3}(,\d{3})+|\d{4,})\)?$")   # 화폐성(콤마그룹 또는 4자리+)

# 구조 앵커 토큰(규제 서식 라벨). 매직'값'이 아니라 서식 어휘 — config 로도 뺄 수 있으나 서식 고정어.
_REV_TOKENS = ("매출액", "매출")
_COMP_TOKENS = ("비율", "비중", "사업부문", "매출유형", "품목", "부문")
_TOTAL_TOKENS = ("합계", "소계", "총계", "전체", "계")


def _clean(s):
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", s).replace("&cr;", " ").replace("&nbsp;", " ")).strip()


def _section_span(raw, section_title):
    tops = []
    for m in _TITLE_RE.finditer(raw):
        t = _clean(m.group(1))
        rm = _ROMAN_RE.match(t)
        if rm:
            tops.append((m.start(), rm.group(2).replace(" ", "")))
    if not tops:
        return None
    anchor = section_title.replace(" ", "")
    idx = next((i for i, (_, n) in enumerate(tops) if anchor in n), None)
    if idx is None:
        return None
    start = tops[idx][0]
    end = tops[idx + 1][0] if idx + 1 < len(tops) else len(raw)
    return raw[start:end]


def _row_cells(tr):
    return [_clean(c) for c in _CELL_RE.findall(tr)]


def _to_num(cell):
    c = cell.replace(" ", "")
    if not _NUM_RE.match(c):
        return None
    neg = c.startswith("(") and c.endswith(")")
    v = float(c.strip("()").replace(",", ""))
    return -v if neg else v


def _is_segment_table(tbl):
    flat = _clean(tbl).replace(" ", "")
    return any(t in flat for t in _REV_TOKENS) and any(t in flat for t in _COMP_TOKENS)


def segment_shares(raw, section_title):
    """부문 매출 → 집중도 프로필. 반환 (profile|None, status).

    profile = {"seg_n": int, "seg_top_share": float, "seg_hhi": float}.
    status ∈ {ok, no_section, no_table, no_rows}.
    """
    if not raw:
        return None, "no_section"
    span = _section_span(raw, section_title)
    if span is None:
        return None, "no_section"
    tables = [t for t in _TABLE_RE.findall(span) if _is_segment_table(t)]
    if not tables:
        return None, "no_table"
    revs = []
    for tbl in tables:                                     # 첫 부문표에서 매출 수집(여러개면 병합)
        for tr in _ROW_RE.findall(tbl):
            cells = _row_cells(tr)
            if not cells:
                continue
            label = cells[0].replace(" ", "")
            if not label or any(t in label for t in _TOTAL_TOKENS):
                continue                                   # 합계/소계 행 제외
            nums = [n for n in (_to_num(c) for c in cells[1:]) if n is not None and n > 0]
            if nums:
                revs.append(max(nums))                     # 행 내 최대 화폐성 = 부문 매출
        if revs:
            break
    revs = [r for r in revs if r > 0]
    if not revs:
        return None, "no_rows"
    tot = sum(revs)
    shares = [r / tot for r in revs]
    return ({"seg_n": len(shares),
             "seg_top_share": round(max(shares), 6),
             "seg_hhi": round(sum(s * s for s in shares), 6)}, "ok")
