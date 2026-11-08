"""Audit named saved scripts read-only. Counters are not semantic approval."""
import argparse,json,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from worker.wuxia_narration_audit import diagnose

def main():
 p=argparse.ArgumentParser();p.add_argument('scripts',type=Path,nargs='+');p.add_argument('--output',type=Path,required=True);args=p.parse_args();records=[]
 for path in args.scripts:
  data=json.loads(path.read_text());scenes=data.get('scenes') or data.get('sections') or []
  records.append({'source':str(path),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'episode':data.get('episode'),'language':data.get('settings',{}).get('language'),'scene_count':len(scenes),'separate_visual_scene_count':sum(bool(s.get('visual_action') or s.get('visual_states')) for s in scenes),'actual_audio_auditioned':False,**diagnose(scenes)})
 args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps({'scope':'Explicit local saved snapshots, not a live DB readback or final audio audition','scripts':records},ensure_ascii=False,indent=2));print('Audited',len(records),'saved script snapshots without rewriting')
if __name__=='__main__':main()
