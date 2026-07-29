# AIR Worker — 종료(Shutdown) 프로토콜

- 관련 문서: [PROCESS_MODEL](./AIR_WORKER_PROCESS_MODEL.md), [RUNTIME](./AIR_WORKER_RUNTIME.md)
- 구현: `worker/manager.py::WorkerManager.graceful_shutdown`, `worker/shutdown_flag.py`

## 0. Windows에서 발견한, 설계를 바꾼 사실

AIR-0227A는 `Popen.terminate()`가 자식 프로세스의 `signal.signal(SIGTERM, ...)` 핸들러를
깨울 것이라 가정했다(모의 워커들이 실제로 그런 핸들러를 등록해뒀다). **Windows에서는 이
가정이 틀렸다** — `subprocess.Popen.terminate()`는 무조건적인 `TerminateProcess()`이고,
Python 시그널 핸들러는 이 경로로는 절대 호출되지 않는다(실제로 콘솔에서 Ctrl+C를 누를
때만 의미가 있다). 이번 Task에서 실제로 종료 시퀀스를 돌려보다가 이걸 재확인하고,
구현을 시작하기 전에 방향을 바꿨다.

**해결책**: 이미 여러 곳(heartbeat 상태 파일, pause flag, cancel flag, command 채널)에 쓰던
파일 폴링 IPC 패턴을 종료 신호에도 그대로 적용했다 — `worker/shutdown_flag.py`.
Manager가 `STATE_DIR/shutdown_flags/<name>.flag` 파일을 쓰면, 각 자식의 메인 루프가 매
이터레이션마다 그 파일 존재 여부를 확인하고 스스로 정상 종료한다. Manager는 지정한
타임아웃 동안 `popen.poll()`을 폴링해서 자식이 스스로 나갔는지 확인하고, 못 나갔을
때만(즉 렌더링 중처럼 블로킹 호출 안에 있어서 루프를 못 도는 경우만) `terminate()` →
`taskkill /PID <pid> /T /F`로 에스컬레이션한다.

## 1. os._exit(0) 제거와 그 전제조건

AIR-0227A는 Local API가 Manager 프로세스 안의 스레드였고, `uvicorn.Server.run()`이 백그라운드
스레드에서 돌 때 Manager 프로세스가 스스로 끝나지 않는 경우가 있어 `os._exit(0)`로 강제
종료했다. AIR-0227B는 Local API를 완전히 별도 OS 프로세스(`local_api_process.py`)로
분리했다 — 이제 Manager 프로세스 안에는 데몬이 아닌 스레드가 정리된 후 아무것도 남지
않으므로, `main()`이 정상적으로 끝까지 실행되면 인터프리터가 스스로 종료된다. **정상
종료 경로에서 `os._exit`를 완전히 제거했다.**

## 2. 실행 중 발견하고 고친 두 번째 버그: 데몬 스레드 경합

처음 구현에서는 `shutdown_all` 커맨드 핸들러가 `graceful_shutdown()`을
`daemon=True` 스레드로 띄웠다. 그런데 `graceful_shutdown()`의 2단계가 `self._stopping = True`를
설정하는 순간 `run_supervisor_loop()`의 while 루프(메인 스레드에서 도는)가 즉시 빠져나가고
`main()`이 끝나버린다 — **데몬 스레드는 인터프리터의 메인 스레드가 끝나는 순간 강제로
잘린다**. 실제로 돌려보니 로그가 1~4단계에서 멈추고 Render Worker/Local API는 한 번도
정지 요청을 못 받은 채 프로세스가 죽었다.

**수정**: `shutdown_all` 스레드를 `daemon=False`로 바꾸고 `self._shutdown_thread`에 보관,
`main()`이 `run_supervisor_loop()`에서 빠져나온 뒤 `self._shutdown_thread.join()`으로 반드시
완주를 기다리게 했다. 이 수정 후 재검증: 11단계가 전부 로그에 찍히고, 리프로세스 확인
결과 leftover PID 0.

## 3. 11단계 프로토콜 (실측 로그 기준)

```
1  SHUTDOWN_INITIATED reason=<트리거>
2  Manager를 shutting_down으로 표시 (supervisor loop가 다음 tick에 빠져나감)
3  manager_status.json에 shutting_down 게시 (Local API/CLI가 읽을 수 있게)
4  Hermes Worker 정지 요청 (우선순위 낮음, 즉시 중단 가능)
5  Render Worker의 job_active 여부 확인 (job_store 상태 파일 조회)
6  Render Worker 정지 요청 - job_active면 SHUTDOWN_JOB_ABORT_GRACE_SECONDS 추가 유예
   (단, RENDERING/UPLOADING 중이면 블로킹 호출이라 flag를 못 보고, 결국 타임아웃 후 강제 kill됨 - 정직하게 문서화)
7  Render Worker 정지 결과 반영 - 중단된 작업은 회수(recovery)로 넘김
8  Local API 정지 (이 종료 요청 자체를 처리 중인 프로세스라 마지막에 정지)
9  leftover PID 점검 - 남은 프로세스 있으면 ERROR 레벨로 로그
10 stale command 파일 정리 + Hermes pause flag 정리
11 SHUTDOWN_COMPLETE total_elapsed=<초> leftover_pids=<개수>
```

## 4. 실측 결과

정상 상태(활성 작업 없음)에서 종료 요청 → 완료까지 **2.22초**, leftover_pids=**0**
(로그: `worker/logs/manager.log`, `[SHUTDOWN step N/11]` 태그로 검색 가능). 종료 후
`Get-CimInstance Win32_Process`로 `manager.py`/`render_worker.py`/`hermes_worker_mock.py`/
`local_api_process.py` 커맨드라인을 가진 프로세스가 하나도 남지 않음을 확인했다.

## 5. 알려진 한계

- RENDERING/UPLOADING 도중 종료 요청이 오면 "정상 종료"가 아니라 타임아웃 후 강제
  `taskkill /T /F`로 귀결된다 — `remote_render_executor_func`에 취소 훅이 없다는 근본
  제약(§JOB_RECOVERY §2)과 동일한 이유. 이때 중단된 작업은 다음 Manager 시작 시
  `run_startup_recovery()`가 ABANDONED로 인식해 재시도한다(§JOB_RECOVERY).
- Local API의 `/shutdown`처럼 파괴적인 엔드포인트에 로컬 전용 토큰 게이트가 아직 없다
  (docs/AIR_WORKER_SECURITY.md §5에 이미 잔여 위험으로 명시됨, 이번 Task 범위 밖).
