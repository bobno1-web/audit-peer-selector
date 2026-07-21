# LOOP_WEB5 — 최신(2023~2025) 스냅샷 빌드 + 웹 연결

## 의미
웹앱이 2022(dev) 스냅샷만 봤다. 실무용으로 최신 데이터가 필요하다. 2023~2025 데이터로
"최신 스냅샷"을 세우고, 웹이 그걸 조회하게 한다. ★ 확정 엔진을 최신 데이터에 **적용(apply)**만
한다 — 재학습(fit) 아님.

## ★ 절대 원칙
1. 엔진 가중치·로직은 dev 확정값 **고정 로드**만. 최신 데이터로 재학습/재탐색/튜닝 금지(봉인 위반).
   "확정 엔진 apply(predict)"이지 "학습(fit)" 아님.
2. ORACLE·채점기·엔진 코드 무변경. 데이터만 최신화.
3. 디자인·화면·템플릿 무변경. "보는 데이터"만 2022→최신. UI 코드 미변경.
4. point-in-time 유지: 각 시점엔 그 시점 이전 데이터만. 룩어헤드 0.

## 핵심 발견 (PART 0~2 이미 충족)
- **2023~2025 PIT 데이터가 이미 존재**(holdout 구축 + Loop 7 개봉·적용 시 수집·피처화 완료).
  `data/pit/features/{industry,scale,mktcap,growth}_{2023,2024,2025}`, `universe_*`, `ratios_*`,
  텍스트 벡터(business) 모두 완비. → **신규 DART 수집 0(캐시 웜)**. 재수집은 api-budget 위반이라 안 함.
- **확정 L6 = 5축[industry,scale,mktcap,text,growth]** (segment 미사용). 그래서 segment_2023~2025
  부재는 무관. weights = `runs/2026-07-15_loop4_similarity/weights.json`(dev 동결).
- 완비 최신 연도 = **2025** → 최신 as_of = **2025-05-15**(직전 사업연도 fiscal 2024).

## 적용 (apply, fit 아님)
- `build_report.l6_cfg_weights` 가 dev 동결 weights 를 **로드**해 `year_engine(2025,...)` 에 적용.
- 신뢰등급 임계=Loop 8 동결 `thresholds.json`, τ_r=dev 유도(_ctx 의 dev 리스트, holdout 미참조).
  → 스냅샷 연도만 2025 로 바뀌고 가중치/임계값은 전부 dev 동결. 순수 apply.

## 웹 연결 (데이터 소스만)
- `web_engine._snapshot_year()`: 기본 = **데이터 완비 최신 연도(2025)**. 롤백/고정 =
  env `PEER_SNAPSHOT_YEAR` 또는 `config/web_snapshot.json` 의 `serve_as_of_year`(2022 로 롤백).
  ★ 데이터 소스 선택 로직만. `_ctx` 의 dev 유도(τ/threshold)·엔진·템플릿 무변경.
- as_of 표기: 템플릿이 `r.target.as_of` 를 그대로 출력 → 자동 2025-05-15 갱신(화면 코드 무변경).
- 2022 스냅샷 보존: `out/results` 를 `out/results_snapshot_2022/` 로 백업 후 2025 로 재생성(롤백 가능).
- 키: 세션 메모리만, 미저장(기존 유지).

## 완료 조건 Z1~Z20 → 상태
Z1 최신 as_of=2025-05-15 point-in-time 정의 · Z2 기존 파이프라인 재사용(신설0) · Z3 DART probe:
신규호출0(캐시 웜) resume 불요 · Z4 캐시 재사용 · Z5 수집 성공률(기존 완비) · Z6 raw 캐싱 활용 ·
Z7 서브에이전트 불요(수집 완료) · Z8 기존 피처 로직 · Z9 임베딩 캐싱 신규0 · Z10 형식 동일 ·
Z11 피처 파라미터 dev 고정 · Z12 weights 해시 동일(재학습0) · Z13 신뢰등급·τ dev 동결 로드 ·
Z14 최신 결과 형식동일·데이터만 최신 · Z15 룩어헤드0 · Z16 웹 최신 조회·화면 무변경 ·
Z17 as_of 갱신 · Z18 2022 보존·키 미저장 · Z19 데이터외 변경0(해시) · Z20 재학습 안함 검증.

## 금지
최신 데이터로 재학습/재탐색/튜닝 · ORACLE/채점기/엔진 변경 · 화면/템플릿/디자인/UI 변경 ·
룩어헤드 · 캐시 없이 대량 재호출 · DART 억지 반복 · 키 저장 · 새 파이프라인 신설.

## 상태
진행 중 — 변경: `web_engine.py`(_snapshot_year 데이터소스 선택), `config/web_snapshot.json`(신규 포인터),
`out/results/*.json`(2025 재생성, 2022 백업 보존), 이 문서, `out/screenshots/web5_*.png`.
불변(해시): weights·holdout_freeze·thresholds·build_report·app.py·templates·default.yaml.
</content>
</invoke>
