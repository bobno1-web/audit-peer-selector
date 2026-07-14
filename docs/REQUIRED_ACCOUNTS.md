# REQUIRED_ACCOUNTS — 필수 계정 (자동 유도)

> ★ 이 파일은 `scripts/derive_required_accounts.py` 의 **산출물**이다. **손으로 편집 금지.**
> 갱신: `python scripts/derive_required_accounts.py --write`.

유도 경로: `docs/ORACLE.md` 채점 비율 → `config/default.yaml` 비율→계정 매핑 → 분자·분모 합집합.

## 채점 비율 (4개)

- 매출총이익률
- 영업이익률
- 재고자산회전율
- 매출채권회전율

## 필수 계정 (6개)

- 매출액
- 매출원가
- 매출채권
- 매출총이익
- 영업이익
- 재고자산

## 필수 아님 — 엔진 허용 입력 중 채점 비율에 안 쓰이는 것 (피처 전용)
  없다고 그 기업을 버리지 않는다. (config `engine_allowed_inputs` 에서 자동 계산)

- 산업분류
- 총자산
- 종업원수
- 사업내용텍스트
