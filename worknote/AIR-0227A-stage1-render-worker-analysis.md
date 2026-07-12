# AIR-0227A — Stage 1: 기존 렌더링 서버(원격 워커) 분석 보고서

## Task ID
`AIR-0227A-Stage1`

## Date
`2026-07-12`

## 상태
조사 완료. 코드 변경 없음.

---

## 핵심 요약

현재 "원격 렌더링 서버"는 **Windows 설치 프로그램도, 자동 업데이트도, 프로세스 감시도 없는
단일 콘솔 스크립트**다. GPU 사용은 플래그만 있고 실제로 어디에도 연결되어 있지 않다(모든
인코딩이 `libx264` CPU 하드코딩). 게다가 렌더링 관련 경로가 **3가지**나 존재하는데 그 중
하나(로컬 HTTP-push 큐)는 **이미 죽은 코드**다. 이런 상태를 AIR Worker로 통합하는 것은
"기능을 합치는 것"이자 "빠진 설치·업데이트·감시 인프라를 처음으로 갖추는 것"이기도 하다.

## 1. 실행 방식

`remote_drive_worker.py` — **동기 블로킹 루프**, asyncio/threading 없음(내부적으로
MoviePy/ffmpeg 서브프로세스가 도는 것 외에는). `argparse`로 `--once`/`--check`/무인자(=`run_forever`)
3가지 모드. `run_forever()`는 `while True: ... time.sleep(poll_interval)` 형태, 예외는
전부 잡아서 로그만 찍고 계속 돌지만 `KeyboardInterrupt`는 명시적으로 다시 raise한다
(`remote_drive_worker.py:316-317`). **한 번에 작업 1개만 처리** — 큐잉/병렬성 없음.

## 2. 진입점

`remote_drive_worker.py`의 `if __name__ == "__main__"`(`:337-349`)이 유일한 진입점.
**빌드 경로가 2개 있는데 서로 다른 이름의 exe를 만든다** — 실제 버그성 불일치:
- `PicadiriRemoteWorker.spec`으로 빌드 → `PicadiriRemoteWorker.exe` (문서가 말하는 이름)
- `_dev/build_remote_worker.py`로 빌드(문서가 실제로 안내하는 방법) → `AIRRemoteWorker.exe`
둘 다 `remote_drive_worker.py`를 그대로 패키징하지만 하나는 `.spec` 파일의 `copy_metadata('replicate')`
등을 거치고 하나는 안 거침. 이번 작업 범위 밖이라 수정하지 않고 기록만 함.

## 3. API 서버

**없음.** `remote_drive_worker.py`는 순수 아웃바운드 클라이언트 — Supabase REST와 Google Drive API로만
나간다. 리스닝 서버(uvicorn/FastAPI/http.server) 전무. 상태 확인은 `--check` CLI 플래그(stdout 출력)뿐.

## 4. 렌더링 프로세스

**메인 앱과 완전히 동일한 파이프라인을 재사용**한다 — 별도 렌더 엔진 없음.
`process_job()` → `services/remote_render_service.py::remote_render_executor_func()` →
(뮤직 모드는 raw ffmpeg subprocess 직접 호출) 또는 (일반 롱폼/숏폼은)
`services/video_service.py::create_slideshow()` — `app/routers/video.py`의 동기 렌더 엔드포인트가
쓰는 것과 **같은 MoviePy 코드**.

## 5. GPU 사용 방식 — **사실상 죽은 플래그**

`USE_GPU_RENDER` 환경변수가 `use_gpu` 파라미터로 끝까지 전달되지만, 실제 인코딩 호출부
(`video_service.py`의 여러 `write_videofile()` 호출, `remote_render_service.py`의 raw ffmpeg
명령)는 **전부 `libx264`(CPU 소프트웨어 인코더)를 하드코딩**하고 있다. `nvenc|qsv|amf|cuda|hwaccel`
전체 저장소 검색 결과 렌더링 코드 어디에도 없음(Whisper 자막 정렬용 CUDA 줄은 주석 처리되어
`device="cpu"`로 고정). `config.USE_GPU_RENDER`도 실제로 정의된 적 없어
`getattr(config, "USE_GPU_RENDER", True)`가 항상 기본값(`True`)으로 조용히 폴백한다.
**결론: "GPU 렌더"는 오늘 시점엔 "물리적으로 다른(더 빠른) PC에서 CPU 인코딩"을 의미할 뿐이다.**

## 6. 작업 큐

Supabase `remote_render_queue`(`auth-web/supabase_schema.sql:519-540`). 폴링 주기
`REMOTE_RENDER_POLL_INTERVAL`(기본 10초). Claim은 **PostgREST 조건부 PATCH로 구현된 원자적
compare-and-swap** — `PATCH ...?id=eq.{id}&status=eq.pending`으로 `status='rendering'`을 시도,
이미 다른 워커가 선점했으면 WHERE절에 걸려 0행 매치 → 애플리케이션 레벨 락/뮤텍스 전혀 없이
Postgres 단일 UPDATE의 원자성에만 의존. `render_mode='drive_api'` 행만 필터링해서 가져옴.

## 7. 로그

**워커 자체의 파일 로그가 없다.** 전부 `print()` → 콘솔(exe가 `console=True`로 빌드됨). 다만
호출하는 공용 렌더 코드(`video_service.py`)가 `config.DEBUG_LOG_PATH`(`%LOCALAPPDATA%\AIRStudio\logs\debug.log`)에
일부 기록을 남기긴 하지만, 폴링/claim/작업 성공-실패 등 **워커 자체의 운영 로그는 어디에도
영구 저장되지 않는다.**

## 8. 업데이트 방식

**전혀 없음.** 완전 수동 재빌드 + 수동 배포(`docs/REMOTE_DRIVE_WORKER.md`: "EXE 옆에 .env를
준비해야 합니다"). 메인 앱은 `services/updater_service.py` + `packaging/windows/launcher/AIRUpdater.py`의
정교한 원자적 스왑(`app/`→`app_backup/`→`app_new/`→`app/` NTFS rename, SHA256 재검증, 구조화 로그)을
갖추고 있는데, 원격 워커는 이 인프라를 **전혀 공유하지 않는다.**

## 9. 설치 프로그램 구조

**설치 프로그램이 없다.** Inno Setup `.iss` 없음(`AIRStudio.iss`만 존재). `_dev/build_remote_worker.py`가
`--onefile` bare exe만 만들고 끝 — 바로가기/레지스트리/시작메뉴/제거 프로그램 전무. exe +
사이드카 `.env` 파일을 수동으로 복사하는 배포 모델.

## 10. 종료 및 재시작 방식

**Graceful shutdown**은 기본 `KeyboardInterrupt`(Ctrl+C)에만 의존, `signal.signal()` 핸들러 등록
없음. 렌더링 도중 Ctrl+C가 오면 `process_job()`의 `except Exception`에 안 잡히고(BaseException이라)
그대로 전파되어 **Supabase 작업 행이 `rendering` 상태로 stuck** — 타임아웃/재큐잉 로직이
코드 어디에도 없음. **프로세스 감시 전무** — Windows Service/NSSM/작업스케줄러/워치독 스크립트
없음. `run_remote_worker.bat`도 1회 실행 후 `pause`일 뿐, 크래시 시 재시작은 전적으로 사람 몫.

## 부가 발견: 렌더링 경로가 실제로는 3개, 그 중 1개는 죽은 코드

1. **동기 직접 렌더**(`render_target="local"`, 기본값) — 요청-응답 내에서 바로 처리.
2. **Google Drive 릴레이**(`render_target="drive_api"`) — 이 문서의 대상. `remote_render_queue`
   + `remote_drive_worker.py`.
3. **인프로세스 HTTP-push 큐**(`services/render_queue_worker.py` + `POST /remote/render`) —
   "한국 렌더링 서버가 베트남 클라이언트로부터 ZIP을 받는다"는 옛 아키텍처의 잔재. **이미 죽음**:
   호출하는 `poll_remote_render_status`/`download_remote_render_result` 함수가 저장소 어디에도
   정의되어 있지 않아 실행되면 `ImportError`가 나고, 그 코드를 타는 프로젝트 상태
   (`remote_rendering`)로 전이시키는 코드도 없으며, 프론트엔드(`render.html`)는
   `remote_url`을 명시적으로 항상 빈 문자열로 강제한다. AIR Worker 설계는 이 3번 경로를
   **참고/재사용 대상에서 제외**한다 — 살아있는 건 1번과 2번뿐.

## Files Changed
없음 (조사만). 이 보고서 1개 파일 신규.
