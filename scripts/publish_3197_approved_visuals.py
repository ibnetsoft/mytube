"""Publish approved 3197 visuals to one unsubmitted project, never the shared topic.

Default is a local dry run. --upload verifies immutable Storage objects; --drive
adds a versioned package to the existing folder; --apply uses CAS and rollback.
Old user media files are preserved; outdated associations are retired only.
"""
import copy
import hashlib
import json
import sys
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_active_content import fetch
from scripts.repair_active_materials import dump, patch_row
from scripts.repair_existing_topic_scripts import _headers

OUT = ROOT / 'output/3197_approved_visual_revision'
PID = '10b3d223-1457-415a-ba40-7b947c6c1b3d'
REV = '3197-approved-visuals-20260912'
BUCKET = 'content-assets'
PREFIX = f'std-projects/{PID}/{REV}'
SHA = 'b6a1ae235bb5025c4826130123071e6360dc3989156e233ef713c723368a7658'
STALE = {'retention_hook','emotional_shift','character_choice','dramatic_function',
    'reveal_or_question','scene_emotion','scene_purpose','shot_hints','visual_direction_plan',
    'payoff','opening_hook','planner_notes','title_promise','media_prompt_director',
    'benchmark_analysis','material_repair_previous_subtitles','visual_package_drive',
    'material_repair','visual_revision_status','tts_generated_at','global_mood',
    'title_candidates','sanitized_to_title_from_scene_situation'}
VIDEO = {'video_url','video_asset_id','video_drive_file_id','video_file_name',
    'video_storage_path','video_storage_object_path','video_path','video_source_url'}

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def clean(value):
    if isinstance(value, list): return [clean(v) for v in value]
    if not isinstance(value, dict): return value
    return {k: clean(v) for k,v in value.items() if k not in STALE | VIDEO}

def file_plan():
    files = {f'scenes/scene-{i:03d}.png': OUT/f'scenes/scene-{i:03d}.png' for i in range(1,54)}
    files.update({f'characters/{key}.png': path for key,path in {
        'deoksu':ROOT/'output/3197_visual_revision/character-reference-1.png',
        'sunim':ROOT/'output/3197_visual_revision/character-reference-2.png',
        'mother':ROOT/'output/3197_visual_revision/character-reference-3.png',
        'jang':OUT/'character-jang.png','bokdong':OUT/'character-bokdong.png'}.items()})
    files.update({name:OUT/name for name in ('thumbnail-background.png','thumbnail-final.png')})
    for name,path in files.items():
        assert path.is_file(), name
        with Image.open(path) as im:
            im.verify()
        if name.startswith('scenes/'):
            with Image.open(path) as im: assert im.size == (1920,1080), name
    assert len({digest(p) for k,p in files.items() if k.startswith('scenes/')}) == 53
    return files

def upload(files):
    base,headers = _headers()
    def one(item):
        name,path = item
        sha = digest(path)
        object_path = f'{PREFIX}/{sha[:12]}/{name}'
        url = f'{base}/storage/v1/object/public/{BUCKET}/{object_path}'
        existing = requests.get(url, timeout=90)
        if existing.status_code != 200:
            assert existing.status_code in (400,404), existing.status_code
            response = requests.post(f'{base}/storage/v1/object/{BUCKET}/{object_path}',
                headers={**headers,'Content-Type':'image/png','x-upsert':'false'}, data=path.read_bytes(),timeout=120)
            response.raise_for_status()
            existing = requests.get(url,timeout=90)
        existing.raise_for_status()
        assert hashlib.sha256(existing.content).hexdigest() == sha, name
        print('Storage verified: '+name,flush=True)
        return name, {'url':url,'path':object_path,'sha256':sha,'size':path.stat().st_size}
    result = dict(ThreadPoolExecutor(max_workers=5).map(one, files.items()))
    dump(OUT/'uploaded.json',result)
    return result

def drive_package(files):
    local_deps=OUT/'python-deps'
    if local_deps.exists(): sys.path.insert(0,str(local_deps))
    from services.google_drive_service import GoogleDriveService
    service=GoogleDriveService(); drive=service._get_drive_service()
    folder='1a113s4dDhJTVdufT66q4QJfxX3AHI4EP'
    meta=drive.files().get(fileId=folder,fields='id,name,mimeType,trashed').execute()
    assert meta['mimeType']=='application/vnd.google-apps.folder' and not meta.get('trashed')
    package=OUT/(REV+'.zip')
    if not package.exists():
        with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
            for name,path in files.items(): z.write(path,name)
            for name in ('prepared.json','manifest.json','uploaded.json','generation-provenance.json'): z.write(OUT/name,name)
            for grid in sorted(OUT.glob('grid-*.png')): z.write(grid,'grids/'+grid.name)
            z.write(ROOT/'docs/script-revisions/3197-approved-20260912.md','approved-script.md')
    md5=hashlib.md5(package.read_bytes()).hexdigest()
    found=drive.files().list(q=f"'{folder}' in parents and name = '{package.name}' and trashed = false",
        fields='files(id,name,size,md5Checksum,webViewLink,parents)').execute().get('files',[])
    same=[f for f in found if f.get('md5Checksum')==md5]
    result=same[0] if same else service.upload_file(str(package),folder_id=folder,filename=package.name,
        mimetype='application/zip',make_public=False,description='Approved script and matching project-local visuals. Previous versions preserved.')
    assert result and result.get('id')
    actual=drive.files().get(fileId=result['id'],fields='id,name,size,md5Checksum,webViewLink,parents').execute()
    assert actual['md5Checksum']==md5 and int(actual['size'])==package.stat().st_size and folder in actual['parents']
    actual.update(folder_id=folder,script_sha256=SHA)
    dump(OUT/'drive.json',actual)
    print('Drive package verified: '+actual['id'],flush=True)
    return actual

def build(before,prepared,uploaded,drive_info=None):
    # PostgREST serializes timestamptz as +00:00, not Z. Keep exact readback CAS.
    p=before['project']; now=time.strftime('%Y-%m-%dT%H:%M:%S+00:00',time.gmtime())
    revision={**p['project_payload']['approved_script_revision'],
        'requires_revalidation':['uploaded_video_clips','tts','subtitle_timing'],
        'note':'Approved script with matching new scene images, prompts and thumbnail. Old video/audio files preserved but not active.'}
    url=lambda name:uploaded[name]['url']
    anchors=json.loads((ROOT/'output/3197_visual_revision/anchors.json').read_text(encoding='utf-8'))
    deoksu=anchors['main_character']; sunim,mother=anchors['supporting_characters'][:2]
    sunim.update(name='순임',role='주인공 — 누명을 벗고 자기 이름을 되찾는 며느리',tags=['순임','Sunim','주인공'])
    deoksu.update(role='순임의 남편',tags=['덕수','Deoksu','남편'])
    cast=[('sunim',sunim),('deoksu',deoksu),('mother',mother),
        ('jang',{'name':'장 노인','role':'과거 사건의 증인','character_key':'approved-jang','age_group':'70s','gender':'male'}),
        ('bokdong',{'name':'복동','role':'순임이 살려 키운 열 살 조카','character_key':'approved-bokdong','age_group':'10','gender':'male'})]
    for key,c in cast:
        f=uploaded[f'characters/{key}.png']
        c.update(image_url=f['url'],storage_bucket=BUCKET,storage_object_path=f['path'],
            visual_dna_en=prepared['cast_dna'][key],continuity_instruction=prepared['cast_dna'][key],
            image_generation_status='ready',generation_model='codex_builtin_image_gen',reference_fingerprint=f['sha256'])
    anchors={'main_character':sunim,'supporting_characters':[c for k,c in cast[1:]],'max_character_anchors':5}
    design=copy.deepcopy(p['project_payload']['thumbnail_design'])
    design.update(bg_url=url('thumbnail-background.png'),editor_bg_url=url('thumbnail-background.png'),
        thumbnail_url=url('thumbnail-final.png'),saved_at=now)
    for layer,text,y in zip(design['text_layers'],prepared['thumbnail_texts'],[72,87]): layer.update(text=text,y=y)
    image_ids={i:str(uuid.uuid5(uuid.NAMESPACE_URL,f'{PID}/{REV}/scene/{i}')) for i in range(1,54)}
    def scene(old,i):
        s=clean(copy.deepcopy(old)); plan=prepared['scenes'][i-1]; text=plan['scene_text']
        for k in ('text','scene_text','narration','narration_text','script_excerpt','scene_summary','scene_situation'):
            if k in s or k in ('scene_text','narration','script_excerpt'): s[k]=text
        s.update(image_prompt=plan['image_prompt'],video_prompt=plan['video_prompt'],image_url=url(f'scenes/scene-{i:03d}.png'),
            video_url=None,visual_type='image',image_asset_id=image_ids[i],video_prompt_required=i<=12,
            asset_status='ready',visual_revision=REV,approved_script_revision=revision)
        s['cowork_image_asset']={'source':'codex_builtin_image_gen','bucket':BUCKET,
            'object_path':uploaded[f'scenes/scene-{i:03d}.png']['path'],'width':1920,'height':1080}
        if isinstance(s.get('metadata'),dict): s['metadata']=scene(s['metadata'],i)
        return s
    def payload(old):
        result=clean(copy.deepcopy(old))
        result.update(character_anchors=anchors,main_character=sunim,supporting_characters=anchors['supporting_characters'],
            publish_metadata=prepared['publish_metadata'],thumbnail_url=url('thumbnail-final.png'),
            thumbnail_bg_url=url('thumbnail-background.png'),thumbnail_design=design,
            thumbnail_hook_texts=prepared['publish_metadata']['thumbnail_hook_texts'],thumbnail_image_prompt=prepared['thumbnail_prompt'],
            thumbnail_completed=True,thumbnail_generation_status='completed',thumbnail_confirmed_at=now,
            image_grid_prompts=prepared['image_grid_prompts'],image_style='realistic',approved_script_revision=revision,
            visual_revision_status='completed',visual_revision={'id':REV,'script_sha256':SHA,'scene_count':53,
                'video_prompt_count':12,'generated_video_clips':0,'review':'manual_context_and_image_review','saved_at':now})
        if drive_info: result['visual_package_drive']=drive_info
        if 'upload_title' in result: result['upload_title']=p['title']
        if 'generated_title' in result: result['generated_title']=p['title']
        if isinstance(result.get('scenes'),list):
            assert len(result['scenes'])==53
            result['scenes']=[scene(s,i) for i,s in enumerate(result['scenes'],1)]
        for key in ('structure','pregenerated_structure','progress_payload'):
            if isinstance(result.get(key),dict): result[key]=payload(result[key])
        if isinstance(result.get('subtitles'),list):
            for sub in result['subtitles']:
                i=int(sub['scene_number']); sub.update(image_url=url(f'scenes/scene-{i:03d}.png'),video_url=None)
        return result
    editor,source,progress=[payload(p[k]) for k in ('project_payload','source_payload','progress_payload')]
    operations=[]
    for old in before['scenes']:
        i=old['scene_number']; s=scene(old,i)
        operations.append(('std_project_scenes',old,{k:s[k] for k in ('image_prompt','video_prompt','asset_status','metadata')}|{'shot_hints':[]}))
    for a in before['assets']:
        if a['asset_type'] in ('image','video','thumbnail') and a['status'] in ('uploaded','assigned','ready'):
            operations.append(('std_project_assets',a,{'status':'replaced','metadata':{**(a.get('metadata') or {}),
                'superseded_by_visual_revision':REV,'original_file_preserved':True}}))
    records=[]
    for i in range(1,55):
        is_thumb=i==54; name='thumbnail-final.png' if is_thumb else f'scenes/scene-{i:03d}.png'; f=uploaded[name]
        records.append({'id':str(uuid.uuid5(uuid.NAMESPACE_URL,f'{PID}/{REV}/thumbnail')) if is_thumb else image_ids[i],
            'project_id':PID,'scene_id':None if is_thumb else before['scenes'][i-1]['id'],
            'scene_number':None if is_thumb else i,'asset_type':'thumbnail' if is_thumb else 'image',
            'file_name':Path(name).name,'mime_type':'image/png','file_size':f['size'],'checksum':f['sha256'],
            'status':'uploaded','uploaded_by':p['user_id'],'storage_bucket':BUCKET,'storage_path':f['path'],
            'metadata':{'source':'codex_builtin_image_gen','storage_bucket':BUCKET,'storage_path':f['path'],
                'storage_public_url':f['url'],'visual_revision':REV,'script_sha256':SHA}})
    operations.append(('std_projects',p,{'project_payload':editor,'source_payload':source,'progress_payload':progress}))
    for table,old,changes in operations: changes['updated_at']=now
    assert editor['script']==p['project_payload']['script'] and source['pregenerated_script']==editor['script']
    assert [(s['id'],s['text']) for s in editor['subtitles']]==[(s['id'],s['text']) for s in p['project_payload']['subtitles']]
    return operations,records

def main():
    prepared=json.loads((OUT/'prepared.json').read_text(encoding='utf-8'))
    before=json.loads((OUT/'before.json').read_text(encoding='utf-8'))
    files=file_plan()
    uploaded=upload(files) if '--upload' in sys.argv else json.loads((OUT/'uploaded.json').read_text(encoding='utf-8'))
    assert set(uploaded)==set(files)
    for name,path in files.items():
        assert uploaded[name]['sha256']==digest(path), 'Local image changed after upload'
        assert uploaded[name]['path'].startswith(PREFIX+'/'), 'Wrong project Storage path'
    drive_info=drive_package(files) if '--drive' in sys.argv else (json.loads((OUT/'drive.json').read_text(encoding='utf-8')) if (OUT/'drive.json').exists() else None)
    operations,records=build(before,prepared,uploaded,drive_info)
    dump(OUT/'publish-plan.json',{'operations':[{'table':t,'id':b['id'],'changes':c} for t,b,c in operations],'new_assets':records})
    print(json.dumps({'operations':len(operations),'new_assets':len(records),'apply':'--apply' in sys.argv}),flush=True)
    if '--apply' not in sys.argv:return
    p=fetch('std_projects',id='eq.'+PID)[0]
    assert p==before['project'],'Project changed since backup; stop for reconciliation'
    assert p['employee_email']=='supapitmusic@gmail.com' and not p.get('submitted_at') and p['status']=='in_progress'
    assert hashlib.sha256(p['project_payload']['script'].encode()).hexdigest()==SHA
    assert fetch('std_project_scenes',project_id='eq.'+PID,order='scene_number.asc')==before['scenes']
    assert fetch('std_project_assets',project_id='eq.'+PID,order='id.asc')==sorted(before['assets'],key=lambda a:a['id'])
    base,headers=_headers(); completed=[]; inserted=False
    dump(OUT/'publish-before.json',before)
    try:
        for table,old,changes in operations[:-1]:
            assert fetch('std_projects',id='eq.'+PID)[0]==p,'Concurrent project edit'
            assert fetch(table,id='eq.'+old['id'])[0]==old,'Concurrent scene/asset edit'
            saved=patch_row(table,old,changes); completed.append((table,old,changes,saved))
            dump(OUT/'publish-journal.json',{'completed':[{'table':t,'id':b['id']} for t,b,c,s in completed]})
        response=requests.post(f'{base}/rest/v1/std_project_assets',headers=headers,json=records,timeout=120)
        response.raise_for_status(); inserted=True
        table,old,changes=operations[-1]
        assert fetch(table,id='eq.'+PID)[0]==old,'Concurrent project edit'
        saved=patch_row(table,old,changes); completed.append((table,old,changes,saved))
    except Exception:
        for table,old,changes,saved in reversed(completed):
            patch_row(table,saved,{key:old.get(key) for key in changes})
        # A transport error may follow a successful insert; look up only our
        # deterministic IDs before retiring them, never remove stored files.
        owned_ids={a['id'] for a in records}
        created=[a for a in fetch('std_project_assets',project_id='eq.'+PID,order='id.asc') if a['id'] in owned_ids]
        if inserted or created:
            requests.patch(f'{base}/rest/v1/std_project_assets',headers=headers,
                params={'project_id':'eq.'+PID,'id':'in.('+','.join(a['id'] for a in records)+')'},json={'status':'replaced'},timeout=60).raise_for_status()
        raise
    actual=fetch('std_projects',id='eq.'+PID)[0]
    live_scenes=fetch('std_project_scenes',project_id='eq.'+PID,order='scene_number.asc')
    active=[a for a in fetch('std_project_assets',project_id='eq.'+PID,order='id.asc') if a['status'] in ('uploaded','assigned')]
    assert len([a for a in active if a['asset_type']=='image'])==53
    assert len([a for a in active if a['asset_type']=='thumbnail'])==1
    assert not [a for a in active if a['asset_type'] in ('video','audio')]
    assert actual['project_payload']['script']==p['project_payload']['script']
    for s,plan in zip(live_scenes,prepared['scenes']):
        assert s['scene_text']==plan['scene_text'] and s['image_prompt']==plan['image_prompt'] and s['video_prompt']==plan['video_prompt']
        assert not s['metadata'].get('video_url')
    dump(OUT/'verified.json',{'project_id':PID,'script_sha256':SHA,'scenes':53,'video_prompts':12,
        'thumbnail':True,'active_video_clips':0,'active_audio':0,'storage_objects_verified':len(uploaded),'drive':drive_info})
    print('Project-only publish verified',flush=True)

if __name__=='__main__': main()
