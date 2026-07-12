# AIR Worker — 작업(Job) 프로토콜

- 상태: **설계안 / CTO 승인 대기**
- 관련 문서: [ARCHITECTURE](./AIR_WORKER_ARCHITECTURE.md), [PROCESS_MODEL](./AIR_WORKER_PROCESS_MODEL.md), [RESOURCE_POLICY](./AIR_WORKER_RESOURCE_POLICY.md)

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

## 6. 재시도/실패 처리

- `retry_count < max_retries`이고 재시도 가능한 오류(네트워크 타임아웃 등)면 Job Scheduler가
  같은 job을 다시 큐에 올린다(`status: failed → queued`, `retry_count += 1`).
- `max_retries` 소진 시 `status: failed`로 확정, `error_code`/`error_message`를 채워 중앙
  서버에 보고(진행률 보고 채널, §ARCHITECTURE §4 "진행률 보고"). 이 보고 자체도 Worker Token
  범위 안의 "작업 진행률 및 결과 전송" 권한으로 수행(§SECURITY).
- `health_check`는 재시도 개념이 없음 — 실패해도 그냥 다음 주기에 다시 시도(하트비트 성격).
