#!/usr/bin/env python3
"""Prepare and optionally publish GIF patches; preserve the source PNG."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from ambient_loop import prepare_gif,validate,digest

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('source','gif','output'):p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--region',type=json.loads,required=True,help='Normalized [left,top,right,bottom]')
 p.add_argument('--protected-regions',type=json.loads,required=True,help='All face/lettering/important-information boxes; [] only for empty backgrounds')
 p.add_argument('--role',choices=['background','hair','cloth','environment'],required=True)
 p.add_argument('--start-ms',type=int,default=0);p.add_argument('--end-ms',type=int,required=True)
 p.add_argument('--phase-ms',type=int,default=0);p.add_argument('--once',action='store_true')
 p.add_argument('--upload-prefix',help='Explicit upload using configured worker GCS credentials')
 p.add_argument('--package',type=Path,help='Local wuxia_ae_package JSON to attach published frames')
 p.add_argument('--scene');p.add_argument('--state');a=p.parse_args()
 if a.package and not (a.upload_prefix and a.scene and a.state):p.error('--package needs --upload-prefix, --scene and --state')
 package=None;state=None
 if a.package:
  package=json.loads(a.package.read_text(encoding='utf-8'))
  state=next((s for scene in package['scenes'] if scene['scene_id']==a.scene for s in scene['states'] if s['asset_id']==a.state),None)
  if state is None or state.get('sha256')!=digest(a.source):p.error('Exact state/source checksum mismatch')
 loop=prepare_gif(a.source,a.gif,a.output,region=a.region,protected_regions=a.protected_regions,role=a.role,start_ms=a.start_ms,end_ms=a.end_ms,phase_ms=a.phase_ms,repeat=not a.once)
 if a.upload_prefix:
  from ae_highlight_worker import _upload_gcs_file
  for f in loop['frames']:
   path=a.output/f.pop('local_path');bucket,key,url=_upload_gcs_file(path,a.upload_prefix.rstrip('/')+'/'+f['sha256']+'.png','image/png')
   f.update(gcs_bucket=bucket,gcs_path=key,media_url=url)
  for path,mime,name in [(a.source,'image/png','source.png'),(a.gif,'image/gif','source.gif'),(a.output/'poster.png','image/png','poster.png')]:
   _upload_gcs_file(path,a.upload_prefix.rstrip('/')+'/'+name,mime)
  validate(loop);target=a.output/'manifest.json';target.write_text(json.dumps(loop,ensure_ascii=False,indent=2),encoding='utf-8')
  _upload_gcs_file(target,a.upload_prefix.rstrip('/')+'/manifest.json','application/json')
  if state is not None:
   state['ambient_loops']=[item for item in state.get('ambient_loops',[]) if not (item.get('gif_sha256')==loop['gif_sha256'] and item.get('region')==loop['region'] and item.get('role')==loop['role'])]+[loop]
   temporary=a.package.with_suffix('.ambient.tmp')
   temporary.write_text(json.dumps(package,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(a.package)
 print(json.dumps({'frames':len(loop['frames']),'cycle_ms':sum(f['duration_ms'] for f in loop['frames']),'published':bool(a.upload_prefix),'package_attached':state is not None},ensure_ascii=False))
if __name__=='__main__':main()
