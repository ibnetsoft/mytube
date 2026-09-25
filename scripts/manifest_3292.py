"""Use canonical exporter/crop contract with staged approved structure, no queue overwrite."""
import json
from draft_3292_scoped import OUT,save
from scripts.repair_existing_topic_scripts import _headers
from services.image_grid_prompts import build_compact_image_grid_prompts,grid_windows,validate_image_grid_prompt_readiness
import cowork_scene_assets as helper
c=json.loads((OUT/'candidate-final.json').read_text(encoding='utf-8'))
m=json.loads((OUT/'media-prompts.json').read_text(encoding='utf-8'))
r=json.loads((OUT/'request.json').read_text(encoding='utf-8'))
a=json.loads((OUT/'character-anchors.json').read_text(encoding='utf-8'))
m['scenes'][15]['image_prompt']='Highly realistic late Joseon wealthy household wooden porch, present time. Close-up of Sunduk age42, same stored reference narrow face, dusty blue jeogori and low dark bun, trembling lips and troubled eyes while remembering her mother. Yeoni age20 is a blurred edge-of-frame presence beside her. Geumrye is NOT present: she is at home. Natural courtyard daylight, no flashback overlay, no extra people, no text, no modern objects.'
scenes=[];elapsed=0
for i,(text,media,timing) in enumerate(zip(c['sections'],m['scenes'],r['schedule']),1):
    end=elapsed+timing['duration_seconds']
    scenes.append({**media,'scene_order':i,'scene_id':f'repair3292-final-{i:03d}',
        'scene_text':text['text'],'narration':text['text'],'duration_seconds':timing['duration_seconds'],
        'target_duration':timing['duration_seconds'],'time_range':f'{elapsed}-{end}s','start_time':elapsed,'end_time':end,
        'image_style':'realistic','image_url':None,'video_url':None,'asset_status':'missing','video_prompt_required':i<=12})
    elapsed=end
positions=['Top-Left','Top-Right','Bottom-Left','Bottom-Right']
specs=[]
for n,(start,end) in enumerate(grid_windows(53),1):
    selected=scenes[start:end]
    specs.append({'grid_number':n,'scene_numbers':[s['scene_number'] for s in selected],
        'shared_style':'Photorealistic late Joseon Korean rural village. Each panel is a 16:9 landscape frame; overall canvas16:9. Reference1 Yeoni20, reference2 Sunduk42, reference3 Geumrye68. De-age only explicitly marked flashbacks; preserve facial structure. No modern objects.',
        'negative_prompt':'no text, no words, no letters, no labels, no captions, no watermarks, no borders, no grid lines, no dividers, correct anatomy, no extra limbs',
        'panels':[{'scene_number':s['scene_number'],'scene_id':s['scene_id'],'position':positions[j],'panel_prompt':s['image_prompt']} for j,s in enumerate(selected)]})
grids=build_compact_image_grid_prompts(specs)
validate_image_grid_prompt_readiness(scenes,grids,status='ready',require_status='ready',require_compact_template=True)
structure={'scenes':scenes,'scene_count':53,'image_grid_prompts':grids,'character_anchors':a,**a,
    'target_duration_seconds':900,'narrative_blueprint':c['narrative_blueprint'],'repair_version':'3292-final-20260915'}
save('staged-structure.json',structure)
base,headers=_headers()
# Only the read source is staged; canonical export validates Storage refs and every grid.
helper._topic=lambda topic_id:({'id':3292,'topic':r['title']},structure,base,headers)
path=helper.export_manifest('3292',OUT/'scene-assets/manifest.json','content-assets')
print(path,flush=True)
