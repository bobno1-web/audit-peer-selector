# 규칙: 거짓 출처 금지 (no-false-provenance)

## 무엇이 금지인가
산출물(scores.json·showdown·문서 등)의 **상태 라벨**이 **실제 파일 상태와 어긋나는 것.**
- 예: `targets: "corrected"` 라 써놓고 실제 target 데이터는 미교정.
- 예: `median@k10` 이라 써놓고 실제 peers.parquet 은 k=5(stale).
- 예: 작업 노트("regen/swap 미실행")와 산출물 라벨("corrected")이 **모순**.

**작업이 미완이면 '완료' 라벨을 붙이지 않는다.** 라벨과 실제가 모순되면 **그 루프는 미완**이다.

## 왜 위험한가
라벨이 실제와 묶여 있지 않으면, 코드는 고쳤으나 데이터에 미반영인 채 "corrected" 라벨만 달려
**틀린 결과가 맞는 것처럼 보고**된다. 특히 데이터층(data/pit)이 gitignore 라 커밋 저장소만으로는
라벨을 독립 검증할 수 없으면, 검증방도 즉시 못 잡는다. (Loop 6 에서 실제 발생: regen/swap 을 하고도
결과 파일 라벨의 **출처가 데이터에 결속되지 않아** 검증 불가 상태로 커밋됐다.)

## 규칙 (코드로 강제)
1. **라벨은 실제에 결속(stamp).** 결과 생성기는 실제 사용한 데이터의 **콘텐츠 지문**(write 독립
   `provenance.combined_targets_digest`)과 **실제 k**(`provenance.peers_k`)를 결과 JSON 에 스탬프한다.
2. **라벨-실제 일치 강제.** `tests/test_provenance_integrity.py` 가 스탬프 지문을 **라이브 데이터에서
   재계산**해 대조하고(불일치→FAIL), 라벨 k 를 **peers.parquet 실제 peer 수**와 대조한다(stale k→FAIL).
   음성(위조 지문·stale k) 탐지 테스트를 **항상** 돌려 방어가 작동함을 실증한다.
3. **gitignore 데이터의 출처는 매니페스트로 커밋.** target 데이터가 커밋 안 되면, 그 **콘텐츠 지문과
   변경 집계**(`runs/…/provenance.json`)를 커밋해 검증방이 재생성 후 지문 비교로 독립 확인하게 한다.
4. **미완이면 미완 라벨.** 재생성·스왑·재채점 중 하나라도 실제 실행 안 됐으면 'corrected/완료' 금지.

## 기계적 강제
- `scripts/provenance.py`: write-독립 콘텐츠 해시 + 검증 헬퍼.
- `scripts/loop6_finalize.py`·`loop6_showdown.py`: 결과에 지문·실제 k 스탬프 + **라벨≠실제면 assert 중단.**
- `tests/test_provenance_integrity.py`: 양성(커밋 결과↔라이브 일치) + 음성(위조 탐지) 강제.

## 근거 (실제 사고)
- **Loop 6**: 매출채권 매핑 버그를 코드로 고치고 regen/swap 도 실행했으나, 결과 파일의 "corrected"
  라벨이 **실제 데이터 지문에 결속되지 않아** 커밋 저장소만으로는 교정 여부를 확인할 수 없었다. 또
  `regen_summary.json` 이 diff 카운터 버그로 **총자산 11,775 변경**이라는 거짓 수치를 담았다(실제 0).
  → 이 규칙과 provenance 스탬프·매니페스트·테스트로 재발을 코드가 막는다.
