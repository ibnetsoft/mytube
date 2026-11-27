"""Verify and archive the three authorized topic-image deliveries."""
import argparse,hashlib,json,sys,time,zipfile
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'worker/connection.env',override=False)
from worker.script_worker_store import ScriptStore
parser=argparse.ArgumentParser();parser.add_argument('--episode',choices=['06'],required=True);args=parser.parse_args()
OUT=ROOT/('output/pawnshop-series/episode-'+args.episode)/'image-production';store=ScriptStore()
def save(n,v):
    p=OUT/n;t=p.with_suffix('.tmp');t.write_text(json.dumps(v,ensure_ascii=False,indent=2));t.replace(p)
def main():
    while not (OUT/'scene-image-publication.json').exists():time.sleep(15)
    initial=json.loads((OUT/'source-topic.json').read_text());publication=json.loads((OUT/'scene-image-publication.json').read_text());topic=str(initial['id']);count=len(initial['pregenerated_structure']['scenes'])
    assets=[a for g in publication['grids'] for a in g['scenes']]
    assert sorted(a['scene_number'] for a in assets)==list(range(1,count+1))
    for a in assets:
        p=OUT/f"scenes/scene-{a['scene_number']:03d}.png"
        assert hashlib.sha256(p.read_bytes()).hexdigest()==a['sha256'] and a['storage_readback_verified'] is True
        with Image.open(p) as im:assert im.size==(1920,1080);im.verify()
    rows,_=store.request('GET','topics_queue',params={'select':'*','id':'eq.'+topic});row=rows[0]
    assert row['pregenerated_script']==initial['pregenerated_script']
    scenes=row['pregenerated_structure']['scenes'];assert len(scenes)==count
    for a in assets:
        s=next(s for s in scenes if int(s.get('scene_number') or s.get('scene_order'))==a['scene_number'])
        assert s['image_url']==a['url'] and s['metadata']['cowork_image_asset']['sha256']==a['sha256']
    # Guard the progress document by its writer's revision marker; never touch
    # assignment, project payload, subtitles, narration, or user work.
    progress_verified=False
    for attempt in range(5):
        rows,_=store.request('GET','topics_queue',params={'select':'id,status,assigned_employee_email,progress_payload','id':'eq.'+topic});r=rows[0];old=r.get('progress_payload') or {};progress=dict(old)
        params={'id':'eq.'+topic,'status':'eq.'+r['status']}
        if r.get('assigned_employee_email'):params['assigned_employee_email']='eq.'+r['assigned_employee_email']
        if old.get('sync_id'):params['progress_payload->>sync_id']='eq.'+str(old['sync_id'])
        elif old.get('source_script_job_id'):params['progress_payload->>source_script_job_id']='eq.'+str(old['source_script_job_id'])
        elif old.get('local_script_job_id'):params['progress_payload->>local_script_job_id']='eq.'+str(old['local_script_job_id'])
        else:raise AssertionError('Missing progress provenance guard')
        count=old.get('scene_image_count');params['progress_payload->>scene_image_count']='is.null' if count is None else 'eq.'+str(count)
        progress.update(scene_image_count=count,image_generation_status='completed',basic_scene_images_ready=True)
        result,_=store.request('PATCH','topics_queue',params=params,body={'progress_payload':progress},prefer='return=representation')
        if result:
            assert result[0]['progress_payload']['scene_image_count']==count
            progress_verified=True;break
    assert progress_verified
    reviews=[]
    for n in range(1,len(publication['grids'])+1):
        review=json.loads((OUT/f'raw/grid-{n:03d}-review.json').read_text());f=Path(review.get('source_file') or OUT/f'raw/grid-{n:03d}.png')
        assert review['visual_inspected'] is True and hashlib.sha256(f.read_bytes()).hexdigest()==review['sha256'];reviews.append(review)
    global_audits=OUT
    audits=[json.loads(p.read_text()) for p in sorted(global_audits.glob('face-audit-*.json'))]
    save('QUALITY_NOTES.json',{'grid_reviews':reviews,'face_reference_audits':audits,'quality_notes_only':True,'all_visual_quality_approved':False})
    text='# '+args.episode+'화 이미지 검수 기록\n\n- 토픽 #'+topic+' 기본 씬 이미지 '+str(count)+'장, 1920×1080.\n- 내장 image_gen으로 생성. 원본 그리드·수정본·프롬프트·해시와 검토 기록 보존.\n- 전 씬 GCS 재다운로드 해시와 현재 DB 이미지 주소·해시 대조 완료.\n- 대본 본문 및 기존 사용자 작업 보존.\n- 아래 실제 우려 사항은 제작 완료 여부와 별도로 보존하며, 전 항목 미술 승인으로 해석하지 않음.\n'
    for r in reviews:text+='\n- 씬 '+str(r['scenes'][0])+'~'+str(r['scenes'][-1])+': '+' / '.join(r['quality_notes'])
    if audits:text+='\n\n## 인물 비교 기록\n\n실제 저장 참고 이미지와 새 회차 인물의 비교 결과는 QUALITY_NOTES.json의 face_reference_audits에 원문으로 보존. similar/uncertain을 통과로 바꾸지 않음.\n'
    (OUT/'QUALITY_NOTES.md').write_text(text+'\n')
    save('FINAL_READBACK.json',{'topic_id':topic,'script_sha256':hashlib.sha256(row['pregenerated_script'].encode()).hexdigest(),'images':assets,'scene_image_count':count,'image_generation_status':'completed','script_unchanged':True})
    files=sorted((OUT/'scenes').glob('*.png'))+sorted((OUT/'raw').glob('*.png'))+sorted((OUT/'raw').glob('*.json'))+sorted(OUT.glob('cast-sheet-*.png'))+[OUT/'owner-reference.png',OUT/'cat-reference.png',OUT/'scene-image-jobs.json',OUT/'QUALITY_NOTES.md',OUT/'QUALITY_NOTES.json',OUT/'FINAL_READBACK.json',OUT/'scene-image-publication.json']
    extras=sorted(OUT.parent.glob('*.md'))+sorted(OUT.parent.glob('*.json'))+sorted(OUT.parent.glob('thumbnail-*.png'))+sorted((OUT/'characters').glob('*.png'))
    files+=extras
    (OUT/'SHA256SUMS.txt').write_text('\n'.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+(str(p.relative_to(OUT)) if p.is_relative_to(OUT) else 'episode-package/'+p.name) for p in files)+'\n');files.append(OUT/'SHA256SUMS.txt')
    target=OUT/('EPISODE_'+args.episode+'_IMAGES.zip')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for p in files:z.write(p,str(p.relative_to(OUT)) if p.is_relative_to(OUT) else 'episode-package/'+p.name)
    with zipfile.ZipFile(target) as z:assert z.testzip() is None
    save('DELIVERY_RECEIPT.json',{'topic_id':topic,'episode':args.episode,'scene_images':count,'dimensions':[1920,1080],'all_storage_and_database_readbacks_verified':True,'zip_integrity_verified':True,'zip_path':str(target),'zip_bytes':target.stat().st_size,'quality_notes_path':str(OUT/'QUALITY_NOTES.md'),'completed_at':time.time()})
    print('delivered episode',args.episode,'topic',topic,flush=True)
if __name__=='__main__':
    for attempt in range(100):
        try:main();break
        except Exception as error:
            save('delivery-error.json',{'type':type(error).__name__,'message':str(error),'retry':attempt+1})
            if isinstance(error,AssertionError):raise
            time.sleep(min(60,10*(attempt+1)))
