# AIR-0230 세션 요약 — 웹어드민 주제생성 개선 + Hermes 벤치마크 워커 파이프라인

## 날짜
2026-07-29

## 상태
설계·구현 완료 (**주제 → 기획 → 대본 전체 파이프라인**), **배포 전 단계**(마이그레이션 미적용,
브랜치 미병합, 워커 미배포). **사용자 결정으로 STD의 claim-큐 흐름은 실시간 생성 폴백을 완전히
제거**했으므로, 배포 전까지는 STD가 주제를 claim해도 기획/대본이 나오지 않는다(PRO 수동 프로젝트는
영향 없음). 아래 "미해결·다음 단계" 참고.

## 배경

웹어드민 "AI 주제 자판기 생성"이 카테고리마다 뻔하고 비슷비슷한 주제를 계속 찍어내는 문제에서
출발했다. 조사 결과 두 가지 근본 원인을 확인:

1. 주제 생성 프롬프트가 **기존에 이미 생성된 주제를 전혀 참고하지 않음** — 다양성 지시도 없었음.
2. "구독자 대비 조회수가 높은 실제 영상을 찾아 분석"하는 기능(`templates/pages/topic.html`)이
   이미 존재하지만 **PRO 등급 전용 수동 기능으로 고립**돼 있어, 실제 주제 대부분을 받는 STD
   사용자(웹어드민이 미리 채운 큐에서만 주제를 받음)에게는 전혀 연결되지 않음.

이 두 문제를 해결하는 과정에서 스코프가 커져, 최종적으로는 "실제 시장 데이터로 주제를 검증하고
그 근거가 대본기획까지 이어지는" 파이프라인 설계(AIR-0230)까지 진행했다.

---

## 1. 즉시 반영된 개선 (main에 커밋+push 완료, 즉시 유효)

### 1a. 웹어드민 카테고리별 주제 전체삭제
대기중 주제 하나씩만 지울 수 있던 것을, 카테고리 단위로 한 번에 삭제하는 기능 추가.
- `auth-web/app/api/admin/topics-queue/route.ts`: `DELETE`에 `categoryId+all=true` 모드 추가
- `auth-web/components/DashboardContent.tsx`: "전체삭제 (N)" 버튼

### 1b. 주제생성 프롬프트 개선 — 중복회피 · 다양성 · temperature
- 카테고리별 기존 주제 최대 80개를 조회해 "겹치는 주제 금지" 지시로 프롬프트에 주입
- "최소 5개 이상 서로 다른 각도" 다양성 요구사항 추가
- `generateJsonWithModelSetting`/`callClaude`/`callGemini`(`auth-web/lib/aiRouter.ts`)에 옵션
  `temperature` 파라미터 추가, 주제생성 호출에만 `1.0` 명시 적용(다른 호출부는 영향 없음)

### 1c. 대본기획 배선 복구 (죽은 코드 재연결)
`/api/gemini/generate-structure`(`app/routers/gemini.py`)가 벤치마크 분석/누적 학습지식/최근
주제 목록을 **조회만 하고 실제로는 버리고 있던** 문제 발견 — `scene_planner_service.plan_scenes()`
(`app/services/scene_planner.py`)가 이 세 값을 받아 프롬프트에 실제로 반영하도록 수정.

### 1d. 대기 주제 일괄 삭제 (실제 운영 작업, 1회성)
쌓여있던 대기중 주제 **2,163개**를 전부 삭제(진행중/완료 상태는 건드리지 않음). 이후 개선된
프롬프트로 다시 생성하도록 안내.

---

## 2. AIR-0230: Hermes 벤치마크 워커 아키텍처 (설계 + 구현)

### 2a. 조사로 확인된 사실들
- `topic.html`의 유튜브 검색+분석 기능은 클라이언트에서만 "성과도" 계산(저장 안 됨), 저장되는
  `viral_score`는 구독자 수와 무관한 별개 지표
- 분석 저장 시 백그라운드로 성공전략을 추출해 학습지식으로 축적하지만, **사용자 개인 로컬
  SQLite에만 쌓여** 플랫폼 전체가 공유하지 못함
- AIRWorker.exe(렌더링 PC 상시 프로그램)에 이미 Hermes Worker 프로세스가 존재 — PR #86
  (`feat/air-0227e-p3-real-hermes-worker`, 검증 완료·미병합)이지만, 순수 "키워드→LLM 프롬프트로
  주제 생성"만 하고 실제 유튜브 검색/자막/댓글 분석 로직은 없음(직접 검색으로 0건 확인)
- 렌더용 중앙 job lease/claim 프로토콜이 이미 설계+구현돼 있음(`migrations/air_0227d_worker_central_protocol.sql`,
  AIR-0227D) — 단, **실제 Postgres에는 미적용**, `remote_render_queue.project_id`가 `NOT NULL`이라
  프로젝트 없는 topic/기획 작업은 그대로 못 씀

### 2b. 설계 결정
- 벤치마크 분석(유튜브 검색+자막+댓글+AI분석)은 **렌더링 PC(Hermes Worker)에서 실행하고 결과
  JSON만 중앙에 전송** — 자막추출(`youtube_transcript_api`)이 Python 전용이라 Vercel/Next.js에서
  못 돌리는 게 핵심 이유
- 중앙 job 테이블은 `remote_render_queue` 재사용이 아니라 **완전히 분리된 신규 테이블**
  (`remote_hermes_queue`) — `project_id NOT NULL` 제약 때문에 렌더 테이블에 억지로 넣으면
  기존 프로덕션 워커 계약을 건드리게 됨

### 2c. 구현한 것
| 구성요소 | 내용 | 위치 |
|---|---|---|
| `topic_benchmark_analyze` job_type | 유튜브 검색→구독자 대비 조회수 랭킹→상위 1~3개 자막/댓글 분석→성공전략 추출. 기존 함수(`source_service`, `gemini_service`) 재사용, 새 AI 로직 없음 | `worker/hermes_worker.py` |
| 중앙 job 프로토콜 (결정 B) | `remote_hermes_queue`+감사로그+idempotency 테이블, RPC 4개(claim/renew/progress/outcome). 렌더 테이블·RPC는 전혀 안 건드림. `workers`/`worker_tokens`는 이미 범용이라 재사용 | `migrations/air_0230_hermes_worker_central_protocol.sql` |
| 웹어드민 트리거 (§2b, 수동+자동 둘 다) | 카테고리별 "고성과 영상 분석 실행" 버튼(수동, 7일 이내 완료 분석 있으면 재사용) + 매일 새벽 3시(UTC) 전체 카테고리를 훑는 Vercel Cron(자동) — 두 트리거가 `lib/benchmarkAnalyzeTrigger.ts`로 정책 공유(중복 큐잉 방지 포함) | `auth-web/app/api/admin/topics-queue/benchmark-analyze/route.ts`, `auth-web/app/api/admin/cron/trigger-benchmark-analyze/route.ts`, `DashboardContent.tsx`, `vercel.json` |
| 분석결과 → 주제생성 반영 | 카테고리의 최신 완료 분석을 프롬프트에 실제 근거로 주입 + 생성되는 모든 주제에 `benchmark_analysis`로 저장 | `topics-queue/route.ts` POST |
| claim_topic 연결 (§2c) | `topics_queue.benchmark_analysis`/`pregenerated_structure`/`pregenerated_script`를 각각 `project_settings`로 복사 | `app/routers/user_topics.py` |
| `script_plan_generate` job_type | `topics_queue` 행 하나의 씬 구조를 미리 생성 — `scene_planner_service.plan_scenes()`를 그대로 재사용(실시간 생성과 결과물 동일 모양) | `worker/hermes_worker.py` |
| **`script_generate` job_type** | 씬 구조를 받아 **본문 나레이션 텍스트를 섹션 단위로 전부 사전생성** — `templates/pages/script_gen.html`의 클라이언트 알고리즘(길이 계산, 나레이션 모드 지침, 정제 정규식, multi 모드 등장인물 연속성)을 Python으로 포팅 | `worker/hermes_worker.py` |
| 파이프라인 체이닝 | `script_plan_generate` 완료 시 같은 topic에 대해 자동으로 `script_generate`를 이어서 큐잉(구조가 있어야 대본을 쓸 수 있으므로) | `auth-web/.../jobs/[jobId]/complete/route.ts` |
| 사전생성 버퍼 (§2d) | 주제 생성 직후 카테고리당 **최신 3개만** 기획→대본까지 체이닝(전체 백로그 사전생성은 비용 폭증이라 채택 안 함) | `topics-queue/route.ts` POST |
| 완료 시 자동 반영 | job 완료되면 `topics_queue.pregenerated_structure`/`pregenerated_script`에 자동 기록, 실패 시 상태만 표시(재시도 판단용) | `auth-web/.../jobs/[jobId]/complete·fail/route.ts` |
| **실시간 생성 폴백 완전 제거 (사용자 결정)** | `topics_queue`에서 claim된 프로젝트(`project_settings.topic_queue_id` 존재)는 사전생성이 준비 안 됐을 때 AI를 대신 부르지 않고 "대기중" 상태만 반환. **PRO의 수동 생성 프로젝트(`topic_queue_id` 없음)는 영향 없음** — 실시간 생성이 그대로 유일한 경로로 남음. 3가지 분기(대기/준비됨/수동프로젝트 무관)를 전부 테스트로 확인 | `app/routers/gemini.py::generate_script_structure_api()`, `templates/pages/script_gen.html::generateScript()` |
| 렌더 워커 중앙연동 이식 | `render_worker.py`의 로컬↔중앙 이중 소스 패턴(lease 갱신, 완료/실패 보고, 재시도 큐)을 Hermes Worker에도 이식 — 공유 모듈(`central_client.py`/`job_store.py`)이 이미 범용이라 거의 그대로 재사용 | `worker/hermes_worker.py` |

부수적으로 발견해 함께 고친 기존 버그:
- `central_client.renew_lease()`가 존재하지 않는 경로(`/renew-lease`)를 호출해 렌더 작업 lease
  갱신도 원래 항상 404였음 — `/renew`로 수정.
- **[중요] `script_gen.html`이 AIR-0209 이후 모든 대본 생성 프롬프트에 "제목: undefined"를
  보내고 있었음** — `scene_planner.py`의 실제 씬 스키마(`scene_summary`/`scene_situation`/
  `scene_purpose` 등)와 이 파일이 읽던 필드(`section.title`/`section.key_points`)가 애초에
  안 맞았고, 그 둘을 변환하는 코드가 프로젝트 어디에도 없었음(전수 검색으로 확인) — 씬 기획의
  디테일이 실제 대본 생성에 지금까지 전혀 반영이 안 되고 있었다는 뜻. 실제 씬 필드를 쓰도록
  라이브 코드와 워커 포팅본 둘 다 수정.
- `script_gen.html`이 프로젝트 언어(`projectLanguage`)를 조회만 하고 실제로는 안 써서 항상
  한국어로만 생성되고 있었음 — 언어 지침 추가.

### 2d. 남은 것
본문 대본 사전생성까지 이번 세션에서 마저 구현했다(위 표 참고, 원래는 범위 밖이었으나 사용자
결정으로 착수). 남은 건 순수 배포 작업뿐(§4).

---

## 3. 검증

- 모든 변경: `py_compile`(Python), `tsc --noEmit`(TypeScript, 기존 에러 외 신규 없음 확인)
- SQL 마이그레이션 5개: `pglast` 문법 검증 통과
- 워커 로직: mocked 유닛테스트로 payload 검증/랭킹/전체 상태전이(PREPARING→RENDERING→UPLOADING→COMPLETED) 확인, 원격 job은 `central_client.complete_job`이 올바른 result_payload로 호출되고 로컬 job은 호출 안 됨을 확인
- `script_generate`: mocked 테스트로 씬 필드(`scene_summary` 등)가 실제 프롬프트에 반영되는지, **multi 모드에서 등장인물 이름이 섹션 i→i+1로 정확히 이어지는지** 별도 확인
- 실시간 생성 폴백 제거: 3가지 분기(대기중 프로젝트/준비된 프로젝트/PRO 수동 프로젝트) 전부 직접 테스트로 확인 — PRO 프로젝트는 크레딧 체크·AI 호출 경로에 그대로 도달함을 증명
- `script_gen.html` 수정본: `node --check`로 JS 문법 확인, Jinja2 템플릿 파싱 확인(로그인 필요라 브라우저 클릭 테스트는 못 함)
- 기존 회귀 테스트(`test_script_style_integration.py` 등) 18개 통과 유지
- **실 API(YouTube/Gemini/Supabase)로는 검증 안 함** — 마이그레이션 미적용 상태라 불가능
- 웹어드민 신규 UI는 관리자 로그인 뒤에 있어 클릭 테스트는 못 함(dev 서버 컴파일 정상까지만 확인)

---

## 4. 미해결·다음 단계

이번 세션에서 남긴 건 이제 **순수 배포/운영 작업뿐** — 코드 관점의 열린 설계 결정은 없음.

1. **마이그레이션 5개 스테이징 적용** — 전부 "DO NOT run against production" 초안 상태, 순서
   중요(1번이 먼저 — 워커 인증 테이블):
   - `migrations/air_0227d_worker_central_protocol.sql` (선행, AIR-0230 이전부터 미적용 상태였음 — `workers`/`worker_tokens` 포함)
   - `migrations/air_0230_hermes_worker_central_protocol.sql`
   - `migrations/air_0230_topics_queue_benchmark_analysis_column.sql`
   - `migrations/air_0230_topics_queue_pregenerated_structure_columns.sql`
   - `migrations/air_0230_topics_queue_pregenerated_script_columns.sql`
2. **워커 토큰 발급** — 마이그레이션 적용 후 `POST /api/admin/worker-tokens`로
   `{worker_id, worker_group:"air-worker", allowed_job_types:["topic_research","topic_benchmark_analyze","script_plan_generate","script_generate"]}` 호출 →
   응답의 `raw_token`을 렌더링 PC의 `AIRWORKER_TOKEN`/`AIRWORKER_CENTRAL_SERVER_URL` 환경변수로 설정.
3. **브랜치 리뷰/병합**:
   - PR [#86](https://github.com/ibnetsoft/mytube/pull/86) `feat/air-0227e-p3-real-hermes-worker` (선행, 미병합)
   - PR [#135](https://github.com/ibnetsoft/mytube/pull/135) `feat/air-0230-topic-benchmark-analyze` (이번 세션, #86을 base로 함, 커밋 9개)
4. **AIRWorker.exe 실제 렌더링 PC 재배포** — 위 두 PR 병합 후에나 의미 있음
5. **배포 전까지 STD 흐름 영향 인지** — 실시간 생성 폴백을 완전히 제거했으므로, 위 배포가 끝나기
   전에는 STD가 주제를 claim해도 기획/대본이 나오지 않는다("대기중" 응답만 받음). PRO 수동
   프로젝트는 영향 없음.

## 관련 문서
- [docs/AIR_0230_HERMES_BENCHMARK_WORKER_ARCHITECTURE.md](../docs/AIR_0230_HERMES_BENCHMARK_WORKER_ARCHITECTURE.md) — 설계 원문, 진행상황 계속 갱신됨
- [docs/AIR_WORKER_JOB_PROTOCOL.md](../docs/AIR_WORKER_JOB_PROTOCOL.md) §5a/§5b/§5c — 이번에 추가한 job_type 3개의 payload 스키마
- [worknote/AIR-0226-stage1-current-state-analysis.md](./AIR-0226-stage1-current-state-analysis.md) — 이 작업의 선행 조사(주제 큐 현황 분석)

## 커밋 목록

**main** (`461e22f5`..`c58ad2f4`, 전부 push 완료):
```
9d8920de docs(AIR-0230): Hermes benchmark worker architecture
55feec37 docs(AIR-0230): specify manual + automatic trigger modes
2a169688 docs(AIR-0230): record topic_benchmark_analyze implementation progress
564ee90c docs(AIR-0230): record central job protocol (decision B) implementation progress
ece74802 fix(script-plan): reconnect benchmark analysis + accumulated knowledge into scene planning
d5e4bc9a feat(topics-queue): dedup/diversity in topic generation + bulk delete + AIR-0230 benchmark pipeline
3a05f3e4 feat(AIR-0230 §2d): pre-bake scene structures ahead of topic claim
80273626 chore(migrations): copy AIR-0227D render-worker central protocol migration onto main
4cefc5de feat(AIR-0230 §2b): automatic (scheduled) trigger for topic_benchmark_analyze
c58ad2f4 feat(AIR-0230 §2d, user decision): remove live-generation fallback for claimed topics, fix scene-field + language bugs
```

**`feat/air-0230-topic-benchmark-analyze`** (PR #86 기준, 전부 push 완료, PR #135):
```
ff56f507 feat(AIR-0230): add topic_benchmark_analyze job type to Hermes Worker
3eb47bd5 feat(AIR-0230): central job protocol for Hermes/topic_* jobs (decision B)
ff48f413 fix(script-plan): reconnect benchmark analysis + accumulated knowledge (cherry-pick)
3d79f4cc feat(AIR-0230): add script_plan_generate job type - §2d pre-bake, structure only
00ae68d5 feat(AIR-0230): sync script_plan_generate results back to topics_queue
cb6dbf55 feat(AIR-0230): add script_generate job type - full narration pre-generation, fixes live scene-field bug
ebbd08dc feat(AIR-0230 §2d): chain script_plan_generate -> script_generate, sync script results
```
