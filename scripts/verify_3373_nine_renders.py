import runpy,sys,json,subprocess
from pathlib import Path
from PIL import Image,ImageDraw
sys.argv=['process_3373_nine_mouths.py','render'];m=runpy.run_path('scripts/process_3373_nine_mouths.py');d=m['DIR'];ff=m['ffmpeg']();panels=[];report=[]
for record in m['data']['scenes']:
 n=record['number'];p=d/f'processing-{n}';t=json.loads((p/'mouth-images-ready.json').read_text(encoding='utf8'));out=p/'final-with-voice.mp4'
 subprocess.run([ff,'-v','error','-i',str(out),'-f','null','-'],check=True,capture_output=True)
 master=m['ROOT']/'output/codex-local-console/ae-mouth/db93c4ef790211c53236f3ea8ca1655add9ff30e2156bb2af4dce8c98ebf5241/final-narration.mp3'
 a,b,rows=m['timing'](n);samples=m['decode_scene_audio'](ff,master,a,b-a)
 for i,s in enumerate(t['speakers']):
  cues=m['amplitude_cues'](samples,[r for r in rows if r['kind']=='dialogue' and r['speaker']==s['speaker']],start=a,duration=b-a)
  print(n,s['speaker'],str(cues[:2]),flush=True)
  times=[0,(b-a)/2,max(0,b-a-.15)]
  for k,sec in enumerate(times):
   target=p/f'render-sample-{i}-{k}.png';subprocess.run([ff,'-y','-v','error','-ss',str(sec),'-i',str(out),'-frames:v','1',str(target)],check=True,capture_output=True)
   im=Image.open(target);box=s['face_box'];crop=im.crop((int(box[0]*1920)-25,int(box[1]*1080)-25,int(box[2]*1920)+25,int(box[3]*1080)+25));crop.thumbnail((220,230));panel=Image.new('RGB',(240,260),'#202020');panel.paste(crop,((240-crop.width)//2,25));ImageDraw.Draw(panel).text((8,6),f'{n} / {i} / {sec:.1f}s',fill='white');panels.append(panel)
 report.append({'scene':n,'decode':'passed','duration_expected':b-a})
for group in range((len(panels)+11)//12):
 chunk=panels[group*12:(group+1)*12];sheet=Image.new('RGB',(960,780),'#101010')
 for i,panel in enumerate(chunk):sheet.paste(panel,((i%4)*240,(i//4)*260))
 sheet.save(d/f'render-face-samples-{group}.jpg')
listing=d/'concat-scenes.txt';listing.write_text('\n'.join("file '"+str((d/f'processing-{s["number"]}'/'final-with-voice.mp4').resolve()).replace('\\','/')+"'" for s in m['data']['scenes']),encoding='utf8')
subprocess.run([ff,'-y','-v','error','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(d/'nine-scenes-with-voice.mp4')],check=True)
(d/'render-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
