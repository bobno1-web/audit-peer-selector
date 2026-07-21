#!/usr/bin/env bash
# 동종기업 선정기 - 웹 UI 기동 래퍼 (macOS / Linux)
# 엔진/채점기 코드는 수정하지 않습니다. app.py 가 web_engine.query() 로 기존 엔진을 호출만 합니다.
# 회사명은 브라우저 화면에서 입력합니다(키는 선택 — 데모는 pre-built 스냅샷에서 순위).
# 최초 1회: chmod +x start_web.sh  후  ./start_web.sh

cd "$(dirname "$0")" || exit 1
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export PEER_OPEN_BROWSER=1

echo "============================================================"
echo "  동종기업 선정기 - 웹 UI (로컬 전용)"
echo "  브라우저에서 회사명을 입력합니다. (키는 선택)"
echo "============================================================"
echo

# 1) Python 확인
PY=""
if command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
else
  echo "[오류] Python 을 찾을 수 없습니다."
  echo "  https://www.python.org/downloads/ 에서 Python 3.11 이상을 설치한 뒤 다시 실행하세요."
  exit 1
fi

# 2) 의존성 확인 - 없으면 최초 1회 설치 시도
if ! "$PY" -c "import flask, pandas, numpy, yaml, pyarrow" >/dev/null 2>&1; then
  echo "[설치] 필요한 라이브러리를 설치합니다. 최초 1회만 걸립니다..."
  "$PY" -m pip install -r requirements.txt || {
    echo "[경고] 자동 설치에 실패했습니다. 아래를 직접 실행해 보세요:"
    echo "      $PY -m pip install -r requirements.txt"
    echo
  }
fi

echo
echo "=== 웹 서버를 시작합니다. 잠시 후 브라우저가 자동으로 열립니다 ==="
echo "  * 이 창을 닫지 마세요 - 창이 서버를 유지합니다."
echo "  * 종료하려면 이 창에서 Ctrl+C 를 누르세요."
echo

"$PY" app.py

echo
echo "[종료] 웹 서버가 중지되었습니다."
