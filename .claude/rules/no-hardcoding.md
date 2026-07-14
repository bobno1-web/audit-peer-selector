# 규칙: 하드코딩 금지 (no-hardcoding)

## 무엇이 금지인가
- 종목코드·회사명 문자열 리터럴
- 임의 임계값 상수 (매출 ±30%, 시총 0.5~2배 등)
- 특정 산업·기업만을 위한 예외 분기

상수가 필요하면 `config/`로 빼거나 데이터에서 학습한다.

## 왜 위험한가
하드코딩된 값은 특정 데이터에 과적합된 "커닝"이다.
다른 시점·다른 종목에 일반화되지 않고, 룩어헤드·생존편향의 통로가 된다.
임계값으로 후보를 거르면 필터 금지 규칙까지 함께 위반한다.

## 위반 예시
```python
# BAD: 종목코드 리터럴로 특별취급
if ticker == "005930":                 # 삼성전자
    weight *= 2

# BAD: 매직넘버 임계값으로 후보 거르기
peers = [p for p in cands if 0.7 < p.mktcap / target.mktcap < 2.0]

# BAD: 회사명 예외 분기
if name == "카카오":
    weight *= 1.5
```

## 올바른 예시
```python
# GOOD: 임계값은 config에서
band = cfg["mktcap_band"]              # 설정에서 온 값

# GOOD: 상수는 데이터에서 유도
band = derive_band(universe.as_of(T))

# GOOD: 전 종목을 피처로 점수화 (거르지 않음)
scores = score_all(cands, target, cfg)
```
