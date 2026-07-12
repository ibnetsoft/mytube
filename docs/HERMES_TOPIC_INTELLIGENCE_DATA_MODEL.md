# AIR Topic Intelligence — 데이터 모델 (설계 + SQL 초안)

- 상태: **설계안 / SQL 초안 — production에 적용하지 않음** (지시사항 6단계 금지사항 준수)
- 명명/스타일 컨벤션은 `worknote/AIR-0225B-stage0-service-role-removal-investigation.md`에서
  정리한 이 저장소의 기존 하우스 스타일(UUID PK, `profiles(id)` FK, `metadata JSONB`,
  `created_at`/`updated_at` + 트리거, RLS enabled + self-only SELECT, CHECK 제약 상태값,
  soft-delete 없음)을 그대로 따른다.

## 0. 공통 원칙

- **모든 사용자 관련 데이터에 `tenant_id`를 포함**한다 (원칙 그대로). `tenant_id`는 기존
  멀티테넌트 개념(`services/web_admin_client.py`의 `tenant_key`류)과 정렬하되, 정확한 참조
  대상(별도 `tenants` 테이블 존재 여부)은 CTO 확인이 필요해 `TEXT`로 느슨하게 시작한다
  (§CTO 결정 참고).
- **`channel_id` 단위로 주제 기록과 성과를 분리**한다 — 이번 기능에서 신규 도입하는 개념.
  마찬가지로 정확한 참조 대상(프로필의 `youtube_channel` 재사용 vs 신규 `channels` 테이블)은
  CTO 결정 필요, 우선 `TEXT`로 시작.
- **Hermes는 이 테이블들에 직접 연결하지 않는다.** 전부 `AIR Topic Service`(내장 FastAPI)를
  통해서만 읽고 쓴다 — RLS는 "service_role 전용, 정책 없음" 컨벤션을 유지하고, Hermes는애초에
  service_role을 받지 않으므로(원칙 #5) 이 테이블에 물리적으로 접근할 수단이 없다.

## 1. `topic_research_jobs` — 시장조사 작업 단위

```sql
CREATE TABLE IF NOT EXISTS public.topic_research_jobs (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             TEXT NOT NULL,
    channel_id            TEXT,                       -- NULL 허용: 카테고리 단위 조사(채널 무관)
    category_id           BIGINT,                      -- 기존 Supabase categories.id 참조(느슨한 FK, 크로스 프로젝트라 하드 FK 미설정)
    trigger_source        TEXT NOT NULL DEFAULT 'manual'
                              CHECK (trigger_source IN ('manual','scheduled','sync_fallback')),
    status                TEXT NOT NULL DEFAULT 'queued'
                              CHECK (status IN ('queued','running','completed','failed',
                                                 'invalid_output','timeout')),
    hermes_model_version  TEXT,
    request_context       JSONB NOT NULL DEFAULT '{}'::jsonb,   -- AIR Topic Service가 Hermes에 보낸 컨텍스트(카테고리/채널기억/이력 요약)
    research_context_summary TEXT,                    -- Hermes 응답의 요약 필드(§ARCHITECTURE §4)
    candidate_count       INT NOT NULL DEFAULT 0,
    error_message         TEXT,
    started_at            TIMESTAMPTZ,
    completed_at          TIMESTAMPTZ,
    duration_ms           INT,
    estimated_cost_usd     NUMERIC(10,4),
    actual_cost_usd         NUMERIC(10,4),
    fallback_used           BOOLEAN NOT NULL DEFAULT false,
    fallback_reason          TEXT,
    metadata                  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_topic_research_jobs_tenant ON public.topic_research_jobs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_topic_research_jobs_channel ON public.topic_research_jobs(channel_id);
CREATE INDEX IF NOT EXISTS idx_topic_research_jobs_status ON public.topic_research_jobs(status);
CREATE INDEX IF NOT EXISTS idx_topic_research_jobs_category ON public.topic_research_jobs(category_id);

ALTER TABLE public.topic_research_jobs ENABLE ROW LEVEL SECURITY;
-- service_role(AIR Topic Service 백엔드)만 접근 - 정책 없음 = 기본 거부(AIR-0225B 컨벤션).
```

## 2. `topic_candidates` — Hermes가 생성한 개별 주제 후보

```sql
CREATE TABLE IF NOT EXISTS public.topic_candidates (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    research_job_id       UUID NOT NULL REFERENCES public.topic_research_jobs(id) ON DELETE CASCADE,
    tenant_id             TEXT NOT NULL,
    channel_id            TEXT,
    category_id           BIGINT,

    -- §ARCHITECTURE §4 JSON 스키마 그대로 컬럼화
    title                 TEXT NOT NULL,
    core_concept          TEXT,
    summary               TEXT,
    category              TEXT,
    target_country         TEXT,
    target_language          TEXT,
    target_age                 TEXT,
    emotions                     JSONB NOT NULL DEFAULT '[]'::jsonb,
    trend_reason                  TEXT,
    score_channel_fit               NUMERIC(5,2),
    score_novelty                     NUMERIC(5,2),
    score_trend                         NUMERIC(5,2),
    score_competition                     NUMERIC(5,2),
    score_retention                         NUMERIC(5,2),
    score_total                               NUMERIC(5,2),
    similar_topic_ids                           JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence                                      JSONB NOT NULL DEFAULT '[]'::jsonb,
    risk_flags                                      JSONB NOT NULL DEFAULT '[]'::jsonb,

    status                TEXT NOT NULL DEFAULT 'candidate'
                              CHECK (status IN ('candidate','promoted','rejected','expired')),
    promoted_topics_queue_id BIGINT,                  -- 승격 시 topics_queue.id 역참조(느슨한 FK)
    promoted_at            TIMESTAMPTZ,
    promoted_by            UUID REFERENCES public.profiles(id),  -- NULL이면 자동승격
    rejected_reason         TEXT,
    expires_at                TIMESTAMPTZ,             -- §ARCHITECTURE §3, 기본 7일 제안
    metadata                    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_topic_candidates_job ON public.topic_candidates(research_job_id);
CREATE INDEX IF NOT EXISTS idx_topic_candidates_tenant ON public.topic_candidates(tenant_id);
CREATE INDEX IF NOT EXISTS idx_topic_candidates_channel ON public.topic_candidates(channel_id);
CREATE INDEX IF NOT EXISTS idx_topic_candidates_status ON public.topic_candidates(status);
CREATE INDEX IF NOT EXISTS idx_topic_candidates_score_total ON public.topic_candidates(score_total DESC);
CREATE INDEX IF NOT EXISTS idx_topic_candidates_expires_at ON public.topic_candidates(expires_at);

ALTER TABLE public.topic_candidates ENABLE ROW LEVEL SECURITY;
-- service_role 전용. (PRO 확장 시 "자기 채널 것만 SELECT" 정책 추가를 고려 - 이번 범위 아님)
```

## 3. `topic_usage_history` — 중복 검사용 사용 이력 (지금 없는 기능, §Stage1 §5)

```sql
CREATE TABLE IF NOT EXISTS public.topic_usage_history (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             TEXT NOT NULL,
    channel_id            TEXT,
    source                TEXT NOT NULL DEFAULT 'topics_queue'
                              CHECK (source IN ('topics_queue','topic_candidates','manual')),
    source_id             TEXT NOT NULL,              -- topics_queue.id 또는 topic_candidates.id (텍스트로 통일)
    title                 TEXT NOT NULL,
    core_concept_summary  TEXT,                        -- Hermes 컨텍스트 조립 시 이 요약만 전달(§SECURITY §2)
    category              TEXT,
    language               TEXT,
    used_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    embedding_vector           JSONB,                  -- 향후 벡터 유사도 검색 도입 시 사용(초기엔 NULL, PoC는 텍스트 비교로 대체)
    metadata                     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_topic_usage_history_tenant ON public.topic_usage_history(tenant_id);
CREATE INDEX IF NOT EXISTS idx_topic_usage_history_channel ON public.topic_usage_history(channel_id);
CREATE INDEX IF NOT EXISTS idx_topic_usage_history_used_at ON public.topic_usage_history(used_at DESC);

ALTER TABLE public.topic_usage_history ENABLE ROW LEVEL SECURITY;
-- service_role 전용. Hermes에게는 원문 테이블이 아니라 AIR Topic Service가
-- research-context API 응답에 담아주는 "제목+핵심사건 요약 리스트"로만 노출(§SECURITY §2).
```

## 4. `topic_feedback_events` — 후보/큐 항목에 대한 사람 피드백

```sql
CREATE TABLE IF NOT EXISTS public.topic_feedback_events (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             TEXT NOT NULL,
    channel_id            TEXT,
    topic_candidate_id    UUID REFERENCES public.topic_candidates(id) ON DELETE SET NULL,
    topics_queue_id       BIGINT,                      -- topic_candidates 경유 없이 기존 큐 항목에 대한 피드백도 허용
    actor_id              UUID REFERENCES public.profiles(id),
    event_type            TEXT NOT NULL
                              CHECK (event_type IN ('approved','rejected','claimed','skipped',
                                                     'reported_duplicate','reported_low_quality')),
    reason                TEXT,
    metadata               JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_topic_feedback_events_tenant ON public.topic_feedback_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_topic_feedback_events_candidate ON public.topic_feedback_events(topic_candidate_id);
CREATE INDEX IF NOT EXISTS idx_topic_feedback_events_type ON public.topic_feedback_events(event_type);

ALTER TABLE public.topic_feedback_events ENABLE ROW LEVEL SECURITY;
-- service_role 전용.
```

## 5. `channel_content_profile` — "채널 기억" (목표 문구 원문 그대로 구현)

```sql
CREATE TABLE IF NOT EXISTS public.channel_content_profile (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             TEXT NOT NULL,
    channel_id            TEXT NOT NULL,
    channel_display_name  TEXT,
    primary_category      TEXT,
    target_country          TEXT,
    target_language            TEXT,
    tone_profile                  JSONB NOT NULL DEFAULT '{}'::jsonb,   -- Hermes가 누적 학습한 톤/감정 경향
    recurring_themes                JSONB NOT NULL DEFAULT '[]'::jsonb,
    avoided_themes                     JSONB NOT NULL DEFAULT '[]'::jsonb,  -- 과거 저성과/반려 사유 누적
    audience_notes                       TEXT,
    last_research_job_id                    UUID REFERENCES public.topic_research_jobs(id),
    last_updated_by_hermes                     TIMESTAMPTZ,
    metadata                                     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                                     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                                       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_channel_content_profile_tenant_channel
    ON public.channel_content_profile(tenant_id, channel_id);

ALTER TABLE public.channel_content_profile ENABLE ROW LEVEL SECURITY;
-- service_role 전용. Hermes는 research-context API 응답으로 이 행의 요약만 읽고,
-- 조사 후 갱신 제안은 submit-candidates API의 부가 필드로 제출 -> AIR Topic Service가 검증 후 UPDATE.
-- Hermes가 이 테이블에 직접 쓰지 않는다(원칙 #4/#5).
```

## 6. `topic_performance` — 성과 피드백 루프 (PRO 확장 대비, STD는 최소 사용)

```sql
CREATE TABLE IF NOT EXISTS public.topic_performance (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             TEXT NOT NULL,
    channel_id            TEXT,
    topics_queue_id       BIGINT,
    topic_candidate_id    UUID REFERENCES public.topic_candidates(id) ON DELETE SET NULL,
    local_project_id      BIGINT,                      -- SQLite projects.id 역참조(문서 §연동 참고, 로컬 DB라 하드 FK 없음)
    published_at           TIMESTAMPTZ,
    views_24h                BIGINT,
    views_7d                    BIGINT,
    retention_pct_avg              NUMERIC(5,2),
    like_ratio                       NUMERIC(5,2),
    comments_count                     INT,
    performance_tier                     TEXT
                              CHECK (performance_tier IN ('low','average','good','viral', NULL)),
    data_source                            TEXT NOT NULL DEFAULT 'manual'
                              CHECK (data_source IN ('manual','youtube_api','estimated')),
    metadata                                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                                   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_topic_performance_tenant ON public.topic_performance(tenant_id);
CREATE INDEX IF NOT EXISTS idx_topic_performance_channel ON public.topic_performance(channel_id);
CREATE INDEX IF NOT EXISTS idx_topic_performance_candidate ON public.topic_performance(topic_candidate_id);

ALTER TABLE public.topic_performance ENABLE ROW LEVEL SECURITY;
-- service_role 전용.
```

**금지 사항 확인**: `performance_tier`/`views_24h` 등은 전부 `data_source`로 출처를 명시하고,
"실제 조회수 보장 또는 허위 예측 점수" 금지 원칙에 따라 **Hermes가 조회수를 예측해 이 테이블에
쓰는 경로는 설계에 포함하지 않았다** — 이 테이블은 어디까지나 사후(발행 후) 실측/수동 입력용이며,
Hermes의 `score_trend` 등은 어디까지나 `topic_candidates`의 "추천 점수"이지 조회수 예측이 아님을
UI 문구에도 명시해야 한다(§SECURITY §6).

## 7. RLS 정책 초안 요약

전 테이블 공통: `ALTER TABLE ... ENABLE ROW LEVEL SECURITY;` 후 **정책을 추가하지 않는다** —
AIR-0225B에서 확립한 컨벤션 그대로("service_role은 RLS를 우회하므로 별도 정책 불필요", 일반
`anon`/`authenticated` role은 기본 거부). Hermes는 service_role을 받지 않으므로(원칙 #5) 이
테이블들에 물리적으로 접근할 방법이 없다 — 오직 `AIR Topic Service`의 2개 내부 API(§ARCHITECTURE §5)를
통해서만 간접 접근한다.

향후 PRO 확장에서 "사용자가 자기 채널의 `topic_candidates`/`channel_content_profile`을 직접 조회"하는
화면이 생기면, 그때 `auth.uid()`와 `channel_id` 소유권을 연결하는 self-access 정책을 추가 검토
(이번 범위 아님).

## 8. 예상 마이그레이션 파일명

`worknote/AIR-0225B-stage0-service-role-removal-investigation.md`에서 확인한 대로 이 저장소는
`migrations/air_XXXX_*.sql` 넘버링을 여러 작업이 동시에 소비 중이라, **정확한 번호는 구현
착수 시점에 재확인**해야 한다(가제: `air_022X_hermes_topic_intelligence_foundation.sql` +
`_rollback.sql`, 새 테이블 6개짜리 기반 마이그레이션이라 AIR-0221 수준의 전체 5파일 세트
[`.sql`+`_APPLY.sql`+`_rollback.sql`+`_CHECKLIST.md`+`_IMPACT.md`] 패턴을 따르는 것을 제안).

## 9. CTO 결정 필요 항목 (데이터 모델 관련)

1. `tenant_id`의 정확한 참조 대상 — 기존 `tenant_key` 개념과 통합할지, 신규 `tenants` 테이블을
   먼저 만들지.
2. `channel_id`의 정확한 참조 대상 — `profiles.youtube_channel` 재사용 vs 신규 `channels` 테이블.
3. `topic_candidates.expires_at` 기본값(제안: 7일, `user_topic_recommendations` 관례 참고).
4. 자동승격 점수 임계값(예: `score_total >= 80`)과 그 값을 서버 설정으로 둘지 하드코딩할지.
