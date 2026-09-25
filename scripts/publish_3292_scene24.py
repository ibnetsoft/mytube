"""Scope-limited approved scene24 alternative; preserve all other user assets."""
import copy, hashlib, json
from datetime import datetime, timezone
import requests
from flashback_3292 import DEST, MANIFEST, STATE, UID, read, write, recovery, capture
from publish_3292_flashback import SHA
from scripts.repair_existing_topic_scripts import _headers
from worker.cowork_scene_assets import crop_grids

def main():
    journal_path=DEST/'scene24-apply-journal.json'
    assert not journal_path.exists(), 'Inspect existing journal before resumption'
    state=read(STATE); job=recovery.get_job(state,'scene24-alt-1')
    assert job['status']=='ready'; recovery.verify_file(job)
    before=capture(); p=before['project']; q=before['topic'][0]
    assert len(before['linked_projects'])==1
    assert hashlib.sha256(p['project_payload']['script'].encode()).hexdigest()==SHA
    assert hashlib.sha256(q['pregenerated_script'].encode()).hexdigest()==SHA
    structures=[q['pregenerated_structure'],p['source_payload']['pregenerated_structure'],p['project_payload']['structure']]
    for st in structures:
        assert len(st['scenes'])==53
        assert [s['scene_number'] for s in st['scenes'] if not s.get('image_url')]==[24]
    write(DEST/'scene24-before-publish.json',before)
    crop_grids(MANIFEST,DEST,DEST/'cropped')
    blob=(DEST/'cropped/scene-024.png').read_bytes(); sha=hashlib.sha256(blob).hexdigest()
    base,headers=_headers()
    key=f'topics/3292/repairs/{SHA[:16]}/flashback-v2/scene-024-{sha[:12]}.png'
    url=f'{base}/storage/v1/object/public/content-assets/{key}'
    response=requests.get(url,timeout=90)
    if response.status_code in (400,404):
        response=requests.post(f'{base}/storage/v1/object/content-assets/{key}',headers={**headers,'Content-Type':'image/png','x-upsert':'false'},data=blob,timeout=120)
        response.raise_for_status(); response=requests.get(url,timeout=90)
    response.raise_for_status(); assert hashlib.sha256(response.content).hexdigest()==sha
    refs=read(DEST/'flashback-character-anchors.json')
    asset={'scene_number':24,'image_url':url,'sha256':sha,'object_path':key,'width':1920,'height':1080,'prompt':job['prompt'],
      'character_reference_urls':[x['image_url'] for x in refs],'source':'codex_builtin_imagegen','bucket':'content-assets'}
    now=datetime.now(timezone.utc).isoformat()
    revision={'version':'3292-flashback-v2-scene24-alternative','applied_at':now,'script_sha256':SHA,'image_count':53,'scene_count':53,
      'updated_scenes':[24],'missing_image_scenes':[],'status':'images_complete','user_approved_alternative':True}
    def structure(st):
        st=copy.deepcopy(st)
        s=next(x for x in st['scenes'] if x['scene_number']==24)
        old_prompt=s['image_prompt']
        s.update(image_url=url,image_prompt=job['prompt'],asset_status='ready',image_generation_status='ready',visual_character_reference_urls=asset['character_reference_urls'])
        s.setdefault('metadata',{}).update(image_url=url,image_generation_status='ready',cowork_image_asset=asset,
          image_recovery_revision=revision,original_image_prompt=old_prompt)
        st['image_recovery_revision']=revision
        return st
    qs=structure(q['pregenerated_structure']); payload=copy.deepcopy(p['project_payload'])
    payload['structure']=structure(payload['structure']);payload['image_recovery_revision']=revision
    for sub in payload['subtitles']:
        if sub.get('scene_number')==24:
            assert not sub.get('image_url');sub['image_url']=url
    def progress(value):
        value=copy.deepcopy(value or {})
        value.update(scene_image_count=53,missing_image_scenes=[],image_generation_status='completed',image_recovery_revision=revision,
          ready_scene_count=sum(bool(s.get('video_url') or (s['scene_number']>12 and s.get('image_url'))) for s in qs['scenes']))
        return value
    source=copy.deepcopy(p['source_payload']);source['pregenerated_structure']=structure(source['pregenerated_structure'])
    source['progress_payload']=progress(source.get('progress_payload'))
    qpatch={'pregenerated_structure':qs,'progress_payload':progress(q.get('progress_payload'))}
    ppatch={'project_payload':payload,'source_payload':source,'progress_payload':progress(p.get('progress_payload')),'updated_at':now}
    row=next(s for s in before['scene_rows'] if s['scene_number']==24)
    updated=next(s for s in payload['structure']['scenes'] if s['scene_number']==24)
    rowpatch={'image_prompt':job['prompt'],'asset_status':'ready','metadata':{**row['metadata'],**updated['metadata']},'updated_at':now}
    fresh=capture()
    for k in ['project','topic','scene_rows']:
        a,b=fresh[k],before[k]
        if isinstance(a,list):a=sorted(a,key=lambda x:x['id']);b=sorted(b,key=lambda x:x['id'])
        assert a==b,'Concurrent edit: '+k
    write(DEST/'scene24-apply-plan.json',{'project':ppatch,'topic':qpatch,'scene':rowpatch})
    journal=[]
    def patch(table,old,body):
        params={'id':'eq.'+str(old['id'])}
        if old.get('updated_at'):params['updated_at']='eq.'+old['updated_at']
        if table=='std_projects':params.update(user_id='eq.'+UID,submitted_at='is.null',status='in.(claimed,in_progress)')
        r=requests.patch(base+'/rest/v1/'+table,params=params,headers={**headers,'Prefer':'return=representation'},json=body,timeout=90)
        r.raise_for_status();result=r.json();assert len(result)==1,'CAS failed '+table
        journal.append({'table':table,'old':old,'new':result[0]});write(journal_path,journal)
    patch('std_project_scenes',row,rowpatch);patch('topics_queue',q,qpatch);patch('std_projects',p,ppatch)
    after=capture();write(DEST/'scene24-after-publish.json',after)
    for actual,expected in [(after['project'],ppatch),(after['topic'][0],qpatch),(next(x for x in after['scene_rows'] if x['scene_number']==24),rowpatch)]:
        for k,v in expected.items():
            if k!='updated_at':assert actual[k]==v,k
    originals={x['scene_number']:x for x in before['scene_rows']}
    assert all(x==originals[x['scene_number']] for x in after['scene_rows'] if x['scene_number']!=24)
    for old,new in zip(p['project_payload']['structure']['scenes'],after['project']['project_payload']['structure']['scenes']):
        if old['scene_number']!=24:assert old==new
        else:
            for field in ['scene_text','narration','video_url','duration','start_time','end_time']:
                assert old.get(field)==new.get(field)
    assert after['project']['project_payload']['script']==p['project_payload']['script']
    assert after['project']['project_payload']['subtitle_translations']==p['project_payload']['subtitle_translations']
    for old,new in zip(p['project_payload']['subtitles'],payload['subtitles']):
        assert {k:v for k,v in old.items() if k!='image_url'}=={k:v for k,v in new.items() if k!='image_url'}
    assert all(x.get('image_url') for x in after['project']['project_payload']['structure']['scenes'])
    report={**revision,'db_verified':True,'storage_verified':True,'other_scenes_preserved':52,'script_unchanged':True,
      'subtitle_blocks':len(payload['subtitles']),'asset':asset,'drive_backup':'previous_partial_backup_unchanged'}
    write(DEST/'scene24-db-verification.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='asset'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
