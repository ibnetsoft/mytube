# AIR 워커 구성

대본 워커는 독립 실행형입니다. 로컬 미디어 워커는 입 위치 준비·AE·최종 렌더를 한 관리 프로그램에서 순서대로 실행합니다. 기존 큐와 검수 검증을 유지하며 관리자 게시·YouTube 업로드는 실행하지 않습니다.

## 다른 컴퓨터에 대본 워커 설치

1. `python scripts/build_script_worker_bundle.py`로 만든 `AIR-script-worker.zip`을 해당 컴퓨터에 복사해 쓰기 가능한 폴더에 압축 해제합니다. 인증 정보와 프로젝트 원본·음성·캐시는 포함되지 않습니다.
2. Python 3.11 이상과 Codex CLI를 설치하고 `codex login`으로 인증합니다.
3. 해당 폴더에서 `python worker/install.py --role script`를 실행합니다. Windows에서는 `scripts/install_script_worker.ps1`도 사용할 수 있습니다.
4. 생성된 `worker/connection.env`에 관리자가 발급한 신뢰된 워커 연결 정보를 해당 컴퓨터에서 직접 입력합니다. 실제 키가 들어간 파일을 배포·커밋하지 마세요.
5. `.venv-script/Scripts/python.exe -m worker.launch --role script --env-file worker/connection.env --check`로 확인합니다. Linux/macOS에서는 `.venv-script/bin/python`을 사용합니다.
6. 같은 명령에서 `--check`를 빼고 실행합니다. 콘솔은 `http://127.0.0.1:3003`입니다. 대본·번역은 로컬 Codex CLI를 사용합니다. AE 설치는 필요 없습니다.

설치 과정은 기존 연결 설정·작업 기록을 삭제하지 않습니다. `AIRWORKER_HOME`으로 상태·캐시 위치를 별도로 둘 수 있습니다. 범용 사용자 로그인만으로 서버 권한이 자동 발급되지는 않으며 기존 신뢰된 워커 연결 권한이 필요합니다.

## 로컬 미디어 워커

Windows·After Effects·렌더 의존성이 설치된 컴퓨터에서 `scripts/start_local_media_worker.ps1` 또는 `python -m worker.launch --role local`을 실행합니다. 새 환경 설치는 `python worker/install.py --role local`입니다. 기존 개별 워커는 현재 작업이 끝난 뒤 종료합니다. 다른 워커 또는 aerender/FFmpeg가 실행 중이면 통합 워커는 리소스가 비워질 때까지 기다립니다.

상태 화면: `http://127.0.0.1:3004`. CLI: `python -m worker.local_media_supervisor --status`. 로그: `AIRWORKER_HOME/logs/local-media`. 무거운 작업은 별도 숨김 프로세스에서 하나씩 실행합니다. 역할별 프로세스가 3회 연속 실패하면 해당 역할을 차단합니다. 원본·음성·이전 결과와 승인·지문 검증은 유지됩니다.

`--stop`은 현재 작업을 끝내고 종료합니다. `--pause-render`는 렌더 큐 소비만 중지하고 `--resume-render`는 재개합니다. 기존 큐를 삭제하거나 추가하지 않습니다. 기존 하이라이트 작업은 `--enable-highlight`로 명시적으로 활성화한 경우만 처리합니다.

최종 렌더 자동 제출 예약과 로컬 큐 실행기는 별개입니다. 예약 중지는 실행기를 시작한다고 해제되지 않습니다.
# 통합 미디어 워커 화면

로컬 워커 실행 후 http://127.0.0.1:3004/ 에서 큐 대기, 진행 중, 검수 필요,
완료, 실패 상태와 프로젝트별 작업을 확인할 수 있습니다. 프로젝트 이름 검색과
상태 필터를 지원합니다. AE는 대상·분석·검수 완료 씬 수를, 렌더는 큐에 저장된
실제 진행률을 표시합니다. 프로세스 종료만으로 작업을 성공 처리하지 않습니다.
최근 작업은 최대 200건을 조회하며 DB 조회는 15초 간격으로 제한됩니다.
연결 실패 시 마지막 정상 조회 결과와 조회 시각을 표시합니다.
이 화면은 읽기 전용이며 작업 승인·렌더 예약을 실행하지 않습니다.
