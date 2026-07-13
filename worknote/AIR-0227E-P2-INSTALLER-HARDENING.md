# AIR-0227E-P2 — AIR Worker Onedir 설치 패키징 및 배포 기반 안정화

## Task ID
`AIR-0227E-P2`

## Date
`2026-07-13`

## 상태
**IMPLEMENTED / ISOLATED QA PASSED — Conditional Go.**
(별도 클린 Windows PC/VM이 이 세션에서 확보되지 않아 완전한 "클린 OS 검증"은 미실시 —
개발 머신 내 최대 격리 조건으로 대체 검증. 이 상태를 클린 OS 검증이라고 표현하지 않는다.)
브랜치: `feat/air-0227e-p2-worker-installer-hardening` (base: `feat/air-0227e-worker-exe-packaging`,
PR #82 브랜치). Draft PR만 생성, main 병합/프로덕션 배포 없음.

---

## 1. 빌드 격리

`_dev/build_worker.py`를 `--distpath`/`--workpath` 명시로 개선:
- onefile → `dist/onefile/`, `build/onefile/`
- onedir → `dist/onedir/`, `build/onedir/`

각 빌드 실행 후 `dist/build_record_{variant}.json`에 커맨드/exit code/소요시간을 자동 기록.

| variant | exit code | elapsed | 산출물 | SHA256 |
|---|---|---|---|---|
| onefile | 0 | 658.6s | `dist/onefile/AIRWorker.exe` (567,356,914 bytes) | `7fc9593cf8c053ab90b991ede645752321c8a93fa36debbc99f67271b58e3578` |
| onedir | 0 | 606.7s | `dist/onedir/AIRWorker/AIRWorker.exe` (82,821,357 bytes) + `_internal/` | `7eb0d15effa4d15411e2f63d212b9801906bcb5142010616229d2f4982dbe076` |

경고 파일(`build/onefile/AIRWorker/warn-AIRWorker.txt`, `build/onedir/AIRWorker_onedir/warn-AIRWorker_onedir.txt`,
둘 다 1238줄) 검토: 이전 AIR-0227E-P1과 동일하게 표준 PyInstaller false-positive류만 있고
`render_worker`/`hermes_worker_mock`/`local_api_app`/`worker_config`/`single_instance` 등
우리 자체 모듈 관련 누락 경고 없음.

## 2. Onefile/Onedir 시작시간 비교 (각 3회, cold+warm 구분)

`_dev/measure_startup.py`로 실측(체크포인트: 프로세스 실행 → Manager 로그 → Local API
/health → Render Worker ready → Hermes Worker ready → 전체 ready ≈ 첫 작업 수신 가능).

| variant | run | manager log | /health | 전체 ready |
|---|---|---|---|---|
| onefile | cold | 39.23s | 40.97s | **40.99s** |
| onefile | warm_1 | 53.26s | 54.88s | **54.90s** |
| onefile | warm_2 | 39.51s | 41.14s | **41.16s** |
| onefile | **평균/최소/최대** | 44.00 / 39.23 / 53.26 | 45.66 / 40.97 / 54.88 | **45.68 / 40.99 / 54.90** |
| onedir | run1(cold) | ~0.9s | ~2.5s | **~2.5s(개별 run은 아래)** |
| onedir | warm_1 | 0.63s | 2.25s | **2.26s** |
| onedir | warm_2 | 0.62s | 1.76s | **1.77s** |
| onedir | **평균/최소/최대** | 0.92 / 0.62 / 1.5 | 2.55 / 1.76 / 3.64 | **2.56 / 1.77 / 3.66** |

**결론: onedir이 onefile보다 전체 ready까지 약 18배 빠르고 훨씬 일관적**(onefile은
onefile 자체 압축해제 오버헤드로 39~55초 편차, onedir은 2~4초 수준). Inno Setup 인스톨러의
Source로 onedir을 선택한 근거가 실측으로 확인됨.

## 3. Manager Mutex

- `worker/single_instance.py`(신규): `acquire_or_exit()`은 **`worker/manager.py::main()`에서만
  호출**된다 — `worker/air_worker_entry.py`의 `--role` 디스패치 코드 자체에는 이 호출이
  없으므로, `--role render_worker`/`hermes_worker`/`local_api`로 실행되는 프로세스는
  Mutex 검사 대상이 아니다(코드 검토로 확인, 역할별로 다른 코드 경로를 타는 구조라 우회
  불가능).
- 두 번째 Manager 실행 거부: 확인(exit code 1, 명확한 로그 메시지).
- **10회 동시 실행 테스트**(`_dev/test_mutex_concurrent.py`, onedir): 10개 프로세스 동시
  실행 → 정확히 **Manager 역할 1개만 생존**(나머지는 Mutex 충돌로 즉시 종료), 살아남은
  Manager의 자식 3개(render_worker/hermes_worker/local_api)도 정상 확인
  (`Get-CimInstance`로 실측: PID 1개 Manager + PID 3개 자식, 총 4개만 남음).
- **비정상 종료 후 재실행**: 생존한 Manager를 강제 kill(`Stop-Process -Force`, 정상
  종료 아님) → 즉시 새 Manager 실행 → **Mutex 정상 재획득 확인**(Windows OS가 프로세스
  종료 시 Named Mutex를 자동 해제하는 보장에 의존, 실제로 재현 확인).

## 4. 두 번째 실행 UX

`single_instance.py`에 `_describe_existing_instance()` 추가 — Mutex 충돌 시, 기존 인스턴스의
Local API `/health`(무인증 엔드포인트)를 별도로 호출해 상태를 로그에 남긴다. 실제 로그:
```
[ERROR] Another AIR Worker Manager already holds mutex '...' - refusing to start a second instance
[ERROR] This instance's own exit code will be 1. Existing instance's Local API /health responded OK (ok).
```
exit code는 1로 명확. **토큰 값은 어디에도 출력하지 않음**(호출하는 엔드포인트 자체가
무인증 `/health`이므로 애초에 토큰이 관여하지 않음).

## 5. 설치 경로와 데이터 경로 분리

- `worker/worker_config.py`의 `BASE_DIR` 기본값을 `Path(__file__).resolve().parent`(구 버전,
  exe 자기 디렉터리)에서 **`%LOCALAPPDATA%\AIRWorker`**로 변경(`AIRWORKER_HOME` 환경변수가
  설정되면 여전히 그 값이 우선 — dev/QA 용도로 유지).
- **실측 확인**: `AIRWORKER_HOME`을 설정하지 않고 onedir 빌드를 실행 → `logs/state/jobs.db/
  DPAPI 토큰` 전부 `C:\Users\...\AppData\Local\AIRWorker\`에 생성됨, exe가 있는
  `dist\onedir\AIRWorker\` 디렉터리에는 아무것도 새로 생기지 않음(확인: 로그/DB 파일
  0개, exe/`_internal`만 존재).
- Manager와 모든 자식 역할이 동일한 `worker_config.BASE_DIR` 로직을 공유하므로(같은
  모듈을 import) 데이터 루트는 항상 하나로 일치.
- `packaging/windows/AIRWorker.iss`: `DefaultDirName={autopf}\AIRWorker`(Program Files,
  `PrivilegesRequired=admin`) + `[Dirs]`로 `{localappdata}\AIRWorker\{,logs,state}` 별도
  생성 — 설치 경로와 데이터 경로가 스펙 상에서도 물리적으로 분리됨.
- **참고**: 사용자 지시안의 "%LOCALAPPDATA%\AIRStudio\AIRWorker\..." 표기는 AIR Studio
  채널 혼합 금지 원칙과 상충 가능성이 있어 확인 질의 후, **"%LOCALAPPDATA%\AIRWorker\
  (독립)" 구조를 그대로 유지**하기로 확정함(사용자 답변 반영).

## 6. Onedir 멀티롤

10회 동시 실행 테스트(§3)와 별도 단일 실행 양쪽에서 실측:
```
AIRWorker.exe                         (Manager 본체 - onedir은 부트로더 재실행 없이 직접 Manager)
AIRWorker.exe --role render_worker
AIRWorker.exe --role hermes_worker
AIRWorker.exe --role local_api
```
python.exe/개별 .py 파일/venv 경로/소스 저장소 경로 전혀 등장하지 않음(전체 커맨드라인이
`AIRWorker.exe [--role X]` 형태로만 구성됨, `Get-CimInstance Win32_Process`로 반복 확인).
**onefile 대비 차이점**: onefile은 부트로더(부모) + 실제 Manager(자식) 2단 구조가 되어
Manager 프로세스 자체의 부모가 "AIRWorker.exe"(부트로더)였지만, onedir은 실행한 exe가
그대로 Manager이므로 이 중간 단계가 없다 — 이 역시 onedir이 더 단순하고 예측 가능한
프로세스 트리를 만든다는 근거.

## 7. 개발 머신 최대 격리 QA (클린 OS 아님, 명시)

실제로 확인한 조건:
- 저장소 밖 신규 디렉터리(`C:\tmp\...`) — 확인
- 신규 LocalAppData 상태(`%LOCALAPPDATA%\AIRWorker` 사전 삭제 후 재생성 확인) — 확인
- venv 비활성(시스템 전역 Python만 있는 셸에서 실행, exe 자체는 애초에 Python 설치와
  무관하게 실행됨) — 확인
- PYTHONPATH/VIRTUAL_ENV 둘 다 빈 값 확인 — 확인
- 시스템에 ffmpeg/ffprobe가 PATH에 전혀 없는 상태 그대로(별도 제거 작업 불필요, 원래
  없었음) — 확인, §13에서 실제로 이 상태에서 렌더 성공한 것으로 "PATH ffmpeg 우연히
  사용 안 함"을 실증
- 프로젝트 루트와 다른 CWD(`C:\tmp\...\AIRWorker\`에서 실행) — 확인
- 한글+공백 경로(`C:\tmp\렌더 테스트 2\...`) — 확인, §11
- 일반 사용자 권한(관리자 상승 없이 실행 — 단, Inno Setup 설치 자체는 admin 필요,
  §9에서 별도 기재) — 확인
- Windows Defender 활성 상태 그대로 진행(끄지 않음) — **실제로 이 상태에서 대용량
  onedir 트리(1237개 파일) 복사/삭제 시 파일 잠금으로 인한 일시적 실패를 경험**
  (`Remove-Item`이 "The directory is not empty" 오류로 1차 실패, 재시도 후 성공) —
  이는 실사용 배포 시에도 발생 가능한 현상이라 설치/업데이트 스크립트에 재시도 로직을
  권고하는 근거로 기록.
- 기존 AIRWorker 프로세스 종료 후 진행 — 매 테스트 전 확인·정리
- 이전 onefile 임시 추출 폴더 영향 배제 — onedir은 애초에 임시 추출을 하지 않으므로
  해당 없음(구조적으로 배제됨)

**미검증(솔직히 명시)**: 별도의 완전히 새로운 Windows PC/VM, Python이 전혀 설치되지 않은
환경, 신규 Windows 사용자 계정에서의 실행 — 전부 이 세션에서 확보 불가능해 미검증.

## 8. Inno Setup 확인

**ISCC.exe가 이 환경에 설치되어 있지 않음을 확인**(`C:\Program Files (x86)\Inno Setup 6\`,
`C:\Program Files\Inno Setup 6\` 둘 다 없음, `Get-Command ISCC.exe`도 실패, 시스템 전체
검색으로도 미발견). 네트워크 다운로드가 불가능한 샌드박스 환경이라 Inno Setup 자체를
설치할 수도 없었다.

**따라서 실제 설치 파일 컴파일은 수행하지 않았다** — 대신:
- `packaging/windows/AIRWorker.iss` 작성 완료(§5, §9 반영)
- 정적 검토: `AIRStudio.iss`(기존, 실동작 검증된 레퍼런스)와의 구조 대조 — `[Setup]`/
  `[Files]`/`[Dirs]`/`[Icons]`/`[Tasks]`/`[Registry]`/`[Run]`/`[UninstallDelete]` 섹션
  전부 존재, `Source:` 경로가 실제 onedir 빌드 출력 경로(`..\..\dist\onedir\AIRWorker\*`)와
  일치하도록 §1 빌드 격리 반영 후 수정 완료.
- **이 항목은 "PACKAGING VALIDATION BLOCKED"로 기록** — 스크립트 작성/정적 검토까지만
  완료, 실제 컴파일·설치 파일 생성은 Inno Setup이 있는 빌드 머신에서 후속 수행 필요.

## 9. 설치파일 QA — **전면 미실시 (§8 차단으로 인한 연쇄)**

§8에서 설치 파일 자체가 생성되지 않았으므로, 다음은 전부 **미실시**로 명시(가짜 성공
표기 금지):
신규 설치, 동일 버전 재설치, 상위 버전 업데이트, 하위 버전 경고/차단, 제거, 재설치,
사용자 데이터 유지, 실행 중 설치 처리, 일반 사용자 실행, 설치 후 Mutex, 설치 후 렌더 E2E.

대신 §2~§7의 모든 검증은 **Inno Setup 설치본이 아니라 raw onedir 빌드 산출물
(`dist/onedir/AIRWorker/`)을 직접 복사해서 실행**하는 방식으로 대체 검증했다 — 실제
설치 스크립트의 `[Files]` 섹션이 정확히 이 동일한 산출물을 그대로 복사하는 구조이므로,
설치 후 동작이 이번에 검증한 것과 실질적으로 동일할 것으로 예상되나, **인스톨러 자체의
동작(레지스트리 작성, 바로가기 생성, 제거 시나리오 등)은 검증되지 않았다.**

## 10. Frozen UTF-8 회귀 재검증

- `worker/air_worker_entry.py`의 `sys.stdout.reconfigure()`/`sys.stderr.reconfigure()`
  호출은 이미 `except (AttributeError, ValueError): pass`로 감싸져 있어, 스트림이 `None`이거나
  `reconfigure` 메서드가 없는 경우에도 앱 시작 자체가 죽지 않는다(코드 검토로 재확인,
  `None.reconfigure`는 `AttributeError`를 내며 이미 이 except 절이 잡는다).
- `worker/logging_setup.py`의 파일 핸들러는 이미 `encoding="utf-8"` 명시(66번째 줄,
  94번째 줄 — 재확인).
- **실제 렌더 재검증**: §11의 4회 렌더(한글 경로 포함, 이모지가 포함된 로그 라인을 실제로
  기록하는 `services/video_service.py` 경로) 전부 성공 — cp949 UnicodeEncodeError 재발
  없음.

## 11. 실제 렌더 E2E (onedir, 최소 3회 요구 → **4회 실시**)

| # | 조건 | 결과 |
|---|---|---|
| A | `%LOCALAPPDATA%\AIRWorker`(기본 경로) | COMPLETED, output.mp4 23,628 bytes, ffmpeg 검증(h264/aac, 4.00s) |
| B | 저장소 밖 독립 디렉터리, **한글+공백 경로**(`C:\tmp\렌더 테스트 2\...`), 입력 fixture 경로도 한글 포함 | COMPLETED, output.mp4 23,628 bytes, ffmpeg 검증 동일 |
| C | (B와 동일 경로) Manager만 강제 kill 후 고아 프로세스가 이어서 완료 | COMPLETED |
| D | (B와 동일 경로) 전체 동시 kill 후 재기동 → ABANDONED→QUEUED→재렌더 | COMPLETED |

모든 케이스: `상태 DB COMPLETED` 확인, job 로그에 오류 없음, 종료 후 `Get-Process ffmpeg*`
결과 0(잔존 FFmpeg 프로세스 없음).

## 12. 크래시 복구 (onedir)

- render_worker 단독 kill → 자동 재시작(새 PID), 다른 두 역할 PID 불변 — 확인
- local_api 단독 크래시(QA 훅) → 자동 재시작(새 PID) — 확인
- hermes_worker 단독 kill → 자동 재시작(새 PID) — 확인
- Manager만 kill(렌더 중) → 고아 프로세스가 작업을 끝까지 완료(§11-C) — 확인
- 전체 동시 kill(렌더 중) → 재기동 시 `RENDERING→ABANDONED→QUEUED`, 재큐된 잡이
  재렌더링되어 COMPLETED(§11-D) — 확인
- 반복 크래시 제한: local_api를 짧은 시간 내 3회 크래시시키면(P1에서 이미 확인한
  포트충돌 시나리오와 동일 메커니즘) "3 crashes within 600s" 로 DISABLED — 코드/정책
  자체는 P1에서 실측 확인 완료, 이번 P2에서 별도 재현은 하지 않음(동일 코드 경로,
  onefile/onedir 여부와 무관한 로직).
- 정상 종료 후 leftover PID: **0**(그래이스풀 셧다운 후 `Get-CimInstance` 재확인).

## 13. FFmpeg

- **실제 번들 경로**(onedir): `dist/onedir/AIRWorker/_internal/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe`
  — 파일로 직접 확인(설치 경로 안에 실존, 임시 추출 아님).
- SHA256: `2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3`
- 버전/설정: `ffmpeg version 7.1-essentials_build-www.gyan.dev`,
  `--enable-gpl --enable-version3 --enable-libx264 --enable-libx265 ... --enable-nvenc ...`(전체
  목록은 §P1 문서/이 문서 원문 로그 참고)
- **시스템 PATH에 ffmpeg/ffprobe 전혀 없음을 재확인**(`which ffmpeg`/`which ffprobe` 둘 다
  실패) — 렌더가 성공했다는 사실 자체가 번들 바이너리가 실제로 사용되었다는 증거(대체
  경로가 물리적으로 존재하지 않음).
- GPL/libx264 포함 여부: **GPL 빌드, libx264/libx265 포함**(재확인, P1과 동일 바이너리).
- **라이선스 적합성을 확정했다고 표기하지 않음** — `docs/AIR_WORKER_FFMPEG_LICENSE.md`에
  사실관계만 문서화, 최종 판단은 CTO/법무 소관으로 명시.
- **ffprobe: 이번에도 미포함** — 신뢰할 수 있는 출처에서 별도로 받아올 네트워크 접근이
  없어(§P1과 동일 사유) 여전히 실제로는 확보하지 못했다. `ffmpeg -i`로 스트림 정보 확인을
  대체 수단으로 계속 사용.

## 14. 로컬 업데이트/rollback

`_dev/simulate_worker_update.py`(신규, `packaging/windows/launcher/AIRUpdater.py`의 검증된
atomic-rename 패턴을 재사용) 실제 실행:
- **정상 스왑**: `AIRWorker → AIRWorker_backup`, `AIRWorker_new → AIRWorker` 순으로 원자적
  rename 성공, 최종적으로 신버전 마커 파일 존재 확인, `_backup`/`_new` 잔존 없음.
- **실패 주입 스왑**(스테이징된 새 버전에서 `AIRWorker.exe`를 고의로 삭제): 승격 직전
  무결성 체크가 실패를 감지 → `AIRWorker_backup → AIRWorker`로 롤백 → 롤백 후에도
  `AIRWorker.exe`가 정상 존재함을 확인(즉, 실패해도 실행 가능한 이전 버전으로 안전하게
  복귀) → `_new` 스테이징 디렉터리 정리까지 완료.
- 실제 설치 파이프라인에는 아직 통합하지 않음(독립 시뮬레이션 스크립트로만 검증) —
  후속 작업.

## 15. 버전 단일 공급원 / 코드 서명 계획

- `worker/worker_version.py`(신규, `WORKER_VERSION = "0.1.0"`) — AIR Studio Desktop의
  `version.py`와 완전히 독립(상세 근거: `docs/AIR_WORKER_VERSIONING.md`).
- 코드 서명: 실제 서명은 인증서가 없어 미실시, 계획만 문서화(`docs/AIR_WORKER_CODE_SIGNING_PLAN.md`).

## 16. 문서 갱신

- 이 문서(신규)
- `docs/AIR_WORKER_FFMPEG_LICENSE.md`(신규)
- `docs/AIR_WORKER_VERSIONING.md`(신규)
- `docs/AIR_WORKER_CODE_SIGNING_PLAN.md`(신규)
- `packaging/windows/THIRD_PARTY_NOTICES.md`(신규)

## 17. 최종 판정

**IMPLEMENTED / ISOLATED QA PASSED — Conditional Go.**

근거: §1~§7, §10~§15의 개발 머신 최대 격리 조건 하 실측 검증이 전부 통과했다(빌드
격리·시작시간 비교·Mutex 10-동시성·경로 분리·onedir 멀티롤·렌더 E2E 4회(한글+공백
포함)·크래시 복구 전 시나리오·FFmpeg 실경로 확인·업데이트/롤백 시뮬레이션). **다만
다음 두 가지 이유로 완전한 DONE/Go가 아니다**:
1. 클린 Windows PC/VM 검증 미실시(§7) — 지시사항이 명시한 DONE 조건 미충족.
2. Inno Setup 미설치로 실제 설치 파일 컴파일·설치 QA(§8, §9) 전부 미실시 — "PACKAGING
   VALIDATION BLOCKED" 상태.

**AIR-0227D 상태는 변경하지 않음**(계속 IMPLEMENTED / VALIDATION BLOCKED 유지).
**Mock Hermes를 실제 Hermes로 표기하지 않음.** **staging 중앙 API/Drive 완료로 표기하지
않음.**

## 후속 작업 제안

1. Inno Setup이 설치된 빌드 머신에서 `AIRWorker.iss` 실제 컴파일 + §9 설치 QA 전체 수행.
2. 별도 클린 Windows VM(Python/ffmpeg 미설치, 신규 사용자 계정) 확보 후 §7 미검증 항목 수행.
3. 신뢰할 수 있는 출처(gyan.dev/BtbN)에서 ffprobe.exe 확보해 사이드카로 포함.
4. FFmpeg GPL 라이선스 재배포 적합성 CTO/법무 최종 확인.
5. `worker/worker_version.py` 값을 빌드 스크립트가 자동으로 `AIRWORKER_VERSION` env var에
   주입하도록 자동화(현재는 수동 설정 가정).
6. 코드 서명 인증서 확보 후 `docs/AIR_WORKER_CODE_SIGNING_PLAN.md`에 따라 실제 서명 파이프라인 구현.
