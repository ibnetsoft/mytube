"""Continue episode 3 without regenerating final narration or claiming rendered media."""
import copy, hashlib, json, os, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'worker/connection.env',override=False)
from worker.codex_content_runner import CodexStagedContentRunner
from worker.generation_validation import validated_stage
from services.image_grid_prompts import build_compact_image_grid_prompts, grid_windows, validate_scene_image_prompt_readiness, validate_image_grid_prompt_readiness
JOB='8b6c78f054e445148286e8ad0c661610';BASE=ROOT/'output/codex-local-console'/JOB;OUT=ROOT/'output/pawnshop-series/episode-03'
STYLE='Photorealistic contemporary Japanese noir, modern Japan November 2026, realistic anatomy, subdued warm amber practical lighting, petroleum-teal shadows, fine film grain. No anime, no Edo costumes. No baked text, logos or watermarks.'
def save(name,obj):
 p=OUT/name;t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(obj,ensure_ascii=False,indent=2));t.replace(p)
def status(stage,**kw):save('continue-status.json',{'stage':stage,'updated_at':time.time(),**kw});print(stage,flush=True)
def main():
 c=json.loads((BASE/'candidate.json').read_text());s=copy.deepcopy(c['structure']);scenes=s['scenes'];script=c['script']
 assert len(scenes)==144 and abs(sum(x['duration_seconds'] for x in scenes)-2100)<.01
 assert '\n\n'.join(x.get('scene_text') or x.get('narration') or '' for x in scenes)==script
 original_sha=hashlib.sha256((BASE/'candidate.json').read_bytes()).hexdigest()
 review=c.get('script_quality_report') or {};assert review.get('verdict')=='pass'
 save('source-validation.json',{'candidate_sha256':original_sha,'script_sha256':hashlib.sha256(script.encode()).hexdigest(),'scenes':144,'duration_seconds':2100,'recorded_review':review,'manual_notes':['Cash ledger: 18000+30000=48000 rent; camera sale42000 minus redemption30600 leaves11400.','Seven nights Nov2..8; redemption Nov9. Mother hospitalized Feb17 2024, died Feb18; house demolished Sept2025.','No living apparition of mother; telephone voice only. Existing proprietor and cat references retained.','Actual audio length, scene image quality, rendering and publishing remain separate.']})
 runner=CodexStagedContentRunner();cast=s['character_anchors'];census={x['scene_number']:x['characters'] for x in s['scene_cast']}
 for start in range(0,len(scenes),24):
  selected=scenes[start:start+24];ids=[x['scene_number'] for x in selected];status('scene prompts',first=ids[0],last=ids[-1])
  cache=OUT/f'visual-prompts-{ids[0]:03d}-{ids[-1]:03d}.json'
  def validate(raw):
   rows=raw.get('scenes');assert isinstance(rows,list) and [x.get('scene_number') for x in rows]==ids
   for row in rows:
    assert isinstance(row.get('image_prompt'),str) and len(row['image_prompt'])>=160
    assert row.get('characters')==census[row['scene_number']]
  if cache.exists():raw=json.loads(cache.read_text());validate(raw)
  else:
   context={'final_script':script,'selected_scenes':[{k:x.get(k) for k in ('scene_number','scene_text','scene_summary','scene_situation','scene_emotion','scene_purpose')} for x in selected], 'scene_cast':{str(n):census[n] for n in ids},'characters':cast,'style':STYLE,'series_notes':(BASE/'request.json').read_text()}
   task='Create ONLY original still-image prompts for the exact supplied selected_scenes. Return JSON {scenes:[{scene_number:int,image_prompt:"detailed English 180+ character image prompt",characters:[exact scene_cast names]}]}. Preserve narration, dates, money and object custody. Name the location, exact present people and their matching appearance/wardrobe, concrete action, framing and lighting. Some cast entries include hands or face-absent shots: follow narration and do not invent a face. No living mother in present; phone voice is not an apparition. Pawnshop fixed barred service window/lower sliding hatch, proprietor inside and customer outside. The inherited silver radio-cassette player has blue repair thread on handle and stays in pawnshop locked shelf until Nov9 redemption; do not place it in rented room before redemption. Include current modern technology not period fiction. A single 16:9 image per row, no panels/collage/split screen, no readable text/phone UI/captions/logos. Do not generate AE layers or media files. Do not rewrite narration. Preserve reference character identities.'
   raw=validated_stage(lambda n,ctx,t:runner._stage('episode03-'+JOB,n,ctx,t),f'03p_still_prompts_{ids[0]:03d}_{ids[-1]:03d}',context,task,validate)
   save(cache.name,raw)
  for scene,row in zip(selected,raw['scenes']):
   scene.update(image_prompt=STYLE+' '+row['image_prompt'],media_prompt_status='ready',visual_type='image',video_prompt_required=False)
   scene.pop('video_prompt',None)
 grids=[]
 for i,(first,last) in enumerate(grid_windows(len(scenes)),1):
  rows=scenes[first:last]
  grids.append({'grid_number':i,'scene_numbers':[x['scene_number'] for x in rows],'shared_style':STYLE,'panels':[{'scene_number':x['scene_number'],'scene_id':x.get('scene_id') or f'scene{x["scene_number"]:03d}','panel_prompt':x['image_prompt']} for x in rows]})
 grids=build_compact_image_grid_prompts(grids)
 validate_scene_image_prompt_readiness(scenes);validate_image_grid_prompt_readiness(scenes,grids,status='ready',require_status='ready',require_compact_template=True)
 s.update(image_grid_prompts=grids,image_grid_prompt_status='ready',image_grid_prompt_mode='direct_2x2_only',media_prompt_status='ready',layer_production_stage='post_submission',effect_scene_range=None,image_layer_scene_range=None)
 final=copy.deepcopy(c);final['structure']=s;save('prepared-candidate.json',final)
 save('scene-image-jobs.json',{'schema':'episode03-prepared-stills/v1','script_sha256':hashlib.sha256(script.encode()).hexdigest(),'jobs':grids,'actual_scene_images':0})
 (OUT/'EPISODE_03_SCENES_JA.md').write_text('\n\n'.join(f'## {x["scene_number"]}\n\n{x["scene_text"]}\n\n{x["image_prompt"]}' for x in scenes))
 notes=['# 3화 제작 품질 기록','','- 일본어 대본10664자,144씬.35분은 계획값이며 실제음성길이는 미측정.','- 원래 대본·씬순서·시간·합격 검수 원형 보존. 시각 프롬프트만 추가.','- 새 기본값 유지: 영상0씬, 고정효과구간없음, 제출 후 AE레이어.','- 대본단계 재사용안은 저장된 선택을 유지. 캐릭터 키/참고이미지는 후속 이미지 제작에서 고정.','- 실제 씬이미지·음성·AE렌더·관리자게시·YouTube업로드는 완료되지 않았음.','- 청취 품질: '+str(review.get('score'))+'점, 기존 검수 critical_issues='+str(len(review.get('critical_issues') or []))]
 (OUT/'QUALITY_NOTES.md').write_text('\n'.join(notes)+'\n')
 status('media prompts ready',scenes=len(scenes),grids=len(grids),actual_scene_images=0)
if __name__=='__main__':
 try:main()
 except Exception as exc:status('execution failure',error_type=type(exc).__name__);raise
