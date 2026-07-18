-- =============================================================
-- Migration: AIR-0231 — ai_logs 보존 정책 (요약 후 삭제)
-- Description:
--   ai_logs가 하루 평균 ~1,400건씩 쌓여(2026-07-19 기준 90일간 128,135건)
--   무한정 방치하면 스토리지/조회 성능에 부담이 된다. 90일이 지난 원본
--   row는 (날짜, 직원, 모델, task_type) 단위로 집계한 요약만 남기고 삭제한다
--   (auth-web/app/api/admin/cron/rollup-ai-logs가 매일 수행).
--
--   요약 테이블은 원본이 지워진 뒤에도 "지난달 대비 이번달 비용" 같은 장기
--   추이 비교가 가능하도록 남겨두는 것이 목적 - 단순 삭제와 다른 점이다.
--
--   Safe to run multiple times (모든 DDL이 idempotent).
-- =============================================================

CREATE TABLE IF NOT EXISTS public.ai_logs_daily_summary (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    log_date        DATE NOT NULL,
    worker_email    TEXT,
    model_id        TEXT,
    provider        TEXT,
    task_type       TEXT,
    count           INTEGER NOT NULL DEFAULT 0,
    success_count   INTEGER NOT NULL DEFAULT 0,
    input_tokens    BIGINT NOT NULL DEFAULT 0,
    output_tokens   BIGINT NOT NULL DEFAULT 0,
    thinking_tokens BIGINT NOT NULL DEFAULT 0,
    -- 롤업 시점의 모델 단가(global_settings.sys_model_pricing)로 계산해 고정한다.
    -- 이후 단가를 바꿔도 과거 요약치는 그때 기준 그대로 남는다(회계 관례와 동일).
    cost_estimate   NUMERIC(12, 4) NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- (날짜, 직원, 모델, task_type) 조합당 하나의 요약 row만 존재해야 하며,
-- NULL 값이 있어도(직원 미확인 등) 중복 upsert가 안전하도록 COALESCE로 고정한다.
CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_logs_daily_summary_unique
    ON public.ai_logs_daily_summary (
        log_date,
        COALESCE(worker_email, ''),
        COALESCE(model_id, ''),
        COALESCE(task_type, '')
    );

CREATE INDEX IF NOT EXISTS idx_ai_logs_daily_summary_date
    ON public.ai_logs_daily_summary (log_date DESC);

-- updated_at 자동 갱신 (AIR-0229 announcements와 동일한 관례)
CREATE OR REPLACE FUNCTION public.set_ai_logs_daily_summary_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ai_logs_daily_summary_updated_at ON public.ai_logs_daily_summary;
CREATE TRIGGER trg_ai_logs_daily_summary_updated_at
    BEFORE UPDATE ON public.ai_logs_daily_summary
    FOR EACH ROW
    EXECUTE FUNCTION public.set_ai_logs_daily_summary_updated_at();

-- RLS: 다른 admin 전용 테이블들과 동일한 관례 - service_role 전용, 클라이언트
-- 직접 접근 정책 없음 (웹어드민 API가 항상 service_role로 조회).
ALTER TABLE public.ai_logs_daily_summary ENABLE ROW LEVEL SECURITY;
