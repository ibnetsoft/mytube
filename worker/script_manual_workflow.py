"""User-controlled script -> image prompts -> video prompts -> AE directions.
No delivery, image generation, TTS or render is dispatched from this workflow.
"""
import copy, hashlib, json, os, re, time
from pathlib import Path
from worker.script_worker_store import StoreUnavailable

CONTRACT = 'script_manual_workflow/v1'
LABELS = ['대본', '이미지 프롬프트', '영상 씬·프롬프트', 'AE 지침']

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.manual.tmp'); temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8'); os.replace(temp, path)

def validate(index, value, workflow=None):
    if not isinstance(value, dict) or not isinstance(value.get('quality_notes'), list):
        raise ValueError('결과와 검토 메모 형식을 확인하세요.')
    key = ['scenes', 'cuts', 'selections', 'directions'][index]
    rows = value.get(key)
    if not isinstance(rows, list) or not 1 <= len(rows) <= 1000:
        raise ValueError('장면별 결과가 필요합니다.')
    def text(v, limit=24000): return isinstance(v, str) and bool(v.strip()) and len(v) <= limit
    idkey = 'scene_id' if index == 0 else 'cut_id'
    ids = [r.get(idkey) for r in rows if isinstance(r, dict)]
    if len(ids) != len(rows) or any(not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',v) for v in ids) or len(set(ids)) != len(ids):
        raise ValueError('장면/컷 ID는 중복 없이 유지하세요.')
    if index == 0:
        for r in rows:
            if not text(r.get('title'), 200) or not text(r.get('visual_action')) or not isinstance(r.get('spoken_blocks'), list):
                raise ValueError('씬 제목·화면 상황·나레이션/대사를 구분하세요.')
            for b in r['spoken_blocks']:
                if not isinstance(b,dict) or b.get('kind') not in ('narration','dialogue') or not text(b.get('text')) or (b['kind']=='dialogue' and not text(b.get('speaker'),100)):
                    raise ValueError('발화 종류, 대사 화자와 내용을 확인하세요.')
    elif index == 1:
        scenes = {r['scene_id'] for r in workflow['stages'][0]['output']['scenes']}
        if {r.get('scene_id') for r in rows} != scenes or any(not text(r.get('image_prompt')) for r in rows):
            raise ValueError('확정된 모든 씬에 이미지 컷과 프롬프트가 필요합니다.')
        order={r['scene_id']:n for n,r in enumerate(workflow['stages'][0]['output']['scenes'])}
        if [order[r['scene_id']] for r in rows]!=sorted(order[r['scene_id']] for r in rows):raise ValueError('이미지 컷은 확정 대본 씬 순서를 유지하세요.')
        if any(not isinstance(r.get('references'),list) or any(not text(x,500) for x in r['references']) for r in rows):
            raise ValueError('필요한 참조 자산을 목록으로 적으세요. 미확보 자산은 명시하세요.')
    else:
        cuts = [r['cut_id'] for r in workflow['stages'][1]['output']['cuts']]
        if ids != cuts: raise ValueError('확정된 이미지 컷 ID와 순서를 유지하세요.')
        for r in rows:
            if index == 2:
                if type(r.get('selected')) is not bool or not text(r.get('reason')) or not isinstance(r.get('video_prompt'),str):
                    raise ValueError('영상 선택 여부와 이유를 확인하세요.')
                if r['selected'] and not text(r['video_prompt']): raise ValueError('선택한 컷에는 영상 프롬프트가 필요합니다.')
            elif not text(r.get('ae_instruction')) or not text(r.get('timing_note')):
                raise ValueError('컷별 AE 지침과 적용 시점이 필요합니다. 효과 없음도 명시하세요.')
    if len(json.dumps(value,ensure_ascii=False)) > 1800000: raise ValueError('한 단계 결과가 너무 큽니다.')

def render_script(output):
    lines=[]
    for n, scene in enumerate(output.get('scenes',[]),1):
        lines += [f"씬 {n}. {scene['title']}", '화면 상황: '+scene['visual_action']]
        for block in scene['spoken_blocks']:
            lines.append(('나레이션' if block['kind']=='narration' else '대사 · '+block['speaker'])+': '+block['text'])
        if not scene['spoken_blocks']: lines.append('무음 장면')
        lines.append('')
    return '\n'.join(lines)

def package(workflow, request, applied=None):
    first=workflow['stages'][0].get('output') or {'scenes':[]}
    scenes=[]
    for n,r in enumerate(first['scenes'],1):
        spoken='\n'.join((b['speaker']+': ' if b['kind']=='dialogue' else '')+b['text'] for b in r['spoken_blocks'])
        scenes.append({**r,'scene_number':n,'scene_order':n,'scene_text':spoken,'narration':spoken})
    structure={'scenes':scenes,'manual_workflow_contract':CONTRACT}
    from worker.script_transition_export import transition_display_plan
    transition_display=transition_display_plan(workflow)
    if transition_display:structure['cut_transition_plan']=transition_display
    if request.get('series_naming'):structure['series_naming']=request['series_naming']
    if workflow.get('scene_image_prompts'):structure['scene_image_prompt_drafts']=workflow['scene_image_prompts']
    for i,key in [(1,'manual_image_prompts'),(2,'manual_video_directions'),(3,'manual_ae_directions')]:
        if workflow['stages'][i].get('output'):structure[key]=workflow['stages'][i]['output']
    return {'script':render_script(first),'structure':structure,'manual_workflow':workflow,
            'applied_guidelines':applied or [],'remaining':[],
            'completion_scope':'manual_script_and_direction_plans_only'}

TASKS = [
 '''Write the requested script only. Return {scenes:[{scene_id,title,visual_action,spoken_blocks:[{kind:narration|dialogue,speaker,text}]}],quality_notes:[]}. Use stable ASCII scene IDs in story order. visual_action is a SHORT, unspoken account of what the audience sees. Spoken blocks contain only words to be voiced; dialogue needs a named speaker. Silent scenes use an empty spoken_blocks list. Follow confirmed language, genre, era and continuity. Improve story causality, character choices and episode payoff; avoid repetitive injuries, waiting and visible-action narration. Do not generate image prompts, video prompts, AE directions, music, metadata or footage. Do not claim assets exist. There is no downstream automatic step.''',
 '''Use the user-approved script unchanged. Return {cuts:[{cut_id,scene_id,image_prompt,references:[string]}],quality_notes:[]}. Cover every approved scene, in story order, with stable unique ASCII cut IDs. Reuse source-current scene_image_prompt_drafts and their selected reference IDs/paths faithfully; do not replace user-edited prompts. Stale drafts require re-planning against the changed source. Divide into motivated individual full-frame cuts; describe framing, action/contact, characters, anatomy, costume, props and their current states, environment continuity, final 2D style when applicable. references must name required approved asset IDs or explicitly say that an asset is not yet available; do not invent approved assets or claim attachments. Preserve visible identity/prop geometry; no baked text. Follow production guidance and user revisions. No video/AE prompts, actual images, audio, or publication.''',
 '''Use unchanged approved script and image-cut plan. Return {selections:[{cut_id,selected:boolean,reason,video_prompt:string}],quality_notes:[]}, exactly ONE entry for EVERY image cut in the SAME ORDER. Select only narratively motivated motion; all false is valid and no quota applies. A selected video_prompt specifies start/end states, a short 2-3s action, direction/speed/contact timing, continuity, fixed camera or brief motivated move, and unchanged face/costume/props/background plus no dialogue/no narration/no subtitles/no captions/no music/no sound effects/no audio. Unselected prompts may be empty. Do not generate video or AE directions. User can change selection before approval.''',
 '''Use the approved script, image cuts and user-selected video plan unchanged. Return {directions:[{cut_id,ae_instruction,timing_note}],quality_notes:[]}, exactly ONE entry for EVERY image cut in SAME ORDER. Choose only scene-motivated existing effects, or explicitly no effect. Include timing/holds, face/hand/blade/lettering protection, speech/visual anchors, transition, effects strength and duration. No slow/gentle whole-scene zoom. For visible sword/body aura animate only energy throughout visible state, keeping people/blades/text fixed; actual masks require actual artwork review. For impact use motion -> reviewed contact -> optional flash/outward debris/shake. Video-selected cuts preserve their motion and avoid duplicate camera/effects. Final timing requires actual saved voice; do not invent measured timestamps, source reviews or render success. Return PLANS ONLY, not rendering or publishing.'''
]

def generate(index, request, workflow, identity, notify, runner=None):
    if runner is None:
        from worker.codex_content_runner import CodexStagedContentRunner
        runner=CodexStagedContentRunner()
    from worker.script_worker_guidance import load_production_guidance
    from worker.wuxia_generation_gate import policy
    policy_snapshot=policy()
    context={'execution_policy':policy_snapshot,'confirmed_settings':request,'production_guidance':load_production_guidance(),
             'approved_previous_steps':[s['output'] for s in workflow['stages'][:index]],
             'approved_guidance':workflow.get('approved_guidance',''),'current_revision':workflow['revision'],'user_notes':workflow.get('feedback',''),'scene_image_prompt_drafts':workflow.get('scene_image_prompts',{}),'recorded_quality_findings':workflow.get('quality_control',{})}
    notify(f'{index+1}/4 {LABELS[index]} 생성 중')
    from worker.generation_validation import validated_stage
    value=validated_stage(lambda name,ctx,task:runner._stage('manual-'+identity,name,ctx,task),
        f'manual_{index+1}_{workflow["revision"]}',context,TASKS[index],lambda v:validate(index,v,workflow))
    notify(f'{index+1}/4 {LABELS[index]} 결과 검토 중')
    def review_valid(r):
        if type(r.get('passed')) is not bool or not isinstance(r.get('issues'),list) or not isinstance(r.get('evidence'),str) or not r['evidence'].strip() or (r['passed'] and r['issues']):raise ValueError('단계 검토 근거가 필요합니다.')
    review=validated_stage(lambda name,ctx,task:runner._stage('manual-'+identity,name,ctx,task),
        f'manual_{index+1}_{workflow["revision"]}_review',{**context,'result':value},
        'Independently review THIS step only against the approved inputs and requested scope. Return {passed:boolean,issues:[string],evidence:string}. Check continuity, no invented facts/approved assets, script visual/speech separation and pacing in step 1, full cut coverage and consistent geometry/state in step 2, sparse motivated user-controllable silent video directions in step 3, selective source-safe time-bound AE plans in step 4. Never claim actual artwork, audio or rendered output was reviewed. Record uncertainty truthfully. Do not generate any later step.',review_valid)
    from worker.wuxia_generation_gate import policy
    value['guidance_applied']={'policy_sha256':policy_snapshot['sha256'],'scope':'planned_content_only'}
    value['review']=review
    if not review['passed']:value['quality_notes'].append({'step_review':review})
    return value

def initial(identity, request, notify, applied=None, runner=None):
    workflow={'contract':CONTRACT,'revision':1,'approved_guidance':request.get('_approved_guidance',''),'stages':[{'name':n,'status':'pending'} for n in LABELS]}
    value=generate(0,request,workflow,identity,notify,runner)
    workflow['stages'][0].update(status='review',output=value,output_hash=digest(value),input_hash=digest([]))
    return package(workflow,request,applied)

def state_summary(workflow):
    return {'contract':CONTRACT,'revision':workflow['revision'],'stages':[{'name':s['name'],'status':s['status']} for s in workflow['stages']]}

def register(app, jobs, token=""):
    from fastapi import HTTPException
    from pydantic import BaseModel, Field
    # Module-level annotations allow FastAPI to resolve the model.
    class ManualAction(BaseModel):
        action: str
        step: int = Field(ge=1,le=4)
        expected_hash: str = Field(min_length=64,max_length=64)
        output: dict | None = None
        feedback: str = Field(default='',max_length=12000)
    globals()['ManualAction']=ManualAction
    def persist(identity, candidate, **fields):
        write(jobs.root/identity/'candidate.json',candidate)
        if jobs.rows[identity].get('sync_status')=='pending':
            # Continue an existing durable local draft during a known outage.
            # Retain the last cloud CAS revision and visible pending-sync status.
            jobs.rows[identity].update(candidate_hash=digest(candidate),manual_workflow=state_summary(candidate['manual_workflow']),updated_at=time.time(),**fields)
            write(jobs.root/identity/'job.json',jobs.rows[identity])
            return
        jobs.update(identity,candidate_hash=digest(candidate),manual_workflow=state_summary(candidate['manual_workflow']),**fields)
        if jobs.store and jobs.rows[identity].get('sync_status')!='synced':jobs.sync(identity,required=True)
    from worker.script_scene_prompts import register as register_scene_prompts
    register_scene_prompts(app,jobs,persist,token)
    from worker.wuxia_generation_gate import register as register_quality_routes
    register_quality_routes(app,jobs,persist)
    def run(identity,index,request,candidate):
        workflow=candidate['manual_workflow']
        try:
            value=generate(index,request,workflow,identity,lambda stage:jobs.update(identity,stage=stage))
            with jobs.lock:
                if index==0:
                    for sid,entry in workflow.get('scene_image_prompts',{}).items():
                        current=next((s for s in value['scenes'] if s['scene_id']==sid),None)
                        if current is None or digest(current)!=entry.get('source_hash'):entry['status']='stale'
                step=workflow['stages'][index];step.update(status='review',output=value,output_hash=digest(value),input_hash=digest([s['approved_hash'] for s in workflow['stages'][:index]]));step.pop('error',None)
                persist(identity,package(workflow,request,candidate.get('applied_guidelines')),status='awaiting_approval',stage=f'{index+1}/4 {LABELS[index]} 검토 대기',error='')
        except Exception as exc:
            with jobs.lock:
                workflow['stages'][index].update(status='failed',error=type(exc).__name__)
                persist(identity,package(workflow,request,candidate.get('applied_guidelines')),status='failed',stage=f'{index+1}/4 {LABELS[index]} 실행 실패 · 해당 단계 재시도 가능',error='실행 결과를 확정하지 않았습니다. 저장된 이전 결과와 검토 메모를 확인하세요.')
        finally:
            with jobs.lock:jobs.inflight.discard(identity)
    @app.post('/api/jobs/{identity}/manual-stage')
    def action(identity:str,body:ManualAction):
        try:
            with jobs.lock:
                bundle=jobs.load(identity);job=bundle['job'];candidate=copy.deepcopy(bundle['candidate']);workflow=candidate.get('manual_workflow')
                if job.get('worker_id')!=jobs.worker_id:raise ValueError('이 작업을 생성한 컴퓨터의 대본워커에서 진행하세요.')
                if not workflow or workflow.get('contract')!=CONTRACT:raise ValueError('단계별 수동 작업이 아닙니다.')
                if job.get('published') or job.get('status') in ('canceled','cancelled'):raise ValueError('종료된 작업은 변경할 수 없습니다.')
                if jobs.busy():raise ValueError('현재 실행 중인 작업이 끝난 뒤 진행하세요.')
                if digest(candidate)!=body.expected_hash:raise ValueError('결과 버전이 변경됐습니다. 다시 열어 확인하세요.')
                index=body.step-1;step=workflow['stages'][index]
                if any(s['status']!='approved' for s in workflow['stages'][:index]):raise ValueError('앞 단계를 먼저 확인·확정하세요.')
                if body.action not in ('save','approve','generate'):raise ValueError('지원하지 않는 작업입니다.')
                if body.action in ('save','approve') and step['status'] not in ('review','approved'):raise ValueError('생성된 최신 결과를 먼저 확인하세요.')
                if body.action=='save':
                    validate(index,body.output,workflow)
                    changed=step.get('output')!=body.output
                    if not changed:return {'status':job['status'],'candidate_hash':digest(candidate)}
                    write(jobs.root/identity/'manual-history'/f'{workflow["revision"]}-step-{index+1}.json',step)
                    for scene in body.output.get('scenes',[]):
                        entry=workflow.get('scene_image_prompts',{}).get(scene['scene_id'])
                        if entry and entry.get('source_hash')!=digest(scene):entry['status']='stale'
                    body.output['review']={'status':'user_edited','passed':None,'issues':[],'evidence':'사용자 수정본입니다. 이전 자동 검토는 수정 전 버전에 한정됩니다.'}
                    step.update(status='review',output=body.output,output_hash=digest(body.output));step.pop('approved_hash',None)
                elif body.action=='approve':
                    validate(index,step['output'],workflow)
                    if step.get('input_hash')!=digest([s['approved_hash'] for s in workflow['stages'][:index]]):raise ValueError('앞 단계가 변경됐습니다. 이 단계를 다시 생성하세요.')
                    step.update(status='approved',approved_hash=digest(step['output']),approved_at=time.time())
                else:
                    if step.get('output'):
                        write(jobs.root/identity/'manual-history'/f'{workflow["revision"]}-step-{index+1}.json',step)
                    step['status']='running';step.pop('approved_hash',None);workflow['feedback']=body.feedback
                if body.action!='approve':
                    for later in workflow['stages'][index+1:]:
                        later['status']='stale' if later.get('output') else 'pending';later.pop('approved_hash',None)
                workflow['revision']+=1
                result=package(workflow,bundle['request'],candidate.get('applied_guidelines'))
                complete=all(s['status']=='approved' for s in workflow['stages'])
                persist(identity,result,status='running' if body.action=='generate' else 'completed' if complete else 'awaiting_approval',stage=f'{index+1}/4 {LABELS[index]} '+('생성 대기' if body.action=='generate' else '확정 · 다음 단계 수동 시작' if not complete and body.action=='approve' else '수정 저장 · 검토 대기' if body.action=='save' else '확정 · 지침 작성 완료'),error='')
                if body.action=='generate':
                    jobs.inflight.add(identity);jobs.pool.submit(run,identity,index,bundle['request'],result)
                return {'status':jobs.rows[identity]['status'],'candidate_hash':digest(result)}
        except (ValueError,KeyError,TypeError) as exc:raise HTTPException(409,str(exc))
        except StoreUnavailable as exc:
            # A durable reservation failure must never launch a CLI or leave a
            # phantom running row blocking every local job.
            if body.action=='generate' and identity in jobs.rows and identity not in jobs.inflight:
                jobs.rows[identity].update(status='failed',stage='단계 시작 전 Database 저장 지연 · 재동기화 필요')
                write(jobs.root/identity/'job.json',jobs.rows[identity])
            raise HTTPException(502,str(exc))
