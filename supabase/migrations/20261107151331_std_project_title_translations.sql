-- Small durable title records; do not rewrite compressed project/scene payloads.
create table public.std_project_title_translations (
    project_id uuid not null references public.std_projects(id) on delete cascade,
    source_hash text not null check (source_hash ~ '^[0-9a-f]{64}$'),
    locale text not null check (locale in ('ko', 'en', 'vi', 'th')),
    source_title text not null check (length(source_title) > 0),
    translated_title text not null check (length(btrim(translated_title)) > 0),
    created_at timestamptz not null default now(),
    primary key (project_id, source_hash, locale)
);
alter table public.std_project_title_translations enable row level security;
revoke all on public.std_project_title_translations from public, anon, authenticated;
grant select, insert, update, delete on public.std_project_title_translations to service_role;
comment on table public.std_project_title_translations is
    'Source-bound title translations. Server routes must authorize project ownership before access.';
