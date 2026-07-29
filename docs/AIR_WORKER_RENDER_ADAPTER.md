# AIR Worker — Render Job Adapter

- 관련 문서: [RUNTIME](./AIR_WORKER_RUNTIME.md), [JOB_PROTOCOL](./AIR_WORKER_JOB_PROTOCOL.md), [JOB_RECOVERY](./AIR_WORKER_JOB_RECOVERY.md)
- 구현: `worker/render_pipeline_adapter.py`, `worker/render_worker.py`, `worker/upload_adapter.py`, `worker/job_store.py`

## 1. 왜 "어댑터"인가

`services/remote_render_service.py::remote_render_executor_func`는 이미 검증된, 서비스에서
실제로 쓰이는 렌더링 진입점이다. AIR Worker는 이 함수를 **바꾸지 않고 감싼다** — 입력
(`temp_dir` 준비)과 출력(`output.mp4`, `progress.txt` 소비) 양쪽만 책임진다.

## 2. render_video만 지원 (Stage 5)

`worker/render_worker.py`의 `SUPPORTED_JOB_TYPES = ["render_video"]`. `render_image`/
`render_audio`는 `docs/AIR_WORKER_JOB_PROTOCOL.md` §1 스키마에 정의되어 있지만 이번 Task는
구현하지 않는다 — `job_store.claim_next_job()`에 넘기는 job_type 리스트에서 아예 제외되어
있어 실수로 클레임될 일이 없다.

## 3. 입력 준비 (다운로드 대체)

```
payload = {"source_path": "<.zip 파일 경로 또는 이미 준비된 디렉터리 경로>"}
```

`render_pipeline_adapter.prepare_temp_dir(source_path)`:
- `.zip`이면 `tempfile.mkdtemp()`로 만든 스크래치 디렉터리에 압축 해제
- 디렉터리면 그 내용을 스크래치 디렉터리로 복사(원본 픽스처를 훼손하지 않기 위해)
- `config.json`이 없으면 즉시 실패

실제 배포 시 이 자리에 Google Drive 다운로드 어댑터(`services/google_drive_service.py::download_file`,
사용자별 OAuth token_path)를 끼워넣을 수 있도록 인터페이스를 분리해뒀지만, 이번 Task는
로컬 소스만 구현했다(§ARCHITECTURE §0, 실 Drive 연결은 범위 밖).

## 4. 렌더 실행 + 진행률

`render_pipeline_adapter.run_render(job_id, temp_dir, progress_callback)`:
- 메인 스레드(호출자, 즉 render_worker.py의 유일한 작업 스레드)에서 `remote_render_executor_func`를
  **블로킹으로** 직접 호출한다.
- 별도 워처 스레드가 `temp_dir/progress.txt`를 0.5초 간격으로 tail 하며 값이 바뀔 때만
  `progress_callback(pct, msg)`를 호출 — `remote_render_executor_func` 자신은 코드를 고치지
  않았으므로 5/15/30/50/90/100 같은 굵은 체크포인트 단위로만 보고된다(진짜 프레임 단위
  진행률이 아님 — 정직하게 문서화).
- 실패 시 `progress.txt`의 `progress=-1` 값을 확인해 `RenderPipelineError`로 변환하고,
  `render_worker.py`가 이를 잡아 `FAILED` 전이 + 재시도 로직으로 넘긴다.

## 5. 업로드 (Stage 12 로컬 어댑터)

`worker/upload_adapter.py`:
- `LocalCopyUploadAdapter` — 실제로 쓰이는 유일한 어댑터. `output.mp4`를
  `worker/state/delivered/<job_id>.mp4`로 복사.
- `GoogleDriveUploadAdapter` — 설계만 되어 있고 `NotImplementedError`. 실 연결은 다음 Task
  승인 이후.

## 6. 검증 결과

로컬 E2E 픽스처(`worker/fixture/`)로 실제 4초 720p H.264/AAC MP4(23,628 bytes)를 생성해
`worker/state/delivered/`에 전달까지 성공시켰다 — 자세한 로그와 반복 실행 결과는
[LOCAL_E2E_QA.md](./AIR_WORKER_LOCAL_E2E_QA.md) 참고.
