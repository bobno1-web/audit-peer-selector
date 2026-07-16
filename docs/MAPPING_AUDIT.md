# MAPPING_AUDIT — 계정 매핑 독립 검증 + 버그 교정 (Loop 5 PART 3 → Loop 6 PART 0)

## ★ Loop 5 결론 정정 (검증방 Loop 5 발견)
Loop 5 의 이 문서는 **"매출채권 합산선(및기타채권)은 공시 현실 — 순수 매출채권 미공시, APPROX=0"**
이라 결론지어 매핑을 '신뢰 가능'으로 판정했다. **검증방이 이 결론을 뒤집는 버그를 발견했다.** 그 결론은
감사 도구의 **탐지 버그**로 인한 **인공물**이었다 — 순수 매출채권은 다수 기업에서 **실제로 공존**했고,
생산 resolver 는 그것을 놓치고 **합산을 오취득**하고 있었다. Loop 6 PART 0 에서 두 버그를 교정했다.

### 버그 1 — 감사 도구 탐지 (`mapping_audit._is_pure_receivable`)
- 순수 매출채권 여부를 id `tradereceivables`(**복수**)로 매칭했다. 그러나 순수 매출채권의 표준 id 는
  `dart_ShortTermTradeReceivable` → norm `...tradereceivable`(**끝에 s 없음**)이라 **매칭 실패** →
  순수를 '없음'으로 오판 → 합산선을 'DISCLOSURE(순수 미공시)'로 오분류.
- 교정: `tradereceivable`(**단수**, 복수형의 부분문자열이라 둘 다 포착) 매칭 + `otherreceivable`/
  `tradeandother`(기타·합산) 배제.

### 버그 2 — 생산 resolver (`pit_build.extract`)
- 별칭을 **응답 행 순서**로 매칭해 첫 매칭 별칭을 채택 → 합산행(매출채권및기타채권)이 순수행보다
  **먼저 오면 합산을 오취득**.
- 지목 사례 **00141389/2020(OFS)**: 합산 `ifrs-full_TradeAndOtherCurrentReceivables`=12,840,776,999 이
  순수 `dart_ShortTermTradeReceivable`=11,702,295,937 **앞** → 합산 오취득 확인.
- 교정: **별칭 우선순위 순서** 매칭(리스트 앞=더 구체적=순수). 매출채권 별칭 `[매출채권, 유동매출채권,
  매출채권및기타채권, …]` = 순수 먼저 → 순수 존재 시 순수 채택. **계정별 예외분기 없음**(별칭순서=specificity,
  하드코딩 금지 준수). `mapping_audit.our_pick` 도 동일 로직으로 동기화.
- ★ **ORACLE 4비율 정의 불변**(매출채권회전율=매출액/매출채권 그대로). **별칭 해석만** 교정. D-026 사전등록.

## 교정 후 독립 재검증 (n=40, seed=20260716, XBRL id + 키워드 이중 오라클)
| 채점계정 | 판정 | clear 오매핑 |
|---|---|--:|
| 매출액 | OK 40 | 0 |
| 매출원가 | OK 38 · DEFINITIONAL 2 | 0 |
| 매출총이익 | OK 38 · NA 2 | 0 |
| 영업이익 | OK 40 | 0 |
| 재고자산 | OK 35 · NA 5 | 0 |
| **매출채권** | **OK 22(순수 채택) · DISCLOSURE 17(합산만 공시) · NO_PICK 1** | 1(coverage) |

- **교정 전(Loop 5, 버그): 순수 20 / DISCLOSURE 19** → **교정 후: OK 22 / DISCLOSURE 17.** 즉 순수 매출채권이
  **실제로 존재**하는데 생산이 합산을 고르던 사례가 있었고(버그 2), 교정으로 **순수를 채택**한다.
- 전체 clear 오매핑률 = **0.43%(1/233)** — 유일한 1건은 '틀린 계정'이 아니라 IFRS9 표현
  ("매출채권 및 상각후원가측정금융자산") **coverage miss**(결측, 오답 아님).

## ★ targets 재생성 + 변경 보고 (P/Q4)
교정 resolver 로 **dev(2016~2022) targets 재생성**. raw fnlttSinglAcntAll 를 **raw_fin_cache 로 캐시**
(api-budget; 재생성 재취득 0). 예상 호출 수 로그·020 resume. 스크립트: `regen_targets.py` + `regen_swap.py`.

**변경 규모(staged vs 라이브, 실측):**
| 계정 | 변경된 dev firm-year 수 | 방향 |
|---|--:|---|
| **매출채권** | **767** | 합산 → 순수(값 ↓) → 매출채권회전율 ↑ |
| 매출원가 | 25 | 영업비용 → 매출원가(별칭 우선순위 부수효과) |
| 매출액·총자산·매출총이익·영업이익·재고자산 | **0** | 불변 |

- **★ 엔진 허용 입력(매출액·총자산) 0 변경** → 커밋된 엔진 peers(baseline·L2~L5) 는 교정 데이터에서
  **그대로 유효**(재랭킹 불요). 변경은 **채점 targets 에만**(매출채권회전율 767·재고자산회전율 25).
- **PIT 격리(정직한 한계):** 재취득 시 `fnlttSinglAcntAll` 가 **T 이후 정정공시**를 반환한 firm-year
  **2,291건**은 rcept_dt 불일치로 **옛 값 유지**(정정본 사용=룩어헤드이므로 차단). 이들은 원본 filing 을
  이 API 로 다시 못 얻어 **교정 미적용**(옛 값 불변). 즉 실제 교정 필요분은 767 보다 많을 수 있으나,
  **PIT-clean 하게 교정 가능한 767 건만** 반영했다(안전·정직).
- holdout(2023~2025) targets 는 **재생성하지 않음**(미개봉; 개봉 시 함께 재생성).

## ★ 수정 전후 점수 영향 (P12/Q4)
- **L4(median@k5) dev APE: 0.4965(교정 전) → 0.4977(교정 후).** +0.0012 = **사실상 중립(소폭 악화).**
- ★ **매핑 교정은 '정확성(올바른 계정)' 문제이지 점수 최적화가 아니다.** 순수 매출채권(더 작은 분모)이
  매출채권회전율을 키우고 peer 도 같이 커져 APE 는 거의 안 변한다. **좋아지지도 나빠지지도 않음** →
  D-026 대로 **점수에 맞춰 아무것도 조정하지 않는다.**
- **상대 순위 불변:** 모든 대조군을 교정 targets 로 재채점(SHOWDOWN_L6) — baseline<L2<L3<L4 순위 유지,
  엔진 간 우열 뒤집힘 **없음**. **ORACLE 4비율 정의 불변.**

## 원자료 커밋 (P13/Q4)
`runs/2026-07-16_mapping_audit/` — `cases.csv`·**`candidates.csv`**(개념별 모든 후보 행: account_id·nm·값,
검증방이 XBRL id 로 독립 재대조 가능)·`summary.json`·`config.yaml`. `runs/2026-07-16_regen_targets/`
— `regen_summary.json`(변경 집계). (candidates.csv 는 gitignore 예외로 커밋.)

## 발견 라우팅 (PART Z)
- **[발견-M1] 합산-매출채권 별칭 coverage 불완전**(IFRS9 '상각후원가측정금융자산') → 제안(만들지 않음):
  매출채권 매핑을 account_nm variant 나열이 아니라 **XBRL account_id 기반으로 유도**. 사전등록 후 별도 루프.
- **[발견-M2] 정정공시(amendment) 유입** → 2,291 firm-year 가 T 이후 정정본을 반환. 제안: raw_fin_cache 를
  **원본(최초) filing 고정 취득**으로 확장(rcept_no 별 이력 API)해 PIT-clean 재생성 완전화. 별도 루프.
