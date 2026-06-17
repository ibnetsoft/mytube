alter table public.categories
add column if not exists upload_channel_id bigint;

alter table public.categories
add column if not exists upload_channel_name text;

alter table public.categories
add column if not exists upload_channel_handle text;
