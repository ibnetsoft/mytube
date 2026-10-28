"""Locate static scene cuts in the actual decoded final frames, not metadata alone."""
import json,math
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps
D=Path(__file__).resolve().parents[1]/'output/effectcraft/project-3376-final-20261021';read=lambda p:json.loads(Path(p).read_text(encoding='utf8'))
qa=read(D/'final-qa.json');config=read(D/'final-config.json');shots=read(D/'recording.json')['timings'];samples={s['frame']:s for s in qa['samples']};root=Path.home()/'AppData/Local/Temp/air-render-checkpoints'/qa['queue_id'];results=[]
for i,shot in enumerate(shots[1:],1):
    source=root/'images'/config['images'][i]
    if source.suffix.lower() not in ['.png','.jpg','.jpeg','.webp']:continue
    with Image.open(source) as image:fit=ImageOps.contain(ImageOps.exif_transpose(image).convert('RGB'),(480,270),method=Image.Resampling.BICUBIC)
    expected=Image.new('RGB',(480,270),'#0c1018');expected.paste(fit,((480-fit.width)//2,(270-fit.height)//2));reference=np.array(expected).astype(float)[:189]
    first=math.ceil(shot['start']*24);errors=[]
    for offset in [0,1]:
        actual=np.array(Image.open(samples[first+offset]['file']).convert('RGB')).astype(float)[:189];errors.append(float(abs(actual-reference).mean()))
    assert min(errors)<6,(shot['number'],errors)
    results.append(dict(scene=shot['number'],offset_frames=0 if errors[0]<6 else 1,errors=errors))
qa['static_cut_frame_offsets']=results;qa['max_static_cut_lateness_frames']=max(r['offset_frames'] for r in results)
(D/'final-qa.json').write_text(json.dumps(qa,indent=2),encoding='utf8')
print(dict(cuts_checked=len(results),max_offset_frames=qa['max_static_cut_lateness_frames'],one_frame_late=sum(r['offset_frames']==1 for r in results)),flush=True)
