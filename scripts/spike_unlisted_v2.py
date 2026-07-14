#!/usr/bin/env python3
"""[임시] PART C+D — 비상장 감사보고서 재무 추출 재측정(n=200) + 진단대상 계정 원인 진단.
   (진단 대상 계정은 config/account_aliases.yaml 의 diagnose_target 에서 읽는다.)

파서·계정사전은 audit_parser + config/account_aliases.yaml (계정명 코드에 없음).
성공 = 필수 6계정 전부 확보(엄격). 계정별·6개전부 둘 다 보고.
원자료: runs/2026-07-14_spike_unlisted_v2/{summary.json, cases.csv, config.yaml}.
"""
import csv
import io
import json
import random
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_parser as ap                     # noqa: E402
from derive_required_accounts import derive   # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SEED = 20260714
N_TARGET = 200
SCAN_CAP = 1000
RUN_DIR = ROOT / "runs" / "2026-07-14_spike_unlisted_v2"


def log(m):
    print(m, file=sys.stderr, flush=True)


def fetch_nonlisted():
    blob = ap.get_raw("corpCode.xml", {})
    xml = zipfile.ZipFile(io.BytesIO(blob)).read("CORPCODE.xml")
    root = ET.fromstring(xml)
    non = []
    for n in root.iter("list"):
        sc = (n.findtext("stock_code") or "").strip()
        cc = (n.findtext("corp_code") or "").strip()
        if cc and not (len(sc) == 6 and sc.isdigit()):
            non.append({"corp_code": cc, "corp_name": (n.findtext("corp_name") or "").strip()})
    return non


def collect(non):
    random.shuffle(non)
    out, scanned = [], 0
    for rec in non:
        if len(out) >= N_TARGET or scanned >= SCAN_CAP:
            break
        scanned += 1
        res = ap.get_json("list.json", {"corp_code": rec["corp_code"], "bgn_de": "20200101",
                                        "end_de": "20221231", "pblntf_ty": "F", "page_count": "20"})
        if res.get("status") == "000":
            for row in res.get("list", []):
                nm = row.get("report_nm", "")
                if "감사보고서" in nm and "연결" not in nm:
                    out.append({**rec, "rcept_no": row.get("rcept_no", ""),
                                "rcept_dt": row.get("rcept_dt", "")})
                    break
        if scanned % 50 == 0:
            log(f"  collect scanned={scanned} got={len(out)}")
        time.sleep(0.03)
    return out, scanned


def main():
    random.seed(SEED)
    aliases, target, base = ap.load_aliases()
    required = derive()[0]
    req_aliases = {a: aliases[a] for a in required}
    non = fetch_nonlisted()
    log(f"nonlisted {len(non)}")
    sample, scanned = collect(non)
    log(f"collected {len(sample)} (scanned {scanned})")

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    cases = []
    acct_ok = Counter()
    all6 = rec_base_ok = rec_full_ok = 0
    rec_class = Counter()
    miss_succ, miss_fail = Counter(), Counter()
    for i, rec in enumerate(sample, 1):
        text = ap.fetch_doc_text(rec["rcept_no"])
        rows = ap.parse_rows(text)
        found = ap.extract_found(rows, req_aliases)
        comp = ap.get_json("company.json", {"corp_code": rec["corp_code"]})
        ind2 = (comp.get("induty_code") or "").strip()[:2] or "NA"
        flat = ap.flat_text(text)
        rb = ap.account_in_numeric_row(rows, base)
        rf = ap.account_in_numeric_row(rows, aliases[target])
        rec_base_ok += int(rb)
        rec_full_ok += int(rf)
        cls = ""
        if not rb:                                   # 0-D 기본 별칭 기준 실패 케이스만 분류
            if rf:
                cls = "a_dict"                       # 표기차이/합산 → 사전으로 해결(파서)
            elif not ap.alias_in_text(flat, aliases[target]):
                cls = "c_absent"                     # 계정 자체 없음(데이터)
            elif len(rows) == 0 or len(text) < 2000:
                cls = "d_format"                     # 파일 형식(데이터)
            elif ap.alias_in_text(flat, aliases[target]):
                cls = "b_notInTable"                 # 텍스트엔 있으나 숫자표 밖(파서)
            else:
                cls = "e_other"
            rec_class[cls] += 1
        ok6 = all(a in found for a in required)
        all6 += int(ok6)
        for a in required:
            acct_ok[a] += int(a in found)
        (miss_succ if ok6 else miss_fail)[ind2] += 1
        cases.append({"corp_code": rec["corp_code"], "corp_name": rec["corp_name"],
                      "rcept_no": rec["rcept_no"], "induty2": ind2, "tables": len(rows),
                      "all6": int(ok6), **{a: int(a in found) for a in required},
                      "recv_base": int(rb), "recv_full": int(rf), "recv_class": cls})
        if i % 20 == 0:
            log(f"  measure {i}/{len(sample)} all6={all6} recv_full={rec_full_ok}")
        time.sleep(0.03)

    n = len(sample)
    parser_probs = rec_class.get("a_dict", 0) + rec_class.get("b_notInTable", 0)
    data_probs = rec_class.get("c_absent", 0) + rec_class.get("d_format", 0)
    summary = {
        "meta": {"seed": SEED, "n": n, "scanned": scanned, "required": required,
                 "parser": "scripts/audit_parser.py", "aliases": "config/account_aliases.yaml",
                 "success_def": "필수 6계정 전부 확보(엄격)"},
        "D3_account_success_pct": {a: round(100 * acct_ok[a] / n, 1) for a in required},
        "D3_account_success_count": {a: acct_ok[a] for a in required},
        "D3_all6_success_pct": round(100 * all6 / n, 1),
        "D3_all6_success_count": all6,
        "C_receivable_base_pct": round(100 * rec_base_ok / n, 1),
        "C_receivable_full_pct": round(100 * rec_full_ok / n, 1),
        "C_receivable_failure_classes": dict(rec_class),
        "C_parser_problems": parser_probs,
        "C_data_problems": data_probs,
        "C_parser_vs_data_note": ("(a)합산/표기차이+(b)표밖 = 파서, (c)없음+(d)형식 = 데이터. "
                                  f"분류 대상 = 기본 별칭({','.join(base)})으로 실패한 케이스."),
        "D4_missingness_induty2": {"success": dict(miss_succ), "fail": dict(miss_fail)},
    }
    (RUN_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    with open(RUN_DIR / "cases.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(cases[0].keys()))
        w.writeheader()
        w.writerows(cases)
    cfg = (
        "# spike_unlisted_v2 실행 설정 (원자료 재현용)\n"
        f"seed: {SEED}\nn_target: {N_TARGET}\nscan_cap: {SCAN_CAP}\n"
        "parser: scripts/audit_parser.py\naliases_file: config/account_aliases.yaml\n"
        "num_regex: '^\\(?-?(\\d{1,3}(,\\d{3})+|\\d{4,})\\)?$'\n"
        f"required_accounts: [{', '.join(required)}]\n"
        f"diagnose_target: {target}\n"
        f"receivable_base: [{', '.join(base)}]\n"
        "success_definition: 필수 6계정 전부 확보\n"
        "report_types: 감사보고서 (pblntf_ty=F, 연결 제외)\nperiod: 2020-2022\n"
    )
    (RUN_DIR / "config.yaml").write_text(cfg, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    log("unlisted_v2 완료.")


if __name__ == "__main__":
    main()
