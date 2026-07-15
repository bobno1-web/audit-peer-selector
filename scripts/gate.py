#!/usr/bin/env python3
"""게이트 = 코드로 강제되는 STOP. 문서가 아니라 실행 조건이다.

근거: Loop 0-F 게이트 위반(DECISIONS D-011). 문서-only 게이트는 설득·합리화가 가능했다.

불변식:
  - status=PASS 로 가는 유일한 경로는 `approve` (사람의 명시적 승인 인자) 뿐이다.
    create/measure/fail 은 **절대** PASS 를 만들 수 없다(코드가 거부).
  - 게이트 파일은 서명(HMAC)된다. 파일을 손으로 편집해 status=PASS 로 바꿔도
    서명이 불일치 → `verify()` 실패 → 빌드 차단.
  - 빌드/후속 스크립트는 `require_pass(gate_id)` 를 호출한다. 미통과면 sys.exit(1).

위협 모델(정직히): 에이전트는 FS 접근권이 있어 `.gatekey` 를 읽어 위조하거나 이 파일을
고칠 수도 있다. 그것은 **의도적 위·변조**로, 합리화(0-F)와는 다른 종류의 명백한 위반이며
서명·감사로 드러난다. 이 게이트가 막는 것은 "되돌릴 수 있으니/부재중이니/안전하니 넘자"는
**합리화에 의한 통과**다 — create/measure/build 어디에도 PASS 경로가 없다.
"""
import argparse
import hashlib
import hmac
import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALID = {"PASS", "FAIL", "PENDING"}
SIGNED = ("gate_id", "loop", "status", "criteria", "measured", "decided_by", "decided_at")


def gate_dir():
    return Path(os.environ.get("GATE_DIR", ROOT / "runs" / "gates"))


def _key():
    d = gate_dir()
    d.mkdir(parents=True, exist_ok=True)
    kf = d / ".gatekey"
    if not kf.exists():
        kf.write_text(secrets.token_hex(32), encoding="utf-8")
    return kf.read_text(encoding="utf-8").strip().encode()


def _canon(obj):
    return json.dumps({k: obj.get(k) for k in SIGNED},
                      sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def _sign(obj):
    return hmac.new(_key(), _canon(obj), hashlib.sha256).hexdigest()


def path_of(gid):
    return gate_dir() / f"{gid}.json"


def read_gate(gid):
    p = path_of(gid)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _write(obj):
    obj["sig"] = _sign(obj)
    path_of(obj["gate_id"]).write_text(
        json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return obj


def _set(gid, loop, status, criteria, measured, decided_by, decided_at):
    if status not in VALID:
        raise ValueError(f"invalid status {status}")
    return _write({"gate_id": gid, "loop": loop, "status": status, "criteria": criteria,
                   "measured": measured, "decided_by": decided_by, "decided_at": decided_at})


def create(gid, loop, criteria, decided_at="0000-00-00", measured=None):
    """게이트를 PENDING 으로 만든다(측정 전). 절대 PASS 아님."""
    return _set(gid, loop, "PENDING", criteria, measured or {}, "script", decided_at)


def measure(gid, measured, status, decided_at="0000-00-00"):
    """측정 결과 기록. status 는 FAIL 또는 PENDING 만 허용 — PASS 는 여기서 못 만든다."""
    if status == "PASS":
        raise PermissionError("measure()로 PASS 불가. approve(사람 승인)만 PASS 가능.")
    g = read_gate(gid) or {}
    return _set(gid, g.get("loop"), status, g.get("criteria", {}), measured, "script", decided_at)


def approve(gid, human_approval, decided_at="0000-00-00"):
    """★ PASS 로 가는 유일한 경로. 사람의 명시적 승인 인자가 반드시 필요."""
    if not human_approval or not str(human_approval).strip():
        raise PermissionError("approve 는 사람의 명시적 승인 인자(--human-approval)가 필요하다.")
    g = read_gate(gid)
    if g is None:
        raise FileNotFoundError(f"gate {gid} 없음 — 먼저 create/measure")
    g = dict(g)
    g["measured"] = {**g.get("measured", {}), "human_approval_token": str(human_approval)}
    return _set(gid, g.get("loop"), "PASS", g.get("criteria", {}), g["measured"],
                "human", decided_at)


def _cmp(v, op, t):
    if v is None:
        return False
    return {"<=": v <= t, "<": v < t, ">=": v >= t, ">": v > t, "==": v == t}.get(op, False)


def judge(gid, decided_at="0000-00-00"):
    """★ 코드 판정 (LOOP_0H): criteria.checks 를 measured 에 기계적으로 적용해 PASS/FAIL 을 정한다.
    사람이 손으로 approve 하지 않는다 — 사람의 승인은 criteria(D-016) 를 확정한 것으로 갈음한다.
    측정값(measured)은 원자료(runs/)로 재집계 가능해야 하고, threshold 는 criteria 에 고정돼 있다."""
    g = read_gate(gid)
    if g is None:
        raise FileNotFoundError(f"gate {gid} 없음")
    checks = (g.get("criteria") or {}).get("checks", [])
    measured = g.get("measured", {})
    results = []
    for c in checks:
        v = measured.get(c.get("metric"))
        ok = _cmp(v, c.get("op"), c.get("threshold"))
        results.append({"name": c.get("name"), "metric": c.get("metric"), "op": c.get("op"),
                        "threshold": c.get("threshold"), "value": v, "pass": bool(ok)})
    passed = len(results) > 0 and all(r["pass"] for r in results)
    return _set(gid, g.get("loop"), "PASS" if passed else "FAIL", g.get("criteria", {}),
                {**measured, "judge_results": results}, "gate_criteria_auto", decided_at)


def verify(gid):
    """status==PASS 이고 서명이 유효한가. (손편집·위조 탐지.)"""
    g = read_gate(gid)
    if g is None or g.get("status") != "PASS":
        return False
    return hmac.compare_digest(g.get("sig", ""), _sign(g))


def require_pass(gid):
    """빌드/후속 스크립트가 호출. 미통과면 종료."""
    if not verify(gid):
        g = read_gate(gid)
        st = g.get("status") if g else "NONE"
        sys.stderr.write(
            f"[GATE] '{gid}' 미통과(status={st}). 게이트가 열리기 전엔 실행할 수 없다.\n"
            f"       PASS 는 사람의 승인으로만: python scripts/gate.py approve {gid} "
            f"--human-approval <승인>\n")
        sys.exit(1)
    return True


def _cli():
    ap = argparse.ArgumentParser(description="게이트 관리. PASS 는 approve(사람 승인)로만.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check"); p.add_argument("gid")
    p = sub.add_parser("show"); p.add_argument("gid")
    p = sub.add_parser("fail"); p.add_argument("gid"); p.add_argument("--at", default="0000-00-00")
    p = sub.add_parser("approve")
    p.add_argument("gid"); p.add_argument("--human-approval", dest="ha", default="")
    p.add_argument("--at", default="0000-00-00")
    p = sub.add_parser("judge"); p.add_argument("gid"); p.add_argument("--at", default="0000-00-00")
    a = ap.parse_args()

    if a.cmd == "check":
        ok = verify(a.gid)
        print(f"{a.gid}: {'PASS(verified)' if ok else 'NOT PASS'}")
        return 0 if ok else 1
    if a.cmd == "show":
        g = read_gate(a.gid)
        print(json.dumps(g, ensure_ascii=False, indent=2) if g else f"{a.gid}: 없음")
        return 0
    if a.cmd == "fail":
        g = read_gate(a.gid) or {}
        measure(a.gid, g.get("measured", {}), "FAIL", a.at)
        print(f"{a.gid}: FAIL 기록")
        return 0
    if a.cmd == "approve":
        try:
            approve(a.gid, a.ha, a.at)
        except PermissionError as e:
            sys.stderr.write(f"거부: {e}\n")
            return 1
        print(f"{a.gid}: PASS (사람 승인). 서명 갱신.")
        return 0
    if a.cmd == "judge":
        g = judge(a.gid, a.at)
        print(f"{a.gid}: {g['status']} (코드 판정, decided_by={g['decided_by']})")
        for r in g["measured"].get("judge_results", []):
            print(f"    {r['name']}: {r['value']} {r['op']} {r['threshold']} -> "
                  f"{'PASS' if r['pass'] else 'FAIL'}")
        return 0 if g["status"] == "PASS" else 1
    return 2


if __name__ == "__main__":
    sys.exit(_cli())
