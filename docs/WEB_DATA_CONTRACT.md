# WEB_DATA_CONTRACT — 웹 화면이 쓰는 실제 출력 스키마 (Loop WEB-1 · PART 0)

★ 이 문서는 화면을 만들기 **전에** 실제 산출물 스키마를 확인해 고정한 계약이다.
출처: `scripts/build_report.py`(생성기), `runs/2026-07-16_loop8/sample_reports.json`(실측),
`docs/OUTPUT_FORMAT.md`(스키마 정의). 화면은 **여기 있는 필드만** 쓴다. 없는 건 안 만든다.

웹은 이 스키마를 **on-demand 로 한 기업**에 대해 재생성한다(`web_engine.py`). 재생성은
build_report 의 **검증된 함수를 그대로 호출**(`target_report`·`grade`·`build_ratio_block`)하므로,
출력은 sample_reports.json 과 **바이트 단위로 일치**한다. (예: 강원에너지 00100601 →
peer_cohesion 0.5337, rank1 sim 0.5676 — 커밋된 샘플과 동일함을 실측 확인.)

---

## A. 실제 출력 필드 (build_report 가 내보내는 전부)

### A-1. 타겟(기업/시점 1건)
| 필드 | 타입 | 실제/유도 | 화면 사용 |
|---|---|---|---|
| `target` (corp_code) | str | 실제(엔진 코드) | 내부키(표시는 회사명) |
| `as_of` | "YYYY-05-15" | 실제 | ✅ 메타(평가시점) |
| `peer_confidence` | HIGH·MEDIUM·LOW | 실제(Loop 8, 응집도 삼분위) | ✅ **그룹 배지 1개** |
| `peer_cohesion` | float | 실제(top-k 유사도 평균) | ✅ 참고 표기 |
| `peers[]` | list | 실제 | ✅ 리스트 |
| `ratios[]` | list | 실제(채점기 재활용) | ✅ 확인필요지점만 |

### A-2. peer 1건 (`peers[]`)
| 필드 | 타입 | 실제/유도 | 화면 사용 |
|---|---|---|---|
| `rank` | int(1..10) | 실제 | ✅ 순위(코랄) |
| `peer_code` | str | 실제 | 내부키 |
| `similarity` | float | 실제(가중합) | ✅ 유사도 표기 |
| `rationale` | {industry,scale,mktcap,text,growth} | 실제(w_c·sim_c, 축별 기여) | ✅ **상위 축 태그** |

### A-3. ratio 1건 (`ratios[]`)
| 필드 | 타입 | 실제/유도 | 화면 사용 |
|---|---|---|---|
| `ratio` | str | 실제(비율명) | ✅ 확인필요지점 라벨 |
| `peer_median` | float·null | 실제(예측치) | (이번 루프 미표시) |
| `target_actual` | float | 실제 | (이번 루프 미표시) |
| `deviation_pct` | float·null | 실제(편차) | ✅ 확인필요지점 근거 |
| `direction` | 상위·하위 | 실제 | ✅ 확인필요지점 근거 |
| `check_needed` | bool | 실제(편차 dev 상위 10%↑) | ✅ 하단 안내 트리거 |
| `confidence` | HIGH·MEDIUM·LOW | 실제 | (그룹 배지로 대체) |
| `valid_peers` | int | 실제 | (미표시) |
| `comparable` | bool | 실제(손익분기 근처=false) | ✅ 확인필요지점 주석 |
| `note` | str | 실제 | ✅ 있을 때만 |

### A-4. 원장에서 결합하는 메타 (universe_2022.csv — 실제 공시 원장)
| 필드 | 출처 | 화면 |
|---|---|---|
| `corp_name`(타겟·peer) | universe corp_name | ✅ 회사명 |
| `market` | universe corp_cls (Y/K/N/E → 표시명) | ✅ 시장 |
| `induty_code` | features induty_code (KSIC 코드) | ✅ 업종(코드) |
| `stock_code` | universe stock_code | ✅ 참고 |
| `fiscal_year` | as_of 연도−1 (5/15 스냅샷=직전 사업연도) | ✅ 회계연도 |

---

## B. 화면에 쓰는 필드 (확정) — 전부 A 에 존재 (지어낸 필드 0)

**랜딩:** (데이터 없음 — 정적 마케팅)

**결과 페이지:**
1. 타겟: `corp_name`(큰 글씨) + 메타 `market · induty_code · fiscal_year(평가시점 as_of)` — 전부 실제
2. 그룹 신뢰등급 배지 1개: `peer_confidence` (색 규칙: 높음 초록 / 보통 노랑 / 낮음 회색)
3. "비교 가능한 동종기업 N곳": `len(peers)`
4. peer 행: `rank`(코랄) · `peer_name` · `similarity` · 상위 축 태그(`rationale` 상위 2축)
5. 하단 "확인이 필요할 수 있습니다": `ratios` 중 `check_needed==true` 인 것만
   (근거로 `ratio·deviation_pct·direction`, `comparable==false`면 `note`)

## C. ★ 데이터 정직성 결정 (설계 대비 조정 — 근거 명시)

1. **신뢰등급 배지는 peer별이 아니라 '그룹 1개'다.** 실제 출력의 `peer_confidence` 는
   **peer 그룹 전체**의 등급(응집도 기반) 1개뿐이다. **peer별 등급 필드는 존재하지 않는다.**
   설계 시안은 "[순위][회사명][신뢰등급 배지]"로 peer 행마다 배지를 두었으나, peer별 등급을
   화면에서 **지어내지 않기 위해**(절대 원칙) 배지는 그룹 수준에 1개만 둔다. peer 행에는 실제
   per-peer 필드인 `similarity` 와 `rationale`(축 태그)를 쓴다. → **W2·W15·W16 을 정직하게 충족.**
2. **축 태그는 실제 `rationale` 에서만.** 각 peer 의 축별 기여(`rationale`)는 실제 존재하므로,
   기여 상위 2축을 태그로 표시한다(예: "규모 유사 · 시가총액 유사"). 정렬·라벨은 표시 변환일 뿐
   새 판정 로직이 아니다. → **W3 충족(있으니 표시).**
3. **업종은 KSIC '코드'만.** 산업분류 '명칭' 데이터는 산출물에 없다 → 코드(예: 289)만 표시,
   명칭을 지어내지 않는다.
4. **회계연도는 유도값(as_of−1)임을 명시.** 5/15 스냅샷은 직전 사업연도 사업보고서를 담는다
   (`pit/reader.py` 스냅샷 의미). 평가시점 `as_of` 도 함께 표기한다.
5. **비율 상세표(peer_median vs target_actual)는 이번 루프 미표시.** 설계상 "리스트까지만".
   확인필요지점 안내에만 편차를 근거로 인용한다.

## D. 룩어헤드·holdout 방어
- 스냅샷 = **2022-05-15**(dev 최신). `as_of(2022-05-15)` 는 2022 파일만 읽어 holdout(2023~2025)에
  물리적으로 접근하지 않는다. 웹은 연도를 dev 최신으로 고정(사용자가 시점을 못 바꾼다) → **W7·W21**.
- 임계값은 Loop 8 dev 산출 `thresholds.json`(동결) 로드 — 화면용 재튜닝 0.
