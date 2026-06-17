alter table public.topics_queue
add column if not exists local_project_id bigint;

alter table public.topics_queue
add column if not exists progress_payload jsonb default '{}'::jsonb;

alter table public.topics_queue
add column if not exists progress_updated_at timestamptz;
