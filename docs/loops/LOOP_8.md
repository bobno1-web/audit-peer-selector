# Loop 8: 산출물 정교화 + 설계 여정 기록

## 위치
C:\Users\gmg97\Desktop\25-26년\동종업계탐색기_클로드

## 의미
성능 검증 종료(Loop 7). 예측 오차 상한 도달, holdout 소진. 이번엔 (1) 검증된 엔진을 실무 도구로
정교화(숫자 미변경), (2) 설계 여정 기록(JOURNEY.md). ★ 예측오차 저하·holdout 재사용 금지.
전부 "결과 표현·활용"이지 "성능"이 아니다.

## 순서
PART 1(산출물 정교화·숫자 불변) → PART 2(설계 여정 기록) → PART Z

## 완료 조건 T1~T18
[정교화]
T1. peer 신뢰도 등급, 기준 config·dev 유도
T2. 신뢰등급 채점비율 실제값 미사용
T3. peer 선정 근거(축별 기여) 출력
T4. 확인필요지점 표시(채점기 값 재활용)
T5. 출력 형식 확정, OUTPUT_FORMAT.md 스키마
T6. 사용 예시(dev 기업, holdout 아님)
T7. 정교화가 예측오차 불변(엔진 점수 확인)
[여정]
T8. JOURNEY.md 존재
T9. 문제정의 + 핵심 설계결정(대안 포함)
T10. 하네스 발견: 게이트오류 6종 + 거짓라벨 2회 + 매핑버그
T11. holdout 결과·승리조건 미달·상한 정직 기록
T12. 방법론 원칙
T13. ★ 외부제출/평가/면접/지원/포트폴리오 언급 0
T14. ★ 톤: 판단 기록, 과장 없음
T15. README 갱신, 외부제출 언급 0
[불변]
T16. 예측오차·엔진점수 불변
T17. holdout 미재사용, ORACLE 불변, provenance 결속
T18. PART Z 미반영 0

## 진행 상태 — ★ 완료

### T1~T18 자가 체크 — 전부 ✅
- T1 신뢰등급(응집도 삼분위, dev 유도 q33=0.431/q67=0.523) ✅  T2 채점비율 실제값 미사용(grade=응집도 함수, test_report_layer) ✅
- T3 축별 기여 근거(rationale) ✅  T4 확인필요지점(채점기 편차 재활용, dev q90) ✅  T5 OUTPUT_FORMAT.md 스키마 ✅
- T6 사용예시(dev 2022, HIGH/MED/LOW/확인필요/비교부적합) ✅  T7 **엔진점수 불변**(L6 dev 0.4794) ✅
- T8 JOURNEY.md ✅  T9 문제정의+설계결정(버린 대안 2종 등) ✅  T10 게이트오류 6종+거짓라벨 2회+매핑버그 ✅
- T11 holdout −10%·승리조건 미달·상한 0.50 정직 ✅  T12 방법론 원칙 6 ✅  T13 외부제출/평가/면접 언급 0(grep 확인) ✅
- T14 톤: 판단 기록·과장 없음 ✅  T15 README 갱신·외부제출 0 ✅
- T16 예측오차·엔진점수 불변(L6 0.4794/holdout 0.5029) ✅  T17 holdout 미재사용·ORACLE 불변·provenance 결속 ✅  T18 PART Z 0 ✅

### 산출물
- 정교화: `scripts/build_report.py`(표현 계층) + config `report` 블록(dev 유도) + `docs/OUTPUT_FORMAT.md` +
  `runs/2026-07-16_loop8/{sample_reports.json, peer_report.csv, thresholds.json}` + `test_report_layer`(2).
- 여정: `docs/JOURNEY.md`(문제정의·설계결정·하네스 발견·한계·원칙), `README.md` 갱신.
- ★ 엔진/채점기 미변경. 91 tests green. holdout 미재사용.
