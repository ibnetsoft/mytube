-- Rollback for AIR-0231 — ai_logs_daily_summary
DROP TRIGGER IF EXISTS trg_ai_logs_daily_summary_updated_at ON public.ai_logs_daily_summary;
DROP FUNCTION IF EXISTS public.set_ai_logs_daily_summary_updated_at();
DROP TABLE IF EXISTS public.ai_logs_daily_summary;
