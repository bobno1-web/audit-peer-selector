# Loop 7: holdout 개봉 + 최종 결론 ★ 되돌릴 수 없는 1회성

## 위치
C:\Users\gmg97\Desktop\25-26년\동종업계탐색기_클로드

## 의미
2016~2022(dev)에서 학습·개발한 모든 것을 2023~2025(holdout)에 딱 한 번 적용해 out-of-sample 확정.
★ holdout 1회성. 열면 되돌릴 수 없다. ★ holdout 재학습·튜닝·가중치·k 변경 절대 금지. dev 확정 설정 적용만.
★ 결과 나빠도 왜곡·재시도 금지. 나온 대로가 최종.

## 순서
PART 0(개봉 전 게이트·freeze) → PART 1(개봉·적용) → PART 2(최종결론) → PART Z

## 완료 조건 S1~S16
[개봉 전]
S1. D-028: 적용 엔진·설정 개봉 전 확정
S2. freeze 파일 생성, 해시 기록 ★
S3. targets 교정본 확인(dev digest d5db24e4)
S4. 개봉 선언 기록
[개봉·적용]
S5. holdout 채점, dev 설정 그대로(재학습 0) ★
S6. freeze 해시 개봉 후 불변 ★
S7. dev/holdout 나란히(전체·안정)
S8. dev 순위 holdout 유지 판정
S9. L6 개선 holdout 유의(firm-clustered 부트)
S10. 과적합 정도(dev→holdout 저하율)
S11. 비율별·within·coverage holdout
[최종]
S12. FINAL_REPORT.md: 판정 3종 + 정직한 결론
S13. 산출물 사용 가이드(신뢰범위·한계)
S14. 정교화 권고(holdout 재사용 아닌 표현 개선)
[불변]
S15. holdout 재학습·왜곡 0, ORACLE 불변, provenance 결속
S16. PART Z 미반영 0

## 진행 상태 — ★ 완료 (holdout 개봉·검증 종료)

### S1~S16 자가 체크 — 전부 ✅
- S1 D-029 엔진·설정 확정 ✅  S2 freeze+해시 d582865680b490c7 ✅  S3 dev digest d5db24e4 ✅  S4 개봉선언 ✅
- S5 holdout 채점 dev설정 그대로(재학습0) ✅  S6 **freeze_unchanged_after_open=True** ✅  S7 dev/holdout 나란히 ✅
- S8 순위 유지 판정(완전 유지) ✅  S9 L6개선 holdout 유의(clustered) ✅  S10 저하율 +2.9~6.4% ✅  S11 비율별·within·cov ✅
- S12 FINAL_REPORT 판정3종+결론 ✅  S13 사용가이드(신뢰범위) ✅  S14 정교화 권고(재사용 아님 명시) ✅
- S15 재학습·왜곡0·ORACLE불변·provenance결속(holdout digest 4f539b70) ✅  S16 PART Z 미반영 0 ✅

### ★★ holdout 개봉 결과
| 엔진 | dev | holdout | 저하 |
|---|--:|--:|--:|
| baseline | 0.5427 | 0.5585 | +2.9% |
| L4 | 0.4977 | 0.5297 | +6.4% |
| **L6** | **0.4794** | **0.5029** | +4.9% |

- **순위 완전 유지**: [L6<L4<L3<L2<baseline] dev==holdout.
- **L6 vs baseline holdout −10.0%** clustered CI[−0.074,−0.037] **유의**. **L6 vs L4 −5.1%** CI[−0.042,−0.010] **유의**(k=10 실재).
- **과적합 경미**(진짜 개선). **승리조건 0.433 미달**(holdout 0.5029/안정 0.4657). 상한 ≈0.50 확정.
- freeze 해시 개봉 후 불변(튜닝 0). 89 tests green. 상세 `docs/FINAL_REPORT.md`.
