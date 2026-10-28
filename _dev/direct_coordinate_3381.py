"""Finish one known coordinate job without a long database lease."""
import copy, dataclasses, os, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from ae_media_utils import ref as image_reference
import ae_highlight_worker as ae
from ae_mouth import locate_speakers,digest
from codex_content_runner import CodexStagedContentRunner
from mouth_geometry import validate

PROJECT='6b46f709-b4bf-4ccd-ac12-9c8c3981e249'
def main(number:int):
 base,headers=ae._supabase();url=base+'/rest/v1/std_project_assets'
 rows=ae._request('GET',url,headers,params={'select':'*','project_id':'eq.'+PROJECT,'scene_number':'eq.'+str(number)}).json()
 job=next(x for x in rows if x.get('metadata',{}).get('kind')=='ae_speaker_coordinates');meta=copy.deepcopy(job['metadata']);scene=meta['input']['scenes'][0]
 future=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat();ae._request('PATCH',url,{**headers,'Prefer':'return=representation'},params={'id':'eq.'+job['id']},json={'metadata':{**meta,'state':'processing','failures':[],'results':[],'error':None,'current_scene':number,'worker_token':'direct-codex'},'updated_at':future})
 directory=ROOT/'output/codex-local-console/speaker-coordinates'/meta['fingerprint'];directory.mkdir(parents=True,exist_ok=True);bucket,path=image_reference(scene['image']);image=directory/f'scene-{number}.png'
 if not image.exists():ae._download_gcs_file(ae.GcsRef(bucket,path),image)
 runner=CodexStagedContentRunner();runner.config=dataclasses.replace(runner.config,timeout_seconds=min(runner.config.timeout_seconds,240));speakers=locate_speakers(runner,meta['fingerprint']+'-'+str(number)+'-direct',scene,image,scene['rows'],meta['input']['cast'])
 for speaker in speakers:
  if speaker.get('status')!='offscreen':validate(speaker,digest(image))
 result={'number':number,'image_id':scene['image']['id'],'source_path':path,'source_sha256':digest(image),'speakers':speakers}
 try:
  from prepared_mouth_layers import prepare_scene
  from prepared_mouth_preview import prepare_preview
  art=prepare_scene(image,{**result,'state':'ready'},technical=True);preview=prepare_preview(PROJECT,number,image,{**result,'state':'ready'},art);result['mouth_preparation']=art
  if preview.get('state')=='ready':ae._request('POST',url,{**headers,'Prefer':'return=representation'},json={'project_id':PROJECT,'asset_type':'other','status':'uploaded','scene_number':number,'file_name':'mouth-preview.mp4','mime_type':'video/mp4','metadata':{**preview,'source_image_id':scene['image']['id']}})
 except Exception as exc:result['preparation_error']=str(exc)[:500]
 final={**meta,'state':'ready','current_scene':None,'results':[result],'failures':[],'error':None,'reviewer':'local-codex-visual-analysis'};ae._request('PATCH',url,{**headers,'Prefer':'return=representation'},params={'id':'eq.'+job['id']},json={'metadata':final,'updated_at':ae._now()});print(number,'ready',flush=True)
if __name__=='__main__':main(int(sys.argv[1]))
