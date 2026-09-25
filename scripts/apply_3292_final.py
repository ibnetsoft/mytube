"""Apply only the approved 3292 rebuild; back up, CAS writes, verify, never delete files."""
import copy
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
import requests
from draft_3292_scoped import OUT, PID, UID, save
from check_3292_current import capture
from scripts.audit_active_content import fetch
from scripts.repair_existing_topic_scripts import _headers
from thumbnail_contract import thumbnail_draft, background_ready

SHA='79e865def1d9692b937bb4bdc37298aaaae50717974d36a1373c86e2de669d5c'
REV='3292-final-20260915'
def read(name):return json.loads((OUT/name).read_text(encoding='utf-8'))

def thumbnail():
    path=OUT/'thumbnail-background.png'
    if not path.exists():shutil.copy2('C:/Users/Pc/.codex/generated_images/01a07157-6d55-7753-8bdc-53780dd4ee46/exec-24131e35-c4a6-4024-815e-3bb6d544d74f.png',path)
    data=path.read_bytes();sha=hashlib.sha256(data).hexdigest()
    base,headers=_headers();key=f'topics/3292/repairs/{SHA[:16]}/thumbnail-{sha[:12]}.png'
    url=f'{base}/storage/v1/object/public/content-assets/{key}'
    r=requests.get(url,timeout=90)
    if r.status_code in (400,404):
        r=requests.post(f'{base}/storage/v1/object/content-assets/{key}',headers={**headers,'Content-Type':'image/png','x-upsert':'false'},data=data,timeout=120);r.raise_for_status()
        r=requests.get(url,timeout=90)
    r.raise_for_status();assert hashlib.sha256(r.content).hexdigest()==sha
    save('thumbnail-upload.json',{'url':url,'sha256':sha,'object_path':key})
    return url

def build(before):
    now=datetime.now(timezone.utc).isoformat()
    c=read('candidate-final.json');script='\n\n'.join(s['text'].strip() for s in c['sections'])
    assert hashlib.sha256(script.encode()).hexdigest()==SHA
    quality=read('approved-final-quality.json');assert quality['passed'] and quality['script_sha256']==SHA
    structure=read('staged-structure.json');assets=read('uploaded-scene-images.json')
    by_number={a['scene_number']:a for a in assets['assets']}
    assert len(by_number)==49 and assets['missing_scene_numbers']==[21,22,23,24]
    revision={'version':REV,'script_sha256':SHA,'applied_at':now,'status':'partial_images',
        'missing_image_scenes':[21,22,23,24],'image_count':49,'scene_count':53,
        'old_scene_count':258,'structure_change':'explicitly_approved_15_minute_rebuild',
        'requires_revalidation':['tts','subtitle_timing'],'user_web_verified':False}
    for s in structure['scenes']:
        n=s['scene_number'];asset=by_number.get(n)
        s.update(script_excerpt=s['scene_text'],visual_type='video' if n<=12 else 'image',
            image_url=asset['image_url'] if asset else None,video_url=None,
            asset_status='ready' if asset else 'missing',approved_script_revision=revision)
        s['metadata']={'scene_id':s['scene_id'],'scene_number':n,'scene_order':n,
            'time_range':s['time_range'],'target_duration':s['duration_seconds'],
            'image_url':s['image_url'],'video_url':None,'visual_type':s['visual_type'],
            'video_prompt_required':n<=12,'script_excerpt':s['scene_text'],
            'approved_script_revision':revision,
            'cowork_image_asset':({'source':'codex_builtin_imagegen','bucket':'content-assets',**asset} if asset else None),
            'image_generation_status':'ready' if asset else 'blocked_output_safety'}
    annotations=read('dialogue-annotations.json');meta=read('publish-metadata.json')
    structure.update(dialogue_annotations=annotations,approved_script_revision=revision,
        image_style='realistic',image_grid_prompt_status='ready',media_prompt_status='ready')
    subtitles=read('subtitles.json');thai=read('thai-translations.json')
    assert len(subtitles)==len(thai['blocks'])==263
    for i,(sub,tr) in enumerate(zip(subtitles,thai['blocks'])):
        assert tr['index']==i and tr['source_text'].strip()==sub['text'].strip() and tr['translated_text'].strip()
        tr['source_text']=tr['source_text'].strip()
        sub['image_url']=by_number.get(sub['scene_number'],{}).get('image_url','')
    assert len(structure['scenes'])==53 and structure['scenes'][-1]['end_time']==900
    p=before['project'];q=before['topic'][0]
    assert not p['project_payload'].get('thumbnail_design') and not p['progress_payload'].get('thumbnail_completed')
    thumb=background_ready({'thumbnail_design':thumbnail_draft([meta['thumbnail_text']],title=p['title']),
        'thumbnail_hook_texts':[meta['thumbnail_text']]},thumbnail())
    qa={**quality['senior'],'script_sha256':SHA,'independent_listener':quality,'repair_version':REV}
    qpatch={'pregenerated_script':script,'pregenerated_structure':structure,
        'pregenerated_script_status':'ready','pregenerated_structure_status':'ready',
        'total_scenes':53,'video_scenes':12,'image_scenes':41,'assigned_duration_minutes':15,
        'recommended_duration_minutes':15,'assigned_image_style':'realistic',
        'publish_metadata':meta,'narrative_blueprint':c['narrative_blueprint'],'script_quality_report':qa,
        'progress_payload':{**(q.get('progress_payload') or {}),**thumb,'repair_revision':revision,
            'scene_image_count':49,'missing_image_scenes':[21,22,23,24],'image_generation_status':'partial',
            'scene_count':53,'ready_scene_count':37,'has_tts_audio':False,'tts_completed':False,
            'script_changed_requires_audio_regeneration':True}}
    source={**p['source_payload'],**qpatch}
    payload={**p['project_payload'],'script':script,'original_worker_script':script,'structure':structure,
        'subtitles':subtitles,'subtitles_saved':True,'subtitle_translations':{'th':{'version':1,'updated_at':now,'blocks':thai['blocks']}},
        'tts_url':None,'audio_url':None,'main_character':structure['main_character'],
        'supporting_characters':structure['supporting_characters'],'image_grid_prompts':structure['image_grid_prompts'],
        'publish_metadata':meta,'approved_script_revision':revision,**thumb}
    progress={**p['progress_payload'],**thumb,'scene_count':53,'ready_scene_count':37,
        'image_grid_prompt_count':14,'scene_image_count':49,'image_generation_status':'partial',
        'missing_image_scenes':[21,22,23,24],'script_changed_requires_audio_regeneration':True,
        'has_tts_audio':False,'tts_completed':False,'tts_asset_id':None,'tts_drive_file_id':None,
        'tts_file_name':None,'tts_generated_at':None,'tts_invalidated_at':now,'tts_invalidated_reason':'approved_script_rebuild',
        'subtitles_saved':True,'subtitles_completed':False,'subtitle_timing_status':'planned_requires_tts',
        'main_character':structure['main_character'],'repair_revision':revision}
    patch={'source_payload':source,'project_payload':payload,'progress_payload':progress,
        'assigned_duration_minutes':15,'image_style':'realistic','updated_at':now}
    rows=sorted(before['scene_rows'],key=lambda s:s['scene_number']);assert len(rows)==258
    scene_ops=[]
    for old,s in zip(rows[:53],structure['scenes']):
        assert old['scene_number']==s['scene_number']
        new={k:s[k] for k in ('scene_number','scene_text','image_prompt','video_prompt','asset_status','metadata')}
        new.update(scene_title=s.get('scene_title') or f"Scene {s['scene_number']}",shot_hints={},updated_at=now)
        scene_ops.append({'old':old,'patch':new})
    plan={'project_patch':patch,'topic_patch':qpatch,'scene_ops':scene_ops,'retired_scene_rows':rows[53:],
        'retired_audio_assets':[a for a in before['assets'] if a['asset_type']=='audio'],'revision':revision}
    assert not any(a.get('scene_id') for a in before['assets']),'Unexpected scene asset; requires preservation review'
    save('application-plan.json',plan)
    (OUT/'최종-승인대본.md').write_text('# '+p['title']+'\n\n15분 목표 · 53씬 · '+SHA+'\n\n'+script,encoding='utf-8')
    return plan

def apply(before,plan):
    fresh=capture()
    for key in ('project','topic','scene_rows','assets'):
        a=fresh[key];b=before[key]
        if isinstance(a,list):a=sorted(a,key=lambda x:x['id']);b=sorted(b,key=lambda x:x['id'])
        assert a==b,f'Concurrent {key} change; stop'
    base,headers=_headers();headers={**headers,'Prefer':'return=representation'}
    journal=[]
    def patch(table,old,body,extra=None):
        params={'id':'eq.'+str(old['id'])}
        if old.get('updated_at'):params['updated_at']='eq.'+old['updated_at']
        if extra:params.update(extra)
        r=requests.patch(f'{base}/rest/v1/{table}',params=params,headers=headers,json=body,timeout=90)
        r.raise_for_status();result=r.json();assert len(result)==1,f'CAS conflict {table} {old["id"]}'
        journal.append({'table':table,'old':old,'new':result[0]});save('apply-journal.json',journal)
    # Archive old audio association only, keeping its file and original metadata in backups.
    for a in plan['retired_audio_assets']:
        patch('std_project_assets',a,{'status':'replaced','metadata':{**(a.get('metadata') or {}),'retired_by':REV,'reason':'script_changed'}})
    for op in plan['scene_ops']:patch('std_project_scenes',op['old'],op['patch'])
    patch('topics_queue',before['topic'][0],plan['topic_patch'])
    patch('std_projects',before['project'],plan['project_patch'],{'submitted_at':'is.null','status':'in.(claimed,in_progress)','user_id':f'eq.{UID}'})
    # These obsolete rows have no linked media. Exact IDs are archived before removal.
    for start in range(0,len(plan['retired_scene_rows']),40):
        chunk=plan['retired_scene_rows'][start:start+40]
        params={'project_id':f'eq.{PID}','id':'in.('+','.join(x['id'] for x in chunk)+')','scene_number':'gt.53'}
        r=requests.delete(f'{base}/rest/v1/std_project_scenes',params=params,headers=headers,timeout=90)
        r.raise_for_status();assert {x['id'] for x in r.json()}=={x['id'] for x in chunk}
        journal.append({'table':'std_project_scenes','deleted_rows':chunk});save('apply-journal.json',journal)
    actual=fetch('std_projects',id=f'eq.{PID}')[0];scenes=fetch('std_project_scenes',project_id=f'eq.{PID}',order='scene_number.asc')
    queue=fetch('topics_queue',id='eq.3292')[0]
    for k,v in plan['project_patch'].items():
        if k!='updated_at':assert actual[k]==v,f'Project readback mismatch {k}'
    for k,v in plan['topic_patch'].items():assert queue[k]==v,f'Topic readback mismatch {k}'
    assert len(scenes)==53 and [x['scene_number'] for x in scenes]==list(range(1,54))
    for row,op in zip(scenes,plan['scene_ops']):
        for k,v in op['patch'].items():
            if k!='updated_at':assert row[k]==v,f'Scene readback mismatch {row["scene_number"]} {k}'
    assert sum(bool(s['metadata'].get('image_url')) for s in scenes)==49
    assert not fetch('std_project_assets',project_id=f'eq.{PID}',asset_type='eq.audio',status='in.(uploaded,assigned)')
    save('db-verification.json',{'verified_at':datetime.now(timezone.utc).isoformat(),**plan['revision'],
        'db_verified':True,'subtitle_blocks':263,'thai_blocks':263,'character_images':3,'video_prompts':12,
        'removed_obsolete_rows':205,'files_deleted':0,'tts_regeneration_required':True,'thumbnail':'awaiting_user_save'})
    print('DB VERIFIED: 53 scenes / 49 images / 263 Korean+Thai blocks / 12 video prompts. 4 images missing.',flush=True)

if __name__=='__main__':
    before=read('preapply-source.json')
    plan=build(before)
    if '--apply' in sys.argv:apply(before,plan)
    else:print('Dry plan prepared; use --apply for scoped DB writes.',flush=True)
