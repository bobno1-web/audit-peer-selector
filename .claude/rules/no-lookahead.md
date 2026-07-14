# 규칙: 룩어헤드 금지 (no-lookahead)

## 무엇이 금지인가
시점 T의 peer를 고르거나 채점할 때, T 이후에 생긴 정보를 사용하는 것.
- T 이후 공시된 재무제표
- T 이후 개정된 산업분류
- T 이후의 주가·시가총액
- T 시점에 상장돼 있던 기업을 "지금 상장폐지됐다"는 이유로 후보에서 빼는 것 (생존편향)

## 왜 위험한가
미래를 훔쳐본 엔진은 벤치마크에서 비현실적으로 높은 점수를 받는다.
실거래 시점엔 그 정보가 없으므로 성능이 폭락한다. 하네스 전체가 거짓말이 된다.

## 위반 예시
```python
# BAD: 오늘 기준 최신 재무제표를 무조건 로드 (T 이후 데이터 유입)
df = load_financials(ticker)                  # as_of 없음

# BAD: 지금도 상장된 기업만 후보로 (생존편향)
candidates = [c for c in universe if c.is_listed_today]

# BAD: 미래 날짜 하드코딩
snapshot = load_pit("2099-12-31")
```

## 올바른 예시
```python
# GOOD: 평가시점 T를 명시적으로 넘겨 그 시점 스냅샷만 사용
df = load_financials(ticker, as_of=T)

# GOOD: T 시점에 살아있던 전 종목 (이후 상폐 포함)
candidates = universe.as_of(T)                # 생존편향 없음
```
