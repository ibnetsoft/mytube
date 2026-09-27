create table public.user_topic_submissions (
  id uuid primary key,
  owner_email text not null,
  title text not null check (length(title) between 1 and 200),
  status text not null default 'pending' check (status in ('pending','approved','rejected')),
  request_data jsonb not null,
  job_id text unique,
  review_note text not null default '',
  reviewed_at timestamptz,
  created_at timestamptz not null default now()
);
create index user_topic_submissions_owner on public.user_topic_submissions (owner_email, created_at desc);
create index user_topic_submissions_pending on public.user_topic_submissions (created_at) where status = 'pending';
alter table public.user_topic_submissions enable row level security;
revoke all on public.user_topic_submissions from public, anon, authenticated;
grant select, insert, update on public.user_topic_submissions to service_role;
