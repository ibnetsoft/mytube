"""Verify real AE/EffectCraft completed clips -> native FilmCraft final assembly."""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'worker'))
from services.filmcraft_final_service import render_final
from scripts.filmcraft import sha


def main():
    from moviepy import VideoFileClip,AudioFileClip
    from PIL import Image,ImageDraw
    from motion_automation_worker import pcm
    import numpy as np
    base=ROOT/'output/effectcraft/psd-3376-scene25-motion-fix-20261021'
    directory=ROOT/'output/filmcraft/effects-then-final';directory.mkdir(exist_ok=True)
    voice=ROOT/'output/motion-final-production/scene-25-recording.wav'
    with AudioFileClip(str(voice)) as audio:duration=audio.duration
    settings={'subtitle_font_family':'Noto Sans KR','subtitle_font_size':5.4,'subtitle_pos_y':'b:5%',
        'subtitle_stroke_width':0,'subtitle_bg_enabled':False,'subtitle_line_spacing':.1,
        # A deliberately conflicting motion plan must NOT be re-applied to completed video.
        'motion':{'fps':24,'scenes':{'25':{'keys':[{'scale':2}],'effects':[{'type':'impact_flash'}]}}}}
    frozen=json.loads((ROOT/'output/motion-final-production/frozen-recording.json').read_text(encoding='utf8'))
    rows=[r for r in frozen['project']['project_payload']['subtitles'] if r.get('scene_number')==25]
    start=min(r['start'] for r in rows)
    subs=[{'text':r['text'],'start':r['start']-start,'end':min(duration,r['end']-start)} for r in rows if r['start']-start<duration]
    results=[];sheet=Image.new('RGB',(1280,770),'#161a20')
    for index,(engine,name) in enumerate((('AE','ae-reference.mp4'),('EffectCraft','effectcraft.mp4'))):
        source=base/name;before=sha(source);work=directory/engine;work.mkdir(exist_ok=True);begin=time.perf_counter()
        output=render_final(temp_dir=work,images=[str(source)],durations=[duration],audio_path=str(voice),subtitles=subs,
            settings=settings,resolution=(1920,1080),scene_numbers=[25],image_effects=['zoom_in'],transition_effects=['none'])
        elapsed=time.perf_counter()-begin
        assert sha(source)==before
        with VideoFileClip(str(output),audio=False) as result,VideoFileClip(str(source),audio=False) as original:
            import math
            assert abs(sum(1 for _ in result.iter_frames())-math.ceil(duration*24))<=1
            assert result.get_frame(duration-.1)[:900].mean()>5,'A retimed scene must remain visible through the tail'
            a=original.get_frame(4*10/duration);b=result.get_frame(4)
            picture_mae=float(np.abs(a[:900].astype(float)-b[:900].astype(float)).mean())
            assert picture_mae<12,picture_mae
            for column,frame in enumerate((a,b)):
                sheet.paste(Image.fromarray(frame).resize((640,360)),(column*640,index*385+25))
                ImageDraw.Draw(sheet).text((column*640+8,index*385+5),engine+(' completed effects' if column==0 else ' -> FilmCraft final'),fill='white')
        a=pcm(voice,duration=duration);b=pcm(output);n=min(len(a),len(b));correlation=float(np.corrcoef(a[:n],b[:n])[0,1]);assert correlation>.99
        receipt=json.loads((work/'filmcraft-final/filmcraft-receipt.json').read_text(encoding='utf8'))
        assert abs(receipt['gpu_composition']['compositedFrames']-math.ceil(duration*24))<=1
        results.append({'effect_engine':engine,'source':str(source),'source_sha256':before,'output':str(output),
            'seconds':elapsed,'picture_mae':picture_mae,'audio_correlation':correlation,'gpu':receipt['gpu_composition'],
            'profile':receipt['profile'],'effect_clips_unchanged':True})
        print(engine+' -> FilmCraft final verified',flush=True)
    sheet.save(directory/'comparison.png')
    (directory/'verification.json').write_text(json.dumps({'passed':True,'duration':duration,'note':'Completed scene25 effects retimed natively to the complete finalized recording; visual tail checked','results':results},indent=2),encoding='utf8')
    print(json.dumps(results),flush=True)


if __name__=='__main__':main()
