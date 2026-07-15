# Loop 2: Similarity 엔진 + 데이터층 감사 + baseline 결판

## 위치
C:\Users\gmg97\Desktop\25-26년\동종업계탐색기_클로드
★ docs/loops/LOOP_2.md 로 먼저 저장. 완료조건 M1~M20.

## 의미
baseline(0.5416)을 이기는 엔진을 만든다. 동시에 아무도 검증 안 한 데이터층을 감사한다.
★ 시장중앙값(0.5720)이 이미 강해 peer 선정 여지가 좁다. "similarity가 정말 의미있게 이기나"의 결판.

## 순서
PART 0(데이터 감사) → PART 1(similarity) → PART 2(결판) → PART Z
★ PART 0에서 데이터 오류 크면 멈추고 보고. 틀린 데이터 위 엔진 개선은 무의미.

## PART 0. 데이터층 감사 (검증방 발견 #1)
【진단】"계산이 맞나"만 봤고 "데이터 자체가 맞나"는 아무도 안 봄. targets parquet 재무가 DART
원본과 일치하는지 독립 검증 안 됨. 추출층 계통오차는 개발·검증방이 동일하게 물려받는다.
0-1. 표본 감사: 채점에 쓰인 기업 30+ 무작위(dev), 4비율 분자·분모를 DART 재취득, parquet 대조.
  불일치율·크기 보고. ★ 원자료 runs/ 커밋(검증방 재대조).
0-2. 불일치 분류: 파싱/단위/정의(연결·별도·매핑)/시점(rcept_dt).
0-3. docs/DATA_AUDIT.md: 불일치율·유형분포·★판정(데이터 신뢰 가능한가; 크면 파서 수정 우선).
0-4. ★게이트화 D-020(측정 전, gate_design 5검사): 예) 불일치율 ≤5% AND 계통편향 없음.
  미달 시 PART 1 금지. gate.py 강제.

## PART 1. Similarity 엔진 (PART 0 게이트 PASS 후)
1-1. engines/similarity/: 여러 피처를 '가중 점수' 합산 랭킹(필터 아님). 피처: 산업유사도·규모유사도·
  사업내용 텍스트 유사도(features/business, 임베딩). ★가중치 손으로 정하지 말고 dev 학습/탐색
  (holdout 금지), 방식 문서화. ★임베딩 캐싱.
1-2. 절대규칙: engines↛scoring/targets, as_of만·룩어헤드0, 매직상수/리터럴 금지, 필터 아닌 스코어링.
1-3. ★엔진은 타겟 채점비율 못 봄(마진·회전율 보면 부정, 훅 검사).
1-4. ★개선 표적: 영업이익률(baseline이 시장보다 +11% 나빴음).

## PART 2. 결판 (dev만)
2-1. 동일 dev(2016~2022) similarity 채점. ★baseline과 완전 동일 케이스셋·채점기·페널티·상수.
2-2. 나란히: 시장/랜덤/baseline/similarity — 전체 APE중앙값·비율별(특히 영업이익률)·within·coverage.
2-3. ★승리조건(PLAN): similarity APE ≤ 0.433(baseline −20%)? 미달이어도 왜곡 금지.
  ★D-021 사전 기록: 미달=실패 아니라 "peer 선정 효과 상한" 발견일 수 있음(결과 전 박기).
2-4. docs/SHOWDOWN.md: 네 점수·이겼나 얼마나·승리조건·어느 비율 개선·정직한 결론.

## PART Z + 검증방 발견(#2,#3,#4)
Z-1. 페널티 비대칭(#2): 대조군 A가 페널티 정의하며 자신은 면제 — 명시.
Z-2. 무재무 30% 침묵(#3): 점수는 재무 있는 ~70%만. "점수가 못 다루는 범위" 명시.
Z-3. 고정상수(#4): k=5,q=0.9,min_peers=3은 '자의 일부'. 튜닝 금지 지점 기록.
Z-4. 라우팅 미반영0. LOOP_LOG Loop2.

## 금지
- holdout 열기 금지★. similarity 유리하게 조건변경 금지. 가중치 holdout 학습 금지.
- 승리조건 결과보고 조정 금지. engines↛scoring/targets, 룩어헤드0. 매직상수/리터럴 금지.
- ORACLE 4비율 변경 금지. PART 0 게이트 PASS 전 PART 1 금지.

## 완료 조건 M1~M20
M1. 표본30+ DART재취득 parquet대조. M2. DATA_AUDIT.md 불일치율·유형·판정. M3. 원자료 runs/커밋.
M4. D-020 측정전 기록 5검사통과. M5. 데이터 게이트 gate.py 강제(미달시 PART1 차단).
M6. engines/similarity peers.parquet. M7. 가중치 dev학습(holdout미사용) 문서화. M8. 피처3종+임베딩캐싱.
M9. engines↛scoring/targets(훅·test_engine_isolation). M10. as_of만·룩어헤드0(test_pit_integrity).
M11. 타겟 채점비율 미접근(test_no_leakage). M12. 매직상수/리터럴0. M13. 필터 아닌 스코어링.
M14. baseline과 동일 케이스셋·채점기·페널티·상수. M15. 네 대조군 나란히. M16. 비율별(영업이익률).
M17. 승리조건 판정, D-021 사전기록. M18. SHOWDOWN.md 정직 결론. M19. holdout 미개봉.
M20. ORACLE 4비율 / PART Z 미반영0(#2,#3,#4).

## 출력
1. 데이터 감사 불일치율+판정. 2. 네 대조군 점수. 3. similarity가 baseline 이겼나+승리조건.
4. 영업이익률 개선? 5. 정직한 결론(peer 선정 효과). 6. holdout 미개봉. 7. M1~M20. 8. 제안.
