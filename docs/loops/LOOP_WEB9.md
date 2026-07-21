# LOOP_WEB9 — 키 필수화 + 입력 페이지 극단적 정리

## 프로젝트 (확인)
`동종업계탐색기_클로드` (PeerLens / peer-selection). app.py·templates. ★ DartLens 참조 지시면 다른 프로젝트 — 중단.

## 의미
/key·/search 를 극도로 깔끔하게. 키 필수화, 부수 설명 삭제, 기준시점 드롭다운 제거(항상 최신 고정).
★ 표시·플로우 정리만. 엔진·채점기·데이터·결과 로직 무변경. Web-8 디자인 시스템 유지.

## PART A. /key — 키 필수 + 정리
- A-1 OpenDART API 키 필수: 빈 값이면 /search 로 못 넘어감(차단). "다음" 눌렀을 때 비어있으면
  진행 안 되고 입력창에 조용히 표시(과한 에러 X). 라벨 "(선택)" 제거 → 필수 반영.
- A-2 부수 설명 전부 삭제: 상단 문구·보안 안내 박스(자물쇠)·긴 placeholder 삭제. placeholder="40자리 인증키".
- A-3 남기는 것: 제목 "OpenDART API 키" · 입력창 하나 · 차콜 "다음" · "← 처음으로". 그 외 없음.
- A-4 키는 여전히 세션 메모리만 — 파일·로그·디스크·쿠키·서버 저장 0(안내문만 지움, 저장은 그대로 0).
  ★ 키를 GET URL(쿼리스트링)로 절대 넘기지 않음 — dev 서버 access log 에 남을 수 있어 POST 바디로만 전달.

## PART B. /search — 드롭다운 제거 + 정리
- B-1 기준시점(연도) 드롭다운 완전 제거. 항상 최신 스냅샷 자동 사용(사용자 선택 없음).
- B-2 드롭다운 밑 룩어헤드 안내문 삭제. B-3 회사명 밑 안내문 최소화(제거). 상단 lead 도 제거(부정확·군더더기).
- B-4 남기는 것: 제목 "어떤 회사를 볼까요?" · 회사명 입력창(placeholder "예: 오뚜기") · 차콜 "동종기업 찾기" · "← 이전".
- B-5 드롭다운 없이 최신 스냅샷 자동 조회: /query 는 year 파라미터 없으면 기본=최신(_snapshot_year).
  결과 "평가시점"도 그 최신 시점 자동. (엔진·year 로직 무변경 — 화면에서 선택 UI 만 제거.)

## 구현 (표시·라우팅만)
- app.py `search()`: 키 빈 값이면 `key.html`(key_error) 재렌더 + 400 → 진행 차단(V9-1). 키 있으면 search.html.
  키 게이트는 /search(다음 전환)에 둔다. /query 는 최신 year 기본 경로 그대로(변경 0).
- key.html: lead·보안박스·라벨 제거, `required`+placeholder"40자리 인증키"+aria-label, key_error 시 앰버 인라인 안내.
- search.html: lead·회사힌트·연도 select·연도 힌트 제거. 회사명 입력 + hidden 키(POST 전달) + 찾기 + 이전.
- base.html: `.field input.invalid`(앰버 테두리)·`.field-msg`(앰버 소문구) 추가. (초록·빨강 없음.)

## 유지/금지
유지: Web-8 디자인(warm near-white·차콜·앰버·Pretendard·PeerLens), 3페이지 라우팅, 결과 로직·엔진·데이터·스냅샷, 순위·유사도 원본.
금지: 엔진·채점기·데이터·결과 로직 변경 / 키를 파일·로그·디스크·GET URL 저장 / 초록·빨강·코랄 / 카드 왼쪽선·회색꽉찬배경 / 다른 프로젝트 파일.

## 완료 조건 V9-1~V9-14
키필수: V9-1 키 없이 /search 못 넘어감 · V9-2 "(선택)" 제거 · V9-3 상단 설명 삭제 · V9-4 보안박스 삭제 ·
  V9-5 /key=제목+입력+다음+처음으로만 · V9-6 키 세션만·저장0.
드롭다운제거: V9-7 연도 드롭다운 완전 제거 · V9-8 룩어헤드 안내문 삭제 · V9-9 회사명 안내 최소화 ·
  V9-10 /search=제목+회사명+찾기+이전만 · V9-11 드롭다운 없이 최신 스냅샷 자동 조회·결과 정상.
불변: V9-12 Web-8 디자인·엔진·데이터·결과 로직 무변경(git) · V9-13 3페이지 라우팅·순위무조작·holdout0 · V9-14 다른 프로젝트 미변경.

## 상태
완료 — V9-1~V9-14 충족.
- 수정: `app.py`(search 라우트에 키 필수 게이트: 빈 값→key.html key_error+400),
  `templates/key.html`(lead·보안박스·라벨·"(선택)" 삭제, `required`+placeholder"40자리 인증키"+aria-label,
  key_error 시 앰버 인라인 안내), `templates/search.html`(lead·회사힌트·연도 select·연도 힌트 삭제),
  `templates/base.html`(`.field input.invalid` 앰버 테두리·`.field-msg` 앰버 소문구 추가).
- 실측: 빈 키+다음 → HTML5 required 로 URL 그대로(/key) 차단 + required 우회 시 서버가 key.html 재렌더
  (.field-msg "OpenDART API 키를 입력하세요.", 앰버). /search select·#year 0개(드롭다운 제거). 회사 조회
  결과 평가시점 2025-05-15(최신 자동)·peer 10행 정상.
- 불변(git): engines/·scoring/·scripts/·config/·data/·runs/·ORACLE·DECISIONS 무변경. web_engine.py 는
  Web-7 변경분(year)일 뿐 Web-9 미수정. 키는 POST 바디로만 전달 — 파일·로그·디스크·쿠키·os.environ·GET URL 저장 0.
- 색: 차단 상태 앰버(테두리 #d9a441, 문구 #854f0b) — 초록·빨강·코랄 0. 카드 왼쪽선·회색꽉찬배경 0.
</content>
