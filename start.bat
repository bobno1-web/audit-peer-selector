@echo off
chcp 65001 >nul
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PEER_OPEN_BROWSER=1
cd /d "%~dp0"

echo ============================================================
echo   동종기업 선정기 - 웹 UI (로컬 전용)
echo   브라우저에서 회사명을 입력합니다. (키는 선택)
echo ============================================================
echo.

REM 1) Python 확인
where python >nul 2>nul
if errorlevel 1 (
  echo [오류] Python 을 찾을 수 없습니다.
  echo   https://www.python.org/downloads/ 에서 Python 3.11 이상을 설치한 뒤 다시 실행하세요.
  echo   설치 시 "Add python.exe to PATH" 를 체크하세요.
  echo.
  pause
  exit /b 1
)

REM 2) 의존성 확인 - 없으면 최초 1회 설치 시도
python -c "import flask, pandas, numpy, yaml, pyarrow" >nul 2>nul
if errorlevel 1 (
  echo [설치] 필요한 라이브러리를 설치합니다. 최초 1회만 걸립니다...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [경고] 자동 설치에 실패했습니다. 아래를 직접 실행해 보세요:
    echo       python -m pip install -r requirements.txt
    echo.
  )
)

echo.
echo === 웹 서버를 시작합니다. 잠시 후 브라우저가 자동으로 열립니다 ===
echo   * 이 창을 닫지 마세요 - 창이 서버를 유지합니다.
echo   * 종료하려면 이 창에서 Ctrl+C 를 누르거나 창을 닫으세요.
echo.

python app.py

echo.
echo [종료] 웹 서버가 중지되었습니다.
pause
endlocal
