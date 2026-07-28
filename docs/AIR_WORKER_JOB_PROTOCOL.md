# AIR Worker — 작업(Job) 프로토콜

- 상태: **로컬 구현 및 실측 완료(AIR-0227B/C) / 프로덕션 미배포**
- 관련 문서: [ARCHITECTURE](./AIR_WORKER_ARCHITECTURE.md), [PROCESS_MODEL](./AIR_WORKER_PROCESS_MODEL.md), [RESOURCE_POLICY](./AIR_WORKER_RESOURCE_POLICY.md), [LEASE_PROTOCOL](./AIR_WORKER_LEASE_PROTOCOL.md), [JOB_RECOVERY](./AIR_WORKER_JOB_RECOVERY.md)

> **AIR-0227C 업데이트**: §2의 공통 필드는 실제 구현(`worker/job_store.py`)에서
> `lease_id`/`worker_instance_id`/`lease_expires_at`/`attempt_number`/`remote_job_id`/
> `remote_ack_status`가 추가됐고, `status`는 이 문서의 `queued|claimed|running|paused|...`
> 대신 AIR-0227B가 도입한 `QUEUED/CLAIMED/PREPARING/RENDERING/UPLOADING/COMPLETED/FAILED/
> CANCELED/ABANDONED` 열거형을 실제로 쓴다(§JOB_RECOVERY.md 참고) - 이 문서의 스키마는
> 최초 설계 의도 기록으로 남겨두고, 실제 필드 목록은 [LEASE_PROTOCOL.md](./AIR_WORKER_LEASE_PROTOCOL.md) §2가
> 최신이다.

## 1. 공통 Job Dispatcher

Render Worker Process와 Hermes Worker Process는 **공통 Job Dispatcher가 job_type으로 구분해서
알맞은 프로세스로 라우팅**한다 — Dispatcher 자체는 Job Scheduler(Worker Manager 내부, §PROCESS_MODEL)의
일부. `render_*` 타입은 항상 Render Worker Process로, `topic_*`/`health_check`는 Hermes Worker
Process 또는 Manager 자체로 라우팅된다.

```
job_type              → 처리 프로세스
render_image           → Render Worker Process
render_video           → Render Worker Process
render_audio            → Render Worker Process
topic_research           → Hermes Worker Process
topic_benchmark_analyze    → Hermes Worker Process (AIR-0230, §5a — 구현 완료: worker/hermes_worker.py)
script_plan_generate         → Hermes Worker Process (AIR-0230, §5b — 구현 완료: worker/hermes_worker.py)
topic_generate             → Hermes Worker Process
topic_deduplicate            → Hermes Worker Process (AIR-0226의 하네스 dedup 로직 재사용 대상)
topic_rank                     → Hermes Worker Process
health_check                     → Worker Manager 자체 처리(외부 프로세스 호출 없음)
```

## 2. 공통 작업 필드 (모든 job_type 공통)

```json
{
  "job_id": "uuid",
  "job_type": "render_image | render_video | render_audio | topic_research | topic_generate | topic_deduplicate | topic_rank | health_check",
  "priority": 0,
  "payload": { "...job_type별 상세 필드..." },
  "status": "queued | claimed | running | paused | completed | failed | cancelled",
  "created_at": "ISO8601",
  "started_at": "ISO8601 | null",
  "completed_at": "ISO8601 | null",
  "retry_count": 0,
  "max_retries": 3,
  "error_code": "string | null",
  "error_message": "string | null"
}
```

- `status`에 지시사항 원문엔 없던 **`paused`**를 추가로 정의했다 — 4단계 "실행 중인 Hermes
  작업은 안전한 체크포인트에서 일시 정지 가능하도록 설계"를 상태값으로 표현하려면 필요하다
  (렌더링 작업엔 이 상태가 실질적으로 쓰이지 않지만, 스키마는 공통이므로 함께 정의).
- `payload`는 job_type마다 다른 구조 — render 계열은 project_id/asset 참조/해상도 등,
  topic 계열은 category_id/channel_id/research_job_id 등(AIR-0226 `topic_research_jobs`/
  `topic_candidates` 스키마와 정렬).

## 3. 작업 출처와 이번 Task의 경계

**중앙 서버가 작업을 생성/배분한다**(§ARCHITECTURE §4) — AIR Worker는 이 공통 스키마로
표현된 작업을 **수신만** 하고, 실제 소스 오브 트루스(어떤 렌더 작업이 있는지, 어떤 주제 조사가
필요한지)는 여전히 중앙 서버/Supabase에 있다. 이번 Task(#12 스켈레톤)에서는 **실제 중앙
서버 연동 없이, 로컬 모의 작업 생성기**로 이 스키마의 job 객체를 만들어 Dispatcher →
모의 프로세스로 흘려보내는 것까지만 구현한다(금지사항 "운영 DB 연결 금지" 준수).

## 4. Render 계열 payload (설계 초안, 실 연동은 후속 Task)

```json
{
  "render_image": {"project_id": int, "scene_number": int, "prompt": "string", "style": "string"},
  "render_video": {"project_id": int, "asset_zip_ref": "string(Drive file id 등)", "use_subtitles": bool, "resolution": "string"},
  "render_audio": {"project_id": int, "script_text": "string", "provider": "string", "voice_id": "string"}
}
```
`render_video`의 `asset_zip_ref`는 Stage 1에서 확인한 살아있는 Drive-릴레이 경로
(`services/remote_drive_render_service.py`)의 계약을 그대로 계승 — Drive에 올라간 자산 ZIP을
참조하는 방식.

## 5. Topic 계열 payload (AIR-0226 스키마와 정렬)

```json
{
  "topic_research": {"category_id": "...", "channel_id": "...", "tenant_id": "..."},
  "topic_generate": {"research_job_id": "uuid", "candidate_count": 20},
  "topic_deduplicate": {"candidate_ids": ["..."], "usage_history_window": 200},
  "topic_rank": {"candidate_ids": ["..."], "top_n": 10}
}
```
AIR-0226에서는 "조사→생성→중복검사→랭킹"이 Hermes 한 번의 호출 안에 묶여 있었다(§POC).
AIR Worker의 job_type 세분화(`topic_research`/`topic_generate`/`topic_deduplicate`/`topic_rank`
가 별개 job_type인 것)는 이걸 **선택적으로 단계별 재시도/재개가 가능하게 쪼갤 수 있는 여지**를
설계에 남겨두는 것 — 이번 Task에서 실제로 이렇게 쪼개서 구현하진 않지만(AIR-0226의 단일 호출
방식이 여전히 기본), 스키마 상으로는 각 단계가 독립 job으로 표현 가능하다는 점을 명시해둔다.

### 5a. `topic_benchmark_analyze` payload (AIR-0230, 구현 완료)

```json
{
  "topic_benchmark_analyze": {
    "keyword": "string (필수 — 카테고리의 keywords/name, job 생성 시점에 호출자가 리터럴 값으로 채움)",
    "language": "string, 기본 'ko' (ko|en|ja)",
    "video_type": "string, 기본 'longform' (longform|shorts)",
    "max_candidates": "int, 기본 1, 최대 3 (분석까지 진행할 상위 고성과 영상 개수)",
    "search_pool_size": "int, 기본 15, 최대 30 (성과도 랭킹 대상 검색 후보 수)"
  }
}
```

- `category_id`를 받지 않는다 — 워커는 Supabase 접근 권한이 없으므로(§ARCHITECTURE §4 경계),
  이 job을 만드는 쪽(웹어드민, 수동/자동 트리거 둘 다 — `docs/AIR_0230_HERMES_BENCHMARK_WORKER_ARCHITECTURE.md`
  §2b)이 카테고리의 keywords/language/video_type을 미리 조회해 리터럴 값으로 payload에 넣어야 한다.
- 처리: 유튜브 검색(`search_pool_size`개) → 구독자 대비 조회수(`performance_ratio`)로 랭킹 →
  상위 `max_candidates`개만 자막+댓글 수집 → Gemini 분석 + 성공전략 추출. 기존 함수 재사용
  (`services/source_service.py::extract_text_from_youtube`, `services/gemini_service.py::analyze_comments`/
  `extract_success_strategy`) — 새 AI 로직 없음.
- **결과는 항상 로컬 `RESULTS_DIR`에 저장되고, 원격 claim으로 들어온 job이면 추가로 중앙에도
  보고된다** — [갱신, AIR-0230 중앙 job 프로토콜 커밋] `migrations/air_0230_hermes_worker_central_protocol.sql`의
  `report_worker_hermes_job_outcome`이 `p_result_payload`를 받아 `remote_hermes_queue.result_payload`에
  인라인 저장하고, `central_client.complete_job(..., result_payload=...)`가 이걸 실제로 채운다.
  이전 버전 문서(§3 "이번 Task의 경계")가 말하던 "중앙 업로드 없음"은 topic_research를 만들 당시
  (AIR-0227E-P3) 기준이었고, 지금은 두 job_type 다 중앙 프로토콜을 탄다.
- 비용 주의: `topic_research`(LLM 호출 1회)보다 훨씬 비싸다 — 후보당 검색+통계 조회+댓글 조회+
  AI 호출 2회(분석+전략추출)가 추가된다. `max_candidates`/`search_pool_size` 상한을 넉넉하게
  올리지 말 것.

### 5b. `script_plan_generate` payload (AIR-0230, 구현 완료)

```json
{
  "script_plan_generate": {
    "topic_queue_id": "string (필수 — 결과를 다시 써넣을 topics_queue 행, 다른 job_type과
      달리 이 필드가 없으면 job 자체가 무의미하므로 payload 검증에서 필수로 강제)",
    "topic": "string (필수)",
    "target_duration_seconds": "int, 기본 60",
    "script_style": "string, 기본 'default'",
    "language": "string, 기본 'ko'",
    "benchmark_analysis": "object|null (topics_queue.benchmark_analysis를 그대로 전달 — §5a 결과의
      candidates[0].analysis 형태와 동일한 단일 영상 분석 shape)"
  }
}
```

- §2d "사전생성 버퍼"(주제를 클레임하기 전에 기획을 미리 만들어두기)의 실행 단위 — 웹어드민이
  카테고리당 주제를 생성한 직후, 그중 최신 K개에 대해 이 job_type을 큐잉한다
  (`auth-web/app/api/admin/topics-queue/route.ts`).
- 처리: `app/services/scene_planner.py::scene_planner_service.plan_scenes()`를 **그대로** 호출 —
  실시간 클레임 흐름(`app/routers/gemini.py::generate_script_structure_api()`)이 쓰는 것과
  동일한 함수라서, 미리 만든 결과와 즉석에서 만든 결과가 모양상 구분되지 않는다.
- `resolve_script_style_directive()`가 이 워커 PC의 로컬 `script_style_presets`를 읽으므로,
  이 PC의 프리셋이 웹어드민과 동기화돼 있다는 전제에 의존한다(다른 데스크톱 설치본과 동일한
  기존 가정 — 이 job_type이 새로 만든 리스크 아님).
- **완료 시 자동 반영**: `auth-web/app/api/internal/worker/jobs/[jobId]/complete/route.ts`가
  `job_type === 'script_plan_generate'`이고 성공이면, `result_payload.structure`를
  `topics_queue.pregenerated_structure`에, `pregenerated_structure_status`를 `'ready'`로
  자동 반영한다(sync-back). 이후 `claim_topic()`이 이 컬럼을 `project_settings`로 복사하고,
  `generate_script_structure_api()`가 AI를 다시 부르지 않고 이 값을 즉시 반환한다.
- **대본 본문(narration text) 사전생성은 이번 범위 밖**: 그 로직(`templates/pages/script_gen.html`)은
  지금 클라이언트 JS에만 있고, 섹션 간 상태(등장인물 이름 재사용)를 순차적으로 이어가는 구조라
  Python으로 그대로 옮기면 로직이 두 벌로 갈라져 나중에 어긋날 위험이 크다 — 별도 검토 후 착수
  권장(`docs/AIR_0230_HERMES_BENCHMARK_WORKER_ARCHITECTURE.md` §2d 참고).

## 6. 재시도/실패 처리

- `retry_count < max_retries`이고 재시도 가능한 오류(네트워크 타임아웃 등)면 Job Scheduler가
  같은 job을 다시 큐에 올린다(`status: failed → queued`, `retry_count += 1`).
- `max_retries` 소진 시 `status: failed`로 확정, `error_code`/`error_message`를 채워 중앙
  서버에 보고(진행률 보고 채널, §ARCHITECTURE §4 "진행률 보고"). 이 보고 자체도 Worker Token
  범위 안의 "작업 진행률 및 결과 전송" 권한으로 수행(§SECURITY).
- `health_check`는 재시도 개념이 없음 — 실패해도 그냥 다음 주기에 다시 시도(하트비트 성격).
