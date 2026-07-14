# 규칙: 엔진–채점기 분리 (engine-scoring-separation)

## 무엇이 금지인가
`engines/` 와 `scoring/` 이 서로를 import하는 것.
둘의 유일한 접점은 `runs/<run>/peers.parquet` 파일이다.

## 왜 위험한가
엔진이 채점기 내부(정답 배수, 페널티, 케이스 목록)를 읽을 수 있으면
시험지를 훔쳐보는 것과 같다. 엔진이 채점 로직에 맞춰 커닝하게 된다.
파일 경계로 분리해야 "엔진은 peer만 낸다 / 채점기는 그 파일을 읽어 점수만 낸다"가 강제된다.

## 위반 예시
```python
# BAD: 엔진이 채점기를 import (정답 훔쳐보기)
# engines/similarity/run.py
from scoring.oracle import target_multiples

# BAD: 채점기가 엔진을 import
# scoring/report/make.py
from engines.baseline import pick_peers
```

## 올바른 예시
```python
# GOOD: 엔진은 결과를 파일로만 내보낸다
# engines/baseline/run.py
peers.to_parquet(run_dir / "peers.parquet")

# GOOD: 채점기는 그 파일을 읽을 뿐, 엔진을 import하지 않는다
# scoring/report/make.py
peers = read_parquet(run_dir / "peers.parquet")
```
