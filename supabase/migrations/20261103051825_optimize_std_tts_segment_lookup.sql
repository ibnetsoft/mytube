-- Avoid scanning every saved asset for each subtitle's exact or legacy voice cache lookup.
create index if not exists idx_std_assets_tts_segment_key
  on public.std_project_assets (project_id, asset_type, (metadata ->> 'kind'), (metadata ->> 'cache_key'), created_at desc);

create index if not exists idx_std_assets_tts_segment_voice
  on public.std_project_assets (project_id, asset_type, (metadata ->> 'kind'), (metadata ->> 'voice_id'), created_at desc);
