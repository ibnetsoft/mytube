"""Verify production defaults, without benchmark export/font overrides."""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'worker'))
from filmcraft_render import PIN,VERSION,CONTRACT
from filmcraft_native import render_master
from scripts.filmcraft import sha

def main():
    from moviepy import VideoFileClip
    import numpy as np
    from motion_automation_worker import pcm
    old=ROOT/'output/filmcraft/existing-scene-3376-037-comparison'
    info=json.loads((old/'inputs.json').read_text(encoding='utf8'))
    out=ROOT/'output/filmcraft/default-profile-verification';out.mkdir(exist_ok=True)
    snapshot={'renderer':{'engine':'filmcraft','revision':PIN['revision'],'adapter':VERSION,'profile':CONTRACT['profile']},
        'motion':info['settings']['motion'],'settings':info['settings'],'subtitles':info['subtitles'],
        'scenes':[{'number':37,'source_kind':'image','start':0,'end':info['duration']}]}
    started=time.perf_counter()
    video=render_master(snapshot,sources={37:Path(info['source'])},plans=[{'number':37,'scene':info['shared_plan']}],
        voice=old/'original-voice-window.wav',directory=out,fresh=lambda:None)
    elapsed=time.perf_counter()-started
    receipt=json.loads((out/'filmcraft-receipt.json').read_text(encoding='utf8'))
    assert receipt['encoding']['bitrateKbps']==1540 and receipt['encoding']['hardwareEncoding']=='auto'
    assert receipt['encoding']['audio']['bitrateKbps']==192 and receipt['profile']==CONTRACT['profile']
    assert receipt['gpu_composition']['compositedFrames']==390 and receipt['gpu_composition']['fallbackFrames']==0
    assert .98<video.stat().st_size/3531817<1.02
    reference=ROOT/'output/filmcraft/matched-scene-3376-037/matched-filmcraft-2/filmcraft.mp4'
    with VideoFileClip(str(video)) as clip,VideoFileClip(str(reference)) as previous:
        assert sum(1 for _ in clip.iter_frames())==390
        errors=[float(np.abs(clip.get_frame(t).astype(float)-previous.get_frame(t).astype(float)).mean()) for t in (.5,8,15.5)]
        assert max(errors)<.5,errors
    a=pcm(old/'original-voice-window.wav');b=pcm(video);n=min(len(a),len(b));correlation=float(np.corrcoef(a[:n],b[:n])[0,1]);assert correlation>.99
    result={'passed':True,'adapter':VERSION,'profile':CONTRACT['profile'],'seconds':elapsed,'bytes':video.stat().st_size,
        'encoding':receipt['encoding'],'gpu':receipt['gpu_composition'],'previous_calibrated_frame_mae':errors,
        'audio_correlation':correlation,'output':str(video),'sha256':sha(video),'no_overrides':True}
    (out/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result),flush=True)

if __name__=='__main__':main()
