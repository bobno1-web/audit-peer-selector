# OUTPUT_FORMAT — 산출물 스키마 (Loop 8)

검증된 L6 엔진의 출력을 감사 실무에 쓰기 좋게 정교화한 **표현 계층**의 형식. ★ 예측 오차 미변경
(엔진/채점기 불변; `build_report.py` 는 그 출력을 읽어 표현만 한다). 상수는 config·dev 유도.
생성기: `scripts/build_report.py`. 산출: `runs/2026-07-16_loop8/{sample_reports.json, peer_report.csv, thresholds.json}`.

## 범용 JSON 스키마 (기업/시점 1건)
```json
{
  "target": "<corp_code>", "as_of": "YYYY-05-15",
  "peer_confidence": "HIGH | MEDIUM | LOW",   // peer 그룹 신뢰도(응집도 삼분위)
  "peer_cohesion": 0.53,                        // top-k 유사도 평균(엔진 유사도; 채점비율 미사용)
  "peers": [
    { "rank": 1, "peer_code": "<corp_code>", "similarity": 0.568,
      "rationale": { "industry":0.107,"scale":0.193,"mktcap":0.129,"text":0.129,"growth":0.010 } }
    // rationale = 축별 유사도 기여(w_c·sim_c). 합 ≈ similarity. "왜 이 회사가 peer 인가".
  ],
  "ratios": [
    { "ratio":"매출총이익률", "peer_median":0.208, "target_actual":0.112,
      "deviation_pct":85.2, "direction":"하위", "check_needed":false,
      "confidence":"HIGH", "valid_peers":9, "comparable":true, "note":"" }
    // peer_median = 예측치(peer 비율 중앙값). deviation_pct = |타겟−peer중앙값|/|타겟|(채점기 편차 재활용).
    // check_needed = 편차가 dev 상위분위수 이상(확인 필요 지점). comparable=false → 비교 부적합(손익분기 근처).
  ]
}
```

## 범용 CSV (peer_report.csv)
`target, as_of, peer_confidence, peer_cohesion, rank, peer_code, similarity, why_industry, why_scale,
why_mktcap, why_text, why_growth` — 기업코드·순위·유사도·신뢰등급·축별 근거. 특정 비교 툴 형식은
**미확정**(사용자 확인 대기)이라, 이 범용 형식을 두고 **나중에 특정 툴 스키마로 매핑**한다.

## 필드 유도·의미
| 필드 | 유도 | ★ 정보 차단벽 |
|---|---|---|
| peer_confidence | 응집도(top-k 유사도 평균)의 **dev 삼분위**(q33/q67, config) | 유사도=엔진 허용 피처만. **채점비율 실제값 미사용** |
| peer_cohesion | top-k peer 유사도 평균 | 엔진 유사도 |
| rationale(축별) | w_c·sim_c (가중치×축 유사도) | 엔진 허용 피처(산업·규모·시총·텍스트·성장) |
| peer_median | peer 비율 중앙값(=예측치) | 채점기 산출(감사 이중용도) |
| deviation_pct / check_needed | \|타겟−예측\|/\|타겟\| 및 **dev 상위분위수** 초과 여부 | 채점기가 이미 계산하는 편차 **재활용**(새 계산 아님) |
| confidence(비율별) | 응집도 등급 + **예측불가(비교부적합)·유효peer<3 → LOW** | 예측불가=\|분자\|/총자산(구조), 채점비율 값 아님 |
| comparable | \|비율분자\|/총자산 ≥ τ_r(dev) | 원천 재무구조(D-027), 채점비율 값 아님 |

## dev 유도 임계값(thresholds.json, 예시 실측)
- peer_cohesion 삼분위: q33 = **0.4312**, q67 = **0.5233** (LOW<0.4312≤MEDIUM<0.5233≤HIGH).
- 확인필요지점 편차 임계: dev 편차 상위 10% = **187%**.
- ★ **주의(정직):** 이 방식의 예측이 정밀하지 않아(median APE ≈0.48) dev 편차 분포의 꼬리가 길다 →
  "확인 필요" 임계가 **187%**로 높다. 즉 **극단적 이탈만** 표시된다. 이 표시는 "점 예측이 틀렸다"가
  아니라 "peer 대비 유난히 멀다 = 사람이 볼 값어치"라는 **약한 신호**로 쓴다(강한 red-flag 아님).

## 사용 원칙 (FINAL_REPORT.md 신뢰범위와 일관)
- **점 예측이 아니라 범위·순위·이상탐지 도구.** peer_median 을 정답으로 쓰지 말고 peer 분포 안에서
  타겟 위치를 본다. peer_confidence=LOW / comparable=false 는 그 비교를 신뢰하지 말라는 표시.
- 신뢰등급·근거·확인필요지점은 **엔진 성능을 바꾸지 않는다**(L6 dev APE 0.4794 불변, 코드로 확인).
