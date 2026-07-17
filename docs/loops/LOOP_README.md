# Loop README: GitHub 공개용 README 작성

## 위치
C:\Users\gmg97\Desktop\25-26년\동종업계탐색기_클로드

## 의미
성능 검증 종료(Loop 7)·산출물 정교화와 여정 기록(Loop 8) 이후, 이 프로젝트를 GitHub 공개
저장소로 올리기 위한 **README.md / README.en.md** 를 작성한다. ★ 문서 작업만 — 코드·엔진·
데이터·ORACLE 미변경, holdout 미재사용. 자매 프로젝트(audit-issue-tracker)와 같은 4장 구조·톤.

## 순서
실제 저장소 확인(실행법·경로·산출물) → README.md(한) → README.en.md(영) → grep 검증 → 자가 체크.

## 완료 조건 U1~U16 — 전부 ✅

- **U1** README.md 4장 구조(소개/실행법/예시/설계원칙) ✅
- **U2** 1장: 한 문단 요약 + 차별점 3개 + 유니버스(KOSPI+KOSDAQ 2016~2025) ✅
- **U3** 2장: 실행법이 실제 저장소와 일치(엔트리 `python -m engines.{baseline,similarity}.run`,
  `scripts/build_report.py`, 데이터 빌드 `scripts/pit_build.py`; 지어낸 경로 0) ✅
- **U4** 2장: OpenDART 키 안내 + `.env.example`→`.env` + 키 비저장(gitignore·urllib 헤더 미로깅) ✅
- **U5** 3장: 실제 산출물(`runs/2026-07-16_loop8/sample_reports.json`) 기반, **dev 2022-05-15**(holdout 아님) ✅
- **U6** 3장: 신뢰등급(HIGH/MEDIUM/LOW)·축별 선정근거·확인필요지점·출력 스키마 포함 ✅
- **U7** 4장: 정답라벨 부재 → 재무비율 예측오차 채점 원리 ✅
- **U8** 4장: 필터 아닌 스코어링(전 종목 점수화) ✅
- **U9** 4장: 하드코딩·룩어헤드·생존편향 금지(구조/코드 강제) ✅
- **U10** 4장: 개발–검증 분리 + 원자료 독립 재집계 ✅
- **U11** 4장: 게이트 설계오류 발견·재발방지(하네스 핵심) ✅
- **U12** 4장: holdout −10% + 승리조건(0.433) 미달 + 상한(median APE ≈0.50) 정직 기술 ✅
- **U13** README.en.md 영어판, 동일 구조·정직성 ✅
- **U14** ★ 한/영 both 외부제출/평가/면접 언급 0 (grep 확인) ✅
- **U15** ★ 성능 과장 0, 승리조건 미달 명시 ✅
- **U16** 코드·엔진·데이터·ORACLE 미변경(문서만), holdout 미재사용 ✅

## 산출물
- `README.md`(한국어, 4장) · `README.en.md`(영어, 동일 구조)
- 근거: `runs/2026-07-16_loop8/sample_reports.json`(예시), `docs/FINAL_REPORT.md`(성능),
  `docs/JOURNEY.md`(설계 여정 압축 원본), `.env.example`(키 안내).
- grep 검증: 면접/제출/평가/지원/포트폴리오/채용/이력서·interview/portfolio/resume/recruit/submission = 0.
