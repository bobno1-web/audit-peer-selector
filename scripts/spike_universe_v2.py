#!/usr/bin/env python3
"""[임시] PART F — 상장 유니버스 정제 + 재측정(n=200) + 35% 결측 진단 + KRX 확보 시도.

구조적 근거만(종목명 키워드 없음): stock_code 끝자리, induty_code, corp_cls, 결산월(acc_mt).
KRX 상장종목 데이터(증권구분/상장일/폐지일)를 실제로 받아보고 가부를 기록한다.
"""
import io
import json
import random
import sys
import time
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_parser as ap                     # noqa: E402

SEED = 20260714
N_TARGET = 200
SCAN_CAP = 320
EXCLUDE_INDUTY = ("64", "65", "66", "68")     # 금융·보험·부동산(리츠·펀드·스팩 다수)
YEARS = ["2022", "2021", "2020"]


def log(m):
    print(m, file=sys.stderr, flush=True)


def fetch_listed():
    blob = ap.get_raw("corpCode.xml", {})
    xml = zipfile.ZipFile(io.BytesIO(blob)).read("CORPCODE.xml")
    root = ET.fromstring(xml)
    listed = []
    for n in root.iter("list"):
        sc = (n.findtext("stock_code") or "").strip()
        cc = (n.findtext("corp_code") or "").strip()
        if cc and len(sc) == 6 and sc.isdigit():
            listed.append({"corp_code": cc, "stock_code": sc,
                           "corp_name": (n.findtext("corp_name") or "").strip()})
    return listed


def has_financial(cc):
    for y in YEARS:
        res = ap.get_json("fnlttSinglAcntAll.json", {"corp_code": cc, "bsns_year": y,
                                                     "reprt_code": "11011", "fs_div": "OFS"})
        if res.get("status") == "000" and res.get("list"):
            return True
        time.sleep(0.03)
    return False


def try_krx():
    """KRX 정보데이터시스템 전종목 기본정보(MDCSTAT01901)를 2가지 방식으로 실제 호출.
    (1) getJsonData 직접 (2) OTP 발급 → CSV 다운로드. 하나라도 되면 ok. 실측 기록."""
    headers = {"User-Agent": "Mozilla/5.0",
               "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd"}
    attempts = {}
    bld = "dbms/MDC/STAT/standard/MDCSTAT01901"

    # 방식 1: getJsonData
    try:
        req = urllib.request.Request(
            "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd",
            data=urllib.parse.urlencode({"bld": bld, "mktId": "ALL", "share": "1",
                                         "csvxls_isNo": "false"}).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=25) as r:
            j = json.loads(r.read().decode("utf-8", "ignore"))
        rows = j.get("OutBlock_1") or j.get("output") or []
        attempts["getJsonData"] = {"ok": bool(rows), "rows": len(rows),
                                   "sample_keys": list(rows[0].keys())[:15] if rows else []}
    except Exception as e:  # noqa: BLE001
        attempts["getJsonData"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    # 방식 2: OTP → CSV
    try:
        otp_q = urllib.parse.urlencode({"locale": "ko_KR", "mktId": "ALL", "share": "1",
                                        "csvxls_isNo": "false", "name": "fileDown", "url": bld})
        req1 = urllib.request.Request(
            "http://data.krx.co.kr/comm/fileDn/GenerateOTP/generate.cmd?" + otp_q, headers=headers)
        with urllib.request.urlopen(req1, timeout=25) as r:
            code = r.read().decode("utf-8", "ignore")
        req2 = urllib.request.Request("http://data.krx.co.kr/comm/fileDn/download_csv/download.cmd",
                                      data=urllib.parse.urlencode({"code": code}).encode(),
                                      headers=headers)
        with urllib.request.urlopen(req2, timeout=25) as r:
            raw = r.read()
        text = raw.decode("cp949", "ignore")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        attempts["otp_csv"] = {"ok": len(lines) > 1, "rows": max(0, len(lines) - 1),
                               "header": lines[0][:200] if lines else ""}
    except Exception as e:  # noqa: BLE001
        attempts["otp_csv"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    ok = any(a.get("ok") for a in attempts.values())
    return {"ok": ok, "attempts": attempts}


def main():
    random.seed(SEED)
    listed = fetch_listed()
    common = [x for x in listed if x["stock_code"].endswith("0")]
    random.shuffle(common)
    log(f"listed {len(listed)} common(끝0) {len(common)}")

    measured = success = excluded = scanned = 0
    fail_diag = Counter()
    cls_hist = Counter()
    for rec in common:
        if measured >= N_TARGET or scanned >= SCAN_CAP:
            break
        scanned += 1
        comp = ap.get_json("company.json", {"corp_code": rec["corp_code"]})
        ind2 = (comp.get("induty_code") or "").strip()[:2]
        corp_cls = (comp.get("corp_cls") or "").strip()
        acc_mt = (comp.get("acc_mt") or "").strip()
        cls_hist[corp_cls or "NA"] += 1
        if ind2 in EXCLUDE_INDUTY:
            excluded += 1
            continue
        ok = has_financial(rec["corp_code"])
        measured += 1
        if ok:
            success += 1
        else:                                   # F-1: 35% 결측 진단(구조적)
            if corp_cls == "N":
                fail_diag["konex"] += 1
            elif acc_mt and acc_mt != "12":
                fail_diag["non_december_fy"] += 1
            else:
                fail_diag["newly_listed_or_delisted_or_other"] += 1
        if measured % 25 == 0:
            log(f"  refined {measured}/{N_TARGET} success {success}")
        time.sleep(0.03)

    krx = try_krx()
    summary = {
        "meta": {"seed": SEED, "exclude_induty": list(EXCLUDE_INDUTY), "years": YEARS},
        "F_listed_total": len(listed),
        "F4_refined_scanned": scanned,
        "F4_excluded_fin_realestate": excluded,
        "F4_refined_measured": measured,
        "F4_refined_success": success,
        "F4_refined_success_rate_pct": round(100 * success / measured, 1) if measured else 0,
        "F1_failure_diagnosis": dict(fail_diag),
        "F_corp_cls_hist": dict(cls_hist),
        "F2_krx_fetch": krx,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    log("universe_v2 완료.")


if __name__ == "__main__":
    main()
