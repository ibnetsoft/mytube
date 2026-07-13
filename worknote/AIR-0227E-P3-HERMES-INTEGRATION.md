# AIR-0227E-P3 — 실제 Hermes Worker 통합 및 AIRWorker 단일 실행파일 완성

## Task ID
`AIR-0227E-P3`

## Date
`2026-07-13`

## 상태
**완료 — Conditional Go.** Mock Hermes를 실제 주제 조사 Hermes Worker로 교체했고, 소스 실행 /
onedir 빌드 / 실제 설치본(Inno Setup) 3곳 모두에서 Render Worker와 Hermes Worker가 동시에
독립적으로 동작함을 실측으로 확인했다. Conditional인 이유: 클린 Windows/VM 검증과 코드 서명은
이전 단계(P2-VALIDATION)부터 이어지는 기존 미해결 항목이며, 이번 Task에서도 다루지 않았다.

브랜치: `feat/air-0227e-p3-real-hermes-worker` (base: `feat/air-0227e-p2-installer-validation`,
PR #84 브랜치)

---

## 1. 범위 확인

지시사항대로 아래는 손대지 않았다:
- AIR-0227D staging Supabase 작업, 중앙 Worker API, Worker Token 발급 시스템, lease/heartbeat,
  PostgreSQL claim, 다중 렌더 PC 구조 — 전부 무관, 이번 세션에서 건드리지 않음.
- Google Drive 렌더 파이프라인 자체(`worker/render_worker.py`, `render_pipeline_adapter.py`,
  `drive_adapter.py`, `upload_adapter.py`) — 계약 변경 없음. 유일한 렌더 관련 수정은
  `write_state()`에 `last_success_at`/`last_error` 필드를 추가한 것(§4)뿐이고, 렌더 상태 전이
  (QUEUED→CLAIMED→PREPARING→RENDERING→UPLOADING→COMPLETED/FAILED)나 Drive 연동 로직은
  그대로다.

## 2. Mock Hermes 제거 방식

- `worker/hermes_worker_mock.py`는 **삭제하지 않고 그대로 둠** — `_dev/` QA 스크립트나 향후
  테스트에서 API 키 없이 빠르게 프로세스 슈퍼비전만 확인하고 싶을 때 여전히 유용하다.
- 실제 교체 지점은 `worker/air_worker_entry.py`의 역할 디스패치 단 한 줄:
  `hermes_worker` role → `import hermes_worker_mock` **에서** `import hermes_worker`(신규
  실제 구현)**로 변경**. `worker/manager.py`는 자식 프로세스를 이름으로만 스폰하므로(실제
  모듈은 `air_worker_entry.py`가 결정) 이 한 줄 변경만으로 production 실행 경로 전체가 실제
  Hermes로 넘어간다 — mock은 이제 그 어디서도 자동으로 시작되지 않는다.

## 3. 실제 Hermes Worker 설계 (`worker/hermes_worker.py`, 신규)

- **범위**: 주제 조사만. 콘텐츠 생성, 멀티스텝 에이전틱 리서치는 이번 범위 밖(지시사항 그대로).
- **작업 소스**: 새 서버/DB 없음 — Render Worker가 이미 쓰던 로컬 `worker/job_store.py`
  (SQLite)를 `job_type='topic_research'`로 그대로 재사용. Local API의 기존 범용
  `POST /jobs/submit`/`GET /jobs/{id}`가 이미 job_type-agnostic이라 엔드포인트 추가 없이 바로
  동작.
- **입력 계약(최소 필드)**: `keyword`(또는 `topic`), `language`, `country`(또는
  `target_market`), `count` — `job_id`/생성 시각은 job_store가 자동 부여.
- **출력 계약**: `job_id`/`status`/`topics`(각 `title`/`summary`/`sources`)/`model`/
  `completed_at`/`error` — JSON 파일로 `output/hermes_results/{job_id}.json`에 저장,
  `job_store`의 `output_path`가 그 경로를 가리킴(렌더 결과 파일 포인터 패턴과 동일).
- **상태 기계 재사용**: `job_store.py`의 `TRANSITIONS`(렌더 전용으로 설계된
  CLAIMED→PREPARING→RENDERING→UPLOADING→COMPLETED)를 **수정 없이 그대로** 걸어서 사용 —
  PREPARING="프롬프트 준비", RENDERING="AI 호출 중", UPLOADING="결과 저장 중"으로 재해석만
  했다. `job_store.py` 자체는 한 줄도 바뀌지 않았으므로 Render Worker에 미치는 영향은 없다.
- **AI Provider 연동**: 신규 코드를 만들지 않고 기존 `services/ai_router.py::generate_text()`
  (Gemini/Claude 라우팅 + Claude 실패 시 Gemini 폴백 로직 그대로)를 재사용. 모델은 기존
  `config.py::TOPIC_GENERATION_MODEL`(기본값 `gemini-2.5-flash`) 그대로 사용 — 새 환경변수
  이름을 만들지 않았다.
- **API 키 공급 방식(사용자 확인 후 결정)**: 웹어드민 BYOK를 실시간으로 가져오는 방식(기존
  `desktop_login`/`desktop_resync` 플로우, service_role 미사용) 대신, **렌더 PC 로컬
  환경변수**(`GEMINI_API_KEY`/`CLAUDE_API_KEY`, `config.py`가 이미 `os.getenv`로 읽던 그대로)를
  선택 — AIR Worker는 여전히 Supabase 자격증명이 전혀 필요 없다(`docs/AIR_WORKER_SECURITY.md`
  §1 원칙 유지). 설치파일에는 어떤 키도 포함되지 않는다.
- **자원 우선순위**: `hermes_worker_mock.py`가 이미 구현해 둔 파일 기반 pause 체크포인트
  (`STATE_DIR/hermes_worker.pause`)를 그대로 재사용 — `manager.py::_apply_resource_policy()`도
  전혀 수정하지 않았다. 진행 중인 AI 호출은 끝까지 완료하고, **다음** 작업만 render가 끝날
  때까지 대기한다(중간에 끊지 않음 - 안전 체크포인트 원칙).
- **Local API 상태 노출**: `render_worker.py`/`hermes_worker.py` 둘 다 `write_state()`에
  `last_success_at`/`last_error` 필드를 추가(하위호환 - 없으면 이전 값 유지), `manager.py`의
  `status_snapshot()`이 이 두 필드를 `/status`·`/processes` 응답에 그대로 실어 보냄. 새 API
  엔드포인트는 만들지 않았다.

## 4. 실측 검증 — 소스 실행 (Dev mode)

`GEMINI_API_KEY`는 이 개발 머신의 메인 체크아웃(`LongformGenerator/.env`)에 이미 있던 실제 키를
격리된 `AIRWORKER_HOME`으로만 전달해 사용(코드/로그/git 어디에도 값 노출 없음).

- **시나리오 A**: Manager 기동 → Render/Hermes/Local API 전부 정상 기동 → 실제 한국어 주제
  조사 요청(은퇴 후 자산관리, 5개) → 실제 Gemini 호출 → **1차 시도가 JSON 파싱 실패(응답이
  중간에 잘림) → 자동 재시도(1/3) → 2차 시도 성공, 5개의 실제 고품질 한국어 주제 후보 생성**
  (제목/요약/근거 문단 전부 실제 내용, 목업 아님). 이 실패+자동재시도 자체가 "API 일시
  실패/잘못된 응답 처리" 시나리오(§16)를 저절로 실증함.
- **시나리오 B (렌더 우선순위)**: Hermes 작업 A(실행 중) + Hermes 작업 B(대기) + Render 작업
  C(픽스처) 동시 제출 → Render가 즉시 우선 처리되어 `hermes_paused=true`로 전환 → **A는
  진행 중이던 작업이라 끝까지 완료됨(체크포인트 원칙)** → **B는 render(C)가 완료되고
  paused=false로 돌아올 때까지 정확히 QUEUED 상태로 대기(단 한 번도 CLAIMED되지 않음)** →
  render 완료 즉시 B가 시작되어 완료. 실측 로그로 매 틱 상태를 기록해 확인.
- **시나리오 C (Hermes 크래시)**: `taskkill /PID <hermes_pid> /F` → Manager가 즉시 감지,
  crash_count_window=1로 기록 후 새 PID로 자동 재시작 → 이 동안 render_worker/local_api의
  PID·상태는 전혀 변화 없음(`/processes`로 실측 확인).
- **시나리오 D (Render 크래시)**: 대칭적으로 render_worker를 강제 종료 → 새 PID로 재시작 →
  hermes_worker/local_api 무영향 확인.
- **시나리오 E (전체 종료)**: `/shutdown` 호출 → 11단계 로그 그대로 재현
  (`docs/AIR_WORKER_SHUTDOWN_PROTOCOL.md`) → **"Leftover PID check: 0 process(es) still
  alive: []"** 확인, `tasklist`로도 재확인.

## 5. 패키징 — onedir 빌드 + 실제 Inno Setup 설치본

- 기존 P2 구조(PyInstaller onedir, `copy_metadata("google-genai")`, `collect_submodules
  ("services")`/`("app")`, pykakasi `collect_all`, bundled ffmpeg/ffprobe, Named Mutex,
  `%LOCALAPPDATA%\AIRStudio\AIRWorker`, Inno Setup)를 검토한 결과 **spec 파일 자체는 수정
  불필요**로 판단 — `services/gemini_service.py`/`claude_service.py`/`ai_router.py`/
  `database.py`가 전부 `collect_submodules("services")`로 이미 강제 포함되고, 실제 빌드에서
  ModuleNotFoundError 없이 한 번에 성공해 이 판단이 맞았음을 확인. 유일한 변경은
  `worker/worker_version.py::WORKER_VERSION`을 `0.1.0` → `0.2.0`으로 올린 것.
- ffprobe.exe는 이 worktree 전용 gitignored 캐시라 `_dev/fetch_ffprobe.py`로 재다운로드
  (SHA256 `436bf02524d50135ed9965b90d1e0ad7f26c5c236132613a2edb87ef8b6873d0`, 기존과 동일 —
  P2-VALIDATION 당시와 같은 gyan.dev 7.1 빌드).
- **onedir 빌드**: exit_code=0, 소요 505.1초. `AIRWorker.exe` 82,827,958 bytes, SHA256
  `7a27441ffb73028647156882a34720aa0f33d9d97daf4327d280ba84b878578b`. 전체 onedir 트리 약 1.4GB.
- **onefile 빌드도 (의도치 않게 --help 오타로) 함께 실행**, exit_code=0으로 정상 완료 —
  참고용, 설치본은 onedir 기준(P2-VALIDATION 결정 유지).
- **Inno Setup 컴파일**: `AIRWORKER_VERSION=0.2.0`으로 `ISCC.exe packaging/windows/AIRWorker.iss`
  실행, exit_code=0(370.969초). 결과물 `release/AIRWorkerSetup-0.2.0.exe`, 442,697,879 bytes,
  SHA256 `50eb673c21db54a512181178dd6a3859b7c47d3883723fd5c28a32ebce9a5e97`. 기존과 동일한
  "PrivilegesRequired=admin이지만 localappdata를 씀" 경고만 뜸(이전부터 있던 것, 새로 생긴
  문제 아님).

## 6. 실제 설치본 QA

- `//VERYSILENT //SUPPRESSMSGBOXES //DIR=C:\Temp_AIRWorker_P3_Test`로 실제 조용한 설치 실행,
  exit_code=0 확인.
- 설치 직후 첫 실행 시도에서 `pyi_rth__tkinter` 런타임훅이 `_tcl_data` 폴더를 못 찾는 에러가
  1회 발생 — **원인 조사 결과 실제 패키징 결함이 아니라 이 세션 자체의 테스트 경합(설치가
  완전히 끝나기 전에 실행을 시도한 레이스)으로 판명**: 소스 트리와 설치된 트리의
  `_tcl_data`/`_tk_data` 파일 개수를 직접 비교해 완전히 동일함을 확인했고, 남아있던 프로세스를
  정리한 뒤 깨끗하게 재실행하니 즉시 정상 기동됨. 재현되지 않아 결함으로 분류하지 않음(정직하게
  기록만 남김).
- 재실행 후: Render/Hermes/Local API 3개 역할 전부 정상 기동, 실제 한국어 주제 조사 1건을
  설치된 exe로 정상 완료(재시도 없이 1차 성공), 렌더 픽스처로 조립한 실제 mp4를 ffprobe로
  재확인(h264/aac, 1280x720, 24fps, 4.00초 — 회귀 없음), `/shutdown` 호출 시 동일하게 11단계
  로그 + leftover PID 0 확인.
- `unins000.exe //VERYSILENT //SUPPRESSMSGBOXES`로 조용히 제거, 설치 디렉터리 완전히 사라짐
  확인.

## 7. 실제 Hermes AI E2E 3회+ (실 Gemini API 기준)

| # | 시나리오 | 결과 |
|---|---|---|
| 1 | 정상 한국어 주제 조사(소스 실행) | 1차 JSON 파싱 실패 → 자동 재시도 → 2차 성공, 5개 실제 후보 생성 |
| 2 | 정상 한국어 주제 조사(렌더 우선순위 테스트 중, 소스 실행) | 1차 성공 |
| 3 | 정상 한국어 주제 조사(onedir 빌드) | 1차 성공 |
| 4 | 정상 한국어 주제 조사(렌더 우선순위 테스트 중, onedir 빌드) | 1차 성공 |
| 5 | 정상 한국어 주제 조사(실제 설치본) | 1차 성공 |
| 6 | **영문 키워드**("personal finance for retirees", en/US) | 1차 성공, 영어로 5개 실제 후보 생성 |
| 7 | **의도적 실패**(잘못된 `GEMINI_API_KEY` 값 주입) | 3회 재시도 모두 실패 → `FAILED` 상태로 정상 종료(무한루프 아님), 프로세스 크래시 없음(`crash_count_window=0` 확인), **로그 전체를 grep해도 가짜 키 값이 단 한 곳도 노출되지 않음을 확인** |

## 8. 알려진 제한사항 (정직하게 명시)

- 클린 Windows/VM 검증, 코드 서명 — P2-VALIDATION부터 이어지는 기존 미해결 항목, 이번
  Task에서도 다루지 않음.
- 실제 Google Drive 자격증명 기반 E2E는 여전히 미착수(테스트 자격증명 없음) — 렌더 회귀는
  로컬 픽스처로만 확인(§6), 이는 §DRIVE_LIVE_QA.md에 이미 기록된 기존 제한사항이지 이번
  Task가 새로 만든 gap이 아니다.
- Hermes의 "실행 중인 작업이 render 개입으로 일시정지되는" 케이스(진행 중 작업 자체를
  체크포인트에서 멈추는 것)는 이번 세션에서 별도로 유도하지 못했다 — 실측된 것은 "다음 작업이
  대기하는" 케이스(§4 시나리오 B)뿐이다. 코드 경로는 존재하지만(`hermes_worker.py`의
  스텝 사이 `is_paused()` 체크) 진행 중인 다단계 작업이 없어(한 번의 AI 호출이 통째로 하나의
  스텝) 실질적으로 이 worker에는 "스텝 사이 일시정지"가 관측 가능한 형태로 나타나지 않는다 —
  설계상 원래 그런 것이지 버그는 아니다.

## 9. Git

- 브랜치: `feat/air-0227e-p3-real-hermes-worker` (base `feat/air-0227e-p2-installer-validation`,
  PR #84 브랜치)
- main 병합 없음, production 배포 없음.
