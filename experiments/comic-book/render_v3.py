import json,sys,shutil
from pathlib import Path
from PIL import Image
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root.parents[1]))
from services import comic_render_service as comic
out=root/'v3';out.mkdir(exist_ok=True)
previous=json.loads((root/'v2/manifest.json').read_text(encoding='utf8'))
events=previous['events'];durations=previous['durations']
settings={'comic':{'version':1,'mode':'moving_comic','layout':'wide','page_layouts':{'0':'wide','1':'splash','2':'asymmetric','3':'parallel','4':'spread'},'turn_duration':1.3,'turn_sound':True,'font_size':23,'panels':{},'lettering':{}}}
counts={}
for e in events:
    scene=e['scene'];i=counts.get(scene,0);counts[scene]=i+1
    e['dialogue_kind']=e['kind'];e['dialogue_speaker']=e['speaker']
    x,y,bw=e['placement']
    if scene in (5,6):x,y,bw=.05,(.04 if i==0 else .43),.9
    if scene==3:x,y,bw=(.05,.04,.75) if i==0 else (.57,.42,.38)
    cfg={'kind':e['kind'],'style':e.get('style','speech'),'x':x,'y':y,'width':bw}
    if 'target' in e:cfg.update(target_x=e['target'][0],target_y=e['target'][1])
    settings['comic']['lettering'][f'{scene}:{i}']=cfg
    settings['comic']['panels'][str(scene)]={'motion':'pan','fit':'cover' if scene in (1,2,5,6) else 'contain'}
images=[str(root/'images'/f'scene_{i:02}.png') for i in range(1,11)]
font=str(root.parents[1]/'auth-web/public/fonts/NanumSquareExtraBold.ttf')
frames=comic.ComicFrames(images,durations,events,settings,(1280,720),font)
for i,page in enumerate(frames.pages):Image.fromarray(frames.page(i,page['source_end']-.001,True)).save(out/f'page_{i+1}.png')
for p in (.15,.25,.4,.6):Image.fromarray(frames.frame(frames.pages[0]['end']+p*frames.turn)).save(out/f'curl_{int(p*100)}.png')
(out/'manifest.json').write_text(json.dumps({'settings':settings,'events':events,'pages':frames.pages,'duration':frames.duration,'prototype':True,'dialogue_adapted_for_test':True},ensure_ascii=False,indent=2),encoding='utf8')
frames.close()
shutil.copyfile(root/'v2/speech.wav',out/'speech.wav')
if '--preview' not in sys.argv:
    last=[-1]
    def progress(p,t):
        if p//10!=last[0]:print(p,t,flush=True);last[0]=p//10
    print(comic.render_comic(temp_dir=str(out),images=images,durations=durations,audio_path=str(out/'speech.wav'),subtitles=events,settings=settings,resolution=(1280,720),progress_callback=progress),flush=True)
