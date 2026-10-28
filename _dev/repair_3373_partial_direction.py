import sys,json,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'worker'),str(ROOT)]
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
import ae_highlight_worker as ae
from ae_mouth import direction_text
base,headers=ae._supabase();job_id='9824529b-32f6-4513-a39e-678d496522fc'
job=ae._request('GET',base+'/rest/v1/std_project_assets',headers,params={'id':'eq.'+job_id,'select':'*'}).json()[0]
(ROOT/'output/project-recovery-e9233112/before-partial-direction-repair.json').write_text(json.dumps(job,ensure_ascii=False),encoding='utf8')
meta=copy.deepcopy(job['metadata']);result=next(r for r in meta['results'] if r['number']==12)
already_repaired=result.get('status')=='direction_pending' and (result.get('direction_repair') or {}).get('method')=='explicit_verified_tracking_window'
assert already_repaired or result.get('skip_reason')=='automatic_review_failed'
assert already_repaired or 'Tracking for animated speaker' in result.get('diagnostic_error','')
scene=next(s for s in meta['input']['scenes'] if s['number']==12)
speakers=result['tracking']['speakers']
assert speakers[0]['speaker']=='大五郎' and speakers[0]['visible_until_seconds']==1.375
rows=[r for r in meta['input']['subtitles'] if r['scene_number']==12 and r['kind']=='dialogue']
result['direction']=direction_text(speakers,rows,scene['start'])+' 원본 영상은 1배속으로 유지하고 얼굴·입의 이동·크기·회전을 추적하며 마지막 화면에 6% 줌인을 적용합니다.'
for key in ('skip_reason','fallback','diagnostic_error','reason'):result.pop(key,None)
result.update(status='direction_pending',direction_repair={'method':'explicit_verified_tracking_window',
 'source_frame_reviewed':'scene-12/auto_direction/source-1.8269.png',
 'window_end_seconds':1.375,'outside_window':'original video, no synthetic mouth overlay',
 'runtime_guard':'ae_mouth.py mouthVisible uses visible_from_seconds/visible_until_seconds',
 'review_required':True})
meta.pop('worker_token',None)
meta.update(state='direction_pending',phase='auto_direction',auto_pending=True)
saved=ae._request('PATCH',base+'/rest/v1/std_project_assets',{**headers,'Prefer':'return=representation'},
 params={'id':'eq.'+job_id,'updated_at':'eq.'+job['updated_at']},json={'metadata':meta,'updated_at':ae._now()}).json()
assert len(saved)==1,'Job changed; no repair applied'
print(json.dumps({'scene':12,'direction_repaired':True,'approved':False}),flush=True)
