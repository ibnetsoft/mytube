# Picadiri Remote Drive Worker

Google Drive API 기반 원격 렌더 워커입니다. 메인 PC가 렌더 에셋 ZIP을 Google Drive에 업로드하고 Supabase 큐에 작업을 만들면, 워커 PC가 작업을 가져와 렌더링한 뒤 결과 MP4를 다시 Google Drive에 업로드합니다.

## Current Local Test Flow

1. Supabase SQL Editor에서 `remote_render_queue` 확장 SQL을 실행합니다.
2. 웹어드민 시스템 API 설정에 아래 값을 저장합니다.
   - `Google Drive API Folder ID`
   - `Google OAuth Token Path`
3. 메인 PC 렌더 페이지에서 렌더 대상 `Google Drive API`를 선택합니다.
4. 렌더 시작을 누르면 작업이 `remote_render_queue`에 `pending`으로 등록됩니다.
5. 현재 PC 또는 옆 PC에서 워커를 실행합니다.

```powershell
.\venv\Scripts\python.exe remote_drive_worker.py --check
.\venv\Scripts\python.exe remote_drive_worker.py --once
.\venv\Scripts\python.exe remote_drive_worker.py
```

## Windows Batch Runner

```powershell
.\run_remote_worker.bat
```

메뉴:

- `1`: 계속 대기하면서 작업 처리
- `2`: 설정과 대기열만 확인
- `3`: 작업 1개만 처리하고 종료

## Environment Variables

옆 PC에서는 `.env.remote-worker.example`을 참고해서 `.env`를 만들 수 있습니다.

```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
REMOTE_RENDER_WORKER_ID=render-pc-01
REMOTE_RENDER_POLL_INTERVAL=10
REMOTE_RENDER_DRIVE_FOLDER_ID=
REMOTE_RENDER_GOOGLE_TOKEN_PATH=C:/Picadiri/token.json
USE_GPU_RENDER=true
```

`REMOTE_RENDER_DRIVE_FOLDER_ID`와 `REMOTE_RENDER_GOOGLE_TOKEN_PATH`는 웹어드민 설정에서도 불러옵니다. 로컬 env 값이 있으면 env 값이 우선입니다.

## Build Windows EXE

```powershell
.\venv\Scripts\python.exe _dev\build_remote_worker.py
```

빌드 결과:

```text
dist\PicadiriRemoteWorker.exe
```

배포할 때는 EXE 옆에 `.env` 또는 실행 PC의 환경 변수를 준비해야 합니다.

## Notes

- GPU가 없어도 CPU 렌더링 테스트는 가능합니다. `USE_GPU_RENDER=false`로 둡니다.
- 현재 워커는 Supabase `remote_render_queue`의 `render_mode = drive_api`, `status = pending` 작업만 처리합니다.
- 여러 PC에서 실행할 경우 먼저 작업을 `rendering`으로 claim한 워커만 처리합니다.
