"""Verify all native basic images and prepare an evidence-bounded asset delivery."""
import hashlib,json,pathlib,shutil,sys,time,zipfile
from PIL import Image
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'worker/connection.env',override=False)
from worker.script_worker_store import ScriptStore
OUT=ROOT/'output/pawnshop-series/episode-03';DOC=ROOT/'docs/pawnshop-series/episode-03';JOB='8b6c78f054e445148286e8ad0c661610';BASE=ROOT/'output/codex-local-console'/JOB
store=ScriptStore()
def save(name,value):
 p=OUT/name;t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(value,ensure_ascii=False,indent=2));t.replace(p)
def status(stage,**kw):save('delivery-status.json',{'stage':stage,'updated_at':time.time(),**kw});print(stage,flush=True)
def main():
 status('waiting for all 144 reviewed basic scenes')
 while not (OUT/'scene-image-publication.json').exists():time.sleep(15)
 publication=json.loads((OUT/'scene-image-publication.json').read_text());topic=str(publication['topic_id']);assets=[a for g in publication['grids'] for a in g['scenes']]
 assert sorted(a['scene_number'] for a in assets)==list(range(1,145))
 reviews=[]
 for n in range(1,37):
  path=OUT/f'scene-images/raw/grid-{n:03d}.png';review=json.loads((OUT/f'scene-images/raw/grid-{n:03d}-review.json').read_text());assert review['visual_inspected'] is True and hashlib.sha256(path.read_bytes()).hexdigest()==review['sha256'];reviews.append(review)
 for a in assets:
  p=OUT/f'scene-images/scenes/scene-{a["scene_number"]:03d}.png';assert hashlib.sha256(p.read_bytes()).hexdigest()==a['sha256'];assert a['storage_readback_verified'] is True
  with Image.open(p) as im:assert im.size==(1920,1080) and im.format=='PNG';im.verify()
 status('final database readback')
 rows,_=store.request('GET','topics_queue',params={'select':'id,status,language,pregenerated_script,pregenerated_structure,progress_payload,publish_metadata','id':'eq.'+topic});assert len(rows)==1;row=rows[0]
 script_sha=hashlib.sha256(row['pregenerated_script'].encode()).hexdigest();assert script_sha==json.loads((OUT/'registration-receipt.json').read_text())['script_sha256']
 scenes=row['pregenerated_structure']['scenes'];assert len(scenes)==144
 for a in assets:
  saved=next(s for s in scenes if int(s.get('scene_number') or s.get('scene_order'))==a['scene_number'])
  assert saved.get('image_url')==a['url'];assert saved['metadata']['cowork_image_asset']['sha256']==a['sha256']
 save('final-topic-readback.json',row)
 face=json.loads((OUT/'face-review-results.json').read_text());assert face['current_cast'] is False
 save('visual-quality-notes.json',{'all_36_grids_visually_inspected':True,'formal_face_distinctness_passed':False,'face_report':'face-review-results.json','grid_reviews':reviews,'quality_concerns_do_not_block_production':True})
 notes=(OUT/'QUALITY_NOTES.md').read_text().replace('- 실제 씬이미지·음성·AE렌더·관리자게시·YouTube업로드는 완료되지 않았음.','- 기본 씬 이미지144장(1920×1080) 생성·저장·GCS 다운로드 해시·DB 재조회 완료. 음성·AE렌더·관리자게시·YouTube업로드는 미완료.')
 notes+='\n## 최종 이미지 검증\n\n- 144개 고유 씬 번호, 36개 원본 그리드와 실제 육안검사 기록 확인.\n- 모든 최종 PNG1920×1080, 파일 해시 및 GCS 재다운로드 해시, 현재 토픽 이미지 URL·해시 대조 완료.\n- 대본 본문 SHA256: '+script_sha+' (생성 후 본문 변경 없음).\n- 주제 #'+topic+' 유저웹 등록. 본문·씬구조·제목·설명·썸네일 배경 및 미리보기 포함.\n- 썸네일 편집기 최종 Save, 음성·최종 AE 영상, 관리자 게시·YouTube업로드는 별도.\n\n## 씬별 실제 검토 메모\n'
 for r in reviews:
  notes+='\n- 씬 '+str(r['scenes'][0])+'~'+str(r['scenes'][-1])+': '+' / '.join(r.get('quality_notes') or r.get('notes') or [])
 (OUT/'QUALITY_NOTES.md').write_text(notes+'\n');shutil.copy2(OUT/'QUALITY_NOTES.md',DOC/'QUALITY_NOTES.md')
 bundle=store.get(JOB);c=bundle['candidate'];assert c['script']==row['pregenerated_script']
 c['structure']=row['pregenerated_structure'];c['progress_payload']=row['progress_payload'];c['production_ready']=False
 c['remaining']=['TTS 및 실제 음성 길이 확인','제출 후 AE 레이어·최종 렌더','썸네일 편집기 최종 Save','품질 기록: Naoto/Fumiko 얼굴 구별 미통과 및 소품 표현 우려(제작 중단 사유 아님)','관리자 게시·YouTube 업로드는 별도']
 c['basic_scene_images_completed']=True;c['scene_image_count']=144;c['scene_image_publication']=publication
 bundle['job'].update(status='completed',stage='3화 대본·기본 이미지144장·썸네일 준비 및 유저웹 등록 완료',remaining=c['remaining'],updated_at=time.time(),candidate_hash=hashlib.sha256(json.dumps(c,ensure_ascii=False,sort_keys=True).encode()).hexdigest())
 revision=store.save(bundle);bundle['job'].update(storage_revision=revision,sync_status='synced',sync_error='')
 (BASE/'candidate.json').write_text(json.dumps(c,ensure_ascii=False,indent=2));(BASE/'job.json').write_text(json.dumps(bundle['job'],ensure_ascii=False,indent=2))
 save('final-job-receipt.json',bundle['job']);save('final-candidate.json',c)
 status('archiving actual assets')
 names=['EPISODE_03_JA.md','EPISODE_03_SCENES_JA.md','YOUTUBE_PACKAGE_JA.md','QUALITY_NOTES.md','visual-quality-notes.json','source-validation.json','source-integrity-check.json','registration-receipt.json','final-topic-readback.json','final-candidate.json','final-job-receipt.json','scene-image-publication.json','face-review-results.json','thumbnail-art.png','thumbnail-final.png','thumbnail-review.json','character-reference-review.json','character-reference-publication.json']
 files=[OUT/n for n in names]+sorted((OUT/'scene-images/scenes').glob('*.png'))+sorted((OUT/'scene-images/raw').glob('*.png'))+sorted((OUT/'character-references').glob('*.png'))+sorted((OUT/'scene-images/raw').glob('*-review.json'))+sorted((OUT/'scene-images/raw').glob('*-generation.json'))
 sums=[hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(OUT)) for p in files];(OUT/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n');files+=[OUT/'SHA256SUMS.txt']
 target=OUT/'EPISODE_03_ASSETS.zip'
 with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
  for p in files:z.write(p,str(p.relative_to(OUT)))
 with zipfile.ZipFile(target) as z:assert z.testzip() is None
 receipt={'topic_id':topic,'script_chars':len(c['script']),'scene_count':144,'scene_images':144,'scene_dimensions':[1920,1080],'source_grids':36,'script_sha256':script_sha,'zip_path':str(target),'zip_bytes':target.stat().st_size,'zip_integrity_verified':True,'actual_tts_audio':False,'ae_render_completed':False,'youtube_uploaded':False,'quality_report':'QUALITY_NOTES.md','formal_face_distinctness_passed':False}
 save('DELIVERY_RECEIPT.json',receipt);status('basic assets delivered',**receipt)
if __name__=='__main__':
 try:main()
 except Exception as exc:status('execution failure',error_type=type(exc).__name__);raise
