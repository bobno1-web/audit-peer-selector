"""동종기업 선정기 — 로컬 웹 UI (Flask).

★ 설계 원칙 (CLAUDE.md / LOOP_WEB1):
  - 웹은 **읽기 전용 소비자**다. 엔진/채점기/ORACLE 을 복제·수정하지 않는다.
    회사명 질의는 `web_engine.query()` 로만 처리하며, 그 안에서 Loop 8 표현 계층
    (`build_report.py`)의 검증된 함수를 그대로 호출한다(재구현 0).
  - 스냅샷은 dev 최신(2022-05-15)으로 고정 → 룩어헤드·holdout(2023~2025) 개봉 0.
  - OpenDART 키는 ★화면 입력 → **세션 메모리에만** 둔다. 파일·로그·디스크·서버 os.environ
    어디에도 남기지 않는다(요청 처리 후 지역변수와 함께 소멸). 엔진 질의 경로는 pre-built
    스냅샷에서 랭킹하므로 키를 호출하지 않는다(정직: 신규 기업 수집 확장 시에만 사용).
  - ★로컬 전용 바인딩(127.0.0.1). 외부 노출 금지.
"""
from __future__ import annotations

import json
import socket
import threading
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, url_for

import web_engine

BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "out" / "results"

app = Flask(__name__)

# 랜딩 입력창 placeholder 로 쓸 데모 회사(표시 예시)는 config 에서 로드한다.
# ★ 하드코딩 회사명 리터럴 배제(Web-1 검증방 지적). 엔진·랭킹과 무관 — 순위는 입력 회사에 대해 실시간 산출.
# (Web-2 에서 예시 칩 UI 제거 → index.html 이 examples 를 안 씀. 죽은 examples 전달·인덱스 삭제.
#  /example 라우트는 out/results 를 직접 읽으므로 영향 없음 — Web-6 검증방 지적 정리.)
WEB_EXAMPLES = BASE_DIR / "config" / "web_examples.json"


def _placeholder_company() -> str:
    """랜딩 placeholder 회사명(표시 전용). config web_examples.json 에서 로드(리터럴 미하드코딩)."""
    try:
        cfg = json.loads(WEB_EXAMPLES.read_text(encoding="utf-8"))
        cand = cfg.get("placeholder_company") or (cfg.get("demo_companies") or [""])[0]
        return str(cand or "").strip()
    except Exception:
        return ""


# ── 라우트 (3페이지 플로우: / → /key → /search → 결과) ─────────────────────────
@app.get("/")
def index():
    """랜딩(1페이지). 입력창 없음 — '시작하기' 로만 /key 로 이동(네이버 웨일 톤)."""
    return render_template("index.html")


@app.get("/key")
def key():
    """키 입력(2페이지). OpenDART 키(선택). '다음' → /search. 키는 폼으로만 전달, 저장 0."""
    return render_template("key.html")


def _search_ctx(**over):
    """/search·에러 재렌더용 컨텍스트(연도 목록·placeholder·이어받은 키). 세션 저장 없이 폼 값만."""
    years = web_engine.available_years()
    ctx = {"placeholder": _placeholder_company(), "years": years,
           "selected_year": years[0] if years else None, "opendart_key": ""}
    ctx.update({k: v for k, v in over.items() if v is not None})
    return ctx


def _parse_year(raw, years):
    """폼 연도(문자열) → 유효 연도(int) 또는 None(기본=최신). 임의값 방지."""
    try:
        y = int(raw)
    except (TypeError, ValueError):
        return None
    return y if y in years else None


@app.route("/search", methods=["GET", "POST"])
def search():
    """회사 입력(3페이지). /key 에서 POST 로 온 키를 hidden 으로 이어받아 '전달만' 한다.
    ★ Web-9: OpenDART 키 필수 — 빈 값이면 /key 로 되돌려 진행 차단(V9-1).
    ★ 키는 서버·파일·로그·쿠키 어디에도 저장하지 않는다 — 다음 폼으로 넘길 뿐(반환 시 소멸).
      (키는 POST 바디로만 전달 — GET 쿼리스트링 금지: dev 서버 access log 노출 방지.)"""
    opendart_key = (request.values.get("opendart_api_key") or "").strip()  # 폼 전달용(미저장)
    if not opendart_key:
        return render_template("key.html", key_error=True), 400   # 키 없이 진행 차단
    return render_template("search.html", **_search_ctx(opendart_key=opendart_key))


@app.route("/query", methods=["GET", "POST"])
def query():
    """결과. 회사·연도로 web_engine.query 실행. 실패 시 /search 재렌더(랜딩 아님)."""
    name = (request.values.get("company") or "").strip()
    years = web_engine.available_years()
    year = _parse_year(request.values.get("year"), years)
    sel = year or (years[0] if years else None)
    # ★ 키는 받되 저장하지 않는다 — 지역변수 밖으로 새지 않으며 반환 시 소멸(폼 재전달만).
    #   pre-built 스냅샷 랭킹은 키를 호출하지 않는다(신규 기업 수집 확장 시에만 사용).
    opendart_key = (request.values.get("opendart_api_key") or "").strip()

    if not name:
        return render_template("search.html", **_search_ctx(
            error="회사명을 입력하세요.", company=name, selected_year=sel,
            opendart_key=opendart_key)), 400

    result = web_engine.query(name, year=year)
    if not result.get("ok"):
        return render_template("search.html", **_search_ctx(
            error=result.get("message"), reason=result.get("reason"),
            suggestions=result.get("suggestions", []), company=name, selected_year=sel,
            opendart_key=opendart_key)), 200

    return render_template("result.html", r=result, live=True)


@app.get("/example/<slug>")
def example(slug: str):
    """미리 저장된 결과(out/results/<slug>.json)를 읽어 표시 — 엔진 미실행, 파일만 읽음.
    ★ 경로 조작 방지: results/ 밖으로 못 나가게 검증."""
    path = (RESULTS_DIR / f"{slug}.json").resolve()
    if RESULTS_DIR.resolve() not in path.parents or not path.exists():
        abort(404)
    result = json.loads(path.read_text(encoding="utf-8"))
    if not result.get("ok"):
        abort(404)
    return render_template("result.html", r=result, live=False)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# ── 서버 기동 ────────────────────────────────────────────────────────────────
def _port_in_use(host: str, port: int) -> bool:
    """이미 LISTEN 중인 포트인지 연결 프로브로 확인(Windows SO_REUSEADDR 오탐 방지)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def _find_free_port(host: str, start: int, tries: int = 20) -> int:
    for port in range(start, start + tries):
        if _port_in_use(host, port):
            continue  # 다른 서버가 점유 중(예: 타 프로젝트) — 건너뜀
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))  # ★ SO_REUSEADDR 없이 — 실제 가용성 정확 탐지
                return port
            except OSError:
                continue
    return start


def _open_browser_when_ready(host: str, port: int) -> None:
    import time
    import webbrowser

    url = f"http://{host}:{port}"
    for _ in range(40):  # 최대 ~10초 대기 후 브라우저 오픈
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host, port)) == 0:
                break
        time.sleep(0.25)
    webbrowser.open(url)


def _warmup_bg() -> None:
    """스냅샷 컨텍스트를 백그라운드에서 미리 구축(첫 질의 지연 최소화)."""
    try:
        meta = web_engine.warmup()
        print(f"  [엔진] 스냅샷 준비 완료: as_of={meta['as_of']}, "
              f"universe={meta['n_universe']}종목", flush=True)
    except Exception as exc:  # noqa: BLE001 — 워밍업 실패는 첫 질의 때 표면화
        print(f"  [엔진] 워밍업 지연(첫 질의 때 로드): {exc!r}", flush=True)


if __name__ == "__main__":
    import os

    host = "127.0.0.1"  # ★로컬 전용. 0.0.0.0 금지(외부 노출 방지).
    port = int(os.environ.get("PEER_WEB_PORT") or _find_free_port(host, 5000))
    print("=" * 60)
    print("  동종기업 선정기 — 로컬 웹 UI")
    print(f"  브라우저에서 열기:  http://{host}:{port}")
    print("  ★이 창을 닫지 마세요 — 창이 서버를 유지합니다.")
    print("=" * 60, flush=True)
    threading.Thread(target=_warmup_bg, daemon=True).start()
    if os.environ.get("PEER_OPEN_BROWSER") == "1":
        threading.Thread(target=_open_browser_when_ready, args=(host, port), daemon=True).start()
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
