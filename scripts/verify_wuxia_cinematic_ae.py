"""Actual Adobe probes for source-bound cinematic snapshots; no production DB mutation."""
import argparse,copy,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker'),str(ROOT/'scripts')]
import worker_config,ae_highlight_worker as ae
from verify_wuxia_aura_ae import isolated_script
from ae_mouth_runtime import instance_lock
from ambient_loop import digest
from wuxia_native_timeline import prepare as prepare_timeline,bind_prepared
from ae_flat_scene import prepare as prepare_flat
from ae_scene_production import _download,_render_native,_video_info
from ae_media_utils import ffmpeg,run

def main():
 p=argparse.ArgumentParser();p.add_argument('--snapshot',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--upload-prefix',required=True);a=p.parse_args();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True)
 snap=json.loads(a.snapshot.read_text(encoding='utf-8-sig'));ae._run_afterfx_script=isolated_script;fps=snap['motion']['fps'];receipts=[]
 with instance_lock(worker_config.STATE_DIR/'motion_automation_worker.lock'):
  busy=subprocess.run(['powershell','-NoProfile','-Command',"@(Get-Process aerender -ErrorAction SilentlyContinue).Count"],capture_output=True,text=True,check=True).stdout.strip()
  if busy!='0':raise RuntimeError('Existing aerender active; preserve it and retry')
  for scene in snap['scenes']:
   number=scene['number'];directory=a.output/str(number);directory.mkdir(exist_ok=True);duration=scene['end']-scene['start'];t=copy.deepcopy(scene['wuxia_timeline'])
   print('CINEMATIC_NATIVE_START',number,flush=True)
   runtime=prepare_timeline(t,directory/'sources',lambda:None,lambda f,path:_download(f['gcs_bucket'],f['gcs_path'],path),duration,fps,snap.get('audio'))
   source=Path(runtime['states'][0]['file']);direction={'keys':[{'t':i,'x':.5,'y':.5,'scale':1,'rotation':0,'opacity':100} for i in (0,1)],'fit':'cover','effects':[],'lights':[]}
   prepared=prepare_flat(source,{**scene,'source_kind':'image','start':0,'end':duration},snap['motion'],direction);bind_prepared(prepared,runtime);native=_render_native(prepared,directory,duration)
   out=directory/'actual-ae.mp4';count=len(t['samples']);run([ffmpeg(),'-v','error','-y','-i',str(native),'-an','-frames:v',str(count),'-c:v','libx264','-crf','12','-pix_fmt','yuv420p',str(out)]);run([ffmpeg(),'-v','error','-i',str(out),'-f','null','-']);info=_video_info(out)
   if info['frames']!=count or abs(info['fps']-fps)>1e-6:raise ValueError('Actual native frame count or rate mismatch')
   bucket,key,_=ae._upload_gcs_file(out,a.upload_prefix+'/'+str(number)+'/'+digest(out)+'.mp4','video/mp4')
   receipts.append(dict(scene=number,renderer='actual_adobe_afterfx_and_aerender',frames=count,fps=fps,sha256=digest(out),snapshot_sha256=digest(a.snapshot),gcs_bucket=bucket,gcs_path=key,contract=t['contract']))
   receipt=a.output/'receipt.json';receipt.write_text(json.dumps({'probes':receipts},indent=2));ae._upload_gcs_file(receipt,a.upload_prefix+'/receipt.json','application/json');print('CINEMATIC_NATIVE_SAVED',number,flush=True)
 print('CINEMATIC_NATIVE_COMPLETE',len(receipts),flush=True)
if __name__=='__main__':main()
