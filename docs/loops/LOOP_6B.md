# Loop 6-B: Loop 6 완결 (교정 반영 + 결판 + 거짓라벨 방지)

## 위치
C:\Users\gmg97\Desktop\25-26년\동종업계탐색기_클로드

## 배경
Loop 6은 미완료(검증방 확인): 매출채권 버그 '코드'는 고쳤으나 '데이터 미반영'(regen/swap),
결과 파일 "targets: corrected" 거짓 라벨, showdown L6 행 k=5 stale, 전부 미커밋 가능성.
★ 새 작업 아님. Loop 6을 실제로 완결한다. ★ holdout(2023~2025) 미개봉.

## 순서
PART 1(교정 데이터 반영) → PART 2(거짓라벨 방지) → PART 3(재결판) → PART 4(holdout 판정) → PART Z

## 완료 조건 R1~R16
R1. 교정 resolver regen 실제 실행(swap 완료)
R2. data/pit/targets 교정본 교체(해시·타임스탬프 갱신)
R3. 매출채권 767건 실제 변경 확인·보고
R4. 정정공시 2,291건 방침 DATA_CARD 기록
R5. test_provenance_integrity.py — 라벨-실제 불일치 탐지 실증 ★
R6. showdown 실제 k 읽어 출력·검증(stale k 방지)
R7. no-false-provenance.md 규칙
R8. 교정 targets 전 엔진 재채점
R9. L6 행 진짜 median@k10 ★
R10. L6 vs L4 k10-vs-k5 유효(CI[0,0] 아님) firm-clustered
R11. 교정 전후 순위 유지
R12. 전체/안정 APE 둘 다, 제외비율
R13. candidates.csv 커밋
R14. SHOWDOWN_L6.md 실제 작성
R15. 전부 커밋, LOOP_LOG, holdout 미개봉
R16. ORACLE 4비율 불변 / engines↛scoring/targets / PART Z 미반영 0

## 진행 상태 — ★ 완료

### 실증 검증 결과(먼저 확인한 것)
검증방 지적을 실증 대조: **커밋된 산출물은 실제로 교정/k10 이었다**(일부 지적은 커밋 상태와 불일치).
- showdown_l6.json L6 = 0.4794(k=10, per-ratio 가 L4와 다름 → stale k5 아님), 부트 유의(CI≠[0,0]).
- 라이브 데이터 00141389/2020 = 순수 11.70B(swap 반영됨). scores.json k=10/corrected. docs·candidates 커밋됨.
- ★ **그러나 검증방의 근본 우려는 타당**: data/pit gitignore 라 커밋만으론 '교정' 검증 불가 +
  라벨이 데이터에 결속 안 됨 + `regen_summary` 의 '총자산 11775' 거짓 수치(diff 카운터 버그). → 상환.

### R1~R16 자가 체크
- R1 regen/swap 실행(swap 완료, original/staged 백업 존재) ✅  R2 targets 교정본(digest d5db24e4≠원본 29a17996) ✅
- R3 매출채권 767 실측(provenance 정정) ✅  R4 정정공시 2,291 DATA_CARD #6 ✅
- R5 test_provenance_integrity(양성+음성 위조탐지 7개) ✅  R6 showdown 실제 k 읽어 assert ✅  R7 no-false-provenance.md ✅
- R8 교정 targets 전엔진 재채점 ✅  R9 L6 진짜 median@k10(peers.parquet=10 결속) ✅  R10 L6vsL4 clustered CI[−0.0242,−0.0131] 유의(≠[0,0]) ✅
- R11 순위 유지(base<L2<L3<L4<L6) ✅  R12 전체0.4794/안정0.4452·제외9.9% ✅  R13 candidates.csv 커밋 ✅
- R14 SHOWDOWN_L6.md(+provenance 절) ✅  R15 커밋·LOOP_LOG·holdout 미개봉 ✅  R16 ORACLE 불변·engines↛scoring·PART Z 0 ✅

### 산출물
- 코드: `provenance.py`(콘텐츠해시+검증헬퍼), `regen_provenance.py`(매니페스트), finalize/showdown 스탬프+assert,
  regen_targets diff 버그 교정. 규칙: `.claude/rules/no-false-provenance.md`. 테스트: `test_provenance_integrity.py`(7).
- 매니페스트: `runs/2026-07-16_regen_targets/provenance.json`(원본·교정 지문, 변경 767/25/0). regen_summary 정정.
- ★ 결과 불변: L6 0.4794(안정 0.4452), L4 0.4977, −3.68% 유의. 승리조건 0.433 미달. holdout 미개봉. 87 tests green.
