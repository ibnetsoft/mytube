"""Render a short actual AE probe from an existing frozen submission; never complete its job."""
import argparse,copy,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
import worker_config
from worker.script_worker_store import ScriptStore

def main():
 p=argparse.ArgumentParser();p.add_argument('--job-id',required=True);p.add_argument('--scene',type=int,required=True);p.add_argument('--seconds',type=float,default=7);args=p.parse_args()
 import uuid
 identity=str(uuid.UUID(args.job_id));assert 1<=args.seconds<=10
 from worker.local_media_supervisor import busy_processes
 assert not busy_processes(),'Wait for other native work to finish'
 rows,_=ScriptStore().request('GET','std_project_assets',params={'id':'eq.'+identity,'select':'id,project_id,metadata','limit':1});assert len(rows)==1
 from worker.motion_automation_worker import unseal
 snap=unseal(rows[0]['metadata']['input']);assert snap['project']['employee_email']=='supapitmusic@gmail.com'
 sc=copy.deepcopy(next(s for s in snap['scenes']if s['number']==args.scene));tl=sc['wuxia_timeline'];assert tl['contract']=='wuxia_native_timeline/v3'
 seconds=min(args.seconds,sc['end']-sc['start']);sc['end']=sc['start']+seconds;tl['samples']=tl['samples'][:__import__('math').ceil(seconds*snap['motion']['fps'])]
 directory=ROOT/'output'/'native-probes'/identity/f'scene-{args.scene}';directory.mkdir(parents=True,exist_ok=True)
 from worker.ae_scene_production import _download,_render_native
 from worker.ae_flat_scene import prepare
 from worker.wuxia_native_timeline import prepare as prepare_wuxia
 def download(ref,path):_download(ref['gcs_bucket'],ref['gcs_path'],path)
 runtime=prepare_wuxia(tl,directory/'wuxia',lambda:None,download,seconds,snap['motion']['fps'],snap['audio'])
 source=Path(runtime['states'][0]['file']);prepared=prepare(source,sc,snap['motion'],sc['prepared_direction']);prepared['plan'].update(wuxia_runtime=runtime,width=runtime['size'][0],height=runtime['size'][1],camera=[dict(t=t,x=.5,y=.5,scale=1,rotation=0,opacity=100)for t in (0,1)],fit='cover');prepared['layers']['original']=source
 native=_render_native(prepared,directory,seconds)
 from worker.ae_media_utils import ffmpeg,run
 run([ffmpeg(),'-v','error','-i',str(native),'-f','null','-'])
 digest=hashlib.sha256(native.read_bytes()).hexdigest()
 from worker.ae_highlight_worker import _upload_gcs_file
 bucket,path,_=_upload_gcs_file(native,f'std-motion/{identity}/native-probe/{digest}.mp4','video/mp4')
 report={'job_id':identity,'scene':args.scene,'duration_seconds':seconds,'fps':snap['motion']['fps'],'native_file':str(native),'bytes':native.stat().st_size,'sha256':digest,'gcs_bucket':bucket,'gcs_path':path,'native_ae':True,'full_decode':True,'completes_episode_job':False}
 (directory/'PROBE.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)
if __name__=='__main__':main()
