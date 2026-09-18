-- =============================================================
-- Migration: Secure legacy public tables with RLS (AIR-0250)
-- Description:
--   Fixes Supabase Security Advisor "RLS Disabled in Public" findings for
--   legacy token, notification, activity, and analytics tables.
-- =============================================================

-- These tables live in the exposed public schema. Keep direct client writes
-- closed unless a concrete user-facing flow requires them; server APIs,
-- SECURITY DEFINER trigger functions, and service-role clients remain the
-- trusted write path.

ALTER TABLE public.token_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_activity ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_events ENABLE ROW LEVEL SECURITY;

-- Defense in depth for browser/mobile roles. Policies below add back only the
-- narrow read/update surfaces the product can safely expose.
REVOKE ALL ON public.token_transactions FROM anon, authenticated;
REVOKE ALL ON public.user_notifications FROM anon, authenticated;
REVOKE ALL ON public.user_activity FROM anon, authenticated;
REVOKE ALL ON public.user_events FROM anon, authenticated;

-- Service-role/admin API access. Supabase service_role bypasses RLS, but these
-- policies and grants document the intended privileged access model and support
-- environments that explicitly evaluate service_role policies.
DROP POLICY IF EXISTS token_transactions_service_all ON public.token_transactions;
CREATE POLICY token_transactions_service_all
ON public.token_transactions
FOR ALL TO service_role
USING (true)
WITH CHECK (true);

DROP POLICY IF EXISTS user_notifications_service_all ON public.user_notifications;
CREATE POLICY user_notifications_service_all
ON public.user_notifications
FOR ALL TO service_role
USING (true)
WITH CHECK (true);

DROP POLICY IF EXISTS user_activity_service_all ON public.user_activity;
CREATE POLICY user_activity_service_all
ON public.user_activity
FOR ALL TO service_role
USING (true)
WITH CHECK (true);

DROP POLICY IF EXISTS user_events_service_all ON public.user_events;
CREATE POLICY user_events_service_all
ON public.user_events
FOR ALL TO service_role
USING (true)
WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.token_transactions TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_notifications TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_activity TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_events TO service_role;

-- End-user read access is owner-scoped. Writes to token_transactions,
-- user_activity, and user_events remain server-owned audit/activity records.
DROP POLICY IF EXISTS token_transactions_self_read ON public.token_transactions;
CREATE POLICY token_transactions_self_read
ON public.token_transactions
FOR SELECT TO authenticated
USING ((SELECT auth.uid()) = user_id);

GRANT SELECT ON public.token_transactions TO authenticated;

DROP POLICY IF EXISTS user_notifications_self_read ON public.user_notifications;
CREATE POLICY user_notifications_self_read
ON public.user_notifications
FOR SELECT TO authenticated
USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS user_notifications_self_mark_read ON public.user_notifications;
CREATE POLICY user_notifications_self_mark_read
ON public.user_notifications
FOR UPDATE TO authenticated
USING ((SELECT auth.uid()) = user_id)
WITH CHECK ((SELECT auth.uid()) = user_id);

GRANT SELECT ON public.user_notifications TO authenticated;
GRANT UPDATE (is_read) ON public.user_notifications TO authenticated;

DROP POLICY IF EXISTS user_activity_self_read ON public.user_activity;
CREATE POLICY user_activity_self_read
ON public.user_activity
FOR SELECT TO authenticated
USING ((SELECT auth.uid()) = user_id);

GRANT SELECT ON public.user_activity TO authenticated;

-- Intentionally no anon/authenticated policy on public.user_events. Backend
-- analytics events are written by triggers or trusted server code, and the
-- aggregate analytics dashboard is exposed through controlled RPCs.

COMMENT ON TABLE public.token_transactions IS
    'Token ledger. RLS enabled; users may read own rows, writes are trusted server/service-role only.';
COMMENT ON TABLE public.user_notifications IS
    'User notifications. RLS enabled; users may read own rows and update is_read only.';
COMMENT ON TABLE public.user_activity IS
    'Daily activity/streak state. RLS enabled; users may read own rows, writes are trigger/server-owned.';
COMMENT ON TABLE public.user_events IS
    'Analytics/audit events. RLS enabled; direct client access is intentionally denied.';
