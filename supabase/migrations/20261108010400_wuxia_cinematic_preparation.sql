-- Created with Supabase CLI; ordered after the existing energy preparation prerequisite.
-- Source-bound energy patches share the existing owned preparation lease and atomic publication.
create or replace function public.apply_wuxia_mouth_result(pkg jsonb, result jsonb, timing boolean)
returns jsonb language plpgsql security invoker set search_path=public as $$
declare patch jsonb; si int; sj int; state jsonb; base text[]; manual jsonb; total int; selected int; energy jsonb; loops jsonb; item jsonb; cinematic jsonb; box jsonb; coord jsonb; ci int;
begin
 if jsonb_typeof(result->'states') is distinct from 'array' or jsonb_array_length(result->'states')>1000
 or coalesce(result->'report'->>'state','') not in ('prepared','ready','not_required') then raise exception 'Invalid completed mouth result';end if;
 select coalesce(sum(jsonb_array_length(sc->'states')),0)::int into total from jsonb_array_elements(pkg->'scenes') sc;
 if result#>>'{report,selection_complete}' is distinct from 'true' or jsonb_array_length(result->'states')<>total
 or exists(select 1 from jsonb_array_elements(result->'states') st group by st->>'scene_id',st->>'asset_id' having count(*)<>1) then raise exception 'Incomplete mouth selection';end if;
 select coalesce(sum(jsonb_array_length(st->'art')+jsonb_array_length(coalesce(st#>'{energy,loops}','[]'::jsonb))+case when st#>>'{energy,decision}'='uncertain' then 1 else 0 end+case when st ? 'cinematic' then 1 else 0 end),0)::int into selected from jsonb_array_elements(result->'states') st;
 if (result#>>'{report,state}'='not_required') is distinct from (selected=0)
 or (selected>0 and result#>>'{report,state}' is distinct from case when timing then 'ready' else 'prepared' end) then raise exception 'Mouth selection count differs from completion state';end if;
 for patch in select value from jsonb_array_elements(result->'states') loop
  select (sc.ordinality-1)::int,(st.ordinality-1)::int,st.value into si,sj,state
   from jsonb_array_elements(pkg->'scenes') with ordinality sc,jsonb_array_elements(sc.value->'states') with ordinality st
   where sc.value->>'scene_id'=patch->>'scene_id' and st.value->>'asset_id'=patch->>'asset_id';
  if state is null or state->>'sha256' is distinct from patch->>'sha256' or jsonb_typeof(patch->'art') is distinct from 'array' then raise exception 'Mouth source state changed';end if;
  base:=array['scenes',si::text,'states',sj::text];
  energy:=patch->'energy';
  if energy is not null then
   if energy->>'contract' is distinct from 'wuxia_energy_auto/v1'
    or energy->>'source_sha256' is distinct from state->>'sha256'
    or coalesce(energy->>'decision','') not in ('present','absent','uncertain') or jsonb_typeof(energy->'loops') is distinct from 'array'
   then raise exception 'Invalid actual-art energy result';end if;
   if (energy->>'decision'='present') is distinct from (jsonb_array_length(energy->'loops')>0)
    or (energy->>'decision'='present' and energy#>>'{review,passed}' is distinct from 'true')
   then raise exception 'Energy presence lacks actual composite review';end if;
   if energy->>'decision'='uncertain' and (jsonb_typeof(energy->'quality_notes') is distinct from 'array' or jsonb_array_length(energy->'quality_notes')=0) then raise exception 'Uncertain energy needs truthful quality notes';end if;
   select coalesce(jsonb_agg(value),'[]'::jsonb) into loops from jsonb_array_elements(coalesce(state->'ambient_loops','[]'::jsonb)) where value->>'automation' is distinct from 'wuxia_energy_auto/v1';
   for item in select value from jsonb_array_elements(energy->'loops') loop
    if item->>'contract' is distinct from 'ambient_loop/v1' or item->>'source_sha256' is distinct from state->>'sha256'
     or item->>'automation' is distinct from 'wuxia_energy_auto/v1'
     or item->>'repeat' is distinct from 'true' or item->>'start_ms' is distinct from '0' or item->>'end_ms' is distinct from '3600000' or item#>>'{sword_aura,source_reviewed}' is distinct from 'true'
    then raise exception 'Invalid energy loop or source binding';end if;
   end loop;
   loops:=loops||(energy->'loops');
   if jsonb_array_length(loops)>4 then raise exception 'Energy patch capacity exceeded';end if;
   pkg:=jsonb_set(pkg,base||array['ambient_loops'],loops,true);
   pkg:=jsonb_set(pkg,base||array['energy_preparation'],energy-'loops',true);
   pkg:=jsonb_set(pkg,base||array['energy_only_motion'],to_jsonb(jsonb_array_length(energy->'loops')>0),true);
  end if;
  cinematic:=patch->'cinematic';
  if cinematic is not null then
   if cinematic->>'contract' is distinct from 'wuxia_cinematic/v1' or cinematic->>'source_sha256' is distinct from state->>'sha256'
    or jsonb_typeof(cinematic->'passed') is distinct from 'boolean' or length(coalesce(cinematic->>'evidence',''))=0
    or length(coalesce(cinematic->>'plan_id',''))<>64 or cinematic->>'plan_id' is distinct from cinematic#>>'{plan,plan_id}'
    or jsonb_typeof(cinematic->'protected_boxes') is distinct from 'array' or jsonb_array_length(cinematic->'protected_boxes')>64
    or jsonb_typeof(cinematic->'focus') is distinct from 'array' or jsonb_array_length(cinematic->'focus')<>2
    or jsonb_typeof(cinematic->'quality_notes') is distinct from 'array'
    then raise exception 'Invalid actual-source cinematic review';end if;
   if cinematic->>'passed'='false' and jsonb_array_length(cinematic->'quality_notes')=0 then raise exception 'Uncertain cinematic review needs quality notes';end if;
   foreach ci in array array[0,1] loop
    if jsonb_typeof(cinematic->'focus'->ci) is distinct from 'number' or (cinematic->'focus'->>ci)::numeric not between .15 and .85 then raise exception 'Unsafe cinematic focus';end if;
   end loop;
   for box in select v from jsonb_array_elements(cinematic->'protected_boxes') v loop
    if jsonb_typeof(box) is distinct from 'array' or jsonb_array_length(box)<>4 then raise exception 'Invalid cinematic protection box';end if;
    for coord in select v from jsonb_array_elements(box) v loop
     if jsonb_typeof(coord) is distinct from 'number' or (coord#>>'{}')::numeric not between 0 and 1 then raise exception 'Unsafe cinematic protection box';end if;
    end loop;
    if (box->>0)::numeric>=(box->>2)::numeric or (box->>1)::numeric>=(box->>3)::numeric then raise exception 'Empty cinematic protection box';end if;
   end loop;
   -- base is already source-bound; no original, narration, owner or manual patch changes.
   pkg:=jsonb_set(pkg,base||array['cinematic_review'],cinematic,true);
  end if;
  pkg:=jsonb_set(pkg,base||array['dialogue_mouth_preparation'],patch->'art',true);
  if timing then
   if jsonb_typeof(patch->'mouths') is distinct from 'array' or jsonb_array_length(patch->'mouths')<>jsonb_array_length(patch->'art') then raise exception 'Missing timing result';end if;
   select coalesce(jsonb_agg(value),'[]'::jsonb) into manual from jsonb_array_elements(coalesce(state->'dialogue_mouths','[]'::jsonb)) where value->>'automation' is distinct from 'wuxia_mouth_auto/v1';
   pkg:=jsonb_set(pkg,base||array['dialogue_mouths'],manual||(patch->'mouths'),true);
  end if;
  if coalesce(pkg#>>(base||array['energy_only_motion']),'false')='true' then
   pkg:=jsonb_set(pkg,base||array['dialogue_mouth_preparation'],'[]'::jsonb,true);
   pkg:=jsonb_set(pkg,base||array['dialogue_mouths'],'[]'::jsonb,true);
  end if;
 end loop;
 return jsonb_set(pkg,array[case when timing then 'mouth_timing' else 'mouth_preparation' end],result->'report',true);
end $$;

create or replace function public.wuxia_preparation_enabled(policy jsonb)
returns boolean language sql immutable security invoker set search_path=public as $$
 select (coalesce(policy->>'auto_prepare','false')='true' and coalesce(policy->>'enabled','true')<>'false')
 or (coalesce(policy#>>'{energy_auto,auto_prepare}','false')='true' and coalesce(policy#>>'{energy_auto,enabled}','false')='true')
 or (coalesce(policy#>>'{cinematic_auto,auto_prepare}','false')='true' and coalesce(policy#>>'{cinematic_auto,enabled}','false')='true')
$$;

revoke all on function public.apply_wuxia_mouth_result(jsonb,jsonb,boolean),public.wuxia_preparation_enabled(jsonb) from public,anon,authenticated;
grant execute on function public.apply_wuxia_mouth_result(jsonb,jsonb,boolean),public.wuxia_preparation_enabled(jsonb) to service_role;
