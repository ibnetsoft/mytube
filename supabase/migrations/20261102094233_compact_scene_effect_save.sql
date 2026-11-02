create or replace function public.std_patch_scene_effect_array(p_scenes jsonb, p_numbers int[], p_field text, p_value text)
returns jsonb language plpgsql immutable security invoker set search_path='' as $$
declare result jsonb;
begin
 if jsonb_typeof(p_scenes) is distinct from 'array' then return p_scenes; end if;
 select coalesce(jsonb_agg(case when coalesce(nullif(s->>'scene_number',''),nullif(s->>'scene_order',''),n::text) ~ '^[0-9]+$'
    and coalesce(nullif(s->>'scene_number',''),nullif(s->>'scene_order',''),n::text)::int=any(p_numbers)
   then jsonb_set(jsonb_set(s, array[p_field], to_jsonb(p_value), true), '{metadata}',
     (case when jsonb_typeof(s->'metadata')='object' then s->'metadata' else '{}'::jsonb end) || jsonb_build_object(p_field,p_value),true)
   else s end order by n),'[]'::jsonb) into result
 from jsonb_array_elements(p_scenes) with ordinality a(s,n);
 return result;
end $$;

create or replace function public.std_save_scene_effect(p_project_id uuid, p_owner text, p_numbers int[], p_field text, p_value text)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare p public.std_projects%rowtype; doc jsonb; structure jsonb; scene_count integer;
begin
 if p_field not in ('transition_effect','image_effect','motion_speed') or p_value is null or length(p_value)>100
    or coalesce(cardinality(p_numbers),0)=0 or cardinality(p_numbers)>500
    or exists(select 1 from unnest(p_numbers) n where n is null or n<1)
    or cardinality(p_numbers)<>(select count(distinct n) from unnest(p_numbers) n)
 then raise exception 'Invalid scene effect'; end if;
 select * into p from public.std_projects where id=p_project_id and lower(employee_email)=lower(p_owner) for update;
 if not found then return jsonb_build_object('error','not_found'); end if;
 if p.status in ('approved','canceled','review_requested') then return jsonb_build_object('error','locked'); end if;
 select count(distinct scene_number) into scene_count from public.std_project_scenes
  where project_id=p.id and scene_number=any(p_numbers);
 if scene_count<>cardinality(p_numbers) then return jsonb_build_object('error','missing_scene'); end if;
 doc:=coalesce(p.project_payload,'{}'::jsonb);
 if jsonb_typeof(doc->'scenes')='array' then
   doc:=jsonb_set(doc,'{scenes}',public.std_patch_scene_effect_array(doc->'scenes',p_numbers,p_field,p_value),false);
 end if;
 structure:=doc->'structure';
 if jsonb_typeof(structure)='object' and jsonb_typeof(structure->'scenes')='array' then
   doc:=jsonb_set(doc,'{structure,scenes}',public.std_patch_scene_effect_array(structure->'scenes',p_numbers,p_field,p_value),false);
 end if;
 update public.std_project_scenes set metadata=(case when jsonb_typeof(metadata)='object' then metadata else '{}'::jsonb end) || jsonb_build_object(p_field,p_value), updated_at=clock_timestamp()
 where project_id=p.id and scene_number=any(p_numbers);
 update public.std_projects set project_payload=doc,updated_at=clock_timestamp() where id=p.id;
 return jsonb_build_object('success',true,'scene_numbers',to_jsonb(p_numbers),'field',p_field,'value',p_value);
end $$;
revoke all on function public.std_patch_scene_effect_array(jsonb,int[],text,text), public.std_save_scene_effect(uuid,text,int[],text,text) from public,anon,authenticated;
grant execute on function public.std_patch_scene_effect_array(jsonb,int[],text,text), public.std_save_scene_effect(uuid,text,int[],text,text) to service_role;
