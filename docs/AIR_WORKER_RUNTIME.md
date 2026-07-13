# AIR Worker — Runtime (AIR-0227B, §6 이후 AIR-0227E, §7 이후 AIR-0227E-P2)

- 상태: **로컬 E2E 검증 완료(AIR-0227B, 소스 실행) + Frozen EXE 패키징 PoC 검증 완료(AIR-0227E,
  §6) + Onedir 설치 패키징/Mutex/경로분리 개발머신 격리 QA 통과(AIR-0227E-P2, Conditional Go,
  클린 OS·Inno Setup 실컴파일 미검증) / 프로덕션 미배포**
- 관련 문서: [ARCHITECTURE](./AIR_WORKER_ARCHITECTURE.md), [PROCESS_MODEL](./AIR_WORKER_PROCESS_MODEL.md),
  [RENDER_ADAPTER](./AIR_WORKER_RENDER_ADAPTER.md), [SHUTDOWN_PROTOCOL](./AIR_WORKER_SHUTDOWN_PROTOCOL.md),
  [JOB_RECOVERY](./AIR_WORKER_JOB_RECOVERY.md), [LOCAL_E2E_QA](./AIR_WORKER_LOCAL_E2E_QA.md),
  [FFMPEG_LICENSE](./AIR_WORKER_FFMPEG_LICENSE.md), [VERSIONING](./AIR_WORKER_VERSIONING.md),
  [CODE_SIGNING_PLAN](./AIR_WORKER_CODE_SIGNING_PLAN.md),
  [`worknote/AIR-0227E-PACKAGING-POC.md`](../worknote/AIR-0227E-PACKAGING-POC.md)(P1 전체 검증 로그),
  [`worknote/AIR-0227E-P2-INSTALLER-HARDENING.md`](../worknote/AIR-0227E-P2-INSTALLER-HARDENING.md)(P2 전체 검증 로그)

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

## 6. AIR-0227E — Frozen EXE(AIRWorker.exe) 패키징에서 새로 드러난 사실

상태: **PoC 검증 완료** — 아래 전부 라이브 빌드+실행으로 확인(상세 로그는
[`worknote/AIR-0227E-PACKAGING-POC.md`](../worknote/AIR-0227E-PACKAGING-POC.md)). §1~§5는
`python manager.py`로 소스에서 실행한 결과이고, 이 §6는 **PyInstaller onefile로 얼린
`AIRWorker.exe` 자체**를 실행한 결과다 — 둘은 실행 방식이 근본적으로 달라 별도로 검증이 필요했다.

### 6.1 멀티롤 재실행 패턴 (핵심 변경)

`worker/manager.py`가 자식을 `[python.exe, "render_worker.py"]`처럼 **인터프리터 + 개별 .py
경로**로 띄우던 방식은 얼리면 깨진다 — `sys.executable`이 exe 자신이 되고 개별 .py 파일이
디스크에 없기 때문. `worker/air_worker_entry.py`(신규)가 `--role
{manager,render_worker,hermes_worker,local_api}` 인자로 자기 자신을 재실행하는 표준
PyInstaller 멀티롤 패턴으로 교체했다. 라이브 확인: `--role` 없이 실행 시 Manager가
`AIRWorker.exe --role render_worker` 등으로 정확히 3개 자식을 재실행하고, 프로세스 트리
(부모/자식 PID)가 예상대로 구성됨을 `Get-CimInstance Win32_Process` 조회로 확인.

### 6.2 imageio/MoviePy 패키지 메타데이터 (frozen 전용 버그, 수정 완료)

1차 빌드에서 `MoviePy 또는 Requests가 설치되지 않았습니다 (Error: No package metadata was
found for imageio)`로 렌더가 실패 — `moviepy`/`imageio`가 내부적으로
`importlib.metadata`로 자기 자신의 배포판 메타데이터를 조회하는데, PyInstaller가 `.dist-info`를
기본적으로 번들하지 않아서 발생(이미 `AIRStudio.spec`이 `google-genai`/`pykakasi`에 대해 겪고
고친 것과 동일 클래스). `packaging/windows/AIRWorker.spec`에
`copy_metadata("imageio")`/`copy_metadata("imageio-ffmpeg")`/`copy_metadata("moviepy")` 추가로
해결 — 재빌드 후 렌더 E2E로 재현 없음 확인(§6.5).

### 6.3 `PYTHONIOENCODING`이 frozen exe에서는 적용되지 않음 (frozen 전용 버그, 수정 완료)

§4에서 소스 실행 기준으로 고쳤던 "이모지 stdout → cp949 UnicodeEncodeError" 문제가 **얼린
exe에서는 재발**했다 — `manager.py`가 자식 env에 `PYTHONIOENCODING=utf-8`을 넣어줘도, 얼린
번들의 부트로더/임베디드 인터프리터는 이를 그대로 반영하지 않는 것으로 관찰됨(소스 실행에서는
동일 env로 정상 동작 확인 — frozen 고유 현상). `worker/air_worker_entry.py` 최상단에서
`sys.stdout`/`sys.stderr`를 `encoding="utf-8", errors="replace"`로 명시적
`reconfigure()`하는 것으로 해결 — 모든 역할이 이 진입점을 거치므로 한 곳에서 확실히 적용됨.
재빌드 후 렌더 E2E 성공(이모지 로그 라인 포함)으로 재발 없음 확인.

### 6.4 FFmpeg 배포 구조 — **exe 내부 포함, 시스템 PATH 무의존**

`imageio_ffmpeg` 패키지의 `_pyinstaller_hooks_contrib` 표준 훅(`hook-imageio_ffmpeg.py`)이
빌드 로그에서 자동 처리됨을 확인 — 이 훅이 ffmpeg 바이너리를 datas로 번들한다. 라이브 증거:
시스템 PATH에 `ffmpeg`/`ffprobe`가 전혀 없는 이 머신에서, 저장소 밖 독립 디렉터리로 복사한
exe가 렌더 잡을 정상 완료했다(§6.5) — 즉 ffmpeg는 **시스템 설치에 의존하지 않고 exe 내부에
포함**된다. 별도 사이드카 파일 불필요.

**라이선스 주의(CTO/법무 확인 필요, 이 문서가 임의로 결론 내리지 않음)**: 번들된 ffmpeg
바이너리는 `ffmpeg version 7.1-essentials_build (gyan.dev)`이고 버전 배너에
`--enable-gpl --enable-libx264` 등이 포함되어 있어 **GPL 빌드**다(LGPL-only 빌드 아님).
서브프로세스로만 호출하고 링크하지 않는 한 통상 "별도 프로그램 호출"로 간주되는 경우가
많지만, 상용 폐쇄 소스 제품에 GPL 바이너리를 재배포하는 것에 대한 최종 판단은 법무/CTO
확인 필요 — 이번 PoC 범위에서 임의로 "문제없음"으로 단정하지 않는다.

`ffprobe`는 이 환경에 별도로 존재하지 않아 `ffmpeg -i <file>` (출력 파일 미지정 시 스트림
정보만 출력하고 종료코드 1)로 대체 검증했다 — 코덱/해상도/길이 확인 목적은 동일하게 달성.

### 6.5 실제 렌더 E2E (frozen, 저장소 밖 독립 디렉터리) — 성공

`dist/AIRWorker.exe`를 저장소 밖(`C:\tmp\airworker-e2e-test\`)으로 복사해 그 디렉터리에서
실행, `AIRWORKER_HOME`도 저장소 밖 경로로 지정. Local API `/jobs/submit`으로 fixture render_video
잡 제출 → `QUEUED→CLAIMED→PREPARING→RENDERING→UPLOADING→COMPLETED` 전이 확인 →
`output.mp4`(23,628 bytes) 생성 확인 → `ffmpeg -i`로 h264(1280x720, 24fps)/aac(44100Hz,
stereo) 스트림, 4.00초 길이 확인. **소스 .py나 venv Python 없이, exe 파일 하나만으로 완결.**

### 6.6 경로 처리 — 한글/공백 모두 정상, 단 onefile 기동 시간은 가변적

`AIRWORKER_HOME`에 한글+공백이 섞인 경로(`C:\tmp\...\에어 테스트 폴더\data`)를 줘도 로그/
SQLite/DPAPI 토큰 파일이 정상 생성됨을 확인. **주의**: onefile 부트로더의 자체 압축해제
시간이 일정하지 않다 — 이 세션에서 반복적으로 짧은 간격으로 재기동을 걸었더니 정상 기동까지
15초~60초 이상 걸린 경우가 있었다(디스크 I/O 부하 누적으로 추정). 운영 배포 시 "기동 후
몇 초 안에 응답해야 함" 같은 짧은 헬스체크 타임아웃을 두면 오탐이 날 수 있다 — 헬스체크/모니터링
설계에 여유 있는 타임아웃(예: 60초+)을 두는 것을 권고.

### 6.7 중복 실행 — **락 없음, 포트 충돌은 조용하지 않음(기존 크래시 정책이 흡수)**

동일 `AIRWORKER_HOME`을 가리키는 `AIRWorker.exe`를 두 번 띄우는 것을 막는 **단일 인스턴스
락이 현재 없다**. 실제 관찰된 동작: 두 번째 인스턴스의 Local API가 포트 8765 바인드 실패로
크래시 → 기존 크래시 정책(`worker/manager.py`, 600초 내 3회)에 따라 3회 재시도 후 자동
DISABLED — **조용한 포트 충돌은 아니다**(로그에 명확히 남고, 두 번째 인스턴스는 Local API
없이 렌더/Hermes만 동작). 다만 두 인스턴스의 Render Worker가 **동일 SQLite `jobs.db`를
동시에 폴링**하게 되는 점은 확인됨 — `job_store.claim_next_job()`이 `BEGIN IMMEDIATE`
트랜잭션으로 클레임을 원자화해 코드 레벨에서는 이중 처리를 막지만, **실제 동시 제출 경쟁
상황을 라이브로 재현·검증하지는 않았다**(코드 검토로만 확인, §안전장치이지 실측 아님).
Hermes Worker(모의)도 인스턴스마다 독립적으로 계속 돎 — 실제 Hermes 연동 시 중복 조사
호출(비용 낭비)로 이어질 수 있어, **단일 인스턴스 락 정책(파일 락/Named Mutex 등)은 CTO
결정이 필요한 미해결 항목**으로 남긴다.

### 6.8 강제 종료/크래시 복구 (frozen, 라이브 재현)

- Render Worker만 강제 kill → Manager가 감지해 해당 프로세스만 재시작, 다른 두 역할의 PID는
  불변(재확인).
- Local API만 QA 훅(`POST /_test/crash-local-api`)으로 크래시 → 자동 재시작, 새 PID로 교체,
  `/health` 재정상화.
- **Manager만 강제 kill(렌더 진행 중)** → 나머지 3개 자식은 고아 프로세스로 남아 **감독 없이도
  진행 중이던 렌더 잡을 끝까지 완료**함(작업 손실 없음). 단, 이 상태에서는 그 자식들이
  죽어도 아무도 재시작해주지 않는다 — 새 Manager가 뜨기 전까지는 무감독.
- **전체(Manager+3자식) 동시 kill(렌더 진행 중)** → 잡이 `RENDERING` 상태로 SQLite에 고정된
  채 남음 → 재기동 시 `run_startup_recovery()`가 `RENDERING → ABANDONED → QUEUED`로 정확히
  전이시키고, 재큐된 잡이 재렌더링되어 `COMPLETED`까지 도달함을 확인.
- 정상(graceful) 종료: `/shutdown` API → 11단계 로그 전부 확인, `leftover_pids=0` 자기 보고
  + `Get-CimInstance`로 외부에서도 프로세스 0개 확인(2회 반복 검증).

### 6.9 빌드 산출물 (커밋 시점 기준, 상세는 §POC 문서)

`AIRWorker.exe`: 567,354,123 bytes, SHA256
`8760075e9e22cbff3073e203d0e0a8ea07117a41518b9bba015eaf7900c4281b`, PyInstaller 6.18.0,
Python 3.13.5, Windows 10.0.26200.8655, moviepy 2.1.2 / imageio 2.37.2 / imageio_ffmpeg 0.6.0.
빌드 산출물(`dist/`, `build/`)은 Git에 커밋하지 않음(`.gitignore`로 이미 제외).
