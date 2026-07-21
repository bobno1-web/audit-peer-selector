# LOOP_WEB6 — 웹앱 마무리 (정리 + 데모 예시 + README 반영)

## 프로젝트 (확인)
`동종업계탐색기_클로드` (peer-selection). app.py·engines/similarity·sample_reports.json 있는 그 프로젝트.
★ Streamlit·DartLens·16재무비율·app_flask.py 는 **다른 프로젝트**(재무제표 이상징후) — 건드리지 않음.

## 의미
기능·디자인·최신데이터(Web-5)까지 완료. 마지막 정리: ① 미사용 코드 정리 ② 데모 예시 개선
③ README 웹앱 반영. ★ 표시·문서 계층만. 엔진·채점기·데이터·핵심 화면 디자인 무변경.

## PART 1. 자잘한 정리
- **1-1** app.py 가 index.html 에 넘기지만 안 쓰는 데이터 정리(examples 미사용 전달 등). 죽은 코드만.
- **1-2** 하드코딩 데모 회사명 리터럴 → config 분리. 엔진·랭킹 영향 0(표시 예시 목록일 뿐).

## PART 2. 데모 예시 개선
- **2-1** placeholder·예시를 "peer 깔끔·신뢰등급 높은" 회사로. ★실제 최신 스냅샷에 돌려 확인한 회사만.
  placeholder "예: 강원에너지" → 그 회사로 교체.
- **2-2** CJ제일제당류(업종유사 적은 케이스) 정상 동작 유지 — 정직한 안내.

## PART 3. README 반영 (자매 프로젝트 형식)
- **3-1** README.md·README.en.md 웹앱 섹션: 소개·데모/스크린샷·실행법(start.bat·OpenDART)·"신경 쓴 것"
  (순위 무조작 그룹표시 / 없으면 없다 정직 / 신뢰등급·근거=표현계층 / 확정엔진 최신적용 재학습없음).
- **3-2** 스크린샷 docs/images/ 저장·참조.
- **3-3** ★ 외부제출/평가/면접 언급 0(한/영). 성능 과장 0. 승리조건 미달·상한 0.50 정직.
- **3-4** 돋보기 브랜드 마크 README 반영(favicon/로고 언급 가능).

## 금지
엔진·채점기·데이터·핵심 화면 디자인 변경 / 순위·유사도 조작 / 최신데이터 재학습 /
외부제출·평가·면접 언급·성능과장 / 지어낸 필드 / 왼쪽선·회색배경 / 다른 프로젝트 파일.

## 완료 조건 W6-1~W6-16
정리: W6-1 미사용 전달 정리(기능0) · W6-2 데모명 config 분리(엔진0).
데모: W6-3 placeholder 실측 교체 · W6-4 실측 확인 · W6-5 CJ류 정직 유지.
README: W6-6 md 웹앱 섹션 · W6-7 en 동일 · W6-8 스크린샷 삽입 · W6-9 실행법·키 정확 ·
W6-10 신경쓴것 정직성 · W6-11 외부제출 언급0(grep) · W6-12 성능과장0·상한유지 · W6-13 돋보기 마크.
불변: W6-14 엔진·채점기·데이터·핵심디자인 미변경 · W6-15 순위·점수 무조작·재학습0·키미저장·holdout재개봉0 ·
W6-16 다른 프로젝트 미변경.

## 상태
완료 — W6-1~W6-16 충족.
- 정리: `app.py` 죽은 examples 전달·`_example_index`·`EXAMPLE_ORDER` 제거(스모크테스트 통과), 데모 회사명 →
  `config/web_examples.json`. 살아있는 로직·`/example` 라우트 무영향.
- 데모: placeholder `강원에너지`→`오뚜기`(config 구동). 실측(2025): 오뚜기 HIGH·섹션1 8/10 식품 peer·rank1 농심 0.72.
  CJ ENM(업종유사 0) 정직 안내 유지.
- README: `README.md`·`README.en.md` 웹앱 섹션(소개·▶️데모 스샷 4장·start.bat 실행법·정직성·돋보기 마크).
  스크린샷 `docs/images/web_{landing,result_ottogi,result_ottogi_expanded,honest_notice}.png`.
- 불변(해시): 엔진(build_report)·weights·holdout_freeze·thresholds·default.yaml·`templates/result.html` 미변경.
  외부제출/평가/면접 언급 0(한/영 grep), 성능 과장 0(상한 0.50 정직), 재학습 0·키 미저장·holdout 재개봉 0.
  다른 프로젝트(DartLens) 파일 미변경.
</content>
</invoke>
