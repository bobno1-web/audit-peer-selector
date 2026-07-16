# MAPPING_AUDIT — 계정 매핑 독립 검증 (Loop 5 PART 3)

3루프째 미뤄온 숙제 상환. 지금까지 검증은 **"값이 DART와 같나"**(DATA_AUDIT: 100% 일치)만 봤다.
이 문서는 처음으로 **"우리 별칭이 그 비율의 올바른 분자·분모 계정을 골랐나"**를 독립 재유도한다.

- 스크립트: `scripts/mapping_audit.py`. 원자료: `runs/2026-07-16_mapping_audit/{summary.json, cases.csv, candidates.csv, config.yaml}` (검증방 재대조용, P13).
- 표본: dev 채점 기업 **40개** 무작위 **seed=20260716** — DATA_AUDIT(seed 20260715)와 **다른 독립 표본**.

## ★ 독립성 확보 방법 (개발방 별칭을 신뢰하지 않는다)
매핑이 틀리면 개발방·검증방이 같은 오류를 공유해 서로 대조해도 못 잡는다. 그래서 우리 config 의
별칭 목록을 **쓰지 않고**, 두 독립 오라클로 각 계정 개념을 재검색해 별칭의 선택과 대조한다:
1. **XBRL `account_id`** — DART 표준 택소노미 concept id(`ifrs_Revenue`, `ifrs_CostOfSales`,
   `ifrs_GrossProfit`, `dart_OperatingIncomeLoss`, `ifrs_Inventories`,
   `dart_ShortTermTradeReceivable`(순수) vs `ifrs_TradeAndOtherCurrentReceivables`(합산)). 우리와 독립.
2. **개념 키워드 broad 검색** — raw 재무제표의 모든 후보 행을 나열(별칭 목록과 무관).
별칭이 고른 계정이 '가장 구체적(올바른)' 후보인지 규칙+증거로 판정한다.

## 결과 — 계정별 (n=40 기업)
| 채점계정 | OK | 판정분류 | clear 오매핑 | 대표 account_id |
|---|--:|---|--:|---|
| 매출액 | 40 | 전부 OK | **0** | ifrs(-full)_Revenue |
| 매출원가 | 38 | OK 38 · **DEFINITIONAL 2** | **0** | ifrs(-full)_CostOfSales (2건 dart_OperatingExpenses) |
| 매출총이익 | 38 | OK 38 · NA 2(미정의) | **0** | ifrs(-full)_GrossProfit |
| 영업이익 | 40 | 전부 OK | **0** | dart_OperatingIncomeLoss (40/40) |
| 재고자산 | 35 | OK 35 · NA 5(재고없음=미정의) | **0** | ifrs(-full)_Inventories |
| 매출채권 | 20 | OK 20(순수) · **DISCLOSURE 19(합산)** · NO_PICK 1 | 1(coverage) | dart_ShortTermTradeReceivable / TradeAndOther |

**★ 전체 clear 오매핑률 = 0.43% (1 / 233 평가케이스).** 유일한 1건은 '틀린 계정'이 아니라 **coverage
miss**(아래 3-2). 별칭이 발화한 곳에서 **틀린 계정을 고른 사례(category a) = 0건.**

## ★ 검증방 지목 2건 — 독립 검증 결과 (둘 다 오류 아님 확인)
### (1) 매출원가 ← 영업비용 (5% 우려)
- 실측 2/40 이 영업비용 대체. **두 건 모두 순수 `매출원가` 행이 raw 에 존재하지 않았다** →
  분류 **DEFINITIONAL**(매출원가 미보고 서비스업의 정당한 대체). `account_id`도 `dart_OperatingExpenses`.
- **순수 매출원가가 존재하는데 영업비용을 고른 사례(MISMAP) = 0건.** → D-020/DATA_AUDIT 의 해석
  ("매출원가 미보고 시 대체")이 독립 표본에서 **재확인**. 오매핑 아님.

### (2) 매출채권 "및기타채권" 합산선 (67% 우려)
- 순수 매출채권 20/40(`dart_ShortTermTradeReceivable`) · 합산 19/40(`ifrs_TradeAndOtherCurrentReceivables`).
- ★ **결정적 독립 소견: `APPROX`(합산을 골랐는데 순수도 존재) = 0건.** 합산선 19건은 모두 그 기업이
  **순수 매출채권을 별도 공시하지 않아** 합산선이 **유일한 후보**였다(분류 DISCLOSURE). 즉
  "및기타채권"은 우선순위 실수가 아니라 **공시 현실**이다 — D-020 논거가 독립 표본에서 **실증**됐다.
- 매출채권회전율(매출액÷매출채권)에서 합산선은 분모를 약간 키워 **보수적**(회전율 소폭 저평가). 단
  **모든 엔진에 동일 적용되는 고정 자(尺)** 이므로 baseline↔L2~L5 **상대 비교엔 무영향**(상수).

## 3-2. 불일치 분류 (P10)
| 유형 | 건수 | 처리 |
|---|--:|---|
| (a) 명백한 오매핑(틀린 계정) | **0** | 없음 |
| (b) 허용 근사(합산 표기 등 실무 관행) | 19(매출채권 합산) + 2(영업비용) | 기록·유지 |
| (c) 정의 차이 | — | 연결/별도는 fs_div 로 이미 구분(prow.fs_div), 표본 내 개념혼선 0 |
| coverage miss(별칭 미포함 합산 표현) | 1 | 아래 결정 |

### coverage miss 1건 (심각 아님)
- 기업 00572905(FY2019): 매출채권을 **"매출채권 및 상각후원가측정금융자산(유동)"**(id
  `ifrs_TradeAndOtherCurrentReceivables`)로 공시. 우리 합산 별칭 목록
  (`매출채권및기타채권/기타유동채권/기타수취채권`)에 **이 IFRS9 표현이 없어** exact-match 실패 → 매출채권 **결측**.
- ★ **틀린 값이 아니라 '없는 값'**이다: 그 기업의 매출채권회전율이 **미정의(결측)로 제외**될 뿐(ORACLE
  "정의된 비율만"), **잘못된 숫자를 만들지 않는다.** → category (a) 심각 오매핑 아님.

## 3-3. ★ 판정: 채점 데이터의 매핑을 신뢰할 수 있는가? — **예 (신뢰 가능)**
- **틀린 계정을 고른 사례 0건.** 5개 계정 모두 XBRL 표준 id 와 일치(또는 비표준 id 라도 계정명 정상).
- 검증방 지목 2건(매출원가←영업비용, 매출채권 합산선)은 **오류가 아니라 공시 현실/정당한 대체**로
  독립 재확인. 개발방·검증방이 공유할 "숨은 매핑 오류"는 발견되지 않았다.
- 유일한 흠은 합산-매출채권 별칭의 **coverage 불완전**(IFRS9 '상각후원가측정금융자산' 표현 누락),
  ~2.5% 기업에서 매출채권이 **결측**(틀림 아님)이 될 수 있음.

## 3-3. P12 — 별칭 교정 여부 및 점수 영향
- **심각한 오매핑(category a) = 0건 → 별칭 교정 트리거 미발동.**
- 따라서 **이번 루프 별칭·ORACLE 4비율 전부 불변**(P20). **수정 없음 → 점수 영향 0.**
- coverage miss 는 별칭 교정 후보이지만 **이번 루프엔 고치지 않는다** — 근거:
  1. **하드코딩 위험**: 한 회사의 특정 문자열("…상각후원가측정금융자산")을 별칭에 박는 것은
     no-hardcoding 위반 소지. 원리적 해법은 **매핑을 account_nm 문자열이 아니라 XBRL concept id
     (`TradeAndOtherCurrentReceivables`)로 유도**하는 것이며, 이는 파서/pit_build 를 바꿔 targets 를
     재생성하는 큰 변경(동결된 채점 데이터 파이프라인 접촉) → 별도 루프에서 사전등록 후 진행.
  2. **1-관측 과적합 위험**: 새 독립 표본의 단 1건으로 별칭을 고치면 그 표본에 과적합. 광범위 측정
     후 사람이 판단할 사안.
  3. **안전성**: 미고침의 결과는 '결측'(안전)이지 '오답'이 아니다. 중앙값 편향 없음(임의대체 0,
     케이스 수만 소폭 감소). → 성능을 위해 데이터를 왜곡하지 않는다는 원칙과 일치.
- **미고침의 정량 영향**: 표본상 매출채권 coverage = 39/40 포착, 1/40(2.5%) 결측. 결측은 결측이라
  APE 중앙값을 **편향시키지 않는다**(오답 주입 0). coverage 만 미미하게 낮아질 뿐.

## 3-4. 원자료 커밋 (P13)
`runs/2026-07-16_mapping_audit/` — `cases.csv`(기업×계정 별칭 선택+판정), `candidates.csv`(개념별 모든
후보 행: account_id·account_nm·값 — 검증방이 XBRL id 로 독립 재대조 가능), `summary.json`, `config.yaml`.
(cases.csv 는 git 포함; summary.json·candidates.csv 는 runs/ 규칙에 따라 로컬 — README 경유 재현.)

## 발견 라우팅 (PART Z)
- **[발견-M1] 합산-매출채권 별칭 coverage 불완전** → 제안(만들지 않음): 매출채권 매핑을 account_nm
  variant 나열이 아니라 **XBRL account_id(`TradeAndOtherCurrentReceivables`/`ShortTermTradeReceivable`)
  기반으로 유도**. 사전등록 후 별도 루프. 이번 루프 미반영(정당한 근거 위 3-3).
