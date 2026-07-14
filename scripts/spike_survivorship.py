#!/usr/bin/env python3
"""PART B — 생존편향 해결(게이트). 공시이력으로 시점별 유니버스를 복원한다.

가설: 상장사는 매년 사업보고서(정기공시 A001)를 낸다. 상폐되면 안 낸다.
  universe(T=Y-05-15) = { 기업 c | c가 FY(Y-1) 사업보고서를 rcept_dt <= T 에 제출 }
  → 공시 기록 자체가 '그 시점에 살아있었다'는 증거다. 상폐일 소스가 없어도 된다.

검증(비순환):
  - dropout 표본: 어느 해까지 사업보고서를 내다 끊긴 기업. 폐지 전엔 유니버스에 있고
    이후엔 없음(방식 배선 확인) + ★독립 확증: 최근 FY 재무(fnlttSinglAcntAll)가
    '데이터 없음(013)'이면 진짜로 사라진 것(파싱 누락이 아니라).
  - ipo 표본: 뒤늦게 처음 나타난 기업. 상장 전 시점 유니버스엔 없음 + 상장 전 FY 재무 013.
  - control 표본: 지금도 내는 기업. 최근 FY 재무 000(살아있음).
  → dropout/control 의 최근-FY 000/013 대비가 '살아있음/사라짐'의 독립 근거.

산출:
  runs/2026-07-14_spike_survivorship/{summary.json, cases.csv, config.yaml}   ← 커밋
  data/pit/universe/universe_<Y>.csv   ← PART C가 읽는 시점별 유니버스(디스크; 대용량, 비커밋)

계정명/종목코드 리터럴 없음(구조적). 표준 라이브러리만.
"""
import csv
import random
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_parser as ap                       # noqa: E402
import json                                     # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / "runs" / "2026-07-14_spike_survivorship"
UNIV_DIR = ROOT / "data" / "pit" / "universe"

# --- 스캔 파라미터 (필터 임계값 아님; PLAN/LOOP_0F 의 범위·평가시점) ---
SEED = 20260714
EVAL_YEARS = list(range(2015, 2026))            # 2015..2025 각 5/15 스냅샷
EVAL_MMDD = "0515"                              # 평가시점 = 매년 5월 15일 (PLAN)
WINDOW_START_MMDD = "0101"
# ★ list.json 은 corp_code 없이 검색 시 기간을 3개월로 제한한다(status=100).
#   [Y0101, Y0515] 를 3개월 이하 하위창으로 쪼갠다. (사업보고서 마감=FY말+90일≈3월말.)
SUBWINDOWS = (("0101", "0315"), ("0316", "0515"))
PAGE_COUNT = 100
DETAIL_TY = "A001"                              # 정기공시 - 사업보고서
# --- 게이트 기준 (LOOP_0F PART B 에서 결과 전 고정) ---
GATE_MIN_SAMPLES = 30
GATE_PASS_RATE = 0.90
# --- 검증 표본 크기 ---
N_SAMPLE = 40                                   # 각 표본(dropout/ipo/control) 목표(>=30)
RECENT_PROBE_FY = "2024"                        # '최근 FY' 확증(현재 필러면 000)
CORPORATE_REPRT = "11011"                       # 사업보고서 보고서코드

PERIOD_RE = re.compile(r"\((\d{4})\.(\d{2})\)")


def log(m):
    print(m, file=sys.stderr, flush=True)


def fetch_window(bgn, end):
    """list.json A001 을 [bgn,end] 로 전 페이지 수집. (corp_code, rcept_dt, report_nm, ...)."""
    rows, page = [], 1
    while True:
        res = ap.get_json("list.json", {"bgn_de": bgn, "end_de": end,
                                        "pblntf_detail_ty": DETAIL_TY,
                                        "page_no": str(page), "page_count": str(PAGE_COUNT)})
        st = res.get("status")
        if st == "013":                          # 데이터 없음
            break
        if st != "000":
            log(f"    window {bgn}-{end} p{page} status={st} {res.get('message')}")
            break
        rows.extend(res.get("list", []) or [])
        total_page = res.get("total_page") or 1
        if page >= int(total_page):
            break
        page += 1
        time.sleep(0.03)
    return rows


def period_year(report_nm):
    """report_nm 의 (YYYY.MM) 중 마지막을 회계기간 종료연월로 본다. 없으면 None."""
    ms = PERIOD_RE.findall(report_nm or "")
    if not ms:
        return None
    return int(ms[-1][0])


def is_listed_code(sc):
    """구조적 상장 신호: 6자리 숫자 종목코드. (현재상태 corp_cls 대신 공시행에 보존된 코드 사용 →
    상폐 후 corp_cls=E 로 재분류돼도 과거 유니버스에서 빠지지 않는다 = 생존편향 안전.)"""
    return len(sc) == 6 and sc.isdigit()


def build_universes():
    """EVAL_YEARS 각 Y 에 대해 universe(Y) = FY(Y-1) 사업보고서를 [Y-0101, Y-0515]에 제출한
    '상장'(6자리 종목코드 보유) 기업. 반환: (univ, all_filer_count).
    all_filer_count = 종목코드 무관 A001 제출 기업 수(맥락용)."""
    univ, all_count = {}, {}
    for y in EVAL_YEARS:
        fy = y - 1
        rows = []
        for a, b in SUBWINDOWS:                          # 3개월 제한 → 하위창 분할
            rows.extend(fetch_window(f"{y}{a}", f"{y}{b}"))
        members, all_corps = {}, set()
        for r in rows:
            if period_year(r.get("report_nm")) != fy:      # FY(Y-1) 만
                continue
            cc = (r.get("corp_code") or "").strip()
            if not cc:
                continue
            all_corps.add(cc)
            sc = (r.get("stock_code") or "").strip()
            if not is_listed_code(sc):                     # 상장사만(구조적)
                continue
            dt = (r.get("rcept_dt") or "").strip()
            prev = members.get(cc)
            if prev is None or dt < prev["rcept_dt"]:       # 최초 제출일(정정 이전)
                members[cc] = {"rcept_dt": dt,
                               "corp_name": (r.get("corp_name") or "").strip(),
                               "corp_cls": (r.get("corp_cls") or "").strip(),
                               "stock_code": sc,
                               "report_nm": (r.get("report_nm") or "").strip()}
        univ[y] = members
        all_count[y] = len(all_corps)
        log(f"  universe({y}) FY{fy}: 상장 {len(members)} / A001전체 {len(all_corps)} "
            f"(rows {len(rows)})")
    return univ, all_count


def recent_data_status(cc, fy):
    """fnlttSinglAcntAll 로 corp 의 FY 재무 존재 여부. '000'=존재, 그 외='없음/오류'."""
    for fs in ("OFS", "CFS"):
        res = ap.get_json("fnlttSinglAcntAll.json",
                          {"corp_code": cc, "bsns_year": fy, "reprt_code": CORPORATE_REPRT,
                           "fs_div": fs})
        if res.get("status") == "000" and res.get("list"):
            return "000"
        time.sleep(0.02)
    return res.get("status", "ERR")


def write_universes(univ):
    UNIV_DIR.mkdir(parents=True, exist_ok=True)
    for y, members in univ.items():
        with open(UNIV_DIR / f"universe_{y}.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["corp_code", "corp_name", "corp_cls", "stock_code", "rcept_dt", "report_nm"])
            for cc, m in sorted(members.items()):
                w.writerow([cc, m["corp_name"], m["corp_cls"], m["stock_code"],
                            m["rcept_dt"], m["report_nm"]])


def main():
    random.seed(SEED)
    univ, all_count = build_universes()
    write_universes(univ)

    years = EVAL_YEARS
    first_year, last_year = years[0], years[-1]
    sizes = {y: len(univ[y]) for y in years}

    # 각 corp 의 최초/최종 등장 연도
    first_seen, last_seen = {}, {}
    names = {}
    for y in years:
        for cc, m in univ[y].items():
            first_seen.setdefault(cc, y)
            last_seen[cc] = y
            names[cc] = m["corp_name"]

    # dropout = 중간에 등장했다가 last_year 이전에 끊긴 기업(마지막 등장 <= last_year-2)
    dropouts = [cc for cc, ly in last_seen.items()
                if ly <= last_year - 2 and first_seen[cc] <= ly]
    # ipo = 첫 등장이 first_year 이후(뒤늦게 상장), 그리고 최근까지 존재
    ipos = [cc for cc, fs in first_seen.items()
            if fs >= first_year + 2 and last_seen[cc] >= last_year - 1]
    # control = 처음부터 끝까지(또는 최근까지) 계속 존재
    controls = [cc for cc in univ[last_year]
                if first_seen[cc] <= first_year + 1]

    rnd = random.Random(SEED)
    def take(pool):
        pool = sorted(pool)
        rnd.shuffle(pool)
        return pool[:N_SAMPLE]

    d_s, i_s, c_s = take(dropouts), take(ipos), take(controls)
    log(f"pools: dropout={len(dropouts)} ipo={len(ipos)} control={len(controls)} "
        f"(sampling {N_SAMPLE} each)")

    cases = []
    # dropout 검증: 폐지 전 존재 / 이후 부재 (배선) + 최근FY 재무 013(독립 확증=사라짐)
    d_wired = d_corrob = 0
    for cc in d_s:
        ly = last_seen[cc]
        present_before = int(cc in univ[ly])
        absent_after = int(all(cc not in univ[y] for y in years if y > ly))
        wired = present_before and absent_after
        d_wired += int(bool(wired))
        st = recent_data_status(cc, RECENT_PROBE_FY)
        corrob = int(st != "000")                # 최근 데이터 없음 = 사라짐 확증
        d_corrob += corrob
        cases.append({"kind": "dropout", "corp_code": cc, "corp_name": names[cc],
                      "first_seen": first_seen[cc], "last_seen": ly,
                      "present_before": present_before, "absent_after": absent_after,
                      "wired_ok": int(bool(wired)), "probe_fy": RECENT_PROBE_FY,
                      "probe_status": st, "corroborated": corrob})
    # ipo 검증: 상장 전 부재(배선) + 상장 훨씬 전 FY 재무 013(독립 확증=아직 없음)
    i_wired = i_corrob = 0
    for cc in i_s:
        fs = first_seen[cc]
        absent_before = int(all(cc not in univ[y] for y in years if y < fs))
        present_now = int(cc in univ[last_seen[cc]])
        wired = absent_before and present_now
        i_wired += int(bool(wired))
        early_fy = str(fs - 3)                    # 상장 3년 전 FY: 데이터 없어야 함
        st = recent_data_status(cc, early_fy)
        corrob = int(st != "000")
        i_corrob += corrob
        cases.append({"kind": "ipo", "corp_code": cc, "corp_name": names[cc],
                      "first_seen": fs, "last_seen": last_seen[cc],
                      "present_before": "", "absent_after": "",
                      "wired_ok": int(bool(wired)), "probe_fy": early_fy,
                      "probe_status": st, "corroborated": corrob})
    # control 검증: 최근 FY 재무 000(살아있음) — 사라짐/살아있음 대비의 반대편
    c_alive = 0
    for cc in c_s:
        st = recent_data_status(cc, RECENT_PROBE_FY)
        alive = int(st == "000")
        c_alive += alive
        cases.append({"kind": "control", "corp_code": cc, "corp_name": names[cc],
                      "first_seen": first_seen[cc], "last_seen": last_seen[cc],
                      "present_before": "", "absent_after": "",
                      "wired_ok": "", "probe_fy": RECENT_PROBE_FY,
                      "probe_status": st, "corroborated": int(alive)})

    # 단조증가 여부: 규모 수열이 비감소이기만 하면(한 번도 안 줄면) 생존편향 징후
    seq = [sizes[y] for y in years]
    is_monotonic_increasing = all(b >= a for a, b in zip(seq, seq[1:]))
    n_decreases = sum(1 for a, b in zip(seq, seq[1:]) if b < a)

    d_wired_rate = d_wired / len(d_s) if d_s else 0
    gate_sample_ok = len(d_s) >= GATE_MIN_SAMPLES and d_wired_rate >= GATE_PASS_RATE
    gate_monotonic_ok = not is_monotonic_increasing
    gate = "PASS" if (gate_sample_ok and gate_monotonic_ok) else "FAIL"

    summary = {
        "meta": {"seed": SEED, "eval_years": years, "eval_point": f"매년 {EVAL_MMDD}",
                 "detail_ty": DETAIL_TY, "gate_min_samples": GATE_MIN_SAMPLES,
                 "gate_pass_rate": GATE_PASS_RATE,
                 "universe_def": "FY(Y-1) 사업보고서를 [Y-0101, Y-0515]에 제출한 기업"},
        "B4_universe_sizes": sizes,
        "B4_all_filer_counts": all_count,
        "B4_size_sequence": seq,
        "B4_is_monotonic_increasing": is_monotonic_increasing,
        "B4_n_year_over_year_decreases": n_decreases,
        "B2_dropout_pool": len(dropouts),
        "B2_dropout_sampled": len(d_s),
        "B2_wired_ok": d_wired,
        "B2_wired_rate_pct": round(100 * d_wired_rate, 1),
        "B2_corroborated_gone": d_corrob,
        "B2_corroborated_rate_pct": round(100 * d_corrob / len(d_s), 1) if d_s else 0,
        "B3_ipo_pool": len(ipos),
        "B3_ipo_sampled": len(i_s),
        "B3_wired_ok": i_wired,
        "B3_corroborated_absent_before": i_corrob,
        "B3_corroborated_rate_pct": round(100 * i_corrob / len(i_s), 1) if i_s else 0,
        "control_sampled": len(c_s),
        "control_alive_recent": c_alive,
        "control_alive_rate_pct": round(100 * c_alive / len(c_s), 1) if c_s else 0,
        "GATE_sample_ok": gate_sample_ok,
        "GATE_monotonic_ok": gate_monotonic_ok,
        "GATE": gate,
    }
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    with open(RUN_DIR / "cases.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(cases[0].keys()))
        w.writeheader()
        w.writerows(cases)
    cfg = (
        "# spike_survivorship 실행 설정 (원자료 재현용)\n"
        f"seed: {SEED}\n"
        f"eval_years: [{', '.join(map(str, years))}]\n"
        f"eval_point_mmdd: '{EVAL_MMDD}'\n"
        f"window_start_mmdd: '{WINDOW_START_MMDD}'\n"
        f"disclosure_detail_ty: {DETAIL_TY}  # 정기공시-사업보고서\n"
        f"page_count: {PAGE_COUNT}\n"
        f"gate_min_samples: {GATE_MIN_SAMPLES}\n"
        f"gate_pass_rate: {GATE_PASS_RATE}\n"
        f"sample_size_each: {N_SAMPLE}\n"
        f"recent_probe_fy: {RECENT_PROBE_FY}\n"
        "universe_definition: FY(Y-1) 사업보고서를 [Y-0101, Y-0515]에 제출한 기업\n"
        "corroboration: fnlttSinglAcntAll 최근/상장전 FY 데이터 존재여부(000/013)\n"
    )
    (RUN_DIR / "config.yaml").write_text(cfg, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    log(f"survivorship 완료. GATE={gate}. 원자료 → {RUN_DIR}, 유니버스 → {UNIV_DIR}")


if __name__ == "__main__":
    main()
