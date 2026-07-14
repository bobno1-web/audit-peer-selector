"""pit — Point-in-Time 데이터 접근 계층.

★ 엔진은 오직 `as_of(date)` 로만 데이터에 접근한다(LOOP_0F C-2).
   미래(rcept_dt > date) 정보는 이 계층에서 물리적으로 걸러진다.
"""
from .reader import as_of, pit_violations, Snapshot, EVAL_YEARS  # noqa: F401
