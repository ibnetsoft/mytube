import json,sys,wave
from pathlib import Path
import numpy as np
from PIL import Image
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root.parents[1]))
from services import comic_render_service as comic
from lettering_v2 import lettering,book_turn

out=root/'v2'
events=json.loads((out/'events.json').read_text(encoding='utf8'))
durations=[];chunks=[];clock=0;sample_rate=24000
for scene in range(1,11):
    beginning=clock
    for event in [e for e in events if e['scene']==scene]:
        with wave.open(str(out/(event['id']+'.wav')),'rb') as r:
            assert r.getframerate()==sample_rate and r.getnchannels()==1 and r.getsampwidth()==2
            samples=r.readframes(r.getnframes());duration=r.getnframes()/sample_rate
        event['start']=clock;event['end']=clock+duration
        chunks.append(samples);chunks.append(b'\0\0'*int(sample_rate*.35));clock+=duration+.35
    chunks.append(b'\0\0'*int(sample_rate*.7));clock+=.7
    durations.append(clock-beginning)
with wave.open(str(out/'speech.wav'),'wb') as w:
    w.setparams((1,2,sample_rate,0,'NONE','not compressed'));w.writeframes(b''.join(chunks))
settings={'comic':{'version':1,'mode':'comic','layout':'spread','turn_duration':1.3,'turn_sound':True,'font_size':25}}
images=[str(root/'images'/f'scene_{i:02}.png') for i in range(1,11)]
comic.balloon_layer=lettering
comic.page_curl=book_turn
font=str(root.parents[1]/'auth-web/public/fonts/NanumSquareExtraBold.ttf')
frames=comic.ComicFrames(images,durations,events,settings,(1280,720),font)
(out/'comic_pages').mkdir(exist_ok=True)
for i,page in enumerate(frames.pages):
    Image.fromarray(frames.page(i,page['source_end']-.001,True)).save(out/'comic_pages'/f'page_{i+1:03}.png')
Image.fromarray(frames.frame(frames.pages[0]['end']+.42)).save(out/'turn_midpoint.png')
manifest={'topic_id':3285,'prototype':True,'dialogue_adapted_for_test':True,
    'voice':'Windows Microsoft Heami temporary Korean TTS; one voice with rate differences',
    'duration':frames.duration,'durations':durations,'pages':frames.pages,'settings':settings,'events':events}
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
frames.close()
if '--preview' not in sys.argv:
    last=[-1]
    def progress(p,text):
        if p//10!=last[0]:print(p,text,flush=True);last[0]=p//10
    print(comic.render_comic(temp_dir=str(out),images=images,durations=durations,audio_path=str(out/'speech.wav'),
        subtitles=events,settings=settings,resolution=(1280,720),progress_callback=progress),flush=True)
