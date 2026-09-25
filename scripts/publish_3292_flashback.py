"""Publish only reviewed flashback assets; explicit partial result, CAS and readback."""
import copy, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import requests
from PIL import Image, ImageOps
from flashback_3292 import DEST, MANIFEST, STATE, OUT, PID, UID, read, write, recovery, capture
from scripts.repair_existing_topic_scripts import _headers
from scripts.audit_active_content import fetch
from worker.cowork_scene_assets import _upscale_panel
from worker.codex_character_assets import CharacterAssetStore, digest

SHA='79e865def1d9692b937bb4bdc37298aaaae50717974d36a1373c86e2de669d5c'
NUMBERS={21,22,23}

def main():
    assert not (DEST/'apply-journal.json').exists(),'Inspect existing journal before any resumption'
    state=read(STATE);manifest=read(MANIFEST)
    assert state['source_hash']==recovery.digest(manifest)
    assert recovery.get_job(state,'scene24')['status']=='safety_review'
    for key in ['geumrye38','sunduk12']+[f'scene{n}' for n in NUMBERS]:
        j=recovery.get_job(state,key);assert j['status']=='ready';recovery.verify_file(j)
    before=capture();p=before['project'];q=before['topic'][0]
    assert len(before['linked_projects'])==1
    assert hashlib.sha256(p['project_payload']['script'].encode()).hexdigest()==SHA
    assert hashlib.sha256(q['pregenerated_script'].encode()).hexdigest()==SHA
    assert len(before['scene_rows'])==53
    for struct in [q['pregenerated_structure'],p['source_payload']['pregenerated_structure'],p['project_payload']['structure']]:
        assert len(struct['scenes'])==53
        for s in struct['scenes']:
            if s['scene_number'] in NUMBERS:assert not s.get('image_url'),'User filled scene; stop'
    write(DEST/'before-publish.json',before)
    base,headers=_headers()
    characters=[];store=CharacterAssetStore()
    for key,name,age,parent in [('geumrye38','금례 (38세 회상)','38','3292-final-geumrye'),('sunduk12','순덕 (12세 회상)','12','3292-final-sunduk')]:
        job=recovery.get_job(state,key);ckey='3292-flashback-v2-'+key
        assert not fetch('topic_character_assets',topic_queue_id='eq.3292',character_key='eq.'+ckey),'Character already exists; review before rerun'
        character={'character_key':ckey,'name':name,'role':'회상 시점 캐릭터 참조','gender':'female','age_group':age,
          'visual_dna_en':job['prompt'],'wardrobe_en':'Ochre-brown jeogori,indigo chima,black low bun' if age=='38' else 'Muted blue jeogori,charcoal chima,black braid',
          'continuity_instruction':f'Age-specific variant of {parent}. Use only for approved flashback scenes21-24; keep actual age{age}. Do not replace present-day reference.',
          'image_prompt':job['prompt'],'parent_character_key':parent,'time_period':'flashback','scene_numbers':[21,22,23,24] if age=='38' else [24]}
        anchor=store.publish(3292,character,DEST/(key+'.png'),digest(character),{'category':'옛날이야기','image_style':'realistic'})
        row=fetch('topic_character_assets',topic_queue_id='eq.3292',character_key='eq.'+ckey)[0]
        usage={**row['usage_context'],'parent_character_key':parent,'age':int(age),'time_period':'flashback',
          'scene_numbers':character['scene_numbers'],'approved_script_sha256':SHA,'scene_generation_status':'partial_scene24_blocked'}
        extra={'script_style':'story','story_style':'옛날이야기 / ~습니다 구술체','prompt_en':job['prompt'],
          'dna':{'parent_character_key':parent,'age':int(age),'time_period':'flashback','visual_dna_en':job['prompt']},'usage_context':usage}
        r=requests.patch(base+'/rest/v1/topic_character_assets',params={'id':'eq.'+str(row['id']),'updated_at':'eq.'+row['updated_at']},headers={**headers,'Prefer':'return=representation'},json=extra,timeout=60)
        r.raise_for_status();assert len(r.json())==1
        anchor['usage_context']=usage;characters.append(anchor)
    write(DEST/'flashback-character-anchors.json',characters)
    cropped=DEST/'cropped';cropped.mkdir(exist_ok=True);assets=[]
    for n in sorted(NUMBERS):
        j=recovery.get_job(state,f'scene{n}');target=cropped/f'scene-{n:03d}.png'
        with Image.open(recovery.verify_file(j)) as im:
            image=_upscale_panel(ImageOps.exif_transpose(im).convert('RGB'),1920,1080)
            if target.exists():
                with Image.open(target) as old:assert old.size==image.size and old.convert('RGB').tobytes()==image.tobytes()
            else:image.save(target,format='PNG',optimize=True)
        blob=target.read_bytes();sha=hashlib.sha256(blob).hexdigest()
        key=f'topics/3292/repairs/{SHA[:16]}/flashback-v2/scene-{n:03d}-{sha[:12]}.png'
        url=f'{base}/storage/v1/object/public/content-assets/{key}'
        r=requests.get(url,timeout=90)
        if r.status_code in (400,404):
            r=requests.post(f'{base}/storage/v1/object/content-assets/{key}',headers={**headers,'Content-Type':'image/png','x-upsert':'false'},data=blob,timeout=120);r.raise_for_status()
            r=requests.get(url,timeout=90)
        r.raise_for_status();assert hashlib.sha256(r.content).hexdigest()==sha
        assets.append({'scene_number':n,'image_url':url,'sha256':sha,'object_path':key,'width':1920,'height':1080,'prompt':j['prompt'],
          'character_reference_urls':[characters[0]['image_url']],'source':'codex_builtin_imagegen','bucket':'content-assets'})
        print(f'Scene{n}:1920x1080 uploaded and bytes verified',flush=True)
    write(DEST/'uploaded-assets.json',{'status':'partial','assets':assets,'missing_scene_numbers':[24]})
    lookup={a['scene_number']:a for a in assets};now=datetime.now(timezone.utc).isoformat()
    progress_summary={'scene_image_count':52,'missing_image_scenes':[24],'image_generation_status':'partial'}
    revision={'version':'3292-flashback-v2','applied_at':now,'script_sha256':SHA,'image_count':52,
      'scene_count':53,'updated_scenes':sorted(NUMBERS),'missing_image_scenes':[24],
      'status':'partial_images','blocked_request_id':'da5ab3b7-1b7e-4064-9003-2612e50b120c'}
    def scene_update(s):
        n=s['scene_number'];s=copy.deepcopy(s)
        if n not in lookup:return s
        a=lookup[n];s.update(image_url=a['image_url'],image_prompt=a['prompt'],asset_status='ready',image_generation_status='ready')
        m=s.setdefault('metadata',{});m.update(image_url=a['image_url'],image_generation_status='ready',cowork_image_asset=a,
          image_recovery_revision=revision,original_image_prompt=s.get('original_image_prompt') or next(x['image_prompt'] for x in q['pregenerated_structure']['scenes'] if x['scene_number']==n))
        s['visual_character_reference_urls']=a['character_reference_urls']
        return s
    def structure_update(struct):
        struct=copy.deepcopy(struct);struct['scenes']=[scene_update(s) for s in struct['scenes']]
        struct.update(flashback_character_anchors=characters,image_recovery_revision=revision)
        return struct
    qstructure=structure_update(q['pregenerated_structure'])
    payload=copy.deepcopy(p['project_payload']);payload['structure']=structure_update(payload['structure'])
    payload.update(flashback_character_anchors=characters,image_recovery_revision=revision)
    for sub in payload['subtitles']:
        n=sub.get('scene_number')
        if n in lookup:
            assert not sub.get('image_url'),'Unexpected user subtitle image; stop'
            sub['image_url']=lookup[n]['image_url']
    def progress_update(prog):
        prog=copy.deepcopy(prog or {});prog.update(progress_summary,image_recovery_revision=revision)
        prog['ready_scene_count']=sum(bool(s.get('video_url') or (s['scene_number']>12 and s.get('image_url'))) for s in qstructure['scenes'])
        return prog
    source=copy.deepcopy(p['source_payload']);source['pregenerated_structure']=structure_update(source['pregenerated_structure'])
    source['progress_payload']=progress_update(source.get('progress_payload'))
    source['flashback_character_anchors']=characters
    qpatch={'pregenerated_structure':qstructure,'progress_payload':progress_update(q.get('progress_payload'))}
    ppatch={'project_payload':payload,'source_payload':source,'progress_payload':progress_update(p['progress_payload']),'updated_at':now}
    ops=[]
    for old in before['scene_rows']:
        if old['scene_number'] not in lookup:continue
        updated=next(s for s in payload['structure']['scenes'] if s['scene_number']==old['scene_number'])
        ops.append((old,{'image_prompt':updated['image_prompt'],'asset_status':'ready','metadata':{**old['metadata'],**updated['metadata']},'updated_at':now}))
    # Detect edits made while the files were uploading before touching project content.
    fresh=capture()
    for k in ('project','topic','scene_rows'):
        x,y=fresh[k],before[k]
        if isinstance(x,list):x=sorted(x,key=lambda z:z['id']);y=sorted(y,key=lambda z:z['id'])
        assert x==y,'Concurrent change: '+k
    write(DEST/'apply-plan.json',{'project_patch':ppatch,'topic_patch':qpatch,'scene_ops':ops})
    journal=[]
    def patch(table,old,body):
        params={'id':'eq.'+str(old['id'])}
        if old.get('updated_at'):params['updated_at']='eq.'+old['updated_at']
        if table=='std_projects':params.update(user_id='eq.'+UID,submitted_at='is.null',status='in.(claimed,in_progress)')
        r=requests.patch(f'{base}/rest/v1/{table}',params=params,headers={**headers,'Prefer':'return=representation'},json=body,timeout=90)
        r.raise_for_status();result=r.json();assert len(result)==1,'CAS failed '+table
        journal.append({'table':table,'old':old,'new':result[0]});write(DEST/'apply-journal.json',journal)
    for old,body in ops:patch('std_project_scenes',old,body)
    patch('topics_queue',q,qpatch);patch('std_projects',p,ppatch)
    after=capture();write(DEST/'after-publish.json',after)
    for tablekey,body in [('project',ppatch),('topic',qpatch)]:
        actual=after[tablekey] if tablekey=='project' else after[tablekey][0]
        for k,v in body.items():
            if k!='updated_at':assert actual[k]==v
    for old,body in ops:
        actual=next(s for s in after['scene_rows'] if s['id']==old['id'])
        for k,v in body.items():
            if k!='updated_at':assert actual[k]==v
    oldrows={s['id']:s for s in before['scene_rows']}
    assert all(s==oldrows[s['id']] for s in after['scene_rows'] if s['scene_number'] not in NUMBERS)
    assert after['project']['project_payload']['script']==p['project_payload']['script']
    ss=after['project']['project_payload']['structure']['scenes']
    assert sum(bool(s.get('image_url')) for s in ss)==52
    assert [s['scene_number'] for s in ss if not s.get('image_url')]==[24]
    original={s['scene_number']:s for s in p['project_payload']['structure']['scenes']}
    assert all(s==original[s['scene_number']] for s in ss if s['scene_number'] not in NUMBERS)
    assert all(s.get('video_url')==original[s['scene_number']].get('video_url') for s in ss)
    assert after['project']['project_payload']['subtitle_translations']==p['project_payload']['subtitle_translations']
    for a,b in zip(p['project_payload']['subtitles'],payload['subtitles']):
        assert {k:v for k,v in a.items() if k!='image_url'}=={k:v for k,v in b.items() if k!='image_url'}
    report={**revision,'db_verified':True,'storage_verified':True,'unaffected_images_preserved':49,
      'subtitle_blocks':len(payload['subtitles']),'new_character_references':2,'total_character_references':5,
      'video_files_generated':0,'script_unchanged':True,'verified_at':datetime.now(timezone.utc).isoformat()}
    write(DEST/'db-verification.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
