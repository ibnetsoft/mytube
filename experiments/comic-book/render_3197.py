"""Read-only 12-scene book-mode test using existing 3197 media and narration."""
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
from moviepy import AudioFileClip, CompositeAudioClip, VideoClip, VideoFileClip
from imageio_ffmpeg import get_ffmpeg_exe
from proglog import ProgressBarLogger

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from services.comic_page_turn import page_curl
from services.comic_render_service import animated_balloon
from services.comic_turn_audio import recorded_page_turns

ROOT = REPO / 'output/comic-book-3197'
OUT = ROOT / 'public'
OUT.mkdir(exist_ok=True)
PW, PH, FPS = 504, 672, 24
FONT = str(REPO / 'auth-web/public/fonts/NanumSquareExtraBold.ttf')
font = ImageFont.truetype(FONT, 23)
small = ImageFont.truetype(FONT, 13)
source = json.loads((ROOT / 'source-private.json').read_text(encoding='utf8'))
payload = source['projects'][0]['project_payload']
audio_asset = next(a for a in source['assets'] if a['asset_type'] == 'audio' and a['status'] == 'uploaded')
timing = audio_asset['metadata']['subtitle_timeline']
subs = payload['subtitles']
assert len(timing) == len(subs)
for a, b in zip(timing, subs):
    assert a['text'].strip() == b['text'].strip(), 'Audio/subtitle mismatch'
images = {n: Image.open(ROOT / f'image-{n:02}.png').convert('RGB') for n in range(1, 13)}
videos = {n: VideoFileClip(str(ROOT / f'video-{n:02}.mp4'), audio=False, target_resolution=(960, 540)) for n in [1, 3, 5, 8, 10, 11]}
audio = AudioFileClip(str(ROOT / 'voice.mp3'))
turn = 29 / FPS
tracks, resources, scenes, spreads = [], [], {}, []
clock = 0
for pair in range(6):
    spread_start = clock
    for n in [pair * 2 + 1, pair * 2 + 2]:
        rows = [t for t, s in zip(timing, subs) if s['scene_number'] == n]
        begin, end = rows[0]['start'], rows[-1]['end']
        dest = OUT / f'voice-{n:02}.wav'
        subprocess.run([get_ffmpeg_exe(), '-y', '-ss', str(begin), '-t', str(end-begin), '-i', str(ROOT/'voice.mp3'), '-af', 'atempo=1.10', str(dest)], check=True, capture_output=True)
        clip = AudioFileClip(str(dest)); resources.append(clip)
        duration = math.ceil((clip.duration + .42) * FPS) / FPS
        tracks.append(clip.with_start(clock + .12))
        scenes[n] = {'start': clock, 'end': clock + duration, 'duration': duration,
                     'text': source['scenes'][n-1]['scene_text'].strip('“”'),
                     'kind': 'dialogue' if n in [8, 10] else 'narration',
                     'media': 'video' if n in videos else 'image'}
        clock += duration
    spreads.append({'start': spread_start, 'end': clock, 'duration': clock-spread_start})
    if pair < 5: clock += turn
sounds = []
for n in range(1, 5):
    dest = OUT / f'turn-{n}.wav'
    src = REPO / f'output/comic-test-3285/page-turn-audio/page-turn-{n:02}.mp3'
    subprocess.run([get_ffmpeg_exe(), '-y', '-i', str(src), '-af', f'atempo={1/1.15:.12f}', str(dest)], check=True, capture_output=True)
    sounds.append(dest)
effects, opened = recorded_page_turns(sounds, spreads, turn, .55)
tracks += effects; resources += opened

def wrap(text, width):
    d = ImageDraw.Draw(Image.new('L', (1, 1)))
    result, line = [], ''
    for word in text.split():
        candidate = (line+' '+word).strip()
        if line and d.textlength(candidate, font=font) > width:
            result.append(line); line = word
        else: line = candidate
    if line: result.append(line)
    return result

def crop(im, size, zoom=1., center=(.5, .5)):
    w, h = im.size
    ch = min(h, w*size[1]/size[0])/zoom; cw = ch*size[0]/size[1]
    x = max(0, min(w-cw, center[0]*w-cw/2)); y = max(0, min(h-ch, center[1]*h-ch/2))
    return im.transform(size, Image.Transform.EXTENT, (x,y,x+cw,y+ch), Image.Resampling.BICUBIC), (x,y,cw,ch)

def lettering(n, target=None):
    dialogue = scenes[n]['kind'] == 'dialogue'
    text = scenes[n]['text']
    lines = wrap(text, 310 if dialogue else 416)
    height = max(130, len(lines)*32+48) if dialogue else len(lines)*32+28
    x, y, w = (48, 453, 408) if dialogue else (30, 26, 444)
    assert y+height < PH-30
    mask = Image.new('L',(PW,PH)); d = ImageDraw.Draw(mask)
    if dialogue:
        d.ellipse((x,y,x+w,y+height),fill=255)
        if target:
            cx,cy=x+w/2,y+height/2; dx,dy=target[0]-cx,target[1]-cy
            angle=math.atan2(dy/(height/2),dx/(w/2))
            bx,by=cx+math.cos(angle)*(w/2-3),cy+math.sin(angle)*(height/2-3)
            dist=math.hypot(target[0]-bx,target[1]-by)
            ux,uy=(target[0]-bx)/dist,(target[1]-by)/dist
            d.polygon([(bx-uy*6,by+ux*6),(bx+uy*6,by-ux*6),(bx+ux*25,by+uy*25)],fill=255)
    else: d.rectangle((x,y,x+w,y+height),fill=255)
    edge = ImageChops.subtract(mask.filter(ImageFilter.MaxFilter(5)),mask)
    layer=Image.new('RGBA',(PW,PH));layer.paste('#242426',(0,0),edge)
    fill=Image.new('RGBA',(PW,PH),'#fffefa' if dialogue else '#f5f0e7')
    fill.putalpha(mask.point(lambda v: round(v*(.9 if n==10 else 1))))
    layer=Image.alpha_composite(layer,fill);d=ImageDraw.Draw(layer)
    for i,line in enumerate(lines):
        xx=x+(w-d.textlength(line,font=font))/2 if dialogue else x+14
        d.text((xx,y+(height-len(lines)*32)/2+i*32),line,font=font,fill='#242426')
    return layer

# Extra detail panels are confined to their source page and animate independently.
details = {1:(.49,.38,2.0),3:(.50,.72,2.0),5:(.53,.72,1.6),6:(.5,.72,1.7),9:(.52,.72,1.7),11:(.80,.38,1.8)}
still_motion={2:'left',4:'out',6:'in',7:'up',9:'right',12:'still'}

def leaf(n, t, settled=False):
    scene=scenes[n];local=t-scene['start'];active=local>=0 or settled
    q=max(0,min(1,local/scene['duration']))
    if settled:q=1
    page=Image.new('RGB',(PW,PH),'#fffefa');d=ImageDraw.Draw(page)
    dialogue=scene['kind']=='dialogue'
    x,y,w,h=(18,55,468,350) if dialogue else (18,178,468,286)
    if n in [2,4,7,12]:h=440 if n in [2,7] else 385
    source_image=images[n]
    if n in videos:
        vt=min(max(0,local),videos[n].duration-1/FPS)
        if settled:vt=videos[n].duration-1/FPS
        source_image=Image.fromarray(videos[n].get_frame(vt))
    z=1.;cx,cy=.5,.5
    motion=still_motion.get(n,'video')
    if motion=='in':z=1+.10*q
    elif motion=='out':z=1.1-.1*q
    elif motion=='left':z=1.1;cx=.54-.08*q
    elif motion=='right':z=1.1;cx=.46+.08*q
    elif motion=='up':z=1.08;cy=.54-.08*q
    panel,extent=crop(source_image,(w,h),z,(cx,cy))
    page.paste(panel,(x,y));d.rectangle((x,y,x+w,y+h),outline='#242426',width=2)
    if n in details:
        cx2,cy2,z2=details[n]
        detail,_=crop(images[n],(244,139),z2,(cx2,cy2))
        # Stable detail contrasts with the moving main panel.
        dx=PW-244-25 if n%2 else 25;dy=490
        reveal=max(0,min(1,(q-.22)/.13)) if active else 0
        if settled:reveal=1
        if reveal>0:
            hh=max(1,round(139*reveal));page.paste(detail.crop((0,0,244,hh)),(dx,dy))
            d.rectangle((dx,dy,dx+244,dy+hh),outline='#242426',width=2)
    if active:
        target=None
        if dialogue:
            # Hand-checked positions in these two restrained shots; follow their small drift.
            face=(.59-.015*q,.30) if n==8 else (.43-.01*q,.32)
            ox,oy,cw,ch=extent;iw,ih=source_image.size
            target=(x+(face[0]*iw-ox)/cw*w,y+(face[1]*ih-oy)/ch*h)
            assert x<target[0]<x+w and y<target[1]<y+h
        layer=lettering(n,target);bounds=layer.getbbox();tile=layer.crop(bounds)
        tile,pos=animated_balloon(tile,bounds[:2],local,dialogue and not settled)
        page.paste(tile,pos,tile)
    d.text((PW/2-7,PH-23),str(n),font=small,fill='#8a8278')
    return page

def spread(i,t,settled=False):
    im=Image.new('RGB',(PW*2,PH),'#fffefa')
    im.paste(leaf(i*2+1,t,settled),(0,0));im.paste(leaf(i*2+2,t,settled),(PW,0))
    d=ImageDraw.Draw(im)
    for offset in range(-5,6):
        shade=round(245-26*(1-abs(offset)/6));d.line((PW+offset,0,PW+offset,PH),fill=(shade,shade-2,shade-5))
    return np.array(im)

turn_cache={}
def frame(t):
    i=max(j for j,p in enumerate(spreads) if t>=p['start'])
    p=spreads[i]
    if t>=p['end'] and i<5:
        if i not in turn_cache:turn_cache[i]=(spread(i,p['end'],True),spread(i+1,spreads[i+1]['start']))
        a,b=turn_cache[i];book=page_curl(a,b,(t-p['end'])/turn)
    else:book=spread(i,t)
    canvas=np.zeros((720,1280,3),dtype=np.uint8);canvas[24:696,136:1144]=book
    return canvas

for i,p in enumerate(spreads):Image.fromarray(frame(p['end']-.01)).save(OUT/f'page-{i+1}.jpg')
manifest={'title':source['projects'][0]['title'],'duration':clock,'scene_count':12,'pages':12,'spreads':spreads,'scenes':scenes,'video_scenes':list(videos),'new_ai_generations':0,'page_ratio':'3:4','sound_duration_multiplier':1.15,'voice_speed':1.1,'face_targeting':'manually checked sample coordinates, not automatic face detection'}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
if '--preview' in sys.argv:print('PREVIEW',clock);sys.exit(0)
class Log(ProgressBarLogger):
    last=-1
    def bars_callback(self,bar,attr,value,old_value=None):
        if bar=='frame_index' and attr=='index':
            n=int(value/max(1,self.bars[bar].get('total',1))*10)
            if n!=self.last:print('render',n*10,'%',flush=True);self.last=n
mix=CompositeAudioClip(tracks).with_duration(clock)
video=VideoClip(frame,duration=clock).with_audio(mix)
video.write_videofile(str(OUT/'output.mp4'),fps=FPS,codec='libx264',audio_codec='aac',preset='veryfast',threads=3,logger=Log(),ffmpeg_params=['-pix_fmt','yuv420p','-movflags','+faststart'])
video.close();mix.close();audio.close()
for clip in list(videos.values())+resources:clip.close()
buttons=''.join(f'<button onclick="seek({p["start"]})">{i*2+1}–{i*2+2} 페이지</button>' for i,p in enumerate(spreads))
html='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>보따리 · 만화책 모드</title><style>body{background:#151513;color:#eee;font:16px system-ui;margin:28px}main{max-width:1280px;margin:auto}h1{font-size:26px}p{color:#bdbbb4;line-height:1.8}video{width:100%;background:#000}nav{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}button{background:#3d4842;border:0;color:white;padding:12px;border-radius:5px}</style><main><h1>마을에서 쫓겨난 며느리가 십 년 뒤 들고 온 보따리</h1><p>만화책 모드 · 도입부 12씬 / 좌우 3:4 · 기존 영상 6개와 이미지 활용<br>나레이션은 네모 상자, 대사는 화자 방향 말풍선 · 기존 음성 재사용 · 책장 소리 4종 순환, 길이 15% 증가</p><video id="v" controls preload="metadata" src="output.mp4" poster="page-1.jpg"></video><nav>BUTTONS</nav></main><script>function seek(t){const v=document.getElementById('v');v.currentTime=t;v.play()}</script></html>'''.replace('BUTTONS',buttons)
(OUT/'index.html').write_text(html,encoding='utf8')
print('DONE',clock,flush=True)
