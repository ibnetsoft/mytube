"""Render source-bound short AE probes from the exact frozen episode timeline.

Read-only with respect to production DB. Does not mark an episode render complete.
Uses a separate AfterFX instance and the normal native JSX/aerender pipeline.
"""
import argparse,copy,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
import worker_config
from ambient_loop import digest
from ae_mouth_runtime import instance_lock
from ae_flat_scene import prepare as prepare_flat
from wuxia_native_timeline import prepare as prepare_timeline,bind_prepared
from ae_scene_production import _download,_render_native,_video_info
from ae_media_utils import ffmpeg,run
import ae_highlight_worker as ae

def isolated_script(afterfx,jsx,project,timeout=240):
    # -m creates our own AE process; never replace the other producer's project.
    exe=Path(afterfx).with_suffix('.exe');status=jsx.with_suffix('.status.txt')
    status.unlink(missing_ok=True)
    text=jsx.read_text(encoding='utf-8').replace('status("success|"+S.project);','status("success|"+S.project);app.scheduleTask("app.quit()",1500,false);')
    jsx.write_text(text,encoding='utf-8')
    with (jsx.parent/'afterfx-probe.log').open('wb') as log:
        child=subprocess.Popen([str(exe),'-m','-r',str(jsx.resolve())],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if status.exists():
                result=status.read_text(encoding='utf-8-sig')
                if result.startswith('error|'):raise RuntimeError(result)
                if result.startswith('success|') and project.exists():
                    child.wait(timeout=30);return
            if child.poll() not in (None,0):raise RuntimeError('Isolated AE failed before status receipt')
            time.sleep(1)
        raise TimeoutError('Isolated AE probe timed out; no success claimed')

def main():
    p=argparse.ArgumentParser();p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--upload-prefix',required=True);a=p.parse_args()
    snapshot=json.loads(a.snapshot.read_text(encoding='utf-8-sig'));fps=snapshot['motion']['fps'];a.output.mkdir(parents=True,exist_ok=True)
    receipts=[];ae._run_afterfx_script=isolated_script
    # Same mutex as ordinary native jobs, plus an actual aerender process check.
    with instance_lock(worker_config.STATE_DIR/'motion_automation_worker.lock'):
        busy=subprocess.run(['powershell','-NoProfile','-Command',"@(Get-Process aerender -ErrorAction SilentlyContinue).Count"],capture_output=True,text=True,check=True).stdout.strip()
        if busy!='0':raise RuntimeError('Existing aerender active; retry without disturbing it')
        for scene in snapshot['scenes']:
            timeline=scene.get('wuxia_timeline') or {}
            for state in timeline.get('states',[]):
                if not any(l.get('sword_aura') for l in state.get('ambient_loops',[])):continue
                sid=state['asset_id'];directory=a.output/sid;directory.mkdir(parents=True,exist_ok=True)
                positions=[i for i,s in enumerate(timeline['samples']) if s['state']==sid]
                start=positions[len(positions)//3];count=min(36,len(positions)-len(positions)//3)
                selected=timeline['samples'][start:start+count]
                if len(selected)<12 or any(s['state']!=sid for s in selected):raise ValueError('Need a continuous same-state actual sample window')
                t=copy.deepcopy(timeline);t['states']=[copy.deepcopy(state)];t['samples']=[{**copy.deepcopy(s),'at':i/fps} for i,s in enumerate(selected)];t.pop('transition_source',None)
                duration=count/fps
                def download(frame,path):_download(frame['gcs_bucket'],frame['gcs_path'],path)
                runtime=prepare_timeline(t,directory/'sources',lambda:None,download,duration,fps,snapshot.get('audio'))
                source=Path(runtime['states'][0]['file']);small={**scene,'source_kind':'image','start':0,'end':duration}
                direction={'keys':[{'t':i,'x':.5,'y':.5,'scale':1,'rotation':0,'opacity':100} for i in (0,1)],'fit':'cover','effects':[],'lights':[]}
                prepared=prepare_flat(source,small,snapshot['motion'],direction);bind_prepared(prepared,runtime)
                print('NATIVE_AE_PROBE_START',sid,flush=True);native=_render_native(prepared,directory,duration)
                out=directory/'actual-ae-probe.mp4'
                run([ffmpeg(),'-v','error','-y','-i',str(native),'-an','-frames:v',str(count),'-c:v','libx264','-crf','12','-pix_fmt','yuv420p',str(out)])
                run([ffmpeg(),'-v','error','-i',str(out),'-f','null','-'])
                info=_video_info(out)
                if info['frames']!=count or abs(info['fps']-fps)>1e-6:raise ValueError('Actual probe frame count/rate mismatch')
                bucket,key,_=ae._upload_gcs_file(out,a.upload_prefix+'/'+sid+'/'+digest(out)+'.mp4','video/mp4')
                receipts.append({'state':sid,'source_sha256':state['sha256'],'frozen_snapshot_sha256':digest(a.snapshot),'original_scene':scene['number'],'original_scene_sample_start':selected[0]['at'],'original_global_start':scene['start']+selected[0]['at'],'frames':count,'fps':fps,'sha256':digest(out),'gcs_bucket':bucket,'gcs_path':key,'renderer':'actual_adobe_afterfx_and_aerender','scope':'short same-state probe, separate from full episode and final narration verification'})
                (a.output/'receipt.json').write_text(json.dumps({'probes':receipts},ensure_ascii=False,indent=2),encoding='utf-8')
                ae._upload_gcs_file(a.output/'receipt.json',a.upload_prefix+'/receipt.json','application/json')
                print('NATIVE_AE_PROBE_SAVED',sid,flush=True)
    print('NATIVE_AE_PROBES_COMPLETE',len(receipts),flush=True)
if __name__=='__main__':main()
