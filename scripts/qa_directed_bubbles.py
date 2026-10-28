"""Check actual AE fixture frames, including the tail during fades/scaling."""
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import label

D=Path(__file__).resolve().parents[1]/'output/direction-policy-v2'
canvas=Image.new('RGB',(2400,600),'#262930');draw=ImageDraw.Draw(canvas)
rows=[]; times=[.22,.28,.4,1.5,2.75]
def component(path):
    image=Image.open(path).convert('RGB'); pixels=np.array(image).astype(float)
    labels,_=label(np.min(pixels-pixels[0,0],axis=2)>5)
    sizes=np.bincount(labels.ravel()); sizes[0]=0
    body=labels==int(sizes.argmax())
    y,x=np.where(body)
    return image,int(y.max()),int(body.sum())

for i,tail in enumerate(('left','right','none')):
    for j,t in enumerate(times):
        file=D/f'{tail}-{t}.png'; image,bottom,area=component(file)
        _,body_bottom,_=component(D/f'none-{t}.png')
        connected=tail=='none' or bottom>body_bottom+5
        assert connected,(file.name,'tail is not part of the connected body')
        rows.append({'file':file.name,'body_tail_connected':connected,'connected_area':area,
                     'tail_extension_px':bottom-body_bottom})
        canvas.paste(image.crop((400,190,880,370)),(j*480,i*200+20))
        draw.text((j*480+8,i*200+2),tail+' '+str(t)+'s',fill='white')
canvas.save(D/'bubble-animation-contact.png')
(D/'bubble-qa.json').write_text(json.dumps({'engine':'After Effects actual render','frames':rows,'result':'passed'},indent=2))
print('15 AE frames: body/tail connection preserved during common fade and scale')
