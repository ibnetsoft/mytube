-- =============================================================
-- Migration: AIR-0230 — ai_logs에 worker_email 컬럼 추가
-- Description:
--   데스크톱 앱은 프로젝트에 태깅된 담당 직원 이메일(worker_email)을 로컬
--   ai_generation_logs 테이블에 이미 기록하고 있지만, Supabase로 원격
--   동기화하는 payload에는 빠져 있어 웹어드민에서 "누가" API를 많이 썼는지
--   집계할 수 없었다. 이 컬럼을 추가하고 database.py의 _push_remote()가
--   함께 보내도록 한다(AIR-0230 코드 변경과 짝).
--
--   순수 추가(additive) — 기존 데이터/제약에는 영향 없음.
-- =============================================================

ALTER TABLE public.ai_logs ADD COLUMN IF NOT EXISTS worker_email TEXT;

CREATE INDEX IF NOT EXISTS idx_ai_logs_worker_email
    ON public.ai_logs (worker_email, created_at DESC);
