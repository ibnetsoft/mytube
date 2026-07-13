# AIR Worker — 프로세스 모델

- 상태: **로컬 E2E 검증 완료(AIR-0227B) + Frozen EXE 패키징 PoC 검증 완료(AIR-0227E, `--role` 재실행 패턴으로 자식 스폰 방식 변경 — [RUNTIME §6.1](./AIR_WORKER_RUNTIME.md) 참고) / 프로덕션 미배포·CTO 승인 대기**
- 관련 문서: [ARCHITECTURE](./AIR_WORKER_ARCHITECTURE.md), [JOB_PROTOCOL](./AIR_WORKER_JOB_PROTOCOL.md), [RUNTIME](./AIR_WORKER_RUNTIME.md), [SHUTDOWN_PROTOCOL](./AIR_WORKER_SHUTDOWN_PROTOCOL.md)

> **AIR-0227B 업데이트 — §5와 §7은 더 이상 최신이 아니다, 아래 참고**: Local API는
> 실제로 구현하면서 §5의 "Manager 내부 스레드" 설계를 버렸다 — `uvicorn.Server.run()`이
> 스레드에서 돌면 Manager 프로세스가 스스로 종료되지 않는 문제가 실행 QA로 재확인됐고
> (AIR-0227A에서 이미 `os._exit`로 우회했던 바로 그 문제), 이번엔 완전히 별도
> `subprocess.Popen` 자식(`local_api_process.py`)으로 분리해 근본적으로 없앴다. §7 파일
> 목록도 `worker/manager.py`, `local_api_process.py`, `local_api_app.py`,
> `render_worker.py`, `job_store.py`, `render_pipeline_adapter.py`, `upload_adapter.py`,
> `ipc.py`, `shutdown_flag.py`, `worker_config.py`(구 `config.py`)로 확장됐다. 상세는
> [RUNTIME](./AIR_WORKER_RUNTIME.md) §1, [SHUTDOWN_PROTOCOL](./AIR_WORKER_SHUTDOWN_PROTOCOL.md).

## 1. 프로세스 목록

| 프로세스 | 역할 | 격리 방식 |
|---|---|---|
| **Worker Manager** | 하위 프로세스 시작/중지/재시작, PID·상태 추적, 크래시 감지, 자원 정책 집행(§RESOURCE_POLICY) 지시 | 최상위 부모 프로세스 (`AIRWorker.exe`의 메인 프로세스) |
| **Render Worker Process** | Stage 1에서 확인한 살아있는 렌더 파이프라인(`services/video_service.py`/`services/remote_render_service.py`)을 실행 | 별도 `subprocess.Popen` 자식 |
| **Hermes Worker Process** | 외부 LLM API 호출 기반 시장조사/후보생성 (AIR-0226 설계 재사용, 이번 Task는 모의 구현만) | 별도 `subprocess.Popen` 자식 |
| **Local API Process** | 127.0.0.1 전용 HTTP 서버 — 관리 UI/CLI가 상태를 조회하는 창구 | Worker Manager 내부 스레드 또는 경량 자식 프로세스(§4에서 결정) |
| **Job Scheduler** | 우선순위 큐 유지, "다음에 뭘 실행할지" 결정 | Worker Manager 내부 컴포넌트(별도 OS 프로세스 아님 — 상태 조율 로직이라 IPC 오버헤드보다 인프로세스가 적합) |
| **Health Monitor** | 각 프로세스의 heartbeat/리소스 사용량 수집, 반복 크래시 카운트 | Worker Manager 내부 컴포넌트 |
| **Auto Updater** | 모듈별 독립 업데이트(§UPDATE_STRATEGY) | 별도 `subprocess.Popen` 자식(업데이트 도중 Manager 자체가 교체될 수 있어 분리 필요 — AIR Studio의 `AIRLauncher`/`AIRUpdater` 분리 패턴과 동일한 이유) |

**Job Scheduler/Health Monitor를 별도 OS 프로세스로 만들지 않는 이유**: 이 둘은 "실행"이
아니라 "조율/관찰"이 본질이라, 프로세스 경계를 나누면 상태 동기화 비용만 늘고 격리 이득이
없다(이 둘이 죽어도 격리해서 지킬 "다른 무언가"가 없음 — Manager 자체가 죽으면 전체가
멈추는 게 맞는 설계). 반대로 Render/Hermes/Updater는 "각자 죽어도 나머지는 살아야 하는"
명확한 격리 요구가 있어 별도 프로세스로 나눈다.

## 2. 시작/중지/재시작

- 각 하위 프로세스는 Worker Manager가 소유한 `subprocess.Popen` 핸들로 표현되고,
  독립적으로 start/stop/restart 가능(§JOB_PROTOCOL과 무관하게 이 자체는 프로세스 라이프사이클
  API — Local API의 `/processes/render/start` 등이 이걸 트리거함, §ARCHITECTURE §Local API).
- 시작: Manager가 자식 프로세스 커맨드라인을 구성해 `Popen` 호출, 반환된 PID를 상태 테이블에
  기록(§3).
- 중지: 우선 정상 종료 신호(자식 프로세스가 자체 시그널 핸들러로 안전 종료 로직을 수행할 수
  있게) → 일정 시간 내 종료 안 되면 강제 종료(`terminate()` → `kill()`).
- 재시작: 중지 후 시작을 순차 실행, §3의 재시작 횟수 제한 로직을 통과해야 함.

## 3. PID·상태 추적 및 반복 크래시 대응

Worker Manager가 프로세스별로 다음 상태를 메모리(+로컬 상태 파일, 재시작 후에도 최근 이력
파악용)로 유지한다:

```
{
  process_name: "render_worker" | "hermes_worker" | "updater",
  pid: int | None,
  status: "stopped" | "starting" | "running" | "crashed" | "disabled",
  started_at: datetime,
  last_heartbeat_at: datetime,
  crash_count_window: int,          # 최근 N분 내 크래시 횟수
  restart_count_total: int,
  disabled_reason: str | None,
}
```

- **비정상 종료 시 제한된 횟수만 자동 재시작**: 슬라이딩 윈도우(예: 10분) 내 크래시 횟수가
  임계값(예: 3회)을 넘으면 자동 재시작을 멈춘다.
- **반복 크래시 시 해당 모듈만 비활성화하고 상태 보고**: 임계값 초과 시 `status="disabled"`로
  전환, 그 프로세스만 죽은 채로 두고 **다른 프로세스는 영향받지 않음**(§ARCHITECTURE §3 격리
  원칙의 직접적인 구현) — Local API `/status`/`/processes`에 `disabled` + `disabled_reason`이
  노출되고, 중앙 서버에도 heartbeat 페이로드로 보고되어(§JOB_PROTOCOL `health_check` job_type
  또는 별도 상태 보고 채널) 관리자가 인지할 수 있게 한다.
- 재시작 정책 파라미터(임계값/윈도우 길이)는 하드코딩하지 말고 로컬 설정 파일로 빼서
  운영 중 튜닝 가능하게 한다(§UPDATE_STRATEGY의 독립 업데이트 모듈 중 `config`가 이 역할).

## 4. 로그 분리

프로세스별 별도 로그 파일 — 파일명 충돌 없음(QA 항목 그대로 반영):

```
%LOCALAPPDATA%\AIRWorker\logs\
  ├── manager.log
  ├── render_worker.log
  ├── hermes_worker.log
  ├── local_api.log
  └── updater.log
```

- 기존 AIR Studio의 `debug.log` 단일-파일 관례와 의도적으로 다르게 설계한다 — Stage 1에서
  확인했듯 원격 워커는 로그가 아예 없었고(콘솔 print뿐), 이번엔 "여러 프로세스가 한 로그에
  섞여 쓰기 경합하는" 실패 모드 자체를 원천적으로 피하기 위해 프로세스당 파일을 분리한다.
- 각 자식 프로세스는 자기 로그 파일 경로만 알고 다른 프로세스의 로그 파일에 쓰지 않는다
  (권한이 아니라 설계로 강제 — 각 프로세스는 자기 파일 핸들만 생성).
- 로그 로테이션(크기/일자 기준)은 이번 스켈레톤 범위 밖, 표준 `logging.handlers.RotatingFileHandler`
  도입을 다음 단계 구현에서 제안.

## 5. Local API 프로세스 배치

Stage 12 스켈레톤에서는 **Worker Manager 내부의 별도 스레드**로 구현한다(경량 FastAPI/uvicorn을
자식 프로세스로 또 띄우면 프로세스 개수만 늘고, Local API가 죽어도 격리해서 지킬 "자기만의
상태"가 없음 — 오히려 Manager의 상태를 그대로 반영하는 창구라 인프로세스가 자연스러움). 다만
**"Local API 종료 후 자동 복구"**(QA 항목)를 만족해야 하므로, 이 스레드 자체도 Health Monitor가
살아있는지 주기적으로 확인하고 죽었으면(스레드 예외로 죽는 경우) 재기동하는 로직을 둔다.

## 6. 관리 UI/CLI 상태 화면 (Stage 8)

스켈레톤 구현은 **CLI 상태 화면**(터미널에 주기적으로 상태 테이블을 다시 그리는 형태)으로
시작한다 — Local API의 `/status`/`/processes`를 폴링해서 표시. 표시 항목(중앙 서버 연결
상태/Worker ID/렌더링·Hermes 상태/큐 수/현재 작업/진행률/CPU/RAM/GPU/VRAM/마지막
heartbeat/최근 오류)과 제어(렌더링·Hermes 시작/중지/전체 일시정지/로그 열기/업데이트
확인/종료)는 전부 Local API 엔드포인트 호출로 구현되므로, 나중에 정식 GUI로 교체해도
Local API 계약은 그대로 재사용된다.

## 7. Worker Manager 진입점 (스켈레톤 설계, Stage 12에서 실제 구현)

```
worker/
├── manager.py           # 진입점 - 하위 프로세스 spawn, Job Scheduler, Health Monitor 포함
├── process_registry.py  # PID/상태 추적 테이블(§3)
├── local_api.py          # FastAPI 앱 (127.0.0.1 전용, §SECURITY §Local API)
├── render_worker_mock.py # 모의 Render Worker (실제 렌더 파이프라인 미연결)
├── hermes_worker_mock.py # 모의 Hermes Worker (실제 Hermes 미연결)
├── cli_status.py          # CLI 상태 화면
└── logging_setup.py        # 프로세스별 로그 파일 분리(§4) 헬퍼
```
