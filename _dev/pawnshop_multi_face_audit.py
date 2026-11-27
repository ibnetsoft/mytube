"""Audit actual stored reference pixels without turning uncertainty into approval."""
import hashlib,json,sys,shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'worker/connection.env',override=False)
from worker.cowork_scene_assets import _download_gcs_bytes
from worker.codex_content_runner import CodexStagedContentRunner
OUT=ROOT/'output/pawnshop-series/image-production-245'
inventory=json.loads((OUT/'current-reference-inventory.json').read_text())
old={r['id']:r for r in json.loads((ROOT/'output/pawnshop-series/episode-01/production/existing-reference-pixels.json').read_text())}
folder=OUT/'registry';folder.mkdir(exist_ok=True)
def download(r):
    if not r.get('storage_bucket') or not r.get('storage_object_path'):return {**r,'unavailable':'no stored object'}
    p=folder/(str(r['id'])+'.png')
    try:
        if not p.exists():
            previous=old.get(r['id']) or {}
            if previous.get('storage_object_path')==r['storage_object_path'] and Path(previous.get('local_file','missing')).is_file():
                shutil.copy2(previous['local_file'],p)
            else:p.write_bytes(_download_gcs_bytes(r['storage_bucket'],r['storage_object_path']))
        with Image.open(p) as im:im.verify()
        return {**r,'local_file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    except Exception as error:return {**r,'unavailable':type(error).__name__}
with ThreadPoolExecutor(max_workers=4) as pool:records=list(pool.map(download,inventory))
(OUT/'registry-pixels.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
available=[r for r in records if r.get('local_file')];contacts=[]
for start in range(0,len(available),12):
    page=Image.new('RGB',(3000,2100),'#202020');draw=ImageDraw.Draw(page)
    for index,r in enumerate(available[start:start+12]):
        im=Image.open(r['local_file']).convert('RGB');im.thumbnail((740,640));x=index%4*750;y=index//4*700
        page.paste(im,(x+(750-im.width)//2,y));draw.text((x+10,y+650),'ID '+str(r['id'])+' TOPIC '+str(r['topic_queue_id']),fill='white')
    path=OUT/f'registry-{start//12+1}.jpg';page.save(path,quality=96);contacts.append(str(path))
new=[]
for e in ['02','04','05']:
    p=ROOT/('output/pawnshop-series/episode-'+e)/'image-production'
    for r in json.loads((p/'reference-jobs.json').read_text()):
        path=p/f"cast-sheet-{r['sheet']}.png"
        if e=='04' and r['sheet']==2:path=p/'cast-sheet-2-v2.png'
        new.append({'episode':e,'sheet':r['sheet'],'names':r['characters'],'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
def audit(item):
    context={'_local_image_paths':[item['path']]+[r['path'] for r in new if r!=item]+contacts+[str(ROOT/'output/pawnshop-series/episode-03/character-references/new-cast-contact-sheet.png')],
             'target':item,'other_new_sheets':[r for r in new if r!=item],'stored_references':[{'id':r['id'],'topic':r['topic_queue_id'],'sha256':r['sha256']} for r in available],
             'unavailable_reference_ids':[r['id'] for r in records if r.get('unavailable')]}
    attach=ROOT/'output/codex-local-console/5a0bb74a8d8f4a2d943fa79bc79c7dcc/face-audit-245';attach.mkdir(exist_ok=True)
    paths=[]
    for source in context['_local_image_paths']:
        original=Path(source);target=attach/(hashlib.sha256(original.read_bytes()).hexdigest()[:16]+original.suffix);shutil.copy2(original,target);paths.append(str(target))
    context['_local_image_paths']=paths
    task='Actual-pixel editorial fictional-character face audit. First image is target 2x2 cast, named TL/TR/BL/BR. Other images are other new casts, labeled stored registry sheets across all categories, and episode3 cast. Compare underlying facial geometry, eye spacing/shape, nose, mouth and jaw, ignoring hair/clothes/age/wrinkles as sole differences. Do not identify real people. Return {target_names:[exact names],stored_reference_ids_considered:[all supplied numeric IDs],within_target_checks:[{first,second,verdict:"distinct|similar|uncertain",structural_evidence:[...]}],flagged_pairs:[{target_name,reference_description,verdict:"similar|uncertain",structural_evidence:[...],reason}],review_summary,all_faces_distinct:false}. Only set all_faces_distinct true if every actual comparison has at least THREE independent substantial structural differences visible. Poorly readable sheet faces MUST be uncertain, not invented differences. Explicitly report similar cross-episode/new-cast faces for correction. No media approval and no story rewrite. Keep compact; record limitations honestly.'
    result=CodexStagedContentRunner()._stage('pawnshop-245',f"03_face_audit_{item['episode']}_{item['sheet']}",context,task)
    assert set(result['target_names'])==set(item['names'])
    assert set(result['stored_reference_ids_considered'])=={r['id'] for r in available}
    path=OUT/f"face-audit-{item['episode']}-{item['sheet']}.json";path.write_text(json.dumps({'source':item,'result':result},ensure_ascii=False,indent=2));print(path.name,flush=True)
with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(audit,new))
print('actual reference audit saved',flush=True)
