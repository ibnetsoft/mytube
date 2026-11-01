"""Repair one post-effect-range direct utterance; preserve all generated assets."""
import copy,hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'worker/connection.env')
from worker.script_worker_store import ScriptStore
from worker.codex_content_runner import CodexStagedContentRunner
OUT=ROOT/'output/pawnshop-series/episode-01';JOB='9a74a481741948aaa8bf4cf8bd27734b';BASE=ROOT/'output/codex-local-console'/JOB
payload=json.loads((OUT/'topic-registration-payload.json').read_text());original=copy.deepcopy(payload);structure=payload['pregenerated_structure'];scenes=structure['scenes'];old=scenes[70]['scene_text'];new=old.replace('昨日まで毎日歩いていた道なのに、と小さく添える。','昨日まで毎日歩いていた道で迷う戸惑いを、声を落として修司に伝える。')
assert old!=new and 78<=len(new)<=140
scenes[70].update(scene_text=new,narration=new,has_character_dialogue=False,dialogue_spans=[])
for scene in scenes:
 n=scene['scene_number']
 if n>50:scene.update(has_character_dialogue=False,dialogue_spans=[])
 if not 19<=n<=50:
  for key in ['scene_direction_plan','ae_directorial_plan']:
   plan=scene.get(key) or {}
   plan['speech_bubble_plan']={'contract':'speech_bubble_presets/v1','cues':[]}
   if (plan.get('execution_design') or {}).get('graphics'):plan['execution_design']['graphics']['speech_bubbles']=False
   if n==71:
    plan.update(scene_role='transition',dramatic_intent='慣れた道で迷う奈緒の戸惑いと、それを待つ修司の距離を間接話法で示す。',qa_assertions=['間接話法のナレーションのみ。18秒は最終録音と照合。','一枚絵を保持。吹き出し・口パクを追加しない。','70・72との駅到着後の状況の連続性を確認。'])
    if plan.get('eye_blink_plan'):plan['eye_blink_plan']['reason']='効果範囲外。間接話法のナレーションのみ。'
    if plan.get('focus_target'):plan['focus_target']['reason']='携帯地図を確認する奈緒と、待つ修司。'
ann=structure['dialogue_annotations']
for row in ann['scenes']:
 n=row['scene_number']
 if n>50:row['spans']=[]
 if n==71:row.update(source_text=new,source_sha256=hashlib.sha256(new.encode()).hexdigest())
remaining=[r for r in ann['scenes'] if r.get('spans')];ann['dialogue_scene_index'].update(scene_numbers=[r['scene_number'] for r in remaining],scene_count=len(remaining),dialogue_count=sum(len(r['spans']) for r in remaining))
for row in structure['audio_performance']['scenes']:
 if row['scene_number']==71:row.update(source_text=new,source_sha256=hashlib.sha256(new.encode()).hexdigest(),cues=[])
for container in [structure,ann]:
 index=container['video_dialogue_postwork_index'];index.update(scene_numbers=[],scene_count=0,dialogue_count=0,scenes=[])
structure['scene_direction_plans']=[dict(s['scene_direction_plan'],scene_number=s['scene_number']) for s in scenes]
script='\n\n'.join(s['scene_text'] for s in scenes);payload['pregenerated_script']=script;sha=hashlib.sha256(script.encode()).hexdigest();payload['progress_payload']['script_sha256']=sha
review=CodexStagedContentRunner()._stage('pawnshop-'+JOB,'02q_final_indirect_review',{'script':script,'scene_texts':[{'scene_number':s['scene_number'],'text':s['scene_text']} for s in scenes],'repair':{'scene_number':71,'before':old,'after':new},'requirements':'Original adult contemporary Japanese supernatural pawnshop story. Indirect narration. Scenes 51-end have no directly performed character dialogue. Transaction initial application/final acceptance, memory irreversibility, object custody, daughter identity/timeline must remain coherent. Alien proprietor/cat hinted; no forced villain. No moral sermon. Previously reviewed story passes; assess actual final text without rubber-stamping.'},'Independently review the supplied complete final Japanese narration and minimal repair. Return JSON {verdict:"pass|repair",critical_issues:[],quality_notes:[],checks:{continuity:{passed:true,evidence_quote:"verbatim"},late_indirect_narration:{passed:true,evidence_quote:"verbatim"},repair_preserves_meaning:{passed:true,evidence_quote:"verbatim"},concrete_ending:{passed:true,evidence_quote:"verbatim"}}}. Every evidence quote must be one continuous exact span in final script. No rewriting or invented approval. Identify actual contradictions rather than taste; actual voice duration remains unmeasured.')
(OUT/'final-indirect-review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2))
assert review['verdict']=='pass' and not review['critical_issues']
assert len(review['checks'])==4 and all(v['passed'] is True and v['evidence_quote'] in script for v in review['checks'].values())
payload['progress_payload']['final_indirect_review']=review
payload['script_quality_report']['post_repair_review']=review
# Image 71 remains the same station/map/waiting tableau; no visual event changed.
assert scenes[70]['image_prompt']==original['pregenerated_structure']['scenes'][70]['image_prompt']
assert all(not (s.get('dialogue_spans') or []) for s in scenes[50:])
store=ScriptStore();receipt=json.loads((OUT/'registration-receipt.json').read_text());topic_id=receipt['topic_id'];rows,_=store.request('GET','topics_queue',params={'select':'status,assigned_employee_email','id':'eq.'+str(topic_id)})
assert rows[0]['status']=='pending' and not rows[0].get('assigned_employee_email')
store.request('PATCH','topics_queue',params={'id':'eq.'+str(topic_id),'status':'eq.pending','assigned_employee_email':'eq.'},body={'pregenerated_script':script,'pregenerated_structure':structure,'progress_payload':payload['progress_payload'],'script_quality_report':payload['script_quality_report']})
rows,_=store.request('GET','topics_queue',params={'select':'pregenerated_script,pregenerated_structure,progress_payload','id':'eq.'+str(topic_id)})
assert rows[0]['pregenerated_script']==script and rows[0]['pregenerated_structure']==structure and rows[0]['progress_payload']['script_sha256']==sha
bundle=store.get(JOB);bundle['candidate'].update(script=script,structure=structure,script_quality_report=payload['script_quality_report']);bundle['job'].update(candidate_hash=hashlib.sha256(json.dumps(bundle['candidate'],ensure_ascii=False,sort_keys=True).encode()).hexdigest(),updated_at=time.time());revision=store.save(bundle);bundle['job']['storage_revision']=revision
(BASE/'candidate.json').write_text(json.dumps(bundle['candidate'],ensure_ascii=False,indent=2));(BASE/'job.json').write_text(json.dumps(bundle['job'],ensure_ascii=False,indent=2))
(OUT/'topic-registration-payload.before-indirect-repair.json').write_text(json.dumps(original,ensure_ascii=False,indent=2));(OUT/'topic-registration-payload.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2));receipt.update(script_chars=len(script),script_sha256=sha,final_indirect_review='pass');(OUT/'registration-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
for folder in [OUT,ROOT/'docs/pawnshop-series/episode-01']:
 (folder/'EPISODE_01_JA.md').write_text('# '+payload['topic']+'\n\n'+script+'\n')
 p=folder/'EPISODE_01_SCENES_JA.md';p.write_text(p.read_text().replace(old,new))
 p=folder/'QUALITY_NOTES.md';text=p.read_text();text=text.replace(str(len(original['pregenerated_script']))+'자',str(len(script))+'자').replace(hashlib.sha256(original['pregenerated_script'].encode()).hexdigest(),sha);text+='\n- 최종 화법 보정: 71씬의 발화를 간접화법으로 변경. 51씬 이후 직접 발화 주석 및 효과 범위 밖 말풍선 제거. 71씬 음성 지시문과 대사 지문 갱신. 실제 음성 없음.\n- 수정된 전체 본문을 로컬 Codex CLI로 재검수하여 통과. 이미지/레이어 지시문 재사용, 음향 배치 씬은 변경 없음.\n';p.write_text(text)
print(json.dumps({'topic_id':topic_id,'chars':len(script),'review':'pass','readback_verified':True,'sha256':sha}))
