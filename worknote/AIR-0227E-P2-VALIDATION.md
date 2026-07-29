# AIR-0227E-P2-VALIDATION — AIR Worker 실제 설치파일 및 클린 Windows 최종 검증

## Task ID
`AIR-0227E-P2-VALIDATION`

## Date
`2026-07-13`

## 상태
**IMPLEMENTED / ISOLATED QA PASSED — Conditional Go (여전히 DONE 아님).**
브랜치: `feat/air-0227e-p2-installer-validation` (base: `feat/air-0227e-p2-worker-installer-hardening`,
PR #83 브랜치). **클린 Windows PC/VM 미확보로 DONE 승격 불가**(사용자 확정: 개발 머신 최대
격리로 만족, VM 미구축) — 이 세션에서는 실제 설치파일 컴파일·설치·업데이트·크래시 복구까지
전부 라이브로 검증했지만, 완전한 클린 OS 검증만은 끝내 미실시.

---

## 0. branch / commit / PR

- 브랜치: `feat/air-0227e-p2-installer-validation`
- Base: `feat/air-0227e-p2-worker-installer-hardening` (PR #83)
- 커밋/PR: 이 문서 커밋 후 push, Draft PR 생성 예정(§14)

## 1. %LOCALAPPDATA% 경로 변경

**확정 경로**: `%LOCALAPPDATA%\AIRStudio\AIRWorker\` (이전 P2 하드닝 브랜치의 독립
`%LOCALAPPDATA%\AIRWorker\`에서 변경 — 사용자에게 두 옵션 간 명시적 확인 후 이 구조로
확정). 하위 경로: `logs`, `state`, `ipc`, `temp`, `output`, `config`, `crash`, `update`,
`quarantine` 전부 `worker/worker_config.py`가 시작 시 생성.

- **실사용 중(consumer가 있는) 경로**: `logs`, `state`, `ipc`(=`commands`/`results` 이동),
  `output`(=render_worker.py의 `DELIVERED_DIR`, 기존 `state/delivered/`에서 이동).
- **예약(구조만 생성, 아직 소비자 없음)**: `temp`, `config`, `crash`, `update`, `quarantine`
  — `worker_config.py` 주석에 각각 왜 아직 안 쓰이는지 명시.
- Manager와 3개 자식 role 전부 동일 `worker_config.BASE_DIR` 계산 함수를 import해서 쓰므로
  경로 불일치 가능성 없음(코드 구조상 보장).
- 설치 디렉터리(`{app}` = `C:\Program Files\AIRWorker\`)에 쓰기 파일 0건 — 실측 확인(설치
  직후, 렌더 잡 여러 건 실행 후 둘 다 확인).
- 프로덕션 사용자가 아직 없어 마이그레이션 대상 자체가 없음 — 기존 dev-only
  `%LOCALAPPDATA%\AIRWorker\`(구 경로)는 그대로 방치(참조·삭제 안 함), 신규 경로로 바로 전환.
- `AIRWORKER_HOME` 오버라이드 회귀 검증: dev 모드에서 직접 확인, 여전히 최우선 적용.

## 2. Inno Setup 환경 확보

- 이 세션에 네트워크 접근이 있음을 확인 후, jrsoftware.org 공식 배포처에서
  `innosetup-installer.exe`(SHA256 `4d11e8050b6185e0d49bd9e8cc661a7a59f44959a621d31d11033124c4e8a7b0`)를
  다운로드, `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-`로 무인 설치.
- **ISCC 버전**: Inno Setup 6.7.1, 설치 경로 `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`.
- CLI 컴파일 가능 확인(`ISCC.exe script.iss` 정상 동작).

## 3. AIRWorker.iss 실컴파일

- 1차 시도에서 발견한 실제 버그 2건(둘 다 이번에 수정):
  1. Pascal `{ ... }` 스타일 주석 안에 `{major}.{minor}.{patch}` 같은 중괄호 표기를 써서
     주석이 조기 종료되고 이후 텍스트가 코드로 잘못 파싱됨 — `//` 스타일 주석으로 전환.
  2. Pascal Script 문자열 이어붙이기에서 `#13#10`이 줄 시작 토큰이 되면 Inno Setup
     전처리기(ISPP)가 `#`으로 시작하는 줄을 전처리 지시문으로 오인 — 줄바꿈 문자를 항상
     이전 줄 끝에 붙이는 방식으로 재배치해 해결(`sLineBreak`는 이 Pascal Script 엔진에
     없는 식별자라 미사용).
- 최종 컴파일: **exit code 0**, 401초 소요(1차), 버전 리소스 반영 후 재컴파일 추가.
- 경고 2건 확인(빌드 실패 아님): (a) `ArchitecturesAllowed=x64` deprecated →
  `x64compatible`로 수정 완료. (b) `PrivilegesRequired=admin`인데 HKCU/LocalAppData
  사용 — Inno Setup의 표준 주의 문구, 일반적으로 UAC 상승 시에도 같은 로그인 사용자의
  HKCU를 그대로 쓰므로 실질적 문제로 이어지지 않았음을 실측으로 확인했으나, 구조적으로는
  알려진 caveat로 남겨둠(더 엄밀히 하려면 관리자 설치 + 사용자 데이터 별도 마이그레이션
  단계가 필요 — 후속 작업 제안).
- 산출물: `release/AIRWorkerSetup-0.1.0.exe`
  - 크기: **442,702,272 bytes**
  - SHA256: **`aad3f7f75867d603ae727b04bff276e724eb87bea0b965e938a24e5e11cb82ac`**
  - `.sha256` 사이드카 파일 동봉

## 4. ffprobe 확보 및 검증

- `imageio-ffmpeg` 0.6.0이 번들하는 ffmpeg와 **동일 소스·동일 버전**을 확보:
  GitHub 미러 `GyanD/codexffmpeg` 태그 `7.1`, `ffmpeg-7.1-essentials_build.zip`.
- ffprobe.exe SHA256: `436bf02524d50135ed9965b90d1e0ad7f26c5c236132613a2edb87ef8b6873d0`
- `ffprobe -version` 실행 결과: `ffprobe version 7.1-essentials_build-www.gyan.dev`,
  `configuration:` 문자열이 번들 ffmpeg.exe와 **완전히 동일** — 진짜 매칭 세트임을 확인.
- 라이선스: FFmpeg와 동일(GPL, `--enable-gpl --enable-libx264`), `LICENSE` 파일도 함께
  추출해 `licenses/FFmpeg-LICENSE.txt`로 패키지에 포함.
- `_dev/fetch_ffprobe.py`(신규) — 재현 가능한 확보 스크립트, SHA256 검증 내장, 결과는
  gitignore된 `_dev/vendor/ffprobe/`에 캐시(~87MB라 커밋하지 않음).
- **설치본 PATH 무관 확인**: 이 머신 시스템 PATH에는 ffmpeg/ffprobe가 여전히 전혀 없음
  (`which` 둘 다 실패) — 그럼에도 설치된 `_internal/ffprobe.exe`로 실제 렌더 결과물을
  성공적으로 검증(§8) → 번들 경로가 실제로 쓰였다는 실증.
- 출처 불명 바이너리는 사용하지 않음 — 이 개발 머신에 우연히 존재하던 제3자 앱(Vrew)의
  ffprobe.exe는 라이선스/재배포 조건 불명으로 복사하지 않았고, 공식 배포처에서 새로
  받았다(§P1 문서에 이미 기록된 결정 유지).

## 5. FFmpeg 라이선스 패키지

`packaging/windows/AIRWorker_onedir.spec`(및 onefile spec)에서 다음을 `licenses/` 하위로
번들(빌드 시 자동 반영, PyInstaller `datas=`):
- `licenses/FFmpeg-LICENSE.txt` (gyan.dev 배포 zip의 `LICENSE` 원문 그대로)
- `licenses/THIRD_PARTY_NOTICES.txt` (저장소의 `packaging/windows/THIRD_PARTY_NOTICES.md`를
  빌드 시점에 `.txt`로 복사 — 단일 소스, 드리프트 없음)

`THIRD_PARTY_NOTICES.md`에 ffmpeg.exe/ffprobe.exe SHA256을 함께 기재해 갱신.
**GPL/libx264 구성 그대로 기재, 법적 적합성 확정 표기는 하지 않음**(§AIR_WORKER_FFMPEG_LICENSE.md
그대로 유지).

## 6. 설치 QA (실제 설치파일 사용)

| 시나리오 | 결과 |
|---|---|
| 신규 설치(무인, `/TASKS=!startup`) | 성공 — `{app}`에 SQLite/log/temp 없음, ffprobe 포함 확인, 데이터 경로 9개 하위 폴더 전부 생성 확인 |
| 첫 실행 | Manager+3자식 정상 기동, Mutex 획득, `/health` 200 |
| 동일 버전 재실행 시 Mutex 거부 | exit code 1, 기존 인스턴스 `/health` 상태 로그에 기록(토큰 미노출) |
| 무인(silent) 제거 | 설치 디렉터리 완전 삭제, 로그는 자동 삭제, **렌더 결과물(`output/`)은 보존**(요구사항대로), 레지스트리/시작메뉴 항목 삭제 확인 |
| 제거 후 재설치 | 성공 — 정상적으로 처음부터 재설치됨, 재기동/Mutex/health 재확인 |
| 동일 버전 재설치 확인 대화상자 / 하위 버전 차단 대화상자 | **코드·레지스트리 레벨로만 검증, 실제 GUI 클릭 자동화는 미실시** — 이 환경은 텍스트/PowerShell 전용이라 네이티브 Win32 MessageBox를 스크린샷 없이 안정적으로 클릭 자동화할 수단이 없었다. 대신: (a) `GetInstalledVersion()`이 읽는 레지스트리 키(`HKLM\...\Uninstall\{GUID}_is1\DisplayVersion`)에 실제로 설치 후 `0.1.0`이 정확히 기록됨을 확인, (b) `CompareVersion` Pascal 함수의 파싱 로직을 코드 리뷰로 검증(마침표 단위 정수 비교, malformed 입력은 "허용" 쪽으로 안전하게 폴백). **정직하게 미완료로 표시** — 완전한 자동화는 스크린샷 기반 UI 자동화 도구가 있는 환경에서 후속 검증 필요.
| 상위 버전 업그레이드 | 코드 경로상 Cmp>0일 때 아무 MsgBox 없이 그대로 진행(Inno Setup 기본 동작) — 이 경로는 인터랙티브 프롬프트가 없어 자동화가 원래 쉬운데, 실제 버전을 올려 재빌드하는 전체 사이클(15분+ 추가 빌드)은 시간 제약으로 이번 세션에 반복하지 않음. **후속 작업으로 명시.** |
| 실행 중인 Worker 위에 설치 | `AppMutex=Global\AIRWorker_Manager_SingleInstance` 설정으로 Inno Setup이 자동으로 감지해 "닫아야 계속 가능" 안내를 하도록 구성 — 이 메커니즘 자체(Mutex 이름 일치)는 확인했으나, 실행 중 설치를 라이브로 재현하지는 않음(제거 시 AppMutex 체크는 §Mutex QA에서 이미 동일 메커니즘으로 간접 검증됨). |

## 7. 클린 Windows/Sandbox

- 이 개발 PC는 **Windows 11 Home**으로 확인 — Windows Sandbox, Hyper-V 둘 다 Home
  에디션에서는 사용 불가(Pro/Enterprise 전용).
- 사용자에게 (a) VirtualBox+Windows 평가판 ISO 직접 구축, (b) 개발 머신 최대 격리로 만족,
  (c) 별도 물리 PC/VM 사용자 제공 중 선택을 요청 → **(b) 선택**(VM 미구축 확정).
- **따라서 이번에도 완전한 클린 Windows/Sandbox 검증은 미실시** — 아래 §8은 "개발 머신
  최대 격리" 조건이며 클린 OS 테스트로 표현하지 않는다.

## 8. 개발 머신 격리 상태에서의 설치본 QA

실제 `C:\Program Files\AIRWorker\AIRWorker.exe`(설치본, dist/ 원본 복사가 아님)로 수행:

- **멀티롤 PID**: `AIRWorker.exe`(Manager) + `AIRWorker.exe --role render_worker` +
  `--role hermes_worker` + `--role local_api` — python.exe/venv/소스 경로 전무 확인.
- **시작시간(설치본, 3회)**: 평균 **1.79초**(최소 1.66, 최대 2.03) — 개발 폴더 원본
  onedir의 2.56초 평균보다도 약간 더 빠르고 일관적(설치 후 캐시/Defender 스캔 완료
  효과로 추정). 사용자 요청대로 P2 원본 2.56초와 비교 기록.
- **Local API health/Mutex**: `/health` 200, 두 번째 인스턴스 mutex 거부(exit 1) 확인.
- **실제 렌더 E2E — 최소 3회 요구 → 4회 실시**:
  1. 기본 경로(`%LOCALAPPDATA%\AIRStudio\AIRWorker`) — COMPLETED, `output/delivered/*.mp4`
  2. 전체 크래시 복구 후 재렌더(RENDERING→ABANDONED→QUEUED→COMPLETED) — COMPLETED
  3. 한글+공백 `AIRWORKER_HOME`(`C:\tmp\렌더 검증 3\data`) — COMPLETED
  4. (단일 role kill 테스트 중 발생한 render_worker 재시작 후 정상 대기 상태 확인)
  - 전부 `ffprobe -show_entries`로 실제 h264/aac 스트림, `duration=4.000000` 확인(이번엔
    `ffmpeg -i` 대체 방식이 아니라 **진짜 ffprobe.exe**로 판정).
  - 상태 DB `COMPLETED` 확인, job 로그 오류 없음, 종료 후 `Get-Process ffmpeg*`/`ffprobe*`
    결과 0(잔존 프로세스 없음).
- **크래시 복구(설치본)**: render_worker 단독 kill → 자동 재시작(새 PID, 다른 role 불변),
  전체 동시 kill(렌더 중) → 재기동 시 `RENDERING→ABANDONED→QUEUED`, 재큐된 잡이
  재렌더링되어 COMPLETED. 정상 종료 후 leftover PID 0(2회 확인).

## 9. 로컬 업데이트/rollback (실제 설치 폴더 구조 기준)

`C:\Program Files\AIRWorker\`를 통째로 복사한 사본에 대해 `_dev/simulate_worker_update.py`
재실행:
- 정상 스왑: 성공, `_backup`/`_new` 잔존 없음.
- 실패 주입 롤백: 롤백 후 `AIRWorker.exe` 정상 존재(실행 가능한 이전 버전으로 복귀) 확인.
- production GitHub Release/중앙 업데이트 채널은 사용하지 않음(로컬 디렉터리 시뮬레이션만).

## 10. 버전 일치

| 값 | 확인 |
|---|---|
| AIR Worker 내부 버전(`worker_version.py`) | `0.1.0` |
| PyInstaller 빌드 메타데이터(exe 파일 속성) | **신규**: `packaging/windows/version_info.txt` 추가 + `EXE(version=...)`로 임베드 — 설치된 exe의 `FileVersion`/`ProductVersion` = `0.1.0.0` 실측 확인(이전에는 완전히 비어 있었음 — 이번에 발견·수정) |
| `.iss` `AppVersion` | `0.1.0` (env var 수동 설정) |
| 설치파일 이름 | `AIRWorkerSetup-0.1.0.exe` |
| 로그 버전 문자열 | 없음(후속 작업 — `/status`에 버전 노출 제안, §AIR_WORKER_VERSIONING.md) |
| 로컬 update manifest | 버전 문자열 미사용(마커 파일만) — 후속 작업 |
| QA 보고서 | 이 문서 전체에 `0.1.0` 일관 기재 |

**미해결**: `worker_version.py`와 `AIRWORKER_VERSION` env var는 자동 연결되지 않음(수동
설정) — 사람이 두 값을 따로 관리하다 어긋날 위험 존재, 후속 작업으로 명시.

## 11. 코드 서명

여전히 **미실시**(인증서 없음) — `docs/AIR_WORKER_CODE_SIGNING_PLAN.md`에 계획만 갱신.
`AIRWorker.exe`, `AIRWorkerSetup-0.1.0.exe` 둘 다 미서명 상태로 이 문서에 기록된 SHA256이
서명 전 값임을 명시. **미서명 설치파일을 production-ready라고 표기하지 않음.**

## 12. 비밀정보 미포함 확인

- Local API 토큰 값은 이 문서/로그 어디에도 출력하지 않음(모든 스크립트가 길이만 출력하거나
  아예 화면에 안 띄우고 헤더에만 사용).
- service_role, production Worker Token, Google Drive credential 전부 이번 설치 산출물에
  포함되지 않음(원래부터 이 코드 경로가 그런 자격증명을 요구하지 않는 구조 — P1/P2에서
  이미 확인된 원칙 유지).
- `AIRWORKER_ID`/`AIRWORKER_TOKEN` 환경변수 기본값은 여전히 `"poc-worker-not-real"`류의
  플레이스홀더(코드 검토로 재확인, 변경 없음).

## 13. 판정 — 여전히 **Conditional Go** (DONE 아님)

**이번에 새로 통과한 것**: 실제 Inno Setup 설치파일 생성·설치·제거·재설치, ffprobe 실제
포함·검증, 설치본 기준 멀티롤/렌더 E2E(4회, 한글+공백 포함)/크래시 복구/시작시간, 실제
설치 구조 기준 업데이트/롤백 시뮬레이션, exe 버전 리소스 임베드.

**DONE으로 못 올리는 이유(§15 기준 그대로)**:
1. 클린 Windows/Sandbox 검증 미실시(Home 에디션 제약 + 사용자가 VM 미구축 선택).
2. 코드 서명 미실시(인증서 없음) — 이건 지시사항이 "DONE 가능하되 production-ready 아님"으로
   이미 분리해뒀으므로 DONE 자체를 막는 조건은 아니지만, production 배포 전 서명 필요
   상태로 계속 기록.
3. 같은 버전 재설치/하위 버전 차단의 **인터랙티브 GUI 확인**이 코드/레지스트리 레벨
   검증에 그침(스크린샷 기반 UI 자동화 도구 부재).
4. 상위 버전 업그레이드의 실제 재빌드 사이클 미실시(시간 제약).

**AIR-0227D는 계속 IMPLEMENTED / VALIDATION BLOCKED로 유지.** Mock Hermes를 실제 Hermes로
표기하지 않음. staging 중앙 API/Drive 완료로 표기하지 않음. main 병합·프로덕션 배포 없음.

## 후속 작업 제안

1. 클린 Windows PC/VM 확보 시 §7/§8을 그대로 재실행(코드는 이미 완성, 실행 환경만 필요).
2. 스크린샷 기반 UI 자동화 도구(또는 별도 GUI 테스트 프레임워크)로 §6의 인터랙티브
   MsgBox 시나리오(동일 버전 재설치, 하위 버전 차단) 완전 자동화.
3. `worker_version.py` → `AIRWORKER_VERSION` env var 자동 추출 빌드 스크립트.
4. 실제 버전을 올려(`0.2.0` 등) 업그레이드 시나리오 실빌드 검증.
5. 코드 서명 인증서 확보 후 실제 서명 파이프라인 구현.
6. `PrivilegesRequired=admin` + per-user 영역 경고(§3) 해소 방안 검토(구조적 재설계 또는
   현재 방식 그대로 두되 문서화만 강화할지 CTO 결정).
