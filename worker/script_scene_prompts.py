"""Incremental, source-bound image directions inside manual script cards."""
import copy, hashlib, json, time
from functools import lru_cache
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from worker.script_manual_workflow import digest, package

ROOT=Path(__file__).resolve().parents[1]

@lru_cache(maxsize=512)
def file_hash(path,mtime,size):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def catalog():
    items=[]
    def add(identity,label,kind,path):
        path=Path(path)
        if not path.is_file():return
        items.append({'id':identity,'label':label,'kind':kind,'path':str(path.resolve()),
                      'sha256':file_hash(str(path),path.stat().st_mtime_ns,path.stat().st_size),
                      'review_status':'참조 연결용 · 새 장면의 원화 검수와 별개'})
    base=ROOT/'output/wuxia-series-rebuild/episode-01'
    for key,label in [('seojin','서진'),('dogyeom','도겸'),('jangho','장호'),('clerk','서리'),('guard','철산문 무사')]:
        add('character-'+key,'1화 '+label,'인물',base/'character-sheets'/f'{key}-v1.png')
    manifest=ROOT/'docs/wuxia-props/reference-manifest.json'
    if manifest.exists():
        for n,r in enumerate(json.loads(manifest.read_text()).get('references',[])):
            owner={'seojin':'서진','dogyeom':'도겸','jangho':'장호','clerk':'서리','guard':'철산문 무사'}.get(r.get('character_id'),r.get('character_id',''))
            detail='무기 확대' if 'crop' in r['path'] else '무기 시트' if 'weapon-sheet' in r['path'] else '소품·복장'
            add('prop-'+str(n),owner+' '+detail,'소품',ROOT/r['path'])
    if manifest.exists():
        for r in json.loads(manifest.read_text()).get('weapon_sheets',[]):
            owner={'seojin':'서진','jangho':'장호'}.get(r['character_id'],r['character_id'])
            add('weapon-'+r['character_id'],owner+' 승인 원화 추출 무기 시트','소품',ROOT/r['path'])
    add('style-wuxia','2D 무협 웹툰 화풍','화풍',ROOT/'auth-web/public/img/styles/style_wuxia_webtoon.png')
    # Original episode frames provide scene geometry/state, never assume an intact prop is a broken-state asset.
    inventory=ROOT/'docs/wuxia-handoff/episode-01/image-inventory.json'
    if inventory.exists():
        for r in json.loads(inventory.read_text()):
            add(r['asset_id'],r['asset_id']+' · '+r.get('description',''),'1화 장면',base/r['file'])
    return items

class SceneAction(BaseModel):
    action:str
    scene_id:str=Field(min_length=1,max_length=80)
    expected_hash:str=Field(min_length=64,max_length=64)
    reference_ids:list[str]=Field(default_factory=list,max_length=20)
    image_prompt:str=Field(default='',max_length=24000)
    feedback:str=Field(default='',max_length=12000)

def generate_scene(identity,scene,neighbors,request,refs,feedback,revision):
    from worker.codex_content_runner import CodexStagedContentRunner
    from worker.script_worker_guidance import load_production_guidance
    from worker.generation_validation import validated_stage
    runner=CodexStagedContentRunner()
    from worker.wuxia_generation_gate import policy
    policy_snapshot=policy()
    context={'execution_policy':policy_snapshot,'settings':request,'scene':scene,'neighboring_scenes':neighbors,'selected_reference_images':refs,
             'production_guidance':load_production_guidance(),'user_feedback':feedback}
    def valid(v):
        if not isinstance(v.get('image_prompt'),str) or not v['image_prompt'].strip() or len(v['image_prompt'])>24000:raise ValueError('이미지 프롬프트가 필요합니다.')
    value=validated_stage(lambda n,c,t:runner._stage('scene-'+identity,n,c,t),f'scene_image_{scene["scene_id"]}_{revision}',context,
        'Write ONLY one editable image prompt for THIS scene. Return {image_prompt:string}. Read the selected image files using available image inspection tools before describing their identities/geometry. Preserve named identities, costumes, anatomy, prop custody and current state, adjacent spatial continuity and final 2D Korean wuxia webtoon look. Describe ONE coherent moment, not a collage. No baked dialogue/text. An intact weapon reference does not establish an approved broken weapon state: explicitly flag needed new state assets. Do not attach absent characters or props just because selected references contain them. These paths are available references, not proof that image generation attachments or artwork review occurred. No actual image generation, other scenes, video/AE/TTS or publication.',valid)
    return {'image_prompt':value['image_prompt'],'policy_sha256':policy_snapshot['sha256']}

def register(app,jobs,persist,token):
    @app.get('/api/manual-reference-images')
    def images():return {'images':[{**r,'url':f'/api/manual-reference-images/{r["id"]}/file?local_token={token}'} for r in catalog()]}
    @app.get('/api/manual-reference-images/{asset_id}/file')
    def image(asset_id:str):
        row=next((r for r in catalog() if r['id']==asset_id),None)
        if not row:raise HTTPException(404,'참조 이미지를 찾지 못했습니다.')
        return FileResponse(row['path'])
    def save_bundle(identity,bundle,w):
        w['revision']+=1
        candidate=package(w,bundle['request'],bundle['candidate'].get('applied_guidelines'))
        # Preserve independent title metadata.
        if bundle['candidate'].get('structure',{}).get('series_naming'):candidate['structure']['series_naming']=bundle['candidate']['structure']['series_naming']
        for later in w['stages'][1:]:
            later['status']='stale' if later.get('output') else 'pending';later.pop('approved_hash',None)
        persist(identity,candidate,status='awaiting_approval',stage='씬별 이미지 프롬프트 · 검토 대기',error='')
    def run(identity,bundle,w,scene,neighbors,refs,body):
        entry=w['scene_image_prompts'][scene['scene_id']]
        try:
            value=generate_scene(identity,scene,neighbors,bundle['request'],refs,body.feedback,w['revision'])
            entry['image_prompt']=value['image_prompt'] if isinstance(value,dict) else value
            entry['guidance_applied']={'policy_sha256':value.get('policy_sha256') if isinstance(value,dict) else '', 'scope':'prompt_planning_only'}
            entry.update(status='review',source_hash=digest(scene),references=refs)
        except Exception as exc:
            entry.update(status='failed',error='이미지 프롬프트 생성 실패 · 기존 결과 보존',error_type=type(exc).__name__)
        finally:
            with jobs.lock:
                try:save_bundle(identity,bundle,w)
                finally:jobs.inflight.discard(identity)
    @app.post('/api/jobs/{identity}/scene-image-prompt')
    def action(identity:str,body:SceneAction):
        try:
            with jobs.lock:
                b=jobs.load(identity);j=b['job'];c=copy.deepcopy(b['candidate']);w=c.get('manual_workflow');b['candidate']=c
                if not w or j.get('worker_id')!=jobs.worker_id or j.get('published') or j['status'] in ('canceled','cancelled'):raise ValueError('이 컴퓨터의 편집 가능한 수동 작업을 선택하세요.')
                if jobs.busy():raise ValueError('현재 생성 작업이 끝난 뒤 진행하세요.')
                if digest(c)!=body.expected_hash:raise ValueError('결과 버전이 변경됐습니다. 다시 열어 확인하세요.')
                scenes=w['stages'][0].get('output',{}).get('scenes',[]);scene=next((s for s in scenes if s['scene_id']==body.scene_id),None)
                if not scene:raise ValueError('현재 대본에 있는 씬을 선택하세요.')
                refs_by_id={r['id']:r for r in catalog()}
                if len(set(body.reference_ids))!=len(body.reference_ids) or any(i not in refs_by_id for i in body.reference_ids):raise ValueError('사용 가능한 참조 이미지를 선택하세요.')
                refs=[refs_by_id[i] for i in body.reference_ids]
                if body.action not in ('save','generate'):raise ValueError('지원하지 않는 작업입니다.')
                entry=w.setdefault('scene_image_prompts',{}).setdefault(scene['scene_id'],{})
                # Keep a revision copy before replacing an existing prompt.
                if entry: 
                    from worker.script_manual_workflow import write
                    write(jobs.root/identity/'manual-history'/f'{w["revision"]}-scene-{scene["scene_id"]}.json',entry)
                entry.update(references=refs,source_hash=digest(scene),feedback=body.feedback)
                if body.action=='save':
                    entry.update(image_prompt=body.image_prompt,status='review');entry.pop('guidance_applied',None)
                else:entry.update(status='running',error='')
                save_bundle(identity,b,w)
                if body.action=='generate':
                    jobs.inflight.add(identity);jobs.update(identity,status='running',stage=f'{body.scene_id} 이미지 프롬프트 생성 중')
                    body.feedback+='\n[이 작업에 기록된 실제 문제·해결 근거]\n'+json.dumps(w.get('quality_control',{}),ensure_ascii=False)
                    pos=scenes.index(scene);jobs.pool.submit(run,identity,b,w,scene,scenes[max(0,pos-1):pos+2],refs,body)
                return {'status':jobs.rows[identity]['status']}
        except (ValueError,KeyError) as exc:raise HTTPException(409,str(exc)) from exc
