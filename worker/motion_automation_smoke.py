"""Actual local Codex direction/render/review diagnostic, isolated from production queues.

Uses a synthetic original and finalized calibration recording, not a customer scene or speech audition.
"""
import argparse
import hashlib
import json
import sys
import wave
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'worker'))

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('name');parser.add_argument('--resume',action='store_true');args=parser.parse_args()
    if not args.name.replace('-','').isalnum():raise ValueError('Use a simple diagnostic name')
    directory=ROOT/'output'/'codex-local-console'/'motion-automation-smoke'/args.name
    if directory.exists() and not args.resume:raise ValueError('Use a new name to preserve prior evidence, or --resume the same diagnostic')
    directory.mkdir(parents=True,exist_ok=True)
    import numpy as np
    from PIL import Image,ImageDraw
    from codex_content_runner import CodexStagedContentRunner
    from motion_automation_worker import direct,voice_evidence,render_base,review_output,digest,save_json
    from ae_media_utils import ffmpeg,run
    from services.motion_render_service import render_motion
    source=directory/'synthetic-original.png'
    image=Image.new('RGB',(640,360),'#243c56');draw=ImageDraw.Draw(image)
    draw.rectangle((220,165,420,345),fill='#e5793e');draw.ellipse((260,45,380,175),fill='#f1d3ad')
    draw.ellipse((291,101,298,108),fill='#25354a');draw.ellipse((340,101,347,108),fill='#25354a');draw.line((306,140,333,140),fill='#25354a',width=3)
    draw.rectangle((35,50,150,190),outline='#99c1df',width=5);image.save(source)
    voice=directory/'final-calibration.wav';duration=3
    with wave.open(str(voice),'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(16000)
        audio.writeframes((np.sin(np.arange(duration*16000)*2*np.pi*440/16000)*1200).astype('<i2').tobytes())
    scene={'number':1,'source_kind':'image','start':0,'end':duration,'text':'Synthetic original; immutable calibration tone, no spoken narration.'}
    snapshot={'version':1,'project':{'id':'diagnostic-'+args.name},'audio':{'id':'calibration'},'subtitles':[],
        'motion':{'version':1,'enabled':True,'aspect':'16:9','fps':24,'scenes':{},'automation':{'mode':'ae_only','max_ai_clips':1,'max_ai_seconds':5}},'scenes':[scene]}
    runner=CodexStagedContentRunner();audio_info,waveform=voice_evidence(voice,scene,directory)
    plan=direct(runner,snapshot,scene,source,waveform,audio_info,[],[]);save_json(directory/'direction.json',plan)
    visual=render_base(snapshot,scene,plan,source,source,runner,directory,lambda:None)
    synced=directory/'voice-synced.mp4';run([ffmpeg(),'-v','error','-y','-i',str(visual),'-i',str(voice),'-map','0:v:0','-map','1:a:0','-t',str(duration),'-c:v','copy','-c:a','aac',str(synced)])
    review=review_output(runner,synced,source,voice,scene,plan,directory,lambda:None);save_json(directory/'actual-review.json',review)
    final_dir=directory/'final';final_dir.mkdir(exist_ok=True)
    final=render_motion(temp_dir=str(final_dir),images=[str(synced)],durations=[duration],audio_path=str(voice),subtitles=[],
        settings={'motion':{**snapshot['motion'],'scenes':{'1':{**plan['scene'],'source':'psd'}}}},resolution=(1920,1080),scene_numbers=[1])
    final_review=review_output(runner,Path(final),source,voice,scene,plan,final_dir,lambda:None);save_json(final_dir/'actual-review.json',final_review)
    report={'mode':'ae_only','actual_codex_cli':True,'actual_render':True,'review':review,'final_review':final_review,'output':str(final),'sha256':digest(final),
        'queue':'not_exercised_by_this_local_diagnostic','audio':'calibration_tone_not_customer_narration','native_ae':False}
    save_json(directory/'report.json',report);print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
