# AIR Worker — 업데이트 전략

- 상태: **설계안 / CTO 승인 대기**
- 관련 문서: [ARCHITECTURE](./AIR_WORKER_ARCHITECTURE.md), [PROCESS_MODEL](./AIR_WORKER_PROCESS_MODEL.md)

## 0. 출발점: 지금은 업데이트가 아예 없다

Stage 1 조사 결과, 현재 원격 워커는 업데이트 메커니즘이 **전혀 없다** — 완전 수동 재빌드 +
수동 배포. 이 문서는 "기존 걸 개선"이 아니라 "처음 만드는" 설계다. 반면 AIR Studio(메인
데스크톱 앱)는 이미 검증된 원자적 스왑/롤백 업데이터(`services/updater_service.py` +
`packaging/windows/launcher/AIRUpdater.py`)를 갖고 있다 — **그 원칙을 재사용**하되, 설치
경로와 배포 채널은 AIR Studio와 **완전히 분리**한다(핵심 원칙 그대로).

## 1. 독립 업데이트 가능 모듈

```
launcher        - AIRWorkerLauncher.exe (AIR Studio의 AIRLauncher.exe에 대응)
worker-manager  - Worker Manager 본체
render-runtime  - Render Worker Process가 쓰는 렌더링 파이프라인 코드/의존성
hermes-runtime  - Hermes Worker Process 코드/의존성
local-api       - Local API 프로세스
ui              - 관리 UI(CLI 상태 화면 또는 향후 GUI)
config          - 재시작 정책 임계값 등 로컬 설정(§PROCESS_MODEL §3)
```

각 모듈을 독립적으로 업데이트 가능하게 하는 이유: `render-runtime`에 버그가 생겨도
`hermes-runtime`을 건드리지 않고 그것만 롤백/재배포할 수 있어야 하고, 반대의 경우도
마찬가지 — §ARCHITECTURE §3의 "한쪽 죽어도 한쪽 안 죽는다"는 프로세스 격리 원칙을
**업데이트 시점에도 동일하게 지킨다.**

## 2. AIR Studio Updater 원칙 재사용 + 분리

| 재사용하는 것 (AIRUpdater.py에서 검증된 패턴) | AIR Worker에서 분리하는 것 |
|---|---|
| SHA256 재검증 | 설치 경로: `%LOCALAPPDATA%\AIRWorker\` (AIR Studio의 `%LOCALAPPDATA%\AIRStudio\`와 별도) |
| `app/`→`app_backup/`→`app_new/`→`app/` 원자적 NTFS rename 스왑 | 배포 채널: 별도 GitHub Release 저장소/태그 프리픽스(예: `ibnetsoft/AIR-Worker-releases` 또는 동일 저장소 내 `airworker-v*` 태그 — 정확한 선택은 CTO 결정) |
| `current.json`/`version.json` 버전 기록 | 업데이트 매니페스트(`latest.json`류)도 AIR Worker 전용으로 별도 발행 — AIR Studio의 `latest.json`과 절대 같은 파일/URL을 쓰지 않는다(교차 오염 방지) |
| 구조화 로그(`[EVENT]` 태그, `updater.log`) | 로그 경로도 `%LOCALAPPDATA%\AIRWorker\logs\updater.log`로 독립 |

## 3. 모듈별 업데이트 흐름

1. AIR Worker Launcher가 각 모듈의 매니페스트(버전+체크섬+다운로드 URL)를 주기적으로 조회.
2. 업데이트가 있는 모듈만 선택적으로 다운로드 — 예: `hermes-runtime`만 바뀌었으면
   `render-runtime`은 건드리지 않음(전체 재설치가 아닌 모듈 단위 델타 업데이트).
3. 다운로드한 모듈을 격리된 임시 디렉터리에 풀고 SHA256 검증.
4. 검증 통과 시에만 해당 모듈 디렉터리를 원자적 rename으로 교체.
5. Worker Manager가 교체된 모듈의 프로세스만 재시작(다른 모듈/프로세스는 그대로 유지 — 이게
   가능하려면 §PROCESS_MODEL의 "각 하위 프로세스는 독립적으로 시작/중지 가능"이 반드시
   선행되어야 함, 두 문서가 서로 전제 조건이다).

## 4. 업데이트 실패 시 (요구사항 그대로)

- **기존 버전 유지**: 원자적 rename이라 "절반만 업데이트된" 상태가 나올 수 없음 — 실패하면
  교체 자체가 일어나지 않고 이전 버전이 계속 실행 중.
- **모듈별 롤백**: 교체 직후 헬스체크(새 프로세스가 정상 기동하는지)에 실패하면 `_backup`
  디렉터리로 즉시 되돌린다(AIRUpdater의 `app_backup` 패턴을 모듈 단위로 확장).
- **로그 기록**: 실패 사유를 `updater.log`에 `[EVENT] UPDATE_FAILED module=... reason=...`
  형태로 기록.
- **중앙 서버 상태 보고**: Worker Token 권한 범위 안에서 "이 워커의 업데이트가 실패했다"는
  상태를 보고(§SECURITY §1의 "heartbeat 전송" 권한 범위로 충분 — 별도 권한 신설 불필요).

## 5. 빌드 파이프라인 (Stage 1의 이름 불일치 문제 재발 방지)

Stage 1에서 `PicadiriRemoteWorker.spec`과 `_dev/build_remote_worker.py`가 서로 다른 이름의
exe를 만드는 불일치를 발견했다. AIR Worker는 **처음부터 단일 `.spec` 파일 + 단일 빌드
스크립트**로 시작해 이 혼란을 재현하지 않는다 — AIR Studio의 `tools/build_windows.ps1` +
`packaging/windows/AIRStudio.spec` 체계를 그대로 본떠 `tools/build_airworker.ps1` +
`packaging/airworker/AIRWorker.spec` 형태로 신설하는 것을 제안(정확한 경로/이름은 실 구현
단계에서 확정).

## 6. 이번 Task 범위

이번 Task(#12 스켈레톤)는 업데이트 메커니즘을 **실제로 구현하지 않는다** — 위 설계만 확정.
스켈레톤의 Auto Updater 프로세스(§PROCESS_MODEL §1)는 "독립 프로세스로 존재하고 시작/중지가
된다"는 것만 모의로 보여주고, 실제 다운로드/스왑 로직은 다음 Task로 분리 제안.
