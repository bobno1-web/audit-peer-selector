# LOOP_WEB1 — 웹앱 구축 (화면 + 엔진 연결)

## 의미
검증된 L6 엔진(dev APE 0.4794, holdout 0.5029) 위에 실제 작동하는 로컬 웹앱을 올린다.
회사명을 넣으면 **기존 엔진을 그대로 호출**해 동종기업을 화면에 순위로 보여준다.
자매 프로젝트(특수관계자 모니터링 등)와 같은 실행 방식(로컬 Flask + .bat).

## ★ 절대 원칙 — 데이터 정직성
화면에 표시하는 모든 값은 **실제 산출물에만** 근거한다. 지어내지 않는다.
- 실제 출력 스키마(`runs/2026-07-16_loop8/sample_reports.json`, `scripts/build_report.py`)에
  **있는 필드만** 화면에 쓴다.
- 신뢰등급·확인필요지점은 **Loop 8 계산 그대로** 재사용(화면용 새 판정 로직 금지).
- 엔진/채점기/ORACLE **미변경**. 웹은 출력을 읽어 표시만 하는 소비자.

## 아키텍처 결정 (정직성 근거)
- **스냅샷 = 2022-05-15** (dev 최신연도). `pit.as_of(2022-05-15)` 는 2022 파일만 읽으므로
  **holdout(2023~2025) 파일에 물리적으로 접근하지 않는다** → 룩어헤드·holdout 개봉 0.
- 회사명↔corp_code 는 `data/pit/universe/universe_2022.csv`(공시 원장). 시장은 corp_cls.
- 리포트 생성기: `web_engine.py` — **Loop 8 `build_report.py` 의 검증된 함수를 그대로 재사용**
  (`target_report`, `grade`, `build_ratio_block`). 엔진 로직 재구현 0.
- 임계값(응집도 삼분위·편차분위)은 Loop 8 **dev 산출 committed thresholds.json** 로드(동결값).
- **OpenDART 키:** 엔진 질의 경로(run.py/build_report.py)는 OpenDART 를 호출하지 않는다
  (pre-built PIT 스냅샷에서 랭킹). 키는 자매 프로젝트 패턴대로 화면 입력받아 **세션 메모리에만**
  두고, 스냅샷에 없는 신규 기업 수집(확장) 시에만 자식 프로세스 env 로 전달한다. 파일·로그·커밋 저장 0.

## 완료 조건 W1~W22

### 데이터 계약
- **W1** `docs/WEB_DATA_CONTRACT.md`: 실제 출력 스키마 기록
- **W2** ★ 화면 필드가 전부 실제 스키마에 존재 (지어낸 필드 0)
- **W3** peer별 축분해는 실제로 있을 때만 표시 (없으면 미표시)

### 백엔드
- **W4** Flask 로컬 서버, 127.0.0.1 자동 오픈
- **W5** start.bat / start.sh 존재, 자매 프로젝트 패턴
- **W6** 회사명 입력 → 엔진 L6 실행 → 결과 반환
- **W7** 엔진 기존 코드 호출 (재구현 0), as_of 준수 룩어헤드 0
- **W8** 키 세션 메모리만, 파일·로그·커밋 저장 0, .env.example만
- **W9** 회사 못 찾으면 정직한 에러 (억지 결과 0)

### 랜딩
- **W10** 크림 배경 #FBF0E8, 코랄 #D85A30
- **W11** 헤드라인·부제·CTA·3단계 확정본대로
- **W12** 흰 카드 + 얇은 테두리 + 그림자, 왼쪽 선 0, 회색 배경 0

### 결과
- **W13** 단순 페이지, 사이드바 없음, 순백 배경
- **W14** 타겟 회사명·메타 실제 데이터
- **W15** peer 리스트: 순위·회사명·신뢰등급 (실제 필드)
- **W16** 신뢰등급 배지 색 규칙대로
- **W17** check_needed 실제 값 있을 때만 표시
- **W18** PwC 톤 여백, 왼쪽 선 0, 회색 배경(카드 제외) 0

### 예시·검증
- **W19** 키 없이 볼 예시 결과 저장 (dev 기업, holdout 아님)
- **W20** 실제 엔진 1회 실행으로 화면 채워짐 확인, 스크린샷 저장
- **W21** holdout 미개봉·미사용

### 불변
- **W22** 엔진·채점기·ORACLE 미변경

## 상태
완료 — W1~W22 충족. 산출: `web_engine.py`(질의), `app.py`(Flask), `templates/{index,result}.html`,
`start.bat`/`start.sh`, `out/results/*.json`(dev 예시), `out/screenshots/*.png`, `tests/test_web_contract.py`.
검증: 웹 산출이 커밋된 Loop 8 `sample_reports.json` 과 바이트 단위 일치(test 3 passed).
엔진·채점기·ORACLE·config 미변경(git 확인, 신규 파일만).
