# AIR-0227E-P1 — AIR Worker Frozen EXE 패키징 PoC

## Task ID
`AIR-0227E-P1`

## Date
`2026-07-13`

## 상태
**PoC 완료 — Go (아래 §15 판정 근거 참고).** 브랜치: `feat/air-0227e-worker-exe-packaging`
(base: `feat/air-0227d-worker-central-drive-e2e`). 최종 검증 통과 후 커밋·push·Draft PR
진행(§14). **main 병합 안 함, 프로덕션 배포 아님.**

---

## 0. 범위 확인

- 이번 Task는 `feat/air-0227d`에 이미 있던 Manager+실제 Render Worker+Mock Hermes
  Worker+Local API를 **하나의 실행파일(`AIRWorker.exe`)로 패키징**하는 것만 다룬다.
- 주제 생성 실시간 호출 전환, 실 Hermes 연동, 설치 프로그램, 자동 업데이트, 실 Drive,
  실 중앙 API는 전부 **이번 범위 밖** — §16에서 다시 명시.

## 1. 클린 빌드 결과

```
rm -rf build dist
python -m PyInstaller --noconfirm --clean packaging/windows/AIRWorker.spec
```
- Exit code: **0**
- 산출물: `dist/AIRWorker.exe`, **567,354,123 bytes**
- SHA256: `8760075e9e22cbff3073e203d0e0a8ea07117a41518b9bba015eaf7900c4281b`
- PyInstaller 6.18.0 / Python 3.13.5 / Windows 10.0.26200.8655
- 경고 파일(`build/AIRWorker/warn-AIRWorker.txt`, 1238줄) 검토: 전부 표준 PyInstaller
  false-positive류(`multiprocessing.get_context` 등 stdlib 속성 오탐, `moviepy.editor`는
  버전 호환 fallback으로 의도된 미존재, `imageio.plugins.tifffile_geodb`는 미사용 TIFF
  플러그인) — 우리 자체 모듈(`render_worker`/`hermes_worker_mock`/`local_api_app`/
  `worker_config` 등) 관련 누락 경고 없음.
- imageio/MoviePy 메타데이터 수정: `packaging/windows/AIRWorker.spec`에
  `copy_metadata("imageio")` / `copy_metadata("imageio-ffmpeg")` / `copy_metadata("moviepy")`
  추가(모두 `datas`에 반영). `hiddenimports`에는 `collect_submodules("moviepy")` /
  `collect_submodules("PIL")`도 별도로 포함. moviepy 2.1.2 / imageio 2.37.2 /
  imageio_ffmpeg 0.6.0.

## 2. 독립 디렉터리 실행

`dist/AIRWorker.exe` → `C:\tmp\airworker-e2e-test\AIRWorker.exe`로 저장소 밖 복사(SHA256
재확인 일치), `AIRWORKER_HOME`도 저장소 밖 경로 지정, cwd도 저장소 밖. venv Python 미사용,
소스 `.py` 경로 참조 없음(`Get-CimInstance Win32_Process`로 모든 커맨드라인이
`AIRWorker.exe [--role X]` 형태임을 확인, python.exe 관련 프로세스 전무).

## 3. 멀티롤 프로세스 검증

```
ProcessId ParentProcessId CommandLine
42404     41060           AIRWorker.exe                        (onefile 부트로더)
35232     42404           AIRWorker.exe                        (Manager 본체)
45028     35232           AIRWorker.exe --role render_worker
39064     35232           AIRWorker.exe --role hermes_worker
29576     35232           AIRWorker.exe --role local_api
```
- 자식이 python.exe+.py로 실행되지 않음, 전부 동일 `AIRWorker.exe`가 `--role`로 재실행됨 확인.
- Render Worker 강제 kill → Manager가 감지, 해당 프로세스만 재시작(새 PID), hermes_worker/
  local_api PID는 불변 확인(재시작 전후 `crash_count_window`/`restart_count_total`도 `/status`
  로 확인).

## 4. Local API 검증

- `GET /health`(무인증) → 200
- `GET /status`(오류 토큰) → 401, (정상 토큰) → 200
- `GET /jobs` → 200
- `POST /jobs/submit` → 200, job_id 반환
- `POST /_test/crash-local-api` → local_api만 크래시·재시작(새 PID), `/health` 재정상화
- 실제 토큰 값은 이 문서/로그 어디에도 출력하지 않음 — 검증 스크립트는 길이(43자)만 출력.

## 5. 실제 렌더 E2E

`worker/fixture/build_fixture.py`로 생성한 fixture를 `POST /jobs/submit`으로 제출.

```
QUEUED → CLAIMED → PREPARING → RENDERING → UPLOADING → COMPLETED
```
- `output.mp4`: **23,628 bytes** (>0)
- `ffmpeg -i` 결과(전용 `ffprobe` 바이너리가 이 환경에 없어 대체 — §7):
  Duration 00:00:04.00 / Video: h264(High), yuv420p, 1280x720, 24fps / Audio: aac(LC),
  44100Hz, stereo
- job 로그에 오류 없음, SQLite `jobs` 테이블 상태 `COMPLETED` 확인.

## 6. imageio/MoviePy 회귀 — 렌더 E2E로 최종 판정

1차 빌드는 §5와 동일 잡에서 `MoviePy 또는 Requests가 설치되지 않았습니다 (Error: No package
metadata was found for imageio)`로 3회 재시도 후 FAILED. §1의 `copy_metadata` 3종 추가 후
재빌드 → 동일 잡 재제출 → §5 결과(COMPLETED, output.mp4 정상)로 재발 없음 확인. **단순 import
성공이 아니라 실제 렌더 E2E로 판정.**

## 7. FFmpeg 배포 구조

- **EXE 내부 포함** — `imageio_ffmpeg`의 `_pyinstaller_hooks_contrib` 표준 훅
  (`hook-imageio_ffmpeg.py`, 빌드 로그에서 처리 확인)이 자동으로 바이너리를 datas 번들.
  시스템에 `ffmpeg`/`ffprobe`가 전혀 없는 이 머신에서 저장소 밖 독립 실행이 성공했다는 것
  자체가 실증.
- `ffprobe` 전용 바이너리는 이 환경에 없어 `ffmpeg -i`로 대체(같은 스트림 정보 확인 가능).
- **라이선스 미확정 사항**: 번들 ffmpeg가 `--enable-gpl --enable-libx264` 포함 GPL 빌드 —
  상용 배포 시 라이선스 고지/의무 판단은 CTO·법무 확인 필요, 이 문서가 임의로 "문제없음"
  결론 내리지 않음.
- Windows PATH 비의존 확인(PATH에 ffmpeg 없는 상태에서 정상 동작).

## 8. 파일 경로 검증

- logs/state SQLite/IPC/temp/output/config/token 전부 `AIRWORKER_HOME`(미설정 시 실행파일
  기준 경로) 하위, 전부 사용자 쓰기 가능 디렉터리 사용 — Program Files류 고정 경로 의존 없음.
- 한글+공백 혼합 경로(`...\에어 테스트 폴더\data`)에서도 정상 동작 확인(로그/SQLite/DPAPI
  토큰 파일 전부 정상 생성) — 단, **onefile 압축해제 시간이 안정적이지 않음**을 이번 세션에서
  반복 관찰(짧은 간격 재기동 시 15~60초+ 편차) — 운영 헬스체크 타임아웃은 여유 있게 설계 권고
  (자세한 내용 `docs/AIR_WORKER_RUNTIME.md` §6.6).
- 경로 traversal 관련 신규 취약점 도입 없음(모든 경로가 `AIRWORKER_HOME` 하위 고정 서브경로,
  사용자 입력이 경로 조합에 직접 쓰이는 지점 없음).

## 9. 종료 검증

**정상(graceful)**: `POST /shutdown` → 11단계 로그(Hermes→Render→Local API 순 정지) →
`leftover_pids=0` 자기보고 + `Get-CimInstance`로 외부 확인, 2회 반복 재현.

**강제 상황**:
- Render Worker만 kill → 자동 재시작, 다른 역할 PID 불변(§3).
- Local API만 크래시(QA 훅) → 자동 재시작(§4).
- Local API 반복 3회 크래시(포트 충돌 시나리오, §10) → 600초 내 3회 제한으로 DISABLED 확인.
- **Manager만 강제 kill(렌더 중)** → 나머지 3자식은 고아 프로세스로 남아 진행 중이던 잡을
  끝까지 COMPLETED로 완료(작업 손실 없음). 이 상태에서는 그 자식이 죽어도 재시작해줄 주체가
  없음(무감독) — 새 Manager가 뜰 때까지.
- **전체 동시 kill(렌더 중)** → 잡이 `RENDERING`으로 SQLite에 고정 → 재기동 시
  `run_startup_recovery()`가 `RENDERING → ABANDONED → QUEUED`로 정확히 전이 → 재큐된 잡이
  재렌더링되어 COMPLETED 도달 확인.

## 10. 중복 실행 (정책 미확정 — CTO 결정 필요)

동일 `AIRWORKER_HOME`을 가리키는 두 번째 `AIRWorker.exe`를 띄우면:
- **단일 인스턴스 락은 현재 없음.**
- 두 번째 인스턴스의 Local API는 포트 8765 바인드 실패로 크래시 → 기존 크래시 정책(600초
  3회 제한)에 따라 자동 DISABLED — **조용한 포트 충돌이 아니라 로그에 명확히 남고 안전하게
  격리됨.**
- 두 인스턴스의 Render Worker가 동일 `jobs.db`를 동시 폴링하게 되는 점은 확인됨.
  `job_store.claim_next_job()`이 `BEGIN IMMEDIATE` SQLite 트랜잭션으로 원자적 클레임을
  보장하므로 코드 레벨에서는 이중 처리가 방지되는 구조이지만, **실제 동시 제출 경쟁 상황을
  라이브로 재현해 검증하지는 않았다**(코드 검토로만 확인 — 미검증 항목으로 명시).
- Hermes Worker(mock)는 인스턴스별로 독립적으로 계속 동작 — 실 Hermes 연동 시 중복 조사
  호출(비용 낭비) 리스크로 이어질 수 있음.
- **정책 미확정**: 파일 락/Named Mutex 기반 단일 인스턴스 강제 여부는 CTO 결정 필요 항목으로
  남김(구현하지 않음, 이번 PoC는 "현재 동작을 있는 그대로 문서화"만 함).

## 11. 클린 환경 검증 — 부분 미검증

- 별도의 완전히 새로운 Windows PC/VM은 이 세션에서 확보 불가 — **미검증.**
- 대신 이 개발 머신에서 확보 가능한 최대한의 격리로 대체 검증: 저장소 밖 디렉터리, 소스 코드
  미참조, venv 미사용, PYTHONPATH/VIRTUAL_ENV 둘 다 빈 상태 확인, 한글 계정명 유사 조건
  (한글+공백 경로)은 검증(§8).
- Python 완전 미설치 환경, 새 사용자 계정에서의 실행은 **미검증**으로 명시.

## 12. 산출물 기록

- `dist/AIRWorker.exe` (onefile, single exe — sidecar 파일 없음)
- 567,354,123 bytes / SHA256 `8760075e9e22cbff3073e203d0e0a8ea07117a41518b9bba015eaf7900c4281b`
- PyInstaller 6.18.0, Python 3.13.5, Windows 10.0.26200.8655
- 빌드 commit(base): `1000581232ada7e28c1e41cbc404576b9904b637`
  (`feat/air-0227d-worker-central-drive-e2e`, "Merge main (includes version.py fix PR #77)")
- 빌드 시각: 2026-07-13 11:14 (KST)
- **`dist/`, `build/`는 Git에 커밋하지 않음**(`.gitignore`로 이미 제외 확인).

## 13. 문서 갱신

- 이 문서(신규 파일명, `-DONE.md` → `-PACKAGING-POC.md`로 리네임)
- [`docs/AIR_WORKER_RUNTIME.md`](../docs/AIR_WORKER_RUNTIME.md) §6 신규 추가(프리즌 exe 전용
  발견사항 전체)
- [`docs/AIR_WORKER_ARCHITECTURE.md`](../docs/AIR_WORKER_ARCHITECTURE.md),
  [`docs/AIR_WORKER_PROCESS_MODEL.md`](../docs/AIR_WORKER_PROCESS_MODEL.md),
  [`docs/AIR_WORKER_UPDATE_STRATEGY.md`](../docs/AIR_WORKER_UPDATE_STRATEGY.md) 상태 라인
  갱신, 전부 "무엇이 완료고 무엇이 미완료인지" 명시

**완료**: Frozen EXE 멀티롤 실행, 실제 렌더 E2E, 독립 경로 실행.
**미완료**: Inno Setup 설치 파일, Windows 서비스 등록, 자동 시작, 자동 업데이트, 운영용 Worker
Token 발급 체계, staging 중앙 API 연동, 실 Google Drive 업로드, 실 Hermes Runtime, 코드 서명,
단일 인스턴스 락(§10).

## 14. Git

이 문서 작성 시점 기준 변경 파일(전부 uncommitted):
- `worker/manager.py` (수정 — 자식 스폰 로직)
- `worker/air_worker_entry.py` (신규 — 통합 엔트리포인트)
- `packaging/windows/AIRWorker.spec` (신규)
- `_dev/build_worker.py` (신규)
- `worknote/AIR-0227E-PACKAGING-POC.md` (신규)
- `docs/AIR_WORKER_RUNTIME.md`, `docs/AIR_WORKER_ARCHITECTURE.md`,
  `docs/AIR_WORKER_PROCESS_MODEL.md`, `docs/AIR_WORKER_UPDATE_STRATEGY.md` (갱신)

커밋 → `feat/air-0227e-worker-exe-packaging` push → **Draft PR**(대상: `feat/air-0227d-worker-central-drive-e2e`,
main 아님) 진행 예정.

## 15. 완료 기준 체크 (P1 DONE 여부)

| 기준 | 결과 |
|---|---|
| clean build 성공 | ✅ exit 0 |
| 독립 디렉터리 실행 | ✅ |
| Manager 및 3개 역할 기동 | ✅ |
| 실제 render job 완료 | ✅ COMPLETED |
| output.mp4 생성 | ✅ 23,628 bytes |
| ffprobe 성공 | ⚠️ ffprobe 바이너리 부재, `ffmpeg -i`로 동등 검증 대체 |
| imageio metadata 오류 재발 없음 | ✅ |
| 정상 종료 후 PID 0 | ✅ (2회 재현) |
| 소스 .py 및 Python interpreter 비의존 | ✅ |
| 비밀정보 미포함(토큰 미출력) | ✅ |
| SHA256 기록 | ✅ |
| 문서 갱신 | ✅ |

## 16. 판정 — **P1 Go**

Go로 판정하는 근거: 위 12개 기준 중 11개가 명확히 충족되었고, 유일한 부분 미달(ffprobe
바이너리 부재)은 `ffmpeg -i`로 동등한 정보(코덱/해상도/길이)를 확인해 실질적 검증 목적은
달성했다고 판단. 강제 크래시/전체 크래시/복구까지 라이브로 재현해 설계 문서(§JOB_RECOVERY)의
주장을 실제로 뒷받침했고, frozen 전용 버그 2건(imageio 메타데이터, PYTHONIOENCODING 무효화)을
발견 즉시 수정·재검증까지 완료한 점도 Go 판단에 반영.

**Conditional 요소(후속 Task에서 반드시 다뤄야 함, 이번 Go 판정을 뒤집는 항목은 아님)**:
- 단일 인스턴스 락 정책 미확정(§10) — CTO 결정 필요.
- 동시 job 제출 경쟁 상황 라이브 미검증(§10) — 코드 검토로만 안전성 확인.
- 완전히 새로운 클린 Windows 환경(별도 PC/신규 계정) 미검증(§11).
- ffmpeg GPL 라이선스 배포 의무 미확정(§7) — 법무/CTO 확인 필요.
- onefile 기동 시간 편차(§8) — 운영 헬스체크 설계 시 고려 필요.

**정식 Inno Setup/자동 업데이트 구현 착수 가능 여부**: 착수 가능 — 이번 Task로
`AIRWorker.exe` 단일 실행파일 자체는 실동작이 확인되었으므로, `docs/AIR_WORKER_UPDATE_STRATEGY.md`가
설계한 설치 프로그램/업데이터 작업을 이 산출물 위에서 바로 시작할 수 있는 상태. 단, 위
Conditional 항목(특히 단일 인스턴스 락, GPL 라이선스 확인)은 설치 프로그램 설계 전에
CTO 결정을 먼저 받는 것을 권고.
