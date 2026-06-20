alter table public.topics_queue
    add column if not exists recommended_duration_minutes integer;

alter table public.topics_queue
    add column if not exists assigned_duration_minutes integer;

alter table public.topics_queue
    add column if not exists duration_locked boolean default true;

alter table public.topics_queue
    add column if not exists estimated_payout integer;

alter table public.topics_queue
    add column if not exists payout_policy jsonb;

alter table public.topics_queue
    add column if not exists duration_reason text;

alter table public.topics_queue
    add column if not exists difficulty_level text;
