import json,math,numpy as np
from pathlib import Path
from PIL import Image,ImageDraw
out=Path('output/motion-longform-validation');manifest=json.loads((out/'source-manifest.json').read_text(encoding='utf-8'));samples=json.loads((out/'sample-index.json').read_text(encoding='utf-8'));rows={s['number']:s for s in manifest['rows']};originals={};checks=[]
for sample in samples:
 s=rows[sample['scene']];im=Image.open(sample['file']).convert('RGB');pixels=np.asarray(im,dtype=float);mean=float(pixels.mean());assert mean>5,('Blank frame',sample);score=None
 if not s['psd']:
  if s['number'] not in originals:originals[s['number']]=Image.open(s['file']).convert('RGB').resize((480,270),Image.Resampling.LANCZOS)
  u=(sample['time']-s['start'])/(s['end']-s['start']);scale=1+.015*u;expected=originals[s['number']].transform((480,270),Image.Transform.AFFINE,(1/scale,0,240-240/scale,0,1/scale,135-135/scale),Image.Resampling.BILINEAR);score=float(np.abs(pixels[:210]-np.asarray(expected,dtype=float)[:210]).mean());assert score<18,('Wrong source/transform',sample,score)
 checks.append({**sample,'mean_luminance':mean,'source_rgb_mae_above_captions':score})
midpoints=[min((s for s in checks if s['scene']==r['number']),key=lambda s:abs(s['time']-(r['start']+r['end'])/2)) for r in manifest['rows']]
for g in range(5):
 canvas=Image.new('RGB',(1920,1350),'#141414');draw=ImageDraw.Draw(canvas)
 for i,s in enumerate(midpoints[g*20:g*20+20]):
  im=Image.open(s['file']).convert('RGB');x=i%4*480;y=i//4*270;canvas.paste(im,(x,y));draw.rectangle((x,y,x+200,y+16),fill='black');draw.text((x+4,y+2),f"Scene {s['scene']} @ {s['time']:.3f}s",fill='white')
 canvas.save(out/f'encoded-midpoints-{g}.jpg',quality=92)
values=[s['source_rgb_mae_above_captions'] for s in checks if s['source_rgb_mae_above_captions'] is not None];result={'sample_frames':len(checks),'blank_frames':0,'matched_original_frames':len(values),'source_mae_mean':sum(values)/len(values),'source_mae_max':max(values),'psd_frames_for_visual_review':[s for s in checks if rows[s['scene']]['psd']], 'checks':checks};(out/'frame-qa.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in result.items() if k not in ['checks','psd_frames_for_visual_review']},indent=2))
