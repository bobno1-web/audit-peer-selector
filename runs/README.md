루프 1회 = 폴더 1개. 결과가 여기 쌓인다.

## 산출물 git 정책
`runs/<날짜>_loop<N>_<엔진명>/` 안에서:
- `config.yaml`   → git에 남긴다 (어떤 설정으로 돌렸나).
- `scores.json`   → **git에 남긴다 (몇 점이었나). ★ 필수.**
- `peers.parquet` → git에서 뺀다 (무겁다). `.gitignore`가 `runs/**/*.parquet`, `runs/**/*.csv`를 제외한다.

이유: 점수 이력은 코드보다 중요하다. 코드는 다시 짤 수 있지만
"그때 몇 점이었는지"는 다시 만들 수 없다.
