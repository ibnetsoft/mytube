"""Real native-engine verification: original assets -> GPU timeline -> H.264/AAC master.

Synthetic fixtures only. MoviePy/Pillow/NumPy here decode and inspect the result;
the production FilmCraft adapter does not use them to compose or encode frames.
"""
from __future__ import annotations
import argparse
import copy
import json
import math
import shutil
import sys
import tempfile
import wave
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'worker'))
from filmcraft_render import PIN,VERSION,CONTRACT,execute
from filmcraft_native import NativeTimeline,render_master,EFFECTS
from scripts.filmcraft import sha


def main():
    import numpy as np
    from PIL import Image,ImageDraw
    from moviepy import VideoFileClip
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    base=ROOT/'output/filmcraft';base.mkdir(parents=True,exist_ok=True)
    directory=args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix='native-verification-',dir=base))
    directory.mkdir(parents=True,exist_ok=True)
    assets=directory/'sources';assets.mkdir(exist_ok=True)
    def tone(name,frequency,duration,amplitude=.16):
        path=assets/name
        samples=np.rint(np.sin(np.arange(round(duration*48000))*2*math.pi*frequency/48000)*32767*amplitude).astype('<i2')
        with wave.open(str(path),'wb') as audio:
            audio.setparams((1,2,48000,0,'NONE','not compressed'));audio.writeframes(samples.tobytes())
        return path
    voice=tone('voice-440.wav',440,4)
    bgm=tone('bgm-220.wav',220,.5)
    sfx=tone('sfx-880.wav',880,.75)
    original=assets/'original.png'
    image=Image.new('RGB',(320,180),'#1a2c68');draw=ImageDraw.Draw(image)
    draw.rectangle((210,55,245,105),fill='#00ed30');draw.rectangle((15,15,45,40),fill='#ffb020')
    image.save(original)
    overlay=assets/'design-overlay.png'
    design=Image.new('RGBA',(1920,1080));ImageDraw.Draw(design).rectangle((20,20,200,40),fill='#ffffff');design.save(overlay)
    print('Creating original native video fixtures',flush=True)
    native=NativeTimeline(directory/'video-source',24,(320,180),2,lambda:None)
    native.shape('rectangle',(160,90),(320,180),0,2,'#164cbd',track=1)
    marker=native.shape('rectangle',(60,90),(40,60),0,2,'#00e060')
    native.animate(marker,'graphic_shape','position',[(0,[60,90]),(2,[260,90])])
    video=assets/'original-video.mp4';shutil.copy2(native.export(),video)
    native=NativeTimeline(directory/'ai-source',24,(320,180),1,lambda:None)
    native.shape('rectangle',(160,90),(320,180),0,1,'#d010be',track=1)
    ai=assets/'reviewed-ai.mp4';shutil.copy2(native.export(),ai)
    def keys():return [dict(t=t,x=.5+t*.05,y=.5,scale=1+t*.1,rotation=0,opacity=100) for t in (0,1)]
    effects=[{'type':'shock_ring','start':.25,'end':.75,'center':[.5,.5],'radius':.3,'color':[1,.8,.2],'intensity':.4}]
    plan={'source':'image','fit':'contain','direction':'Native editable camera and vector cue',
        'keys':keys(),'effects':effects,'transition':'cut'}
    scenes=[{'number':1,'source_kind':'image','start':0,'end':2},
            {'number':2,'source_kind':'video','start':2,'end':4}]
    second={**plan,'source':'video','effects':[],'keys':[dict(t=t,x=.5,y=.5,scale=1,rotation=0,opacity=100) for t in (0,1)],'transition':'crossfade','transition_seconds':.25}
    snapshot={'renderer':{'engine':'filmcraft','revision':PIN['revision'],'adapter':VERSION},
        'motion':{'version':1,'enabled':True,'fps':24,'aspect':'16:9','scenes':{}},'scenes':scenes,
        'settings':{'subtitle_font_family':'Noto Sans KR','subtitle_font_size':5,'subtitle_bg_enabled':True,'subtitle_bg_opacity':.5},
        'subtitles':[{'start':.1,'end':1.9,'text':'원본 카메라 · FilmCraft GPU 合成'},
                     {'start':2.1,'end':3.9,'text':'Native timeline · AI insert · 音声'}]}
    plans=[{'number':1,'scene':plan},{'number':2,'scene':second,'ai':{'start':.5,'duration':1}}]
    sources={1:original,2:video}
    settings={**snapshot['settings'],'bgm_path':str(bgm),'bgm_start':0,'bgm_end':4,'bgm_volume':.15,
        'bgm_loop':True,'bgm_fade_in':.25,'bgm_fade_out':.25}
    print('Rendering native 1080p master from original sources',flush=True)
    output=render_master(snapshot,sources=sources,plans=plans,voice=voice,directory=directory/'master',fresh=lambda:None,
        settings=settings,sfx_cues=[{'path':str(sfx),'start':.5,'volume_db':-18},{'path':str(sfx),'start':.75,'volume_db':-18}],
        template_overlay_path=overlay,ai_sources={2:ai})
    receipt=json.loads((output.parent/'filmcraft-receipt.json').read_text(encoding='utf-8'))
    assert receipt['gpu_composition']['compositedFrames']>0
    assert receipt['gpu_composition']['adapter']['deviceType'] in ('DiscreteGpu','IntegratedGpu','VirtualGpu')
    assert {Path(a['path']) for a in receipt['inputs']}=={original,video,voice,bgm,sfx,overlay,ai}
    assert not list(directory.rglob('frame-*.png')),'Pixel frame staging reintroduced'
    with VideoFileClip(str(output)) as clip:
        assert tuple(clip.size)==(1920,1080) and clip.fps==24 and abs(clip.duration-4)<.1
        decoded=sum(1 for _ in clip.iter_frames());assert decoded==96,decoded
        audio=clip.audio.to_soundarray(fps=48000);mono=audio.mean(axis=1)
        rms=float(np.sqrt(np.mean(mono**2)));assert .05<rms<.2,rms
        part=mono[48000:72000];freq=np.fft.rfftfreq(len(part),1/48000);spectrum=np.abs(np.fft.rfft(part))
        def magnitude(f):return float(spectrum[np.abs(freq-f).argmin()])
        assert magnitude(440)>500 and magnitude(220)>30 and magnitude(880)>30
        frames={str(t):clip.get_frame(t) for t in [.05,.5,1,1.9,2,2.2,2.8,3.8]}
        for t,frame in frames.items():Image.fromarray(frame).save(directory/f'actual-{t}.png')
        # The selected original footage is blue; a distinct magenta AI source covers it only in its saved window.
        assert frames['2.2'][400,960,2]>frames['2.2'][400,960,0]
        assert frames['2.8'][400,960,0]>150 and frames['2.8'][400,960,2]>120
        assert frames['3.8'][400,960,2]>frames['3.8'][400,960,0]
        # Real source movement, not an animation pre-encoded outside FilmCraft.
        def green_x(frame):
            region=frame[100:750];mask=(region[:,:,1]>150)&(region[:,:,0]<100)&(region[:,:,2]<100)
            return float(np.where(mask)[1].mean())
        assert green_x(frames['0.05'])>green_x(frames['1.9'])+10
    print('Checking native GPU output against the CPU reference of the same timeline',flush=True)
    cpu=directory/'master/cpu-reference.mp4'
    result=execute(native.cli,['--project',output.parent/'timeline.fcproj','export',cpu,'--format','h264',
        '--gpu-rendering','off','--settings',json.dumps({'bitrateKbps':40000,'includeAudio':True,'burnCaptions':True})],output.parent,'cpu-reference')
    assert result['gpuComposition']['compositedFrames']==0
    with VideoFileClip(str(output)) as gpu_clip,VideoFileClip(str(cpu)) as cpu_clip:
        errors=[float(np.abs(gpu_clip.get_frame(t).astype(float)-cpu_clip.get_frame(t).astype(float)).mean()) for t in [.05,.5,1,1.9,2,2.2,2.8,3.8]]
        assert max(errors)<4,errors
    print('Rendering every supported vector effect natively',flush=True)
    effect_timeline=NativeTimeline(directory/'effects',24,(320,180),3.25,lambda:None)
    effect_plan=copy.deepcopy(plan)
    effect_plan['keys']=[dict(t=t,x=.5,y=.5,scale=1,rotation=0,opacity=100) for t in (0,1)]
    effect_plan['effects']=[]
    for index,kind in enumerate(sorted(EFFECTS)):
        effect_plan['effects'].append({'type':kind,'start':index*.25/3.25,'end':(index*.25+.2)/3.25,
            'center':[.5,.5],'radius':.3,'color':[1,.8,.2],'intensity':.5})
    effect_timeline.source_scene({'number':1,'start':0,'end':3.25,'source_kind':'image'},effect_plan,original,0)
    effect_output=effect_timeline.export()
    with VideoFileClip(str(effect_output),audio=False) as effect_clip:
        reference=effect_clip.get_frame(3.15).astype(float)
        effect_deltas={kind:float(np.abs(effect_clip.get_frame(index*.25+.1).astype(float)-reference).mean()) for index,kind in enumerate(sorted(EFFECTS))}
        assert min(effect_deltas.values())>.01,effect_deltas
    report={'passed':True,'adapter':VERSION,'gpu_composition':receipt['gpu_composition'],'decoded_frames':decoded,
        'audio_rms':rms,'native_audio_tones':[220,440,880],'gpu_cpu_mae':errors,'effects':sorted(EFFECTS),
        'actual_effect_pixel_deltas':effect_deltas,
        'source_sha256':[a['sha256'] for a in receipt['inputs']],'output':str(output),'output_sha256':sha(output),
        'checks':['native_original_media','editable_camera','native_captions','native_looped_bgm','overlapping_sfx',
                  'native_cross_dissolve','native_ai_window','native_template_overlay','hardware_gpu_composition',
                  'cpu_reference_comparison','no_pixel_frame_staging']}
    (directory/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True),flush=True)


if __name__=='__main__':main()

