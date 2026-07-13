# AIR Worker — 버전 단일 공급원 검토 (AIR-0227E-P2 §15)

- 상태: **검토 완료, `worker/worker_version.py` 신규 도입**

## 결론

AIR Worker는 **`version.py`(AIR Studio Desktop의 `APP_VERSION`)를 공유하지 않고, 독립적인
자체 버전 소스 `worker/worker_version.py::WORKER_VERSION`을 새로 둔다.**

## 근거

1. **지시사항의 명시적 금지** — "AIR Studio Desktop 설치·업데이트 채널과 혼합 금지"라는
   조건이 이미 있다. `version.py`를 공유하면 AIR Studio를 릴리스할 때마다 AIR Worker
   버전이 같이 올라가거나, 반대로 AIR Worker만 릴리스하려 해도 `version.py`를 건드려야
   해서 AIR Studio 릴리스 노트/빌드 번호와 뒤섞인다 — 바로 이 지시사항이 막으려는 상황이다.
2. **배포 대상이 다르다** — AIR Studio는 일반 사용자 데스크톱(`{localappdata}\AIRStudio`,
   관리자 권한 불필요)에, AIR Worker는 전용 렌더링 PC(`{autopf}\AIRWorker`, 관리자 권한
   필요, §P2-5)에 배포된다. 서로 다른 운영 주체(일반 사용자 vs 렌더링 PC 운영자)가
   서로 다른 시점에 업데이트를 적용할 수 있어야 한다.
3. **기존 `tools/build_windows.ps1`이 이미 `version.py`를 "AIR Studio 전용" 파일로 취급**
   하고 있다(`AIR_VERSION` env var로 주입, `AIRStudio.iss`가 그 값을 읽음) — 이름 그대로
   AIR Studio만을 위한 파일이라, AIR Worker가 여기 얹혀가는 것 자체가 기존 관례에도 안 맞는다.

## 구현

- `worker/worker_version.py` (신규): `WORKER_VERSION = "0.1.0"` — AIR Worker만의 단일 공급원.
- `packaging/windows/AIRWorker.iss`: `AIRWORKER_VERSION` 환경변수로 버전을 주입받음(빌드
  스크립트가 `worker/worker_version.py`를 읽어 이 env var를 채워주는 것을 후속 작업으로
  제안 — 이번 PoC는 수동으로 env var를 설정해 인스톨러를 빌드하는 것까지만 확인, 자동 추출
  스크립트는 미구현).
- 두 버전 소스(`version.py`의 `APP_VERSION`, `worker/worker_version.py`의 `WORKER_VERSION`)는
  **서로 독립적으로 증가**하며 어느 쪽도 다른 쪽을 참조/의존하지 않는다.

## 후속 작업 (이번 PoC 범위 밖)

- `worker/worker_version.py`를 읽어 `AIRWORKER_VERSION` env var를 자동 설정하는 빌드
  스크립트 보강(`tools/build_windows.ps1`과 유사한 AIR Worker 전용 빌드 스크립트,
  `_dev/build_worker.py`를 확장하거나 별도 `tools/build_worker_windows.ps1` 신설 검토).
- Manager의 `/status` 응답에 `WORKER_VERSION`을 노출해 운영 중 어떤 버전이 떠 있는지
  원격에서 확인 가능하게 하는 것(CTO 승인 시).
