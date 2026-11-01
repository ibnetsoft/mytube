"""Prepare source-bound review translations, restrained camera directions and music briefs."""
import copy,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/pawnshop-series/episode-01/production'
DOC=ROOT/'docs/pawnshop-series/episode-01'
payload=json.loads((OUT.parent/'topic-registration-payload.json').read_text())
structure=copy.deepcopy(payload['pregenerated_structure'])
translations={lang:json.loads((OUT/f'scene-review-translations-{lang}.json').read_text()) for lang in ['ko','th']}
for lang,data in translations.items():
 assert data['source']=='local_codex_cli' and len(data['blocks'])==144
 for scene,row in zip(structure['scenes'],data['blocks']):
  assert row['index']==scene['scene_number'] and row['source_text']==scene['scene_text']
  assert row['source_sha256']==hashlib.sha256(scene['scene_text'].encode()).hexdigest()
lines=['# 전당포 1화 검토용 번역','', '로컬 Codex CLI로 생성한 씬 검토용 번역입니다. 실제 녹음 타이밍 자막과 구분합니다.','']
for i,scene in enumerate(structure['scenes']):
 lines.extend([f"## Scene {scene['scene_number']}",'',f"JA: {scene['scene_text']}",'',f"KO: {translations['ko']['blocks'][i]['translated_text']}",'',f"TH: {translations['th']['blocks'][i]['translated_text']}",''])
(DOC/'EPISODE_01_REVIEW_KO_TH.md').write_text('\n'.join(lines))
movements={55:('push',.5,.5,'青いノートの食い違う記録へ注意を集める。'),64:('pan',.47,.5,'役所の入口へ視線を導く。人物自体は動かさない。'),75:('push',.52,.53,'修正原稿と控えという仕事の証拠に寄る。'),80:('pan',.48,.5,'奈緒の独立した仕事と鞄へ視点を移す。'),101:('push',.49,.48,'記憶が途切れる修司の顔に短く寄って止める。'),108:('pan',.48,.5,'信号を見る奈緒と横断歩道の方向を示す。'),116:('pull',.5,.5,'八時を迎えても続く食卓全体へ短く引く。'),123:('push',.5,.55,'家賃と返済を分けた家計の紙に寄る。'),134:('push',.5,.56,'同じ受渡口を通って戻る封筒を示す。'),140:('push',.52,.53,'請け出した時計と今日の記録を示す。'),144:('pull',.5,.5,'二人分の靴と閉じた玄関を静かに残す。')}
def pose(t,x=.5,y=.5,scale=1):return dict(t=t,x=x,y=y,scale=scale,rotation=0,opacity=100)
def clean(value,n):
 if isinstance(value,list):return [clean(x,n) for x in value]
 if not isinstance(value,dict):return value
 result={k:clean(v,n) for k,v in value.items()}
 if result.get('camera')=='slow_push_in':result['camera']='hold'
 if n>=51 and result.get('contract')=='speech_bubble_presets/v1':result['cues']=[]
 if n>=51 and 'scene_role' in result:result['scene_role']='narration'
 return result
for i,original in enumerate(structure['scenes']):
 n=original['scene_number'];scene=clean(original,n);structure['scenes'][i]=scene
 duration=float(scene.get('duration_seconds') or scene.get('target_duration') or 18)
 camera={'kind':'hold','reason':'原画とナレーションの状況を保持する。','reversal_reason':None,'keys':[pose(0),pose(1)]}
 if n in movements:
  kind,x,y,reason=movements[n];a=min(.2,2/duration);b=min(.9,a+3/duration)
  start=pose(0,scale=1.08 if kind=='pull' else 1);end=pose(1,x,y,1 if kind=='pull' else 1.08 if kind=='push' else 1)
  camera={'kind':kind,'reason':reason,'reversal_reason':None,'keys':[start,{**start,'t':a},{**end,'t':b},end],'movement_seconds':3,'speed_policy':'no_slow_zoom/v1','timing_status':'provisional_until_recorded_audio'}
 design=copy.deepcopy(scene.get('execution_design') or scene.get('ae_directorial_plan',{}).get('execution_design') or {})
 design.update(camera=camera,cue={'quote':scene['scene_text'] if n in movements else '', 'phase':'during'},source_review='actual_files_with_quality_notes_not_blanket_approval',timing_review='pending_final_recording')
 design.setdefault('effects',[]);design.setdefault('transition',{'kind':'cut','reason':'状況・段落の変化で切り替える。','duration_seconds':0})
 design['graphics']={'speech_bubbles':False,'speedlines':False,'reason':'実写調の間接話法。追加の漫画記号は使わない。'}
 scene['execution_design']=copy.deepcopy(design)
 for key in ['ae_directorial_plan','scene_direction_plan']:
  if isinstance(scene.get(key),dict):
   scene[key]['execution_design']=copy.deepcopy(design)
   scene[key]['primary_effect']=camera['kind']
   if n>=51:scene[key]['scene_role']='narration';scene[key]['speech_bubble_plan']={'contract':'speech_bubble_presets/v1','cues':[]}
 for key in ['ae_motion_plan','ae_effect_plan']:
  if isinstance(scene.get(key),dict):
   scene[key]['execution_design']=copy.deepcopy(design);scene[key]['camera']=camera['kind']
   for nested in ['directorial_plan','scene_direction_plan']:
    if isinstance(scene[key].get(nested),dict):scene[key][nested]=copy.deepcopy(scene.get('scene_direction_plan') or scene.get('ae_directorial_plan'))
 if 19<=n<=50:
  scene['layer_delivery_policy']={'independent_png_planes_required':True,'psd_package_required':True,'review_policy':'quality_notes_do_not_block_production','actual_file_checks_required':True}
  scene['ae_layer_direction']={'camera':'hold','depth':'separate background, character and foreground planes; restrained short common-axis depth movement only when source supports it','max_layer_move_ratio':.012,'movement_window_seconds':3,'holds_before_after':True,'mouth_effect':{'enabled':n==42,'speaker':'高瀬修司' if n==42 else None,'text':'そうでしたか' if n==42 else '', 'timing_status':'bind_to_actual_dialogue_recording' if n==42 else 'indirect_narration_no_lip_sync'},'do_not_invent_body_action':True,'actual_render_reviewed':False}
 if n==71:
  scene['scene_situation']='三日目、到着駅の改札脇。奈緒が地図を確認し、修司は少し離れて待つ。'
  scene['has_character_dialogue']=False;scene['dialogue_spans']=[]
structure['scene_review_translations']=translations
for key,scene_key in [('scene_direction_plans','scene_direction_plan'),('ae_effect_plans','ae_effect_plan'),('ae_motion_plans','ae_motion_plan')]:
 existing=structure.get(key)
 if isinstance(existing,list):structure[key]=[copy.deepcopy(s[scene_key]) for s in structure['scenes'] if isinstance(s.get(scene_key),dict)]
music=[(1,8,'質屋と取引','Sparse low cello harmonics, muted felt piano, distant clock-like wooden pulses, dark contemporary Japanese supernatural drama, understated uncertainty, 68 BPM, instrumental, no voices, no jump scares.'),(9,33,'知らない娘の最初の夜','Fragile felt piano fragments and low air-like strings, restrained domestic unease with quiet warmth, 64 BPM, no melodic resolution, instrumental, no voices; leave space for narration and tea-room silence.'),(34,50,'日常へ入る変化','Soft pizzicato bass and muted piano with thin sustained strings, ordinary morning carrying subtle uncertainty, 72 BPM, instrumental, small dynamics, no comedy accents or fantasy spectacle.'),(51,80,'二人の記録と仕事','Intimate piano, brushed low strings and sparse marimba, patient investigative human drama, 70 BPM, instrumental, restrained forward momentum; thin the arrangement during train reflection and administrative dialogue.'),(81,108,'選択と引き換え','Low bowed strings under a simple unresolved piano motif, rising emotional stakes without heroic triumph, 74 BPM, instrumental, gentle tension and meaningful rests, no percussion climax.'),(109,122,'八時を越える食卓','Very sparse sustained room-like tones and soft felt piano, brief musical silence around the eight-o-clock clock strike, return quietly after cup contact, instrumental; exact alignment follows final recorded subtitle cue.'),(123,144,'返済と新しい日々','Warm restrained piano and soft chamber strings with an unresolved final interval, intimate contemporary domestic drama, 66 BPM, instrumental, no triumphant moral ending; fade beneath the final two cup sounds.')]
structure['bgm_plan']={'kind':'music_generation_prompts_not_generated_audio','actual_audio_generated':False,'timing_review':'pending_final_recording','cues':[dict(start_scene=a,end_scene=b,title=t,prompt=p) for a,b,t,p in music],'mix_notes':'Narration first; avoid repetitive full-volume beds. Exact gain/crossfade windows require final audio; preserve existing SFX.'}
structure['production_completion_policy']={'quality_findings':'record_separately_continue_existing_source_and_saved_direction','technical_failures':'recover_with_backoff_preserve_assets','publishing_and_youtube_upload':'separate_not_authorized_by_production_completion'}
assert len(structure['scenes'])==144
assert 'slow_push_in' not in json.dumps(structure)
(OUT/'production-structure-with-defaults.json').write_text(json.dumps(structure,ensure_ascii=False,indent=2))
print('Prepared 144 source-bound KO+TH translations, 11 short camera moves with holds, 32 layered direction briefs, and 7 BGM prompts. Audio/render approval remains pending.')
