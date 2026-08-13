# AIR Worker — 아키텍처 설계

- 상태: **로컬 E2E 검증 완료(AIR-0227B) + Frozen EXE 패키징 PoC 검증 완료(AIR-0227E, [RUNTIME §6](./AIR_WORKER_RUNTIME.md) 참고) + 실제 Inno Setup 설치까지 검증 완료(AIR-0227E-P2-VALIDATION) / 프로덕션 미배포·CTO 승인 대기. [AIR-0227E-P3] Mock Hermes를 실제 Hermes Worker(`worker/hermes_worker.py`, 주제 조사 전용, `services/ai_router.py` 재사용, 실 Gemini API로 5회 이상 실측)로 교체 완료, 설치본에서 Render+Hermes 동시 실행/렌더 우선 정책/역할별 crash isolation까지 실측 완료(worknote/AIR-0227E-P3-HERMES-INTEGRATION.md). 실 Drive/실 중앙 서버는 여전히 미착수.**
- 선행 문서: [`worknote/AIR-0227A-stage1-render-worker-analysis.md`](../worknote/AIR-0227A-stage1-render-worker-analysis.md)
- 관련 문서: [PROCESS_MODEL](./AIR_WORKER_PROCESS_MODEL.md), [JOB_PROTOCOL](./AIR_WORKER_JOB_PROTOCOL.md), [SECURITY](./AIR_WORKER_SECURITY.md), [RESOURCE_POLICY](./AIR_WORKER_RESOURCE_POLICY.md), [RUNTIME](./AIR_WORKER_RUNTIME.md)

> **AIR-0227B 업데이트**: 이 문서는 AIR-0227A(#12 스켈레톤) 설계 시점 그대로 유지하되,
> "실 렌더링/Hermes 미연결"이라는 전제는 렌더링 쪽에 한해 더 이상 사실이 아니다 — Render
> Worker Process는 이제 실제 `services/remote_render_service.py` 파이프라인을 호출해 진짜
> MP4를 만든다(Hermes는 여전히 모의 구현). Local API도 더 이상 Manager 내부 스레드가
> 아니라 완전히 독립된 OS 프로세스다. 변경 내역과 실측 근거는 [RUNTIME](./AIR_WORKER_RUNTIME.md)과
> [LOCAL_E2E_QA](./AIR_WORKER_LOCAL_E2E_QA.md) 참고 — 이 문서(§1 다이어그램 포함)의 구조적
> 설명 자체는 그대로 유효하다.

## 0. 왜 이게 "기능 통합"이자 "인프라 최초 구축"인가

Stage 1 조사에서 확인했듯, 현재 원격 렌더 워커(`remote_drive_worker.py`)는:
- 설치 프로그램이 없다 (bare exe + 사이드카 `.env`)
- 자동 업데이트가 없다 (완전 수동 재빌드/재배포)
- 프로세스 감시가 없다 (크래시 시 사람이 직접 재시작)
- "GPU 렌더"라는 이름의 죽은 플래그만 있고 실제 GPU 가속은 어디에도 없다
- 렌더링 경로가 3개나 있고 그 중 하나(로컬 HTTP-push 큐)는 이미 죽은 코드다

즉 AIR Worker는 단순히 "렌더 워커 + Hermes 워커를 하나의 exe로 합치는 것"이 아니라, **처음으로
설치·업데이트·감시 인프라를 갖추는 작업**이기도 하다. 이 문서는 이 전제를 계속 참조한다.

## 1. 전체 구조

```
┌──────────────────────────────────────────────────────────────────────┐
│                         AIRWorker.exe (렌더링 PC)                       │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                        Worker Manager                             │  │
│  │  - 하위 프로세스 시작/중지/재시작, PID·상태 추적                    │  │
│  │  - 반복 크래시 감지 시 모듈만 비활성화                              │  │
│  │  - Job Scheduler + Health Monitor를 내부에 포함                    │  │
│  └───────┬─────────────┬─────────────┬─────────────┬────────────────┘  │
│          │             │             │             │                    │
│  ┌───────▼──────┐┌─────▼──────┐┌─────▼──────┐┌─────▼──────┐          │
│  │ Render Worker ││ Hermes      ││ Local API   ││ Auto        │          │
│  │ Process       ││ Worker      ││ Process     ││ Updater     │          │
│  │ (독립 프로세스)││ Process     ││ (127.0.0.1) ││ (모듈별)     │          │
│  │               ││ (독립 프로세스)│             ││              │          │
│  └───────┬──────┘└─────┬──────┘└─────┬──────┘└─────────────┘          │
└──────────┼─────────────┼─────────────┼──────────────────────────────────┘
           │              │              │
           │ 렌더 작업 폴링/보고 │ 조사 작업 폴링/보고 │ (로컬 관리 UI/CLI만 접근)
           ▼              ▼              
┌──────────────────────────────────────────────────────────────────────┐
│                        중앙 서버 / Supabase                             │
│  사용자 인증·권한·결제·회원·추천인·운영DB·작업 생성/배분·관리자 승인·      │
│  topics_queue 승격 — 전부 여기서만.                                     │
└──────────────────────────────────────────────────────────────────────┘
```

**핵심 원칙(원칙 #7 그대로)**: 실행 프로그램은 하나(`AIRWorker.exe`)지만, 렌더링과 Hermes는
**절대 같은 Python 프로세스로 합치지 않는다.** Worker Manager가 두 개의 완전히 독립된 자식
프로세스로 각각 기동한다(구현은 `multiprocessing`이 아니라 `subprocess.Popen`으로 — 별도
프로세스 경계가 필요한 이유는 원칙 #6/#7의 격리 요구와 아래 §3의 "한쪽 죽어도 한쪽 안 죽는다"
요구를 OS 프로세스 경계로 물리적으로 보장하기 위함, GIL 공유 위험 회피와도 일치).

## 2. 왜 AIR Worker를 렌더링 PC에 두는가 (핵심 결정 #2, #3, #4, #5 반영)

- 렌더링 PC는 이미 **상시 켜져 있다**는 운영 조건이 있다(핵심 결정 #3) — Hermes 정기 시장조사
  같은 백그라운드 작업을 돌릴 유휴 시간이 자연스럽게 생긴다(렌더 큐가 빌 때, §RESOURCE_POLICY).
- Hermes는 **별도 Vultr 서버에 우선 배치하지 않는다**(#4) — 별도 서버 운영비/관리 부담을
  지금 단계에서 만들지 않기 위함. 대신 Hermes는 **외부 LLM API를 호출**(#5)하므로 렌더링 PC의
  GPU를 점유하지 않는다 — Hermes 프로세스 자체는 가벼운 API 호출 클라이언트일 뿐이다(AIR-0226
  PoC에서 이미 확인: Hermes/대체모델 호출은 순수 HTTPS 요청이지 로컬 추론이 아니다).
- 이 결정 덕분에 "렌더링이 GPU/CPU를 쓰고 Hermes가 그걸 침범하지 않는가"라는 우려는 애초에
  구조적으로 발생하지 않는다 — 자원 경쟁은 CPU/네트워크 대역폭/브라우저 자동화 프로세스 수
  정도로 한정된다(§RESOURCE_POLICY).

## 3. 프로세스 격리 원칙 (핵심 조건 그대로 재확인)

- Hermes 오류가 렌더링을 종료시키지 않는다 / 렌더링 오류가 Hermes와 Manager를 종료시키지
  않는다 — 별도 OS 프로세스이므로 한쪽의 처리되지 않은 예외/크래시가 다른 프로세스의 메모리
  공간에 영향을 줄 수 없다. Worker Manager만이 두 프로세스의 생사를 알고, 죽은 쪽만 재시작
  정책(§PROCESS_MODEL)에 따라 처리한다.
- 각 프로세스는 자기 로그 파일에만 쓴다(§PROCESS_MODEL §4) — 로그 파일 충돌 없음(QA 항목).

## 4. 중앙 서버와 AIR Worker의 경계 (핵심 결정 #8, #9 / Stage 5)

| 중앙 서버(Supabase + auth-web) | AIR Worker |
|---|---|
| 사용자 인증/권한/결제/회원/추천인 | (전혀 관여 안 함) |
| 운영 DB(profiles, referral, withdrawal 등) | (전혀 관여 안 함) |
| 작업 생성/배분 | 작업 수신만 |
| 관리자 승인 | (전혀 관여 안 함) |
| `topics_queue` 승격 | (전혀 관여 안 함 — AIR-0226 설계 그대로, Hermes 후보는 `topic_candidates`까지만) |
| | 렌더링 실행 |
| | Hermes 실행 |
| | 진행률 보고 |
| | 결과 업로드 |
| | 상태·리소스 보고 |

**AIR Worker는 Supabase 테이블을 자유롭게 조회하지 않는다** — 중앙 서버가 노출하는 제한된
API(Worker Token 인증, §SECURITY)를 통해서만 "나에게 배정된 작업"과 "제한된 topic context"만
받는다. 이건 AIR-0225B(service_role 유출 사고)와 AIR-0226(Hermes에게 DB 직접 접근 금지)에서
이미 확립한 원칙을 렌더링 워커에도 동일하게 확장 적용하는 것이다 — **AIR Worker도 "신뢰
경계 밖의 실행 환경"으로 취급**한다(운영자가 관리하는 PC라 해도, 물리적으로 원격지에 있고
중앙 인프라와 같은 신뢰 수준을 가정하면 안 된다는 게 AIR-0225B의 교훈이었다).

## 5. Stage 1 조사 결과의 반영 지점

| Stage 1 발견 | AIR Worker 설계 반영 |
|---|---|
| 설치 프로그램 없음 | §UPDATE_STRATEGY — Inno Setup 기반 정식 설치 프로그램 신설 |
| 자동 업데이트 없음 | §UPDATE_STRATEGY — AIR Studio Updater의 원자적 스왑/롤백 원칙 재사용 |
| 프로세스 감시 없음 | Worker Manager의 핵심 존재 이유(§PROCESS_MODEL) |
| GPU 플래그가 죽어있음 | §RESOURCE_POLICY에서 "GPU/VRAM 표시"는 UI 스켈레톤 항목으로 유지하되, 실제 GPU 가속 연결은 이번 범위 밖임을 명시 — 그대로 이월된 기술부채, AIR Worker가 만드는 게 아니라 물려받는 것 |
| 렌더 경로 3개 중 1개 죽음 | AIR Worker의 Render Worker Process는 살아있는 2개 경로(동기 직접/Drive 릴레이) 중 **Drive 릴레이 방식을 계승**하고, 죽은 HTTP-push 경로(`render_queue_worker.py`+`/remote/render`)는 참고하지 않음 |
| 빌드 경로 2개가 다른 exe 이름을 만듦 | AIR Worker는 단일 `.spec` + 단일 빌드 스크립트로 시작해 이 혼란을 재현하지 않음(§UPDATE_STRATEGY 빌드 파이프라인 절) |

## 6. 관리 UI 스켈레톤 개요 (Stage 8, 상세는 PROCESS_MODEL §UI)

간단한 로컬 상태 창(또는 CLI 상태 화면) — 중앙 서버 연결 상태/Worker ID/렌더링·Hermes
상태/큐 수/현재 작업/진행률/CPU·RAM·GPU·VRAM/마지막 heartbeat/최근 오류를 표시하고,
렌더링·Hermes 시작/중지, 전체 일시정지, 로그 열기, 업데이트 확인, 종료를 제어한다. 이번
Task의 스켈레톤 구현(§12)에서는 **CLI 상태 화면**으로 구현하고(가장 낮은 리스크, 가장
빠르게 QA 가능), 정식 GUI는 후속 Task로 분리 제안한다.
