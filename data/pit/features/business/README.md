# features/business — 사업내용 텍스트 (Loop 2 지연)

엔진 허용 입력 '사업내용 텍스트'. 원천 = 사업보고서 '사업의 내용' 섹션(`document.xml`).

- **전량 추출은 Loop 2(similarity 엔진)로 지연.** 이유: 원문 ZIP 다운로드가 시점×유니버스
  수만 건이라 무겁고, baseline(Loop 1)은 산업분류·규모만으로 동작한다.
- **타당성은 이미 실측됨**: 0-E `SPIKE_UNLISTED` 에서 감사보고서 원문 텍스트 추출 96.7%.
  같은 `audit_parser.fetch_doc_text(rcept_no)` 로 상장사 사업보고서에도 적용 가능.
- 그때 '사업의 내용' 섹션만 정밀 추출하는 파서를 만든다(현재 파이프라인은 flat 발췌까지 실증).
