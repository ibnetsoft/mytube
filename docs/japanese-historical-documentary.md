# 일본 역사 다큐멘터리 제작

웹의 토픽 등록에서 `다큐멘터리 · 수묵화/우키요에`를 선택한다. 일본어·일본 배경·30분·기본 연출로 제작한다. 줄거리에는 인물, 시기, 핵심 역사 질문을 적는다. 선택 사항인 사료 입력란에는 박물관·문서관·학술 출처 URL과 확인할 쟁점, 발췌를 적을 수 있다. 이 입력 자체는 검증된 사실로 취급하지 않는다.

## 실행 경로

`auth-web/lib/topicSubmission.ts` → `user_topic_submissions` → `worker/web_topic_submissions.py` → `worker/codex_local_workflow.py` → `CodexStagedContentRunner.generate`.

`00_documentary_research`만 로컬 Codex CLI의 `--search`를 사용한다. 원사료·공공기관·학술 원문을 열람하고 발췌·URL·발행기관을 수집한다. 최소 두 개의 서로 다른 출처가 필요하다. 부족한 핵심 근거는 한 차례 추가 조사하며, 여전히 부족하면 대본 작성을 중단한다. 주변 쟁점 중 확인하지 못한 것은 `historical_excluded_claims`에 보관해 서사에서 제외한다. 다른 생성·검수 단계와 자막 번역에는 검색을 활성화하지 않는다.

일반 창작의 반전·악역·가족 갈등·변화된 마지막 행동을 억지로 만들라는 지시보다 다큐 계약이 우선한다. 사실·이설·해석은 일본어 나레이션에서도 구분한다. 최종 청취 수정 이후 `02j_documentary_evidence_review`가 모든 장면의 사실 주장을 출처와 독립적으로 대조한다. 장면별 인용 원문 및 대본 구절은 저장된 자료와 정확히 일치해야 하며, 최종 대본 해시와 출처 해시를 저장한다. 대본 수리로 문장이나 자료가 바뀌면 이전 합격을 재사용하지 않는다.

자료와 검수표는 `structure.historical_sources`, `structure.historical_excluded_claims`, `structure.historical_evidence_review`에 저장된다. 수묵화·우키요에 공통 화풍은 인물 참조·씬 이미지·영상·썸네일 프롬프트에 적용한다. 게시 메타데이터가 생성되는 경우 출처 URL 및 이미지 재현 고지를 설명에 포함한다.

## 한계와 운영

인용 일치 검사는 출처의 진위나 해석의 정확성을 수학적으로 증명하지 않는다. 출처의 권위·맥락과 모든 사실 주장에 대한 독립 검수를 함께 요구한다. 생성 이미지와 완성 나레이션, 최종 렌더의 실제 검수는 별도로 수행한다. 자료가 충분하다는 이유만으로 영상 출력을 승인하지 않는다.

기존 다큐를 수리할 때 저장된 출처가 없다면 새 자료를 확보한 후 다시 수리해야 한다. 출처 없는 과거 대본에 새 검수 합격을 임의로 부여하지 않는다. 실행 중 워커는 파이썬 모듈을 유지하므로 유휴 상태에서 재시작해야 새 경로가 적용된다. 웹 배포만으로 로컬 워커 코드가 교체되지는 않는다.

검증: `python -m pytest tests/test_documentary_execution.py tests/test_japanese_historical_documentary.py tests/test_japanese_domestic_drama.py tests/test_web_topic_submissions.py tests/test_codex_content_runner.py -q`, `auth-web`에서 `node tests/topic-submissions.cjs`, `npm run build`.
