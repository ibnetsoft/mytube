# AIR-0230 — Hermes Benchmark Worker: 벤치마크 영상 분석 + 사전생성 파이프라인 설계

- 상태: **설계안 / CTO 승인 대기** (§2a `topic_benchmark_analyze` job_type + 중앙 job
  프로토콜(결정 B)은 구현 완료 — 아래 "진행 상황" 참고. §2b 웹어드민 트리거 UI, §2c
  claim_topic 경유 데이터 전달, §2d 사전생성 버퍼는 아직 미착수. **DB 마이그레이션은
  초안 상태로만 존재, 어떤 Supabase 인스턴스에도 적용되지 않음.**)
- 관련 문서: [HERMES_TOPIC_INTELLIGENCE_ARCHITECTURE](./HERMES_TOPIC_INTELLIGENCE_ARCHITECTURE.md),
  [AIR_WORKER_ARCHITECTURE](./AIR_WORKER_ARCHITECTURE.md), [AIR_WORKER_JOB_PROTOCOL](./AIR_WORKER_JOB_PROTOCOL.md),
  [worknote/AIR-0226-stage1-current-state-analysis.md](../worknote/AIR-0226-stage1-current-state-analysis.md)

## 진행 상황

- **완료 1**: §2a `topic_benchmark_analyze` job_type을 `worker/hermes_worker.py`에 구현 —
  유튜브 검색 → 구독자 대비 조회수 랭킹 → 상위 1~3개 자막/댓글 수집 → Gemini 분석 +
  성공전략 추출까지 기존 함수 재사용으로 구현. `AIR_WORKER_JOB_PROTOCOL.md` §5a에 payload
  스키마 문서화함. 커밋 `ff56f507`.
- **완료 2 — 중앙 job 프로토콜 (결정: B, 별도 테이블)**: 렌더 작업용으로 이미 구현돼 있던
  중앙 lease/claim 프로토콜(`migrations/air_0227d_worker_central_protocol.sql`,
  `remote_render_queue` 재사용 방식)을 그대로 재사용하려 했으나 `remote_render_queue.project_id`가
  `NOT NULL`이라 프로젝트 없는 topic 작업이 못 들어감 — 그래서 완전히 분리된
  `migrations/air_0230_hermes_worker_central_protocol.sql`을 신규 작성:
  - `remote_hermes_queue`(+`hermes_job_events`/`hermes_idempotency_keys`) 신규 테이블,
    `claim_worker_hermes_job`/`renew_worker_hermes_job_lease`/`report_worker_hermes_job_progress`/
    `report_worker_hermes_job_outcome` RPC 4개 — `air_0227d`와 동일한 lease/idempotency
    패턴이지만 렌더 테이블·RPC는 전혀 건드리지 않음
  - `workers`/`worker_tokens`는 이미 범용(`allowed_job_types TEXT[]`)이라 그대로 재사용
  - 기존 `auth-web/app/api/internal/worker/**` 4개 라우트(claim/progress/renew/complete·fail)를
    "인증된 워커 토큰의 allowed_job_types가 topic 계열인지"로 분기하도록 확장
    (`workerAuth.ts::isHermesWorker()`)
  - `worker/hermes_worker.py`에 `render_worker.py`와 동일한 로컬→중앙 이중 job 소스 패턴
    포팅(lease 갱신 스레드, 완료/실패 중앙 보고, pending-ack 재시도) — `central_client.py`/
    `job_store.py`가 이미 job_type-무관 범용이라 거의 그대로 재사용됨
  - `report_worker_hermes_job_outcome`에 `p_result_payload` 컬럼 추가 → 분석 결과 JSON을
    직접 중앙에 인라인 저장(별도 다운로드 스텝 불필요) — "결과 데이터만 웹으로 전송"을
    실제로 완성하는 부분
  - 부수적으로 발견한 기존 버그 수정: `central_client.renew_lease()`가 `/renew-lease`를
    호출하는데 실제 라우트 폴더는 `/renew`라 항상 404였음(렌더용도 동일하게 깨져있었음)
  - 검증: pglast SQL 문법 검증, 변경된 auth-web 파일 `tsc --noEmit`(기존 에러 외 신규
    없음), mocked 유닛테스트로 원격 job은 `central_client.complete_job`이 올바른
    result_payload와 함께 호출되고 로컬 job은 전혀 호출 안 됨을 확인.
  - 브랜치 `feat/air-0230-topic-benchmark-analyze`(베이스: 미병합 PR #86
    `feat/air-0227e-p3-real-hermes-worker`), 커밋 `3eb47bd5`, **push 완료.**
- **미착수**: §2b(웹어드민이 실제로 job을 큐잉하는 트리거 UI/버튼), §2c(claim_topic 경유
  benchmark_analysis를 데스크톱 프로젝트로 전달), §2d(사전생성 버퍼).

## 0. 배경 및 문제의식

웹어드민(`auth-web`)의 "AI 주제 자판기 생성"이 뻔하고 비슷비슷한 주제를 카테고리마다 계속
찍어내는 문제에서 이 논의가 시작됐다. 1차로 다음 개선을 이미 적용했다(§5):

- 웹어드민: 카테고리별 대기 주제 전체삭제 기능
- 웹어드민: 주제 생성 프롬프트에 "기존 주제 목록 참고 → 중복/유사 금지" + "5개 이상 서로 다른
  각도" 다양성 지시 + temperature 명시
- 데스크톱: 대본기획(`scene_planner_service.plan_scenes()`)이 벤치마크 분석/누적 학습지식/
  최근 주제 회피를 실제로 프롬프트에 반영하도록 배선 복구(이전엔 조회만 하고 버려지던 죽은 코드)

하지만 이 개선들은 전부 "LLM이 텍스트만으로 그럴듯하게 지어내는" 수준의 개선이고, **실제
시장 데이터**(구독자 대비 조회수가 높은 실제 영상이 무엇을 어떻게 했는가)는 여전히 반영되지
않는다. 그 실제 데이터를 다루는 기능(유튜브 검색 → 고성과 영상 판별 → 댓글/자막 분석)은 이미
존재하지만, **PRO 등급 전용 수동 기능으로 고립**돼 있어 STD 사용자(대다수 — 웹어드민이 미리
채운 큐에서만 주제를 받는 등급)에게는 전혀 연결되지 않는다.

## 1. 조사로 확인된 현재 상태

### 1a. 고성과 영상 분석 기능 — 지금 어디 있고 어디 없는가

- `templates/pages/topic.html`: PRO 전용, 수동. 유튜브 검색 → 구독자 대비 조회수/채널
  기여도를 **클라이언트 JS에서만** 계산해 정렬 표시(서버 저장 안 됨) → 사용자가 영상 하나를
  골라 "🤖 분석" 클릭 → `POST /api/gemini/analyze-comments`(댓글+자막 → Gemini 분석).
- 분석 저장(`POST /api/projects/{id}/analysis`, [main.py:674](../main.py))은 백그라운드로
  `background_learn_strategy()`를 실행해 일반화된 "성공 전략"을 추출하고
  `db.save_success_knowledge()`로 축적한다 — 그러나 이 저장소는 **사용자 개인 로컬 SQLite**라
  플랫폼 전체가 공유하지 못한다.
- STD 사용자의 실제 주제 경로(`claim_topic()`, [app/routers/user_topics.py](../app/routers/user_topics.py))는
  이 분석 기능을 전혀 거치지 않는다 — STD는 "새 프로젝트" 버튼 자체가 숨겨져 있어
  `topic.html` 접근 경로가 없다.

### 1b. 대본기획 배선 (이번에 복구 완료, §5)

`/api/gemini/generate-structure`([app/routers/gemini.py](../app/routers/gemini.py))가
`db.get_analysis()`(프로젝트별 저장 분석)와 `db.get_recent_knowledge()`(누적 학습지식)를
조회는 했지만, 실제 씬 기획 함수(`scene_planner_service.plan_scenes()`)에는 전달되지 않고
버려지고 있었다(리팩토링 중 끊어진 배선으로 추정). 이번에 두 값을 실제로 프롬프트에 반영하도록
수정했다.

### 1c. AIR Worker / Hermes Worker — 이미 있는 것과 없는 것

- `AIRWorker.exe`(렌더링 PC에 상시 설치되는 프로그램) 안에는 Render Worker와 별개로 Hermes
  Worker 프로세스가 이미 존재한다(`worker/hermes_worker.py`, 브랜치
  `feat/air-0227e-p3-real-hermes-worker`, PR #86, **검증 완료·미병합**). 실제 Gemini API
  호출로 키워드 → 주제 생성까지 end-to-end 확인됨([HERMES_DRIVE_BRIDGE_CTO_REPORT.md](../HERMES_DRIVE_BRIDGE_CTO_REPORT.md)).
- 그러나 `worker/` 디렉터리 전체(26개 파일)를 유튜브/자막/댓글/구독자 키워드로 검색한 결과
  **일치 0건** — Hermes Worker는 순수 "키워드 → LLM 프롬프트로 주제 텍스트 생성"만 하고, 실제
  유튜브 검색/자막추출/댓글분석 로직은 전혀 없다.
- 중앙(Supabase) job 연동도 아직 없다 — 지금은 로컬 job_store에서만 job을 받고, 결과도
  로컬 파일에 씀. 이 "중앙 연동"은 별도 브랜치(`feat/air-0227e-p4-topic-central-sync`)가
  다루는 중이나 역시 미병합.
- **핵심 재사용 포인트**: 유튜브 검색/자막추출/댓글분석에 필요한 로직은 전부 이미 데스크톱 앱에
  순수 Python 함수로 존재한다 — 워커가 FastAPI 라우터가 아니라 이 함수들을 직접 import해서
  호출하면 되므로, "새로 개발"이 아니라 "같은 함수를 새 호출자(워커)에서도 쓰는" 문제에 가깝다:
  - 유튜브 검색/영상/채널 조회: `app/routers/youtube.py` (`/youtube/search`, `/youtube/videos/{id}`,
    `/youtube/channel/{id}`)
  - 자막 추출: `services/source_service.py` (`youtube_transcript_api` — Python 전용 라이브러리,
    Next.js/Vercel에서 못 돌림. 이게 이 작업을 auth-web이 아니라 렌더링 PC에서 해야 하는
    핵심 이유)
  - 댓글 수집 + AI 분석: `services/gemini_service.py::analyze_comments()`
  - 성공전략 일반화 추출: `services/gemini_service.py::extract_success_strategy()`

## 2. 제안 아키텍처

### 2a. 신규 워커 job_type: `topic_benchmark_analyze`

렌더링 PC에 이미 상시 떠있는 Hermes Worker 프로세스에 새 job_type을 추가한다(§AIR_WORKER_JOB_PROTOCOL의
`topic_research`/`topic_generate`와 같은 급의 신규 항목):

1. 입력: `category_id`/`keywords`/`benchmark_channel_url` (또는 `topics_queue` 항목)
2. 유튜브 검색으로 후보 영상 수집 (`app/routers/youtube.py` 로직 재사용)
3. 구독자 대비 조회수로 후보 랭킹 (신규 — 현재 `topic.html` JS에만 있는 산술을 Python으로 이식,
   작은 작업)
4. 상위 N개 자막 추출 (`services/source_service.py`)
5. 댓글 수집 + Gemini 분석 (`services/gemini_service.py::analyze_comments()`)
6. 성공전략 추출 (`services/gemini_service.py::extract_success_strategy()`)
7. **출력은 원본 영상/자막이 아니라 분석 결과 JSON(+추출된 성공전략 리스트)만** — 신규 Supabase
   테이블(가칭 `topic_benchmark_analysis`, `success_knowledge_central`)에 업로드. 로컬 SQLite
   축적을 중앙화해 전체 사용자가 공유하는 학습모델로 진화 가능하게 한다.

### 2b. 웹어드민 "AI 주제 자판기 생성" 연동 — 트리거는 항상 웹어드민(중앙 서버)

**원칙**: 어떤 키워드로 검색할지(카테고리의 `keywords`/`benchmark_channel_url`)와 언제
조사를 시작할지(job 생성) 둘 다 웹어드민이 결정한다. Hermes/AIWorker는 자율적으로 판단하지
않고, 중앙이 큐에 넣어준 job(payload에 `category_id`/`keywords`가 이미 담김)을 폴링해서
`claim`하고 그대로 실행만 한다(`worker/central_client.py`의 `claim_job` 폴링 계약,
`AIR_WORKER_JOB_PROTOCOL.md` §3 원칙 그대로). 트리거 방식은 두 가지를 **둘 다** 지원한다:

- **수동 모드**: 어드민이 웹어드민 화면에서 카테고리를 골라 버튼을 누름 — 기존 "AI 주제
  자판기 생성" 버튼 옆에 "벤치마크 분석 포함 생성" 버튼을 추가하거나, 기존 버튼 자체가
  `topic_benchmark_analyze` job도 함께 큐잉하도록 확장한다. 어드민이 즉시 결과를 보고
  싶을 때, 혹은 특정 카테고리를 우선적으로 조사하고 싶을 때 사용.
- **자동 모드**: 정기 스케줄(예: 카테고리당 1일 1회, cron)로 중앙 서버가 알아서
  `topic_benchmark_analyze` job을 생성. `HERMES_TOPIC_INTELLIGENCE_ARCHITECTURE.md` §2b가
  이미 이 옵션을 전제하고 있음 — 동일 카테고리에 유효기간(§3, 기본 7일 제안) 내 최근 조사가
  있으면 자동 모드는 새로 부르지 않고 스킵(비용 절감), 어드민이 수동으로 "강제 새로고침"하면
  예외적으로 다시 조사.
- 두 모드 모두 동일한 job_type/payload 스키마를 쓰므로 워커 쪽 구현은 트리거 방식과 무관하게
  하나로 통일된다 — 차이는 오직 "누가/언제 job row를 insert하는가"(어드민 버튼 클릭 핸들러 vs
  cron 스케줄러)뿐.

워커가 job을 처리 완료하면 결과를 `topics_queue` 삽입 시점에 반영한다. 이미 적용된 개선(중복
회피 프롬프트, 다양성 지시, temperature)과 상호 보완적으로 작동한다 — 저것들이 "그럴듯한 지어내기"를
개선한다면, 이건 "실제 시장 근거"를 더한다.

### 2c. 대본기획/대본생성 소비 경로 확장

- 이미 완료(§5): `scene_planner_service.plan_scenes()`가 `benchmark_analysis`/
  `accumulated_knowledge`/`recent_titles`를 프롬프트에 반영.
- 남은 일: 이 데이터의 출처를 "로컬 SQLite의 개인 `analysis` 테이블"에서 "`topics_queue`를
  통해 넘어온 중앙 벤치마크 분석"으로 확장 — `claim_topic()`이 이 값을 `project_settings`로
  복사하도록 수정 필요.
- 대본생성(본문 텍스트) 단계에도 같은 데이터를 짧은 "기법 노트" 형태로 전달하는 확장 필요
  (미착수).

### 2d. 사전생성(pre-bake) 파이프라인과 버퍼 정책

목표: 사용자가 주제를 고르기 전에 기획·대본을 미리 만들어 즉시 제공.

**위험**: 대기열 전체에 대해 미리 만들면 비용이 폭증한다 — 이 논의 자체가 "클레임 안 되고
쌓이기만 하는 뻔한 주제"의 만성적 적체 문제에서 출발했다는 점과 정면으로 충돌한다.

**제안**: 카테고리별 상위 K개(예: 3~5개)만 "항상 기획+대본까지 준비된 상태"로 유지하는
버퍼 방식(생산라인 재고 버퍼와 동일한 개념) — 하나가 claim되면 워커가 다음 것을 채운다.
전체 백로그를 미리 만드는 방식은 채택하지 않는다.

- 신규 job_type 필요: `script_plan_generate`, `script_generate` (`AIR_WORKER_JOB_PROTOCOL.md`에
  아직 미정의)
- `claim_topic()`/스크립트 생성 흐름에 "미리 준비된 결과가 있으면 즉시 반환, 없으면 지금처럼
  실시간 생성"하는 폴백이 반드시 필요 — 버퍼가 못 따라간 경우에도 사용자 체감이 끊기지 않아야
  한다.

## 3. 리스크 및 미결정 사항

- 자막추출이 비공식 스크레이핑(`youtube_transcript_api`)에 의존 — 유지보수 리스크는 기존과
  동일(신규 리스크 아님, 이미 데스크톱 앱이 지고 있는 리스크를 그대로 재사용하는 것).
- 유튜브 Data API 쿼터 소모량 증가폭 산정 필요(검색+채널통계+댓글 조회가 카테고리 생성마다
  추가됨).
- 중앙 학습지식 테이블의 스키마/보안(RLS) 설계 필요 — `HERMES_TOPIC_INTELLIGENCE_SECURITY.md`의
  tenant_id/channel_id 격리 원칙 재사용 검토.
- 사전생성 버퍼 크기(K)와 트리거 정책은 실측 후 조정 필요.
- Vercel(auth-web) 서버리스 실행시간 제한 문제는 이 설계에서 애초에 발생하지 않음(무거운
  작업 전부를 렌더링 PC 로컬에서 처리) — 이게 이 아키텍처를 "auth-web에 직접 구현" 대신
  선택하는 핵심 이유 중 하나.

## 4. 다음 단계 제안

1. PR #86(`feat/air-0227e-p3-real-hermes-worker`) + P4(`feat/air-0227e-p4-topic-central-sync`)
   브랜치 리뷰 및 병합 우선순위 결정
2. `topic_benchmark_analyze` job_type 상세 설계 (payload 스키마, `AIR_WORKER_JOB_PROTOCOL.md`
   갱신)
3. 중앙 학습지식 테이블 스키마 설계 (Supabase migration)
4. 사전생성 버퍼 정책 실험 (`script_plan_generate`/`script_generate` job_type)

## 5. 이번 논의 중 이미 반영된 선행 코드 변경 (참고)

- 웹어드민 카테고리별 대기 주제 전체삭제 기능
  (`auth-web/app/api/admin/topics-queue/route.ts`, `auth-web/components/DashboardContent.tsx`)
- 웹어드민 주제생성 프롬프트 개선: 기존 주제 중복회피 + 다양성 지시 + temperature 명시
  (`auth-web/app/api/admin/topics-queue/route.ts`, `auth-web/lib/aiRouter.ts`)
- 데스크톱 대본기획 배선 복구: `scene_planner_service.plan_scenes()`가 `benchmark_analysis`/
  `accumulated_knowledge`/`recent_titles`를 반영하도록 수정
  (`app/services/scene_planner.py`, `app/routers/gemini.py`)
