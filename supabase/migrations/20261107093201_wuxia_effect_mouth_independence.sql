-- Impact-only direction changes must not regenerate reviewed mouth artwork.
create or replace function public.wuxia_mouth_source(s jsonb)
returns jsonb language sql immutable security invoker set search_path=public as $$
 select jsonb_build_object('policy',s->'wuxia_mouth_policy','cast',jsonb_build_object(
 'main',s->'main_character','supporting',s->'supporting_characters','anchors',s->'character_anchors'),
 'package',((s->'wuxia_ae_package')-'mouth_preparation'-'mouth_timing')||jsonb_build_object('scenes',coalesce((
 select jsonb_agg((sc.value-'effects')||jsonb_build_object('states',coalesce((select jsonb_agg(st.value-'dialogue_mouth_preparation'-'dialogue_mouths' order by st.ordinality)
 from jsonb_array_elements(sc.value->'states') with ordinality st), '[]'::jsonb)) order by sc.ordinality)
 from jsonb_array_elements(coalesce(s->'wuxia_ae_package'->'scenes','[]'::jsonb)) with ordinality sc),'[]'::jsonb)))
$$;

