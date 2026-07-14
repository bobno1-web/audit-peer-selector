# LOOP 0-B — 맥락(문서·규칙·훅) (소급 복원)

> **소급 복원**: 근거 `docs/LOOP_LOG.md` + 현재 산출물. 근거 불충분 항목은 `[복원불가]`.

## 목적
"무엇을 하면 반칙인가"를 문서·규칙·훅으로 고정. 코드는 훅(검사용)만.

## 완료조건 (복원)
- C1. `engines/__init__.py`, `scoring/__init__.py` 존재.
- C2. `.gitignore` 지정 내용 반영.
- C3. `runs/README.md`에 scores.json git 보존 정책.
- C4. `CLAUDE.md` 절대규칙 5개.
- C5. `docs/ORACLE.md` 채점 명세 전 섹션. ※ 당시 명세는 **시가총액 오차 기반**(PER·EV/EBITDA·PSR); Loop 0-C에서 재무비율로 교체됨.
- C6. ORACLE.md scores.json 스키마.
- C7. `docs/VERIFY.md` 4규칙.
- C8. `docs/DECISIONS.md` D-001/002/003 + 태그.
- C9. `docs/LOOP_LOG.md` Loop 0-A 기록.
- C10. `.claude/rules/` 4종(각 위반/올바른 예시 포함).
- C11. `.claude/hooks/` 2종(표준 라이브러리만).
- C12. 엔진/채점 로직 `.py` 0개(훅 제외).
- C13. 지시 외 파일 추가 0.
