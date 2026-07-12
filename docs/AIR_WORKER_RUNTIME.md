# AIR Worker — Runtime (AIR-0227B)

- 상태: **로컬 E2E 검증 완료 / 프로덕션 미배포**
- 관련 문서: [ARCHITECTURE](./AIR_WORKER_ARCHITECTURE.md), [PROCESS_MODEL](./AIR_WORKER_PROCESS_MODEL.md),
  [RENDER_ADAPTER](./AIR_WORKER_RENDER_ADAPTER.md), [SHUTDOWN_PROTOCOL](./AIR_WORKER_SHUTDOWN_PROTOCOL.md),
  [JOB_RECOVERY](./AIR_WORKER_JOB_RECOVERY.md), [LOCAL_E2E_QA](./AIR_WORKER_LOCAL_E2E_QA.md)

AIR-0227A(#12 스켈레톤)는 3개 프로세스가 뜨고/죽고/재시작되는 것만 모의로 증명했다.
AIR-0227B는 그 골격 위에 **실제로 동작하는 렌더링**을 연결하고, 스켈레톤 QA에서 발견된
구조적 문제(Local API 스레드, `os._exit`)를 근본적으로 고쳤다.

## 1. 무엇이 실제로 바뀌었나

| 항목 | AIR-0227A | AIR-0227B |
|---|---|---|
| Render Worker | `render_worker_mock.py` (sleep만) | `render_worker.py` — `services/remote_render_service.py::remote_render_executor_func` 실호출 |
| Local API | Manager 내부 스레드 | `local_api_process.py` — 독립 `subprocess.Popen` 자식 |
| 프로세스 간 셧다운 신호 | `signal.SIGTERM` (Windows에서 사실상 무동작 — §SHUTDOWN_PROTOCOL §0) | 파일 기반 shutdown flag (`worker/shutdown_flag.py`) |
| 프로세스 종료 | `os._exit(0)` 워크어라운드 | 정상 `main()` 반환 — 인터프리터가 스스로 종료 |
| 작업 소스 | 없음(모의 생성기) | `worker/job_store.py` (로컬 SQLite), `remote_render_queue`/service_role 미사용 |
| 작업 취소 | 없음 | QUEUED/CLAIMED/PREPARING는 소프트, RENDERING/UPLOADING는 프로세스 트리 kill (§JOB_RECOVERY) |
| 크래시 복구 | 없음 | ABANDONED 감지 → 재시도 또는 격리 (§JOB_RECOVERY) |

`worker/config.py`는 `worker/worker_config.py`로 이름을 바꿨다 — Render Worker가
`services/remote_render_service.py`를 import하면 그 파일이 `from config import config`로
프로젝트 루트의 `config.py`를 찾는데, `worker/` 디렉터리는 자식 스크립트 실행 시 항상
`sys.path[0]`이 되므로 같은 이름의 모듈이 있으면 영구히 가려버린다 — 이번 Task에서 처음으로
실제 파이프라인을 import하게 되면서 드러난 충돌이라 이름을 바꿔 근본적으로 없앴다.

## 2. Render Worker가 실제로 호출하는 것 (Stage 1 재확인 결과)

`services/remote_render_service.py::remote_render_executor_func(task_id, temp_dir, use_gpu=False)`를
그대로 호출한다 — **이 함수를 전혀 수정하지 않았다**. 이 함수를 선택한 이유:

- Supabase/service_role 자격증명을 전혀 받지 않는다 (인자 자체가 없음).
- `temp_dir/config.json` + `temp_dir/{audio,images,...}/`만 읽고, `temp_dir/progress.txt` +
  `temp_dir/output.mp4`만 쓴다 — 순수 로컬 함수.
- 내부에서 `import database as db`가 일어나는 경로(zip 패키징 헬퍼)는 이 함수 밖에 있고,
  `database.py` 자체도 로컬 SQLite뿐이라 네트워크 자격증명이 없다(Stage 1에서 소스 확인).
- `app_mode == 'longform_music'`이면 raw ffmpeg subprocess(`libx264`/`aac` 하드코딩), 아니면
  `services/video_service.py::create_slideshow`(MoviePy 기반, 역시 `libx264`) — 둘 다 실제로
  운영 중인 코드다.

`remote_drive_worker.py`의 Supabase 폴링(`fetch_next_job`/`claim_job`/`update_job`,
service_role 헤더 사용)은 재사용하지 않았다 — `worker/job_store.py`(로컬 SQLite)로 완전히
대체했다. `process_job()`의 **순서**(다운로드 → 압축해제 → 렌더 → output.mp4 확인 → 업로드 →
상태 갱신)만 참고했다.

## 3. 다운로드/업로드 (Stage 1 google_drive_service.py 재확인)

`services/google_drive_service.py::download_file`/`upsert_file`은 **사용자별 OAuth
token_path**를 요구한다 — AIR-0225B의 service_role(관리자 마스터 키)과는 성격이 다른, 더
좁은 범위의 자격증명이다. 그래도 이번 Task는 실제 Drive 연결을 승인 범위 밖으로 두고
(§ARCHITECTURE §0), 로컬 E2E 픽스처는 `worker/upload_adapter.py::LocalCopyUploadAdapter`
(로컬 폴더로 복사)만 사용한다. `GoogleDriveUploadAdapter`는 인터페이스만 문서화해두고
`NotImplementedError`를 낸다 — 실 연결은 다음 Task 승인 이후.

## 4. 실행 중 발견하고 고친, 파이프라인 연동과 무관한 사전 존재 버그

`services/video_service.py`가 stdout에 이모지(`🎬`)를 출력하는데, 이 로컬(한국어 Windows,
cp949 콘솔 코드페이지) 환경에서 백그라운드 프로세스로 실행하면 `UnicodeEncodeError`로
렌더가 그대로 죽는다. `video_service.py`는 건드리지 않고, Manager가 자식 프로세스를 띄울 때
`PYTHONIOENCODING=utf-8`을 환경변수로 강제하는 것으로 해결했다(`worker/manager.py::start_process`) —
장시간 상주하는 백그라운드 워커에는 표준적인 조치이자, "기존 렌더링 서버 수정 금지" 원칙을
지키면서 실제로 동작하게 만드는 데 필요한 최소 개입이다.

## 5. CPU/GPU 표시 (Stage 9)

`worker/worker_config.py`: `RENDER_ENCODER="libx264"`, `RENDER_ACCELERATION="CPU"`,
`GPU_RENDERING_ACTIVE=False` — Stage 1에서 재확인한 그대로, 어떤 인코딩 경로도 GPU를 쓰지
않는다. `render_pipeline_adapter.run_render()`는 `use_gpu=False`를 항상 명시적으로 넘긴다.
`/status` 응답의 `render_status` 필드가 이 값을 그대로 노출한다.
