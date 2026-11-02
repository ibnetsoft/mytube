"""Topic-local optional asset reuse; preserve legacy post-50 plans unchanged."""
import copy
import hashlib
import json
import re
from pathlib import Path
from PIL import Image
from worker.layered_scene_composite import composite_scene
from worker.manga_layer_generation import NativeCodexLayerGenerator, _normalize

VERSION = 'reusable-scenes-v1'
OPTIONAL_VERSION = 'reusable-scenes-v2'
POLICY = 'compatible_first_v2'
OPTIMIZED_POLICY = 'compatible_first_v3'
REQUEST_POLICY = 'reuse_excluded_v1'
TASK = '''Plan reusable image assets for EVERY supplied scene (51 onward). Return JSON:
{"version":"reusable-scenes-v1","backgrounds":[{"id":"room-day-eye-level","prompt":"..."}],
"poses":[{"id":"hero-standing-calm-left","character_key":"exact saved key","prompt":"..."}],
"scenes":[{"scene_number":51,"background":"room-day-eye-level","poses":["hero-standing-calm-left"]}]}.
Minimize generation by grouping compatible locations, time, lighting, perspective and story states.
Reuse character poses across backgrounds and scenes, but keep identity, age, wardrobe, facial expression,
action, viewpoint, scale and lighting appropriate to narration. Never force incompatible reuse.
All assets are full 1920x1080 canvases: backgrounds completely opaque WITHOUT people, silhouettes,
reflections or text; poses transparent WITHOUT scenery, with precisely specified framing/position/scale.
Pose prompts must include character appearance locks and exact screen placement so selected poses
compose together without overlap errors. Use separate pose IDs for different placements if necessary.
Include necessary held props in the pose. Include static occluding furniture only if it does not incorrectly
cover the character; describe compatible placement. Special interactions need dedicated compatible poses.
Scene poses are in back-to-front order, include exactly the scene_cast participants, empty for environment
shots. Do not invent people. Do not rewrite story. Fixed camera, no slow zooms. Reuse is a priority,
not permission to change story facts. Prompts must explicitly specify approved art style and era.
'''


OPTIONAL_TASK = TASK.replace('EVERY supplied scene (51 onward)', 'EVERY supplied still-image scene, including scenes before 51').replace(
    '"version":"reusable-scenes-v1"', '"version":"reusable-scenes-v2"').replace(
    '"scene_number":51,"background"', '"scene_number":1,"mode":"compose","reuse_check":"Same location and matching framing, lighting and pose; reuse room and standing pose","background"') + """
For EVERY still scene, FIRST check matching locations, camera/framing, time, lighting,
character identity/wardrobe/pose/action, expression, placement and props against other supplied scenes.
Record a specific nonempty reuse_check describing the match or why new art is appropriate.
Reuse is OPTIONAL: no minimum reuse count, no requirement to split every scene into assets.
When a complete scene drawing is more appropriate (unique action, inseparable interaction,
incompatible lighting/perspective or no suitable reusable assets), return
{"scene_number":2,"mode":"standalone","reuse_check":"Unique action/framing; use a new complete scene"}.
Standalone rows must omit background and poses. Compose rows have mode=compose, background and poses.
A background may repeat while a new character pose is drawn, or a pose may repeat with a new background.
Use dedicated assets for differences; never force reuse because a room or character name matches.
If a scene participant has no saved character_key, use standalone instead of inventing a reference.
For video scenes preserve the uploaded footage: do not map or regenerate video scenes.
Use final scene narration and directions even when image prompts are still pending.
"""


def composed_scenes(plan):
    return [s for s in plan['scenes']
            if plan['version'] == VERSION or s.get('mode') == 'compose']


def optimize_plan(plan):
    """Conservative image-call estimate, not provider credit pricing. Never mutate input."""
    result = copy.deepcopy(plan)
    rows = composed_scenes(result)
    total = len(result['scenes'])
    flat_calls = lambda count: (count + 3) // 4
    assets = lambda row: {('backgrounds', row['background']), *[('poses', p) for p in row['poses']]}
    # Treat scenes sharing any asset as one candidate. Keeping compatible groups intact
    # avoids buying unique backgrounds/poses simply to satisfy a reuse quota.
    groups = []
    for row in rows:
        linked = [g for g in groups if g['assets'] & assets(row)]
        group = {'rows': [row], 'assets': assets(row)}
        for old in linked:
            group['rows'].extend(old['rows']); group['assets'].update(old['assets'])
            groups.remove(old)
        groups.append(group)
    groups.sort(key=lambda g: (len(g['assets']) - len(g['rows']) / 4,
                               min(r['scene_number'] for r in g['rows'])))
    chosen = set(); selected_assets = set(); current = flat_calls(total)
    for group in groups:
        candidate = chosen | {r['scene_number'] for r in group['rows']}
        candidate_assets = selected_assets | group['assets']
        calls = len(candidate_assets) + flat_calls(total - len(candidate))
        if calls < current:
            chosen, selected_assets, current = candidate, candidate_assets, calls
    for row in result['scenes']:
        if row.get('mode') == 'compose' and row['scene_number'] not in chosen:
            row.pop('background'); row.pop('poses'); row['mode'] = 'standalone'
            row['optimization_reason'] = 'Compatible reuse was checked; new shared assets would not reduce estimated image calls.'
    for kind in ('backgrounds', 'poses'):
        result[kind] = [a for a in result[kind] if (kind, a['id']) in selected_assets]
    result['generation_optimization'] = {
        'model': 'image_calls_2x2_v1', 'baseline_image_calls': flat_calls(total),
        'estimated_image_calls': current, 'estimated_calls_saved': flat_calls(total) - current,
        'shared_asset_count': len(selected_assets), 'composite_scene_count': len(chosen),
        'standalone_scene_count': total - len(chosen),
    }
    return result


def plan_package(stage, job_id, package, *, optimize=False):
    """Only called for newly reserved opt-in jobs, never to retrofit saved work."""
    from worker.generation_validation import validated_stage
    structure = package.get('structure') or {}
    scenes = structure.get('scenes') or []
    if not scenes or not any(s.get('visual_type') != 'video' for s in scenes):
        return package
    anchors = structure.get('character_anchors') or package.get('character_anchors') or {}
    references = [r for r in [anchors.get('main_character'), *anchors.get('supporting_characters', [])]
                  if isinstance(r, dict) and r.get('character_key')]
    cast = structure.get('scene_cast') or package.get('scene_cast') or []
    plan = validated_stage(lambda name, context, task: stage(job_id, name, context, task),
                           '03b_optional_reusable_scene_assets', {
        'scenes': [s for s in scenes if s.get('visual_type') != 'video'],
        'scene_cast': cast, 'character_references': references,
        'content_setting': package.get('content_setting'),
        'image_style': package.get('image_style'),
    }, OPTIONAL_TASK, lambda p: validate_plan(p, scenes, references, cast))
    if optimize:
        plan = optimize_plan(plan)
        structure['image_request_policy'] = REQUEST_POLICY
    structure['reusable_scene_assets'] = plan
    structure['layer_production_stage'] = 'post_submission'
    numbers = {s['scene_number'] for s in composed_scenes(plan)}
    policy = structure.setdefault('image_generation_policy', {})
    policy.update(reuse_policy=OPTIMIZED_POLICY if optimize else POLICY, reuse_checked_scene_count=len(plan['scenes']),
                  shared_composite_scene_numbers=sorted(numbers))
    if optimize:
        policy['generation_optimization'] = plan['generation_optimization']
    for i, scene in enumerate(scenes, 1):
        n = int(scene.get('scene_number') or scene.get('scene_order') or i)
        if n in numbers:
            scene.setdefault('image_generation_policy', {})['source'] = 'shared_background_character_composite'
    package['structure'] = structure
    return package


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def validate_plan(plan, scenes, references, cast=None):
    if not isinstance(plan,dict) or plan.get('version') not in (VERSION, OPTIONAL_VERSION):
        raise ValueError('Invalid reusable scene plan version')
    assets={}
    known={r['character_key'] for r in references}
    for kind in ('backgrounds','poses'):
        rows=plan.get(kind)
        if not isinstance(rows,list):raise ValueError('Missing reusable asset list')
        assets[kind]={}
        for row in rows:
            key=row.get('id') if isinstance(row,dict) else None
            if not isinstance(key,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',key) or key in assets[kind] or not str(row.get('prompt') or '').strip():
                raise ValueError('Invalid or duplicate reusable asset')
            if kind=='poses' and row.get('character_key') not in known:
                raise ValueError('Reusable pose needs a saved character reference')
            assets[kind][key]=row
    expected={int(s.get('scene_number') or s.get('scene_order') or i) for i,s in enumerate(scenes,1)
              if (plan['version'] == OPTIONAL_VERSION or int(s.get('scene_number') or s.get('scene_order') or i)>=51) and s.get('visual_type')!='video'}
    rows=plan.get('scenes');seen=set()
    if not isinstance(rows,list):raise ValueError('Missing reusable scene compositions')
    aliases={str(n).strip().casefold():r['character_key'] for r in references
             for n in [r.get('name'),r.get('character_key'),*(r.get('aliases') or [])] if n}
    cast_by_scene={r['scene_number']:r['characters'] for r in cast or []}
    for row in rows:
        n=row.get('scene_number')
        if type(n) is not int or n not in expected or n in seen:
            raise ValueError('Invalid reusable scene mapping')
        seen.add(n)
        if plan['version'] == OPTIONAL_VERSION:
            if row.get('mode') not in ('compose', 'standalone') or not isinstance(row.get('reuse_check'), str) or not row['reuse_check'].strip():
                raise ValueError('Every scene needs an optional reuse decision and reason')
            if row['mode'] == 'standalone':
                if 'background' in row or 'poses' in row:
                    raise ValueError('Standalone scene must use normal image generation')
                continue
        if row.get('background') not in assets['backgrounds']:
            raise ValueError('Unknown reusable background')
        poses=row.get('poses')
        if not isinstance(poses,list) or any(not isinstance(p,str) or p not in assets['poses'] for p in poses):
            raise ValueError('Unknown reusable pose')
        keys=[assets['poses'][p]['character_key'] for p in poses]
        if len(keys)!=len(set(keys)):raise ValueError('Duplicate character in reusable scene')
        if cast is not None:
            names=cast_by_scene.get(n)
            if names is None or any(str(name).strip().casefold() not in aliases for name in names):
                raise ValueError('Missing saved cast for reusable scene')
            if set(keys)!={aliases[str(name).strip().casefold()] for name in names}:
                raise ValueError('Reusable composition changes scene cast')
        seen.add(n)
    if seen!=expected:raise ValueError('Reusable plan must check every eligible still scene')
    return plan


def scene_numbers(manifest):
    plan=manifest.get('reusable_scene_assets')
    if not plan:return set()
    validate_plan(plan,manifest['scene_specs'],manifest['character_references'],manifest['scene_cast'])
    return {s['scene_number'] for s in composed_scenes(plan)}


def generate(manifest, output_dir, *, generator=None):
    plan=manifest['reusable_scene_assets']
    scene_numbers(manifest)
    compositions = composed_scenes(plan)
    if not compositions:
        return []
    generator=generator or NativeCodexLayerGenerator()
    directory=Path(output_dir);directory.mkdir(parents=True,exist_ok=True)
    cache=directory/'shared-assets';cache.mkdir(exist_ok=True)
    refs={r['character_key']:r for r in manifest['character_references']}
    files={};hashes={}
    for kind in ('backgrounds','poses'):
        used={s['background'] for s in compositions} if kind=='backgrounds' else {p for s in compositions for p in s['poses']}
        for asset in plan[kind]:
            if asset['id'] not in used:continue
            role='background' if kind=='backgrounds' else 'character'
            reference=None if role=='background' else Path(refs[asset['character_key']]['local_file'])
            source_sha=hashlib.sha256(reference.read_bytes()).hexdigest() if reference else None
            fingerprint=digest([plan['version'],kind,asset,source_sha])
            target=cache/(fingerprint+'.png');receipt=cache/(fingerprint+'.json')
            if target.exists():
                if not receipt.exists() or json.loads(receipt.read_text()).get('sha256')!=hashlib.sha256(target.read_bytes()).hexdigest():
                    raise ValueError('Shared asset bytes changed; preserve original')
            else:
                instruction=('Opaque complete environment only, no people. ' if role=='background' else
                             'Only the approved character and held props on transparent alpha, no scenery. Preserve attached identity. ')
                raw=generator.generate(prompt=instruction+'Full 16:9 1920x1080 canvas. '+asset['prompt'],role=role,reference=reference,work_dir=cache/('.generation-'+fingerprint))
                temp=cache/(fingerprint+'.tmp.png')
                _normalize(raw,temp,role)
                temp.replace(target)
                receipt.write_text(json.dumps({'fingerprint':fingerprint,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'asset':asset}))
            files[(kind,asset['id'])]=target
            hashes[(kind,asset['id'])]=hashlib.sha256(target.read_bytes()).hexdigest()
    results=[]
    for scene in compositions:
        n=scene['scene_number'];background=files[('backgrounds',scene['background'])]
        layers=[files[('poses',p)] for p in scene['poses']]
        fingerprint=digest([plan['version'],scene,hashes[('backgrounds',scene['background'])],*[hashes[('poses',p)] for p in scene['poses']]])
        target=directory/f'scene-{n:03d}.png';receipt=directory/f'scene-{n:03d}-shared.json'
        if target.exists():
            previous=json.loads(receipt.read_text()) if receipt.exists() else {}
            if previous.get('fingerprint')!=fingerprint or previous.get('sha256')!=hashlib.sha256(target.read_bytes()).hexdigest():
                raise FileExistsError('Preserve existing scene; use a new output directory for reusable composition')
        else:
            composite_scene(background,layers,target)
            receipt.write_text(json.dumps({'fingerprint':fingerprint,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                                           'composition':scene,'source_files':[str(background),*map(str,layers)]}))
        results.append({'scene_number':n,'scene_file':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    return results
