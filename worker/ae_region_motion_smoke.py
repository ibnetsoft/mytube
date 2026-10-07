"""Explicit native-AE smoke test with synthetic media; no project/database writes."""
from pathlib import Path
import hashlib
import json
import sys
from PIL import Image,ImageDraw
from ae_region_motion import render
from ae_media_utils import ffmpeg,run

def main():
    directory=Path(sys.argv[1]).resolve();directory.mkdir(parents=True,exist_ok=True)
    source=directory/'source.png';image=Image.new('RGB',(640,360),(240,240,240));draw=ImageDraw.Draw(image)
    draw.rectangle((270,80,320,210),fill=(220,40,40));draw.ellipse((285,68,305,88),fill=(30,30,30));image.save(source)
    data={'imageSha256':hashlib.sha256(source.read_bytes()).hexdigest(),'timeline':{'duration':4,'subtitles':[{'id':'s1','start':0,'end':4}]},'regions':[{'id':'arm','name':'Pivot arm smoke test','polygon':[[.415,.18],[.51,.18],[.51,.6],[.415,.6]],'anchor':[.46,.215],'action':'rotate','amplitude':20,'period':2,'cycles':2,'start':0,'subtitleId':'s1'}]}
    output=render(source,directory,data)
    for name,time in [('rest',0),('right',.5),('left',1.5)]:run([ffmpeg(),'-y','-ss',str(time),'-i',str(output),'-frames:v','1',str(directory/(name+'.png'))])
    import numpy as np
    centers=[]
    for name in ['rest','right','left']:
        pixels=np.asarray(Image.open(directory/(name+'.png')).convert('RGB'));mask=(pixels[:,:,0]>150)&(pixels[:,:,1]<100)&(pixels[:,:,2]<100)
        ys,xs=np.nonzero(mask)
        if len(xs)<100:raise RuntimeError('Rendered arm is missing')
        centers.append(float(xs.mean()))
    if max(centers)-min(centers)<25:raise RuntimeError('AE region did not move around the anchor')
    report={'passed':True,'centers':centers,'output':str(output)}
    (directory/'smoke-report.json').write_text(json.dumps(report),encoding='utf-8');print(json.dumps(report),flush=True)
if __name__=='__main__':main()
