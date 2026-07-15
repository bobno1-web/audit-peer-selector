# Loop 1: Baseline 엔진 + 첫 점수  ★ Loop 0 종료, 엔진 시대 시작

## 위치
C:\Users\gmg97\Desktop\25-26년\동종업계탐색기_클로드
★ docs/loops/LOOP_1.md 로 먼저 저장. 완료조건 L1~L18.

## 의미
baseline = "산업분류 + 규모"만 쓰는 무식한 엔진. 앞으로 모든 엔진이 넘어야 할 기준선.
★ baseline이 목적이 아니다. baseline보다 나아지는지 재는 '자(尺)'를 만드는 것이다.

## PART 0. 인프라 정리 (Loop 0 잔여)
0-1. gate.py tol=0.05 매직상수 제거 → 정확 대조(반올림 규칙) 또는 config. (0-I 검증 #3)
0-2. .claude/rules/verification-is-final-defense.md 신규 + DECISIONS D-019. (0-I 검증 #1,#2,#4)
  "게이트 재집계 코드도 에이전트가 수정 가능 → 무한후퇴. 최종 안전장치는 검증방의 독립
   재집계다. 게이트 통과 주장은 검증방의 독립 재현 없이는 확정되지 않는다."

## PART 1. Baseline 엔진 (engines/baseline/)
1-1. 입력: 타겟 i, 시점 T. as_of(T) 유니버스 → peer 상위 k(config,5): 같은 산업분류(우선)+규모 근접.
  규모 거리(로그/비율)·k = config. 매직상수 금지. 출력: runs/<날짜>_loop1_baseline/peers.parquet.
1-2. 절대규칙(훅 검사): scoring/ import 0, targets/ 접근 0, as_of만, 리터럴/매직상수 0,
  필터 아닌 스코어링(전 유니버스 랭킹, 산업 달라도 배제 안 함).
1-3. 규모 결측 처리 명시+config. 임의대체 금지.

## PART 2. 채점기 (scoring/oracle/) — ORACLE.md 그대로
2-1. 입력: peers.parquet만. 각 (i,T): 정의되는 비율만, peer k 중앙값→예측, |예측-실제|/|실제|=APE.
  engines/ import 0. targets/ 는 여기서만 읽음.
2-2. FAIL(peer<3): 제외 아닌 페널티. 페널티는 dev 분포 유도(임의상수 금지).
2-3. 출력 scores.json: 주지표(정의된비율 APE중앙값)+비율별+within 10/20/30+coverage+비율수분포.

## PART 3. 점수 + 대조군
3-1. dev(2016~2022)만 채점. holdout(2023~2025) 안 엶.
3-2. 세 대조군 함께: (A)전체시장 배수중앙값 (B)랜덤5 (C)baseline. 나란히 보고. baseline이 A,B 이기나?
3-3. docs/BASELINE_SCORE.md: 세 점수 나란히+비율별 분해+baseline이 A,B 이기는지.
3-4. holdout 절대 안 엶.

## PART 4. 무결성
4-1 test_engine_isolation, 4-2 test_no_leakage, 4-3 test_pit_integrity, 4-4 훅 전체.

## PART Z
Z-1 라우팅 미반영0. Z-2 LOOP_LOG Loop1(비개발자 한줄).

## 금지
- engines/ → scoring/·targets/ 접근 금지. holdout 열기 금지 ★. 필터 캐스케이드 금지.
- 매직상수/리터럴 금지(config). 결측 임의대체 금지. ORACLE 4비율 변경 금지.
- baseline 잘보이게 대조군 약화 금지.

## 완료 조건 L1~L18
L1. gate.py tol 하드코딩 제거. L2. verification-is-final-defense.md. L3. D-019.
L4. engines/baseline 구현+peers.parquet. L5. 규모거리·k config(매직0). L6. scoring import 0(훅).
L7. targets 접근 0(test_engine_isolation). L8. as_of만·룩어헤드0(test_pit_integrity). L9. 필터 아닌 스코어링.
L10. scoring/oracle 구현 ORACLE대로. L11. engines import0, peers.parquet만. L12. 정의된 비율만(test_ratio_definedness).
L13. FAIL 페널티 dev분포 유도. L14. scores.json 주지표+비율별+within+coverage+비율수분포.
L15. dev에서 (A)(B)(C) 세 점수 나란히 ★. L16. BASELINE_SCORE.md baseline이 A,B 이기는지.
L17. holdout 미개봉(2023~2025 접근0) ★. L18. ORACLE 4비율 그대로 / PART Z 미반영0.

## 출력
1. 세 대조군 APE 중앙값. 2. baseline이 랜덤·시장중앙값 이기나?얼마나. 3. 비율별 분해.
4. 타겟당 정의된 비율 수 분포. 5. holdout 미개봉 확인. 6. L1~L18 자가체크. 7. 제안(만들지 말고).
