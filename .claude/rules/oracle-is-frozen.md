# 규칙: 채점기 동결 (oracle-is-frozen)

## 무엇이 금지인가
`docs/ORACLE.md`의 채점 절차·유효성 규칙·최종점수 정의·`scores.json` 스키마를
"점수가 안 나온다"는 이유로 조용히 바꾸는 것.

## 왜 위험한가
채점기를 결과에 맞춰 고치면 루프 간 점수를 비교할 수 없다.
이 프로젝트의 전부가 "루프마다 점수가 올랐나"인데,
자를 매번 바꾸면 측정 자체가 무의미해진다.

## 위반 예시
```python
# BAD: 점수가 나쁘자 조용히 페널티를 낮춤 (ORACLE와 불일치)
penalty = 0.2                 # 원래는 데이터 상위 분위수에서 유도해야 함

# BAD: 어려운 케이스를 채점에서 빼서 평균을 올림
cases = [c for c in cases if c.n_valid_peers >= 3]   # FAIL을 제외해버림
```

## 올바른 예시
```python
# GOOD: ORACLE 명세 그대로 사용
penalty = cfg["penalty_ape"]  # 데이터에서 유도된 값
cases = all_cases             # FAIL은 제외가 아니라 페널티로 포함
```

변경이 정당하다면: `docs/DECISIONS.md`에 이유와 변경 전/후 점수를 남긴 뒤에만 수정한다.
