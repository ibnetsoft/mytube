# 무협 웹툰 작업 인계 — 2026-11-04

다른 컴퓨터의 Codex는 이 문서와 [회차 완료·재개 계약](WUXIA_SERIES_DELIVERY.md), 저장소 루트의 `AGENTS.md`를 먼저 읽는다. 아래 2026-11-04 기준 「나 혼자 무공을 진화시킨다」 **1·2화는 유저웹 등록 및 DB 재조회까지 완료**됐다. 두 회차를 새로 만들거나 재등록하지 않는다.

## 2026-11-06 추가: 재작성 3화 등록 완료

최신 3화는 **#3432 「살아 돌아온 짐꾼」**, 20씬·실제 원화49개·발화85구간·편집 그래픽50개다. [3화 인계와 복원](wuxia-handoff/episode-03-rewrite/README.md), [승인 원문](wuxia-drafts/EPISODE_03_REWRITE.md), [품질 기록](wuxia-handoff/episode-03-rewrite/QUALITY_NOTES.md)을 먼저 읽는다. 등록 저장 재조회와 실제 유저웹 큐 표시를 확인했다.

기존 3화 **#3430은 제외 상태를 유지**한다. 되살리거나 새로 등록하지 않는다. 재작성 3화는 이번 회차 안에서 야외 탈출·수레·검문까지 진행하므로 예전 3·4화 은신/탈출 분할 계획을 그대로 적용하지 않는다. 다음 회차는 새 `continuity_out`을 승계한다. 3화 파일은 `output/wuxia-series-rewrite/episode-03`로 복원하며, 아래 기존 복원기는 1·2화용이다.

## 현재 완료 상태

| 항목 | 1화 | 2화 |
|---|---|---|
| 회차 제목 | 버려진 짐꾼 | 돌아오는 검 |
| 유저웹 주제 ID | **3428** | **3429** |
| 장면 / 실제 상태 원화 | 26 / 79장 | 24 / 48장 |
| 상세 캐릭터 시트 | 5장 | 기존 인물 3장 재사용 |
| 편집 가능한 말풍선·타이포 | 51개 | 35개 |
| 태국어 검토 번역 | 87블록 | 48블록 |
| 제목·디스크립션·썸네일 | 저장 완료, 편집 글자 3개 | 저장 완료, 편집 글자 3개 |
| 등록 확인 | 정확한 DB 재조회 일치, 웹 준비 판정 true | 정확한 DB 재조회 일치, 웹 준비 판정 true |

- 유저웹: <https://studio.airing.work/std?tab=topics>
- 2화 등록 시각: `2026-11-04T09:13:46.498033+00:00` (한국 시각 18:13).
- 2화 등록 식별자: `8ca1fba036b79f5524e9bd75550613a0`.
- 2화 등록 대본 SHA-256: `9ea3350b958343421f86d1463a343be5e429e131d7d4c657dd9e752fa2b8c41b`.
- 2화는 실제 원화 48장, 보정 원화 17장, 검증된 업로드 자산 총 57개다. 17개 보정 전 원본은 원래 PC의 `episode-02/revisions/`에 보존했다.
- 검증은 DB와 웹의 실제 `isPreparedUserTopic` / `hasReadySceneMediaPrompts` 코드로 수행했다. 로그인된 유저웹 카드 화면을 직접 열람했다고 보고하지 않는다.
- 최종 음성 녹음·AE 실행 완료나 YouTube 업로드를 의미하지 않는다. 해당 단계는 이번 회차 등록 납품과 별도다. 이를 이유로 승인된 회차 제작을 중단하거나 PC 환경 설명을 반복하지 않는다.

## 다른 컴퓨터에서 가져오는 순서

저장소: <https://github.com/ibnetsoft/mytube>. 원래 PC 경로는 `C:\Users\kimse\mytube`였으며 새 PC는 다른 경로를 사용해도 된다.

```powershell
git clone https://github.com/ibnetsoft/mytube.git
cd mytube
# 기존 복제본이면 로컬 변경을 보존한 후 git pull --ff-only
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r worker/requirements-script.txt
.\.venv\Scripts\python.exe scripts/restore_wuxia_handoff.py
```

마지막 명령은 인증 없이 Git에 보존한 **대본·세계관·연출·등록 확인서 등 텍스트 원본**을 `output/wuxia-series-rebuild/episode-01`, `episode-02`로 복원한다. 68개 파일의 스냅샷 SHA-256을 확인한다. 원화 파일까지 복원하려면 아래 인증 설정 뒤 실행한다.

```powershell
.\.venv\Scripts\python.exe scripts/restore_wuxia_handoff.py --assets --readback
.\.venv\Scripts\python.exe scripts/wuxia_episode_status.py --episode-dir output/wuxia-series-rebuild/episode-02 --preflight
```

- `--assets`: 각 회차의 `asset-upload-receipts.json`에 있는 실제 GCS 파일을 내려받고 SHA-256을 검증한다. 기존 동일 파일은 재사용한다.
- `--readback`: 지정된 주제 ID만 읽고 등록 대본 지문을 확인해 현재 DB 재조회 원본을 보존한다. 주제 생성·수정·재등록은 하지 않는다.
- 기존 파일이 스냅샷과 다르면 덮어쓰지 않고 충돌을 알린다. 기존 작업을 따로 보존한 뒤 필요한 파일만 복원한다.
- `--episode 2` 옵션으로 2화만 복원할 수도 있다. 단, 다음 회차 이미지 참조에는 1화 원화도 필요하므로 처음에는 양쪽 복원을 권장한다.
- 원래 PC의 `.venv`, `.env`, 계정 비밀키, 임시 CLI 로그, 보정 전 원화 바이너리 및 QA 스크린샷은 Git에 넣지 않았다. `.env.example` 삭제는 기존 사용자 변경이어서 이번 인계 커밋에 포함하지 않는다.

### 인증·실행 환경

- 이 제작물의 DB는 Supabase **`giorysjpgxzdypbmxwmx` (pica)**다. 이름이 비슷한 다른 AIR 프로젝트로 바꾸지 않는다.
- `worker/worker_config.py`와 `worker/script_worker_store.py`가 읽는 환경 변수에 해당 프로젝트의 URL·승인된 서비스 인증을 새 컴퓨터에서 설정한다. 키는 승인된 비밀 저장소로 전달하고 Git 문서에 쓰지 않는다.
- GCS 계정 설정은 위 DB의 `global_settings`에서 기존 worker 경로로 읽는다. 키 이름은 `sys_api_gcs_bucket_name`, `sys_api_gcs_project_id`, `sys_api_gcs_client_email`, `sys_api_gcs_private_key`다. 실제 값은 출력하거나 문서화하지 않는다.
- 저장된 `/api/std/assets/gcs-file?...` 값은 인증이 필요한 웹 상대 경로다. 공개 이미지 URL로 오해하지 않는다. 복원기는 서비스 계정으로 GCS 원본을 읽는다.
- 새 대본과 검토 번역은 **로컬 Codex CLI worker**를 사용한다. 새 컴퓨터에서도 Codex CLI 로그인과 실행 경로를 확인한다. 검토 번역을 Gemini/OpenAI 모델 API로 우회하지 않는다.
- Node.js가 필요하다. 웹 계약 검사·썸네일 로컬 렌더가 필요하면 다음 의존성을 설치한다. 아래 도구 폴더는 Git 대상이 아니다.

```powershell
npm install --prefix output/wuxia-series-rebuild/episode-01/packaging/tooling typescript@5.9.3 @napi-rs/canvas playwright
```

스냅샷의 `web_contract.cjs`는 다른 PC에서도 위 프로젝트 내부 도구 폴더를 사용하도록 수정했다. 이전 QA 도구 중 `verify_preview.cjs`의 Playwright 경로는 원래 Codex 런타임 절대 경로가 남아 있으므로 새 PC에서는 위 설치 폴더로 바꿔 사용한다. `build_motion_board.py`는 저장소 폰트를 복사해 프리뷰 HTML을 다시 만들 수 있다. 과거 QA 스크린샷이 없다는 이유로 원화를 다시 생성하지 않는다.

## Git에 보존한 실제 이어받기 자료

[`docs/wuxia-handoff/`](wuxia-handoff/)는 계정 비밀이 없는 텍스트 스냅샷이다. 실행은 원래 폴더 구조로 복원한 뒤 한다.

- `episode-01/script-final.json`, `episode-02/script-final.json`: 최종 대본, 대사 블록, 상태별 그림 설명·프롬프트, 캐릭터, 설정과 입출력 연속성.
- 각 `visual-bible.json`: 상세 외형, 석실 구조, 환경·스타일 기준. 다음 회차는 승인된 얼굴을 유지한다.
- `image-generation-jobs.json`, `image-inventory.json`: 실제 자산 ID·참조·원문 프롬프트와 지문. 복원기가 작업/참조 경로를 새 저장소 위치에 맞춘다.
- `direction/ae-scene-package.json`, `build_ae_preview.jsx`, `sound-and-music-direction.json`: 편집 가능한 장면·효과·음악 프롬프트.
- `direction/visual-layout.json`, `visual-reviews.json`, `quality-notes.md`, `preview-verification.json`: 실제 검수 및 배치 근거. 1화는 당시 생성한 대응 파일만 포함한다.
- `packaging/publish-metadata.json`, `thumbnail-design.json`, `review-translation-th.json`: 제목·설명·편집 썸네일·검토 번역.
- `packaging/registration-receipt.json`, `asset-upload-receipts.json`: 등록 사실과 원격 원화/시트/썸네일/연출 자산 복원 정보.
- 불변 `script-final.json` 안의 등록 전 상태 값보다 등록 확인서와 재조회 결과가 우선한다. 최신 `script-summary.json`과 `workflow-state.json`은 등록 완료로 맞췄다.

원화·캐릭터 시트·썸네일 바이너리는 위 확인서의 원격 GCS 객체에 있다. Git 문서에 경로만 적고 로컬 바이너리를 누락한 것이 아니라, 복원 스크립트와 지문을 함께 보존한 것이다. 원격 저장소 읽기 권한이 있는 환경에서 복원한다. 과거 CLI 원시 로그와 2화 보정 전 이미지 17장은 감사용 로컬 자료이며 다음 회차 제작의 필수 원본은 최종 원화다.

## 확정한 제작 방식

- 50화 규모의 **오리지널** 무협 성장 서사. 낮은 신분에서 관찰·실패·적응으로 성장하는 재미를 목표로 한다. 기존 작품의 인물·고유 설정·줄거리를 복제하지 않는다.
- 한국어, 가상의 전근대 중국풍 강호. 문파는 옛 무공과 괴물이 봉인된 ‘무경’의 공략권을 독점한다.
- 서진: 내공을 모으지 못하는 짐꾼. 자신에게만 보이는 ‘진화록’은 관찰과 불완전 동작의 기록이며 즉각적인 무적 보상이 아니다.
- `wuxia_webtoon`: 깨끗한 선·선명한 채색·성인 얼굴. 저장된 스타일 기준과 상세 캐릭터 시트를 재사용한다.
- 영상클립 0. 정지 원화의 상태 전환과 AE 효과 중심. 고정 카메라 기본, 느린 줌 금지. 가짜 분리 레이어·복제 깊이 효과 금지.
- 나레이션을 그대로 자막으로 붙이지 않는다. 상황에 맞는 반응·속말·효과음을 선택해 편집 가능한 타이포그래피로 디자인한다. 반드시 나레이션에 있는 단어일 필요는 없다. 실제 대사는 음성과 맞는 말풍선으로 별도 처리한다.
- 글자를 원화에 구워 넣지 않는다. 음악은 프롬프트만 작성한다.
- 확인된 자료에는 1·2화 최종본과 50화 규모라는 확정 방향이 있다. **50화 전체의 확정 상세 회차표를 별도로 찾았다고 꾸며 쓰지 않는다.** 이후 전개는 승인된 대본·세계관과 연속성을 보존해 이어간다.

## 2화 끝에서 이어야 할 연속성

정확한 원문은 [`episode-02/script-final.json`](wuxia-handoff/episode-02/script-final.json)의 `continuity_out`이다.

1. 서진·도겸 모두 서쪽 피신 홈 아래 배수 점검구를 지나 비좁은 관리 통로로 들어왔다. **도겸이 앞, 서진이 뒤**다.
2. 서진은 터진 아랫입술, 왼쪽 옆구리 상처, 오른손 손바닥 출혈을 유지한다. 도겸은 다친 오른쪽 다리를 딛지 못하고 팔과 왼발로 이동한다.
3. 더 짧아지고 휜 기존 단도는 서진의 **오른쪽 허리 칼집**에 있다. 도겸의 물통은 소리 유도용으로 던져 석실에 남겼다. 목도리는 **오른쪽 무릎 아래** 묶여 있으며 목에 다시 생기면 안 된다. 지게·수레도 회수하지 않았다.
4. 석상은 우두머리 하나와 일반 다섯, 총 여섯 모두 건재하다. 손목에 단도를 끼운 시도는 실패했다. 우두머리는 쓰러지지 않았고 돌검도 남아 있다.
5. 동쪽 철문·남쪽 석판은 닫혔으며 봉함은 계속 철문 밖 장호에게 있다. 부상 회복이나 갑작스러운 내공 획득을 넣지 않는다.
6. 서진은 다친 자신의 보폭을 계산해 귀환 동작 때 짧게 피하는 제한적인 경험만 얻었다.
7. 통로 끝 쇠살 틈 밖에 철산문 무사의 철청색 무복 자락과 검은 장화가 보이고, “안에서 쇳소리가 났다. 배수로도 확인해.”라는 명령이 들린다. 다음 위협의 시작이다.

2026-11-04 인계 당시에는 다음 제작 회차가 3화였다. 2026-11-06 재작성 3화는 위 추가 기록대로 #3432에 등록됐으므로 다시 생성하지 않는다. 후속 회차는 재작성 3화의 확정 결말과 상태를 승계한다.

## 중도 종료 방지와 재개 규칙

[WUXIA_SERIES_DELIVERY.md](WUXIA_SERIES_DELIVERY.md)에 원인과 대책을 기록했다. 핵심 원인은 중간 산출물에서 응답을 끝낸 범위 추적 실패, 웹 등록과 후속 렌더의 혼동, 업로드·번역·포장 작업의 늦은 계획, 상태 기록 불일치였다.

- 회차의 승인된 종점: **실제 파일 완성 → 제목·설명·편집 썸네일 → 업로드/해시 검증 → 준비 판정 → 중복·소유권 확인 → 등록 → 정확한 재조회**.
- 대본·원화·프리뷰까지만 하고 “계속할까요”로 끝내지 않는다. 다음 승인된 단계를 수행하면서 진행 상황을 알린다.
- `scripts/wuxia_episode_status.py`: 등록 확인서·대본 지문·장면 수·재조회를 근거로 완료를 판정한다. 프롬프트 목록을 실제 원화로 세지 않는다.
- `scripts/wuxia_image_checkpoint.py`: 자산마다 파일·원본 경로·지문을 저장하고 서로 다른 기존 원화를 자동 덮어쓰지 않는다.
- `worker/codex_content_runner.py`: 단계 입력 JSON을 ASCII 유니코드 이스케이프로 저장해 Windows 도구의 한글 대체문자 오류를 방지했다.
- 번역은 작은 묶음별 체크포인트를 보존한다. 최종 한국어 원문이 같은 번역은 재사용한다.
- 이미지 도구 응답을 한 번에 수십 장 누적하면 표시 용량 한도를 넘을 수 있다. 즉시 자산별로 저장하고 표시 오류와 저장 실패를 구별한다.
- 품질 우려는 사실대로 기록하며 승인된 제작을 이어간다. 취소·소유권·실제 파일 손상은 보존하고 복구한다. 품질 기록을 숨겨 ‘완벽 검수’로 바꾸지 않는다.
- 이 지침과 상태 도구가 다른 PC의 Codex 실행을 저절로 시작시키는 상주 서비스는 아니다. 새 세션에서 이 문서를 읽고 사용자가 승인한 작업을 이어간다.

2화 품질 기록: [quality-notes.md](wuxia-handoff/episode-02/direction/quality-notes.md). 배낭·목도리·물통·단도 보정 17장을 반영했고, 점검구 공간·배경 단차·일부 인물 위치 등의 남은 차이를 기록했다. 실제 음성 시간에 맞춘 최종 동기화 검증과 혼동하지 않는다.

## 검증과 코드 변경

2026-11-04 인계 검증 결과: 아래 테스트 **41개 통과** (제작 관련 38개 + 복원 3개). 새 작업 폴더에서 68개 파일 복원 및 반복 복원도 통과했다., `git diff --check` 통과. 2화 웹 프리뷰는 그래픽 35개 표시, 글자 넘침/누락/브라우저 오류 0, 필요한 한글 폰트 로드 확인.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_wuxia_handoff_restore.py tests/test_wuxia_delivery_state.py tests/test_script_worker_production_guidance.py tests/test_codex_content_runner.py -q
```

함께 보존한 변경: `AGENTS.md`, `worker/script_worker_guidance.py`, `worker/wuxia_delivery_state.py`, `worker/codex_content_runner.py`, 상태/원화 체크포인트 스크립트와 관련 테스트. 유저웹 기능·배포는 변경하지 않았다.

등록 도구는 복원한 `episode-01/packaging/prepare_registration.py`와 `register_topic.py`다. `WUXIA_EPISODE_DIR`로 대상 회차를 지정한다. **기존 1·2화 확인 용도로 `--register`를 실행하지 않는다.** 새 회차의 준비가 끝난 경우에만 사용하며, 동일 식별자·동일 제목 충돌과 소유권을 먼저 확인한다.
