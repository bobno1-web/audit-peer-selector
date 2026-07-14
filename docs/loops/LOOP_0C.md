# LOOP 0-C — 계획 확정 + 데이터 타당성 조사 (소급 복원)

> **소급 복원**: 근거 `docs/LOOP_LOG.md` + 현재 산출물. 근거 불충분 항목은 `[복원불가]`.

## 목적
목적 변경(밸류에이션 → 감사)에 따라 채점기 교체, 비상장 데이터 존재를 표본으로 확인.

## 완료조건 (복원)
- C1. ORACLE.md 재무비율 기반 교체(시가총액 언급 0).
- C2. ORACLE.md 정보 차단벽(엔진 허용/금지 입력).
- C3. ORACLE.md 상수 유도 규칙(`benchmarks/dev`만).
- C4. DECISIONS.md D-001[폐기]/D-005[신규].
- C5. `docs/PLAN.md`(제품정의/확정사항/루프계약/승리조건/종료조건).
- C6. PLAN 승리조건 숫자(20% 개선).
- C7. PLAN 미국 [확정 — 영구 제외].
- C8. `docs/DATA_FEASIBILITY.md`.
- C9. 비상장 재무 확보 성공률 실측 숫자.
- C10. 모든 항목 확인됨/확인 안 됨 표기.
- C11. `data/pit` features/targets/universe 구조.
- C12. targets/README 엔진 접근 금지 명시.
- C13. `.claude/hooks/check_targets_access.py`.
- C14. `company_names.txt` + 훅 코드 회사명 리터럴 0.
- C15. `tests/test_hooks.py` 통과.
- C16. API 키 미노출.
- C17. 엔진/채점기 로직 0줄.
