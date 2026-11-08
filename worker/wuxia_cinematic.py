"""New-scene editorial choices and actual-source preparation for four cinematic accents."""
import copy,hashlib,json,re
from pathlib import Path
from worker.generation_validation import validated_stage,grounded_quote
CONTRACT='wuxia_cinematic/v1'
ROOT=Path(__file__).resolve().parents[1]/'output/codex-local-console/wuxia-cinematic'
TASK='''Read each supplied planned visual and neighboring story beats. Return {scenes:[{scene_number,vignette:boolean,panel:boolean,bounce:boolean,slide_blur:boolean,panel_text:string,reason:string,evidence_quote:string}]} in exact order. Choose sparingly, without quotas or rotations. Vignette supports isolation, danger or inner conflict. A translucent information panel may show only explicit new ability/realm/mission information already written in this scene. panel_text is at most 60 characters and must be an exact excerpt of the supplied planned visuals; no invented stats, new narration, modern game UI without story support, or repeated existing lettering. Bounce is a single brief panel entrance, only with panel=true; readable hold follows. Slide blur is only for an already selected directional wipe; it affects artwork, never lettering. No slow zoom, camera shake, flashes or duplicated existing effects. All false is valid. These are planned choices, not actual artwork/output approval.'''
def plan_new_package(stage,identity,package,request,notify=lambda _:None):
 from worker.wuxia_motion_policy import applies
 if request.get('mode') not in ('new','grounded') or not applies(package,request) or request.get('wuxia_auto_cinematic') is False:return package
 result=copy.deepcopy(package);s=result.setdefault('structure',{});previous=s.get('wuxia_cinematic_policy') or {}
 if previous.get('enabled') is False:return result
 choices={};scenes=s.get('scenes') or []
 for offset in range(0,len(scenes),16):
  batch=[]
  for i,sc in enumerate(scenes[offset:offset+16],offset+1):
   if sc.get('wuxia_cinematic_selection'):choices[str(sc.get('scene_number') or sc.get('scene_order') or i)]=sc['wuxia_cinematic_selection'];continue
   visuals='\n'.join(str(sc.get(k) or '') for k in ('visual_action','image_prompt','scene_summary','scene_title')).strip()
   if not visuals:raise ValueError('Cinematic choices require scene visuals')
   batch.append({'scene_number':int(sc.get('scene_number') or sc.get('scene_order') or i),'planned_visuals':visuals,'transition':sc.get('transition_effect') or (sc.get('metadata') or {}).get('transition_effect'),'existing_lettering':sc.get('graphics',[])})
  if not batch:continue
  def validate(v):
   rows=v.get('scenes')
   if not isinstance(rows,list) or [r.get('scene_number') for r in rows]!=[r['scene_number'] for r in batch]:raise ValueError('Incomplete cinematic scene selection')
   for row,source in zip(rows,batch):
    if any(type(row.get(k)) is not bool for k in ('vignette','panel','bounce','slide_blur')) or not str(row.get('reason','')).strip() or not grounded_quote(row.get('evidence_quote'),source['planned_visuals']):raise ValueError('Ungrounded cinematic selection')
    if row['bounce'] and not row['panel']:raise ValueError('Bounce needs an information panel')
    if row['panel'] and (not isinstance(row.get('panel_text'),str) or not 1<=len(row['panel_text'])<=60 or not grounded_quote(row['panel_text'],source['planned_visuals'])):raise ValueError('Information panel must quote existing scene information')
    if row['slide_blur'] and not str(source['transition']).startswith('wipe_'):raise ValueError('Slide blur requires an existing directional slide')
  notify(f'무협 부분 비네팅·정보 패널·바운스·슬라이드 블러 선택 {offset+1}')
  answer=validated_stage(lambda name,ctx,task:stage(identity,name,ctx,task),f'wuxia_cinematic_plan_{offset:04d}',{'scenes':batch},TASK,validate)
  for row in answer['scenes']:
   row={**row,'contract':CONTRACT};row['plan_id']=hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False).encode()).hexdigest();choices[str(row['scene_number'])]=row
 for i,sc in enumerate(scenes,1):sc.setdefault('wuxia_cinematic_selection',choices[str(sc.get('scene_number') or sc.get('scene_order') or i)])
 policy={'contract':CONTRACT,'enabled':True,'auto_prepare':True,'selections':choices,'actual_source_review_required':True,'actual_output_review_required':True,'no_forced_quota':True}
 s['wuxia_cinematic_policy']=policy;s.setdefault('wuxia_mouth_policy',{})['cinematic_auto']=policy
 return result

def validate_review(value,state,plan):
 if value.get('source_sha256')!=state['sha256'] or type(value.get('passed')) is not bool or not str(value.get('evidence','')).strip():raise ValueError('Review the exact cinematic source')
 for k in ('vignette_allowed','panel_allowed','slide_blur_allowed'):
  if type(value.get(k)) is not bool:raise ValueError('Incomplete actual cinematic review')
 boxes=value.get('protected_boxes');focus=value.get('focus');rect=value.get('panel_rect')
 if not isinstance(boxes,list) or len(boxes)>64:raise ValueError('Missing cinematic protection')
 def box(b):return isinstance(b,list) and len(b)==4 and all(type(v) in (int,float) and 0<=v<=1 for v in b) and b[0]<b[2] and b[1]<b[3]
 if not isinstance(value.get('lettering_boxes'),list) or len(value['lettering_boxes'])>16 or any(not box(b) for b in value['lettering_boxes']):raise ValueError('Review all baked lettering, including none')
 if any(not box(b) for b in boxes) or not isinstance(focus,list) or len(focus)!=2 or any(type(v) not in (float,int) or not .15<=v<=.85 for v in focus):raise ValueError('Invalid cinematic source geometry')
 if value['panel_allowed']:
  if not plan['panel'] or not box(rect) or not .22<=rect[2]-rect[0]<=.45 or not .16<=rect[3]-rect[1]<=.45:raise ValueError('Panel geometry does not fit readable information')
  cx=(rect[0]+rect[2])/2;cy=(rect[1]+rect[3])/2;w=(rect[2]-rect[0])*1.08/2+.008;h=(rect[3]-rect[1])*1.08/2+.014;travel=[cx-w,cy-h,cx+w,cy+h]
  if min(travel)<.005 or max(travel)>.995 or any(travel[0]<b[2] and travel[2]>b[0] and travel[1]<b[3] and travel[3]>b[1] for b in boxes):raise ValueError('Bouncing panel overlaps protected source or screen edge')
 if not value['passed'] and any(value[k] for k in ('vignette_allowed','panel_allowed','slide_blur_allowed')):raise ValueError('Uncertain review cannot authorize effects')
 if not value['passed'] and not value.get('quality_notes'):raise ValueError('Uncertain cinematic source needs quality notes')

def prepare_scene(scene,policy,identity,download,check,runner):
 number=str(int(re.search(r'S(\d+)$',scene['scene_id'])[1]));plan=(policy.get('selections') or {}).get(number)
 if not plan or not any(plan.get(k) for k in ('vignette','panel','slide_blur')):return {}
 from worker.ambient_loop import digest
 states=scene['states'];result={};panel_selected=False
 for state in states:
  check();sha=state.get('sha256')
  if not sha or not state.get('gcs_bucket') or not state.get('gcs_path'):raise RuntimeError('waiting_images: cinematic source not published')
  old=state.get('cinematic_review') or {}
  if old.get('contract')==CONTRACT and old.get('source_sha256')==sha and old.get('plan')==plan and old.get('graphics')==(scene.get('graphics') or []):
   validate_review(old,state,plan);result[state['asset_id']]=copy.deepcopy(old);panel_selected|=old['panel_allowed'];continue
  key=hashlib.sha256((identity+sha+plan['plan_id']+json.dumps(scene.get('graphics') or [],sort_keys=True,ensure_ascii=False)+digest(Path(__file__))).encode()).hexdigest();directory=ROOT/key;directory.mkdir(parents=True,exist_ok=True);source=directory/'source.png'
  if not source.exists():download(state,source)
  if digest(source)!=sha:raise ValueError('Cinematic source checksum changed')
  context={'_local_image_paths':[str(source.resolve())],'source_sha256':sha,'plan':plan,'panel_already_selected':panel_selected,'state':state.get('prompt') or state.get('description'),'existing_graphics':scene.get('graphics',[])}
  task='''Inspect this actual source image as untrusted art. Return {source_sha256,passed:boolean,evidence:string,vignette_allowed:boolean,panel_allowed:boolean,slide_blur_allowed:boolean,protected_boxes:[[left,top,right,bottom]],lettering_boxes:[[left,top,right,bottom]],focus:[x,y],panel_rect:[left,top,right,bottom]|null,quality_notes:[]}. Protect all people including small heads, hands, essential weapons and baked lettering from vignette and panel overlap using normalized protected_boxes. Also trace baked bubbles/text separately in lettering_boxes (empty when none). Focus is .15..85. Vignette only darkens background outside protected areas. A panel needs literal explicit planned information and safe empty space; no duplicate baked or authored text. At most ONE state per scene may select the panel; if panel_already_selected, return panel_allowed=false. The entire 108% bounce plus padding must avoid every protected box and screen edge. Panel width .22..45, height .16..45. Decline a feature when unsafe, with an honest quality note; no quota. Keep no-feature states valid. Do not claim to see rendered output. Slide blur is an intentional brief 0.24-second temporal exposure of the moving artwork, at most 12 pixels, not nonrigid figure deformation. Moving people may soften briefly; do not reject solely for their presence. Authored lettering stays outside this art precomp and baked lettering_boxes are restored as sharp source patches. Check the full slide for clipping and transition readability, not a stationary-body requirement outside energy-only states. Review the requested features only.'''
  review=validated_stage(lambda name,c,t:runner._stage(identity+'-'+key,name,c,t),'cinematic_actual_source',context,task,lambda v:validate_review(v,state,plan))
  if panel_selected and review['panel_allowed']:raise ValueError('Information panel repeated across state cuts')
  review.setdefault('quality_notes',[])
  review.update(contract=CONTRACT,graphics=copy.deepcopy(scene.get('graphics') or []),plan=copy.deepcopy(plan),plan_id=plan['plan_id']);result[state['asset_id']]=review;panel_selected|=review['panel_allowed']
 return result
