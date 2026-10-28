-- Operational data is accessed by authenticated server endpoints and database triggers.
-- No browser policies: deny direct anon/authenticated access, including TRUNCATE
-- (which RLS does not protect). Keep the server service role operational.
ALTER TABLE public.token_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_activity ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_events ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE
  public.token_transactions, public.user_notifications,
  public.user_activity, public.user_events
FROM PUBLIC, anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
  public.token_transactions, public.user_notifications,
  public.user_activity, public.user_events
TO service_role;
