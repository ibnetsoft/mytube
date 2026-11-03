create or replace function public.std_save_thumbnail_patch(
  p_project_id uuid, p_updated_at timestamptz, p_status text,
  p_payload jsonb, p_progress jsonb
) returns jsonb language plpgsql set search_path = '' as $$
declare result jsonb;
begin
  if jsonb_typeof(p_payload) <> 'object' or jsonb_typeof(p_progress) <> 'object'
     or (p_payload - array['thumbnail_bg_url','thumbnail_url','thumbnail_design']) <> '{}'::jsonb
     or (p_progress - array['thumbnail_completed','thumbnail_render_status','thumbnail_url','thumbnail_confirmed_at']) <> '{}'::jsonb
  then raise exception 'Invalid thumbnail patch'; end if;
  update public.std_projects
     set project_payload = coalesce(project_payload, '{}'::jsonb) || p_payload,
         progress_payload = coalesce(progress_payload, '{}'::jsonb) || p_progress,
         updated_at = clock_timestamp()
   where id = p_project_id and updated_at is not distinct from p_updated_at and status = p_status
   returning jsonb_build_object('id', id, 'updated_at', updated_at) into result;
  return result;
end $$;
revoke all on function public.std_save_thumbnail_patch(uuid,timestamptz,text,jsonb,jsonb) from public, anon, authenticated;
grant execute on function public.std_save_thumbnail_patch(uuid,timestamptz,text,jsonb,jsonb) to service_role;
