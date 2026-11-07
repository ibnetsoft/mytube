-- A zero result is valid only after a complete source-state selection.
create or replace function public.apply_wuxia_mouth_result(pkg jsonb, result jsonb, timing boolean)
returns jsonb language plpgsql security invoker set search_path=public as $$
declare patch jsonb; si int; sj int; state jsonb; base text[]; manual jsonb; total int; selected int;
begin
 if jsonb_typeof(result->'states') is distinct from 'array' or jsonb_array_length(result->'states')>1000
 or coalesce(result->'report'->>'state','') not in ('prepared','ready','not_required') then raise exception 'Invalid completed mouth result';end if;
 select coalesce(sum(jsonb_array_length(sc->'states')),0)::int into total from jsonb_array_elements(pkg->'scenes') sc;
 if result#>>'{report,selection_complete}' is distinct from 'true' or jsonb_array_length(result->'states')<>total
 or exists(select 1 from jsonb_array_elements(result->'states') st group by st->>'scene_id',st->>'asset_id' having count(*)<>1) then raise exception 'Incomplete mouth selection';end if;
 select coalesce(sum(jsonb_array_length(st->'art')),0)::int into selected from jsonb_array_elements(result->'states') st;
 if (result#>>'{report,state}'='not_required') is distinct from (selected=0)
 or (selected>0 and result#>>'{report,state}' is distinct from case when timing then 'ready' else 'prepared' end) then raise exception 'Mouth selection count differs from completion state';end if;
 for patch in select value from jsonb_array_elements(result->'states') loop
  select (sc.ordinality-1)::int,(st.ordinality-1)::int,st.value into si,sj,state
   from jsonb_array_elements(pkg->'scenes') with ordinality sc,jsonb_array_elements(sc.value->'states') with ordinality st
   where sc.value->>'scene_id'=patch->>'scene_id' and st.value->>'asset_id'=patch->>'asset_id';
  if state is null or state->>'sha256' is distinct from patch->>'sha256' or jsonb_typeof(patch->'art') is distinct from 'array' then raise exception 'Mouth source state changed';end if;
  base:=array['scenes',si::text,'states',sj::text];
  pkg:=jsonb_set(pkg,base||array['dialogue_mouth_preparation'],patch->'art',true);
  if timing then
   if jsonb_typeof(patch->'mouths') is distinct from 'array' or jsonb_array_length(patch->'mouths')<>jsonb_array_length(patch->'art') then raise exception 'Missing timing result';end if;
   select coalesce(jsonb_agg(value),'[]'::jsonb) into manual from jsonb_array_elements(coalesce(state->'dialogue_mouths','[]'::jsonb)) where value->>'automation' is distinct from 'wuxia_mouth_auto/v1';
   pkg:=jsonb_set(pkg,base||array['dialogue_mouths'],manual||(patch->'mouths'),true);
  end if;
 end loop;
 return jsonb_set(pkg,array[case when timing then 'mouth_timing' else 'mouth_preparation' end],result->'report',true);
end $$;
