#!/usr/bin/env python3
"""웹 예시 결과 생성 — 키 없이 볼 수 있는 dev 기업 결과를 out/results/ 에 저장(Loop WEB-1 W19).

★ dev 스냅샷(2022-05-15)에서만 생성 → holdout(2023~2025) 미개봉.
★ 산출은 web_engine.query() 그대로(엔진/채점기 미변경). 파일명 = corp_code.
회사 목록은 인자로 받는다(하드코딩 최소화). 못 찾은 이름은 건너뛴다(정직).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import web_engine  # noqa: E402

OUT = ROOT / "out" / "results"

# 기본 예시 후보(dev 기업). 인지도·다양한 신뢰등급·확인필요지점 포함되도록.
DEFAULT_NAMES = ["강원에너지", "삼성전자", "한글과컴퓨터", "오뚜기", "매일유업", "CJ제일제당"]


def main(names):
    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    for nm in names:
        r = web_engine.query(nm)
        if not r.get("ok"):
            print(f"  건너뜀: {nm} ({r.get('reason')})", file=sys.stderr)
            continue
        code = r["target"]["corp_code"]
        (OUT / f"{code}.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        flags = [x["ratio"] for x in r["ratios"] if x.get("check_needed")]
        made.append({"name": r["target"]["corp_name"], "code": code,
                     "confidence": r["peer_confidence"], "check_needed": flags})
        print(f"  저장: {r['target']['corp_name']} [{code}] {r['peer_confidence']} "
              f"확인필요={flags}", file=sys.stderr)
    print(json.dumps({"saved": made, "dir": str(OUT.relative_to(ROOT))},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT_NAMES)
