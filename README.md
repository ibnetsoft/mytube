# AIR Script Worker Source

대본 워커 전용 소스 배포 브랜치입니다. 인증 정보, 프로젝트 원본, 음성, 캐시와 작업 기록은 포함하지 않습니다.

## 설치

1. Python 3.11 이상과 Codex CLI를 설치하고 `codex login`을 실행합니다.
2. `python worker/install.py --role script`를 실행합니다.
3. `worker/connection.env.example`을 참고해 `worker/connection.env`를 로컬에서 작성합니다. 실제 연결 키는 Git에 커밋하지 않습니다.
4. Windows: `.venv-script\Scripts\python.exe -m worker.launch --role script --env-file worker/connection.env --check`
5. macOS/Linux: `.venv-script/bin/python -m worker.launch --role script --env-file worker/connection.env --check`
6. 확인 후 `--check`를 빼고 실행합니다. 로컬 콘솔은 `http://127.0.0.1:3003`입니다.

전체 제품 저장소와 분리된 소스 스냅샷이며, 실행에 필요한 공용 Python 모듈이 포함됩니다.
