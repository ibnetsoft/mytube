"""Render the authorized scenes 1-25 in AE; keep results local for review."""
from pathlib import Path
import json, sys, subprocess, time, re, hashlib
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'worker'))
import worker_config
from adobe_tools import find_afterfx, find_aerender
import ae_highlight_worker as ae
import imageio_ffmpeg

SOURCE = ROOT / '_dev/artifacts/ae_3373_review'
RUN = ROOT / '_dev/artifacts/ae_3373_run/v1'
RUN.mkdir(parents=True, exist_ok=True)
FF = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = 1920, 1080, 24

# (search rectangle %, opacity keyframes %, radius % of width)
LIGHTS = {
    1: [([4, 0, 24, 38], [4, 5, 4, 4], 4), ([68, 25, 82, 55], [3, 4, 3, 3], 2)],
    4: [([65, 60, 92, 98], [6, 8, 6, 7], 3)],
    5: [([0, 52, 38, 98], [5, 6, 5, 5], 3)],
    6: [([0, 45, 40, 95], [5, 5, 5, 4], 3)],
    7: [([3, 20, 24, 52], [4, 5, 4, 4], 1.5)],
    8: [([82, 0, 99, 34], [4, 4, 4, 4], 1.5)],
    10: [([80, 20, 99, 50], [4, 4, 4, 3], 1.5)],
    11: [([78, 0, 99, 44], [4, 5, 4, 4], 3)],
    13: [([44, 20, 74, 64], [3, 4, 4, 4], 2)],
    15: [([66, 34, 90, 83], [3, 3, 3, 3], 3)],
    16: [([74, 52, 97, 95], [3, 4, 4, 3], 2.5)],
}
CAMERAS = {
    19: ([29, 46], [100, 102]), 20: ([45, 48], [100, 101.5]),
    21: ([50, 50], [101.5, 101.5]), 22: ([52, 45], [100, 101.5]),
    23: ([57, 43], [100, 102]), 24: ([39, 61], [100, 101.5]),
    25: ([50, 48], [100, 102]),
}

def command(args, log):
    with log.open('wb') as stream:
        subprocess.run(args, stdout=stream, stderr=subprocess.STDOUT, check=True)

def metadata(path):
    gen = imageio_ffmpeg.read_frames(str(path))
    info = next(gen)
    gen.close()
    return info

def tracking(n, path, duration):
    entries = LIGHTS.get(n, [])
    if not entries:
        return []
    folder = RUN / f'track-{n:02d}'
    folder.mkdir(exist_ok=True)
    command([FF, '-hide_banner', '-loglevel', 'error', '-i', str(path),
             '-vf', 'fps=4,scale=480:270', '-y', str(folder/'%03d.png')], folder/'extract.log')
    output = []
    for rect, opacity, radius in entries:
        positions = []
        for i, f in enumerate(sorted(folder.glob('*.png'))):
            a = np.asarray(Image.open(f).convert('RGB'), dtype=float)
            x1, y1, x2, y2 = [int(v * (480 if j % 2 == 0 else 270) / 100) for j, v in enumerate(rect)]
            crop = a[y1:y2, x1:x2]
            # Warm, bright pixels, rather than skin or blue night sky.
            score = np.maximum(crop[..., 0] - 170, 0) * np.maximum(crop[..., 1] - 135, 0)
            score *= np.maximum(crop[..., 0] - crop[..., 2], 0)
            if score.sum() < 1:
                raise RuntimeError(f'Scene {n}: no reliable light pixels in {rect}')
            yy, xx = np.indices(score.shape)
            x = float((xx * score).sum() / score.sum() + x1) * 4
            y = float((yy * score).sum() / score.sum() + y1) * 4
            positions.append([min(duration, (i / 4) * duration / metadata(path)['duration']), x, y])
        output.append({'positions': positions, 'opacity': opacity, 'radius': radius * W / 100})
    return output

def build():
    project = json.loads((ROOT/'_dev/artifacts/current_ae_project.json').read_text(encoding='utf-8'))
    scenes = []
    for s in project['project_payload']['structure']['scenes'][:25]:
        n = s['scene_number']
        src = SOURCE / f'{n:02d}.mp4'
        if not src.exists(): src = SOURCE / f'{n:02d}.png'
        if not src.exists(): raise FileNotFoundError(src)
        dur = float(s['metadata']['duration_seconds'])
        info = metadata(src) if src.suffix == '.mp4' else {'size': Image.open(src).size}
        scenes.append({'n': n, 'source': src.as_posix(), 'duration': dur,
                       'source_duration': info.get('duration'), 'camera': CAMERAS.get(n),
                       'lights': tracking(n, src, dur),
                       'sha256': hashlib.sha256(src.read_bytes()).hexdigest()})
    (RUN/'plan.json').write_text(json.dumps(scenes, indent=2), encoding='utf-8')
    return scenes

JSX = r'''
app.beginSuppressDialogs();
function writeReceipt(s){var f=new File(STATUS);f.encoding='UTF-8';f.open('w');f.write(s);f.close();}
function ellipse(cx,cy,rx,ry){var s=new Shape();s.vertices=[[cx-rx,cy],[cx,cy-ry],[cx+rx,cy],[cx,cy+ry]];var k=.5522848;s.inTangents=[[0,ry*k],[-rx*k,0],[0,-ry*k],[rx*k,0]];s.outTangents=[[0,-ry*k],[rx*k,0],[0,ry*k],[-rx*k,0]];s.closed=true;return s;}
function rectangle(x1,y1,x2,y2){var s=new Shape();s.vertices=[[x1,y1],[x2,y1],[x2,y2],[x1,y2]];s.closed=true;return s;}
function exposure(layer,v){var e=layer.property('ADBE Effect Parade').addProperty('ADBE Exposure2');e.property('ADBE Exposure2-0003').setValue(v);return e.property('ADBE Exposure2-0003');}
function ease(p){for(var i=1;i<=p.numKeys;i++){var spatial=p.propertyValueType==PropertyValueType.TwoD_SPATIAL||p.propertyValueType==PropertyValueType.ThreeD_SPATIAL;var d=spatial?1:(p.value.length||1);var arr=[];for(var j=0;j<d;j++)arr.push(new KeyframeEase(0,25));p.setTemporalEaseAtKey(i,arr,arr);}}
function correction(base,rect,value,name){var l=base.duplicate();l.name=name;var m=l.property('ADBE Mask Parade').addProperty('ADBE Mask Atom');m.property('ADBE Mask Shape').setValue(rectangle(rect[0]*W/100,rect[1]*H/100,rect[2]*W/100,rect[3]*H/100));m.property('ADBE Mask Feather').setValue([70,70]);exposure(l,value);return l;}
try {
 app.newProject();app.project.bitsPerChannel=16;app.project.workingSpace='Rec.709 Gamma 2.4';
 for(var z=0;z<PLAN.length;z++){
  var p=PLAN[z],D=p.duration,n=p.n,comp=app.project.items.addComp('scene_'+('0'+n).slice(-2),W,H,1,D,FPS);
  var footage=app.project.importFile(new ImportOptions(new File(p.source)));
  var base=comp.layers.add(footage);base.name='original_scene_'+n;base.audioEnabled=false;
  // Normalize the input dimensions once; all masks use the comp-sized precomp.
  var fit=Math.max(W/footage.width,H/footage.height)*100;base.property('ADBE Transform Group').property('ADBE Scale').setValue([fit,fit]);
  if(p.source_duration)base.stretch=100*D/(p.used_source_duration||p.source_duration);
  base.outPoint=D;
  var pre=comp.layers.precompose([base.index],'source_'+('0'+n).slice(-2),true);base=comp.layer(1);base.audioEnabled=false;
  if(p.camera){var pivot=p.camera[0],scale=p.camera[1];var tr=base.property('ADBE Transform Group');tr.property('ADBE Anchor Point').setValue([pivot[0]*W/100,pivot[1]*H/100]);tr.property('ADBE Position').setValue([pivot[0]*W/100,pivot[1]*H/100]);var sc=tr.property('ADBE Scale');sc.setValueAtTime(0,[scale[0],scale[0]]);sc.setValueAtTime(D,[scale[1],scale[1]]);ease(sc);
   if(n==21){var pos=tr.property('ADBE Position');pos.setValueAtTime(0,[W/2+8,H/2]);pos.setValueAtTime(D,[W/2-8,H/2]);ease(pos);}
   if(n==23){sc.setValueAtTime(1.8,[101,101]);ease(sc);}
   if(n==25){sc.setValueAtTime(5.1,[100.8,100.8]);sc.setValueAtTime(6.8,[101.5,101.5]);ease(sc);}
  }
  for(var j=0;j<p.lights.length;j++){
   var li=p.lights[j],l=base.duplicate();l.name='tracked_light_'+j;l.blendingMode=BlendingMode.SCREEN;
   var m=l.property('ADBE Mask Parade').addProperty('ADBE Mask Atom');m.property('ADBE Mask Feather').setValue([35,35]);m.property('ADBE Mask Offset').setValue(4);
   var path=m.property('ADBE Mask Shape');for(var k=0;k<li.positions.length;k++){var pt=li.positions[k];path.setValueAtTime(pt[0],ellipse(pt[1],pt[2],li.radius,li.radius*.9));}
   var blur=l.property('ADBE Effect Parade').addProperty('ADBE Gaussian Blur 2');blur.property(1).setValue(18);
   var protect=l.property('ADBE Mask Parade').addProperty('ADBE Mask Atom');protect.maskMode=MaskMode.SUBTRACT;protect.property('ADBE Mask Shape').setValue(rectangle(-100,H*.78,W+100,H+100));protect.property('ADBE Mask Feather').setValue([12,12]);
   var op=l.property('ADBE Transform Group').property('ADBE Opacity');var ts=[0,.3*D,.65*D,D];for(var k=0;k<4;k++)op.setValueAtTime(ts[k],li.opacity[k]);ease(op);
  }
  if(n==3){correction(base,[0,0,14,100],-.08,'edge_left');correction(base,[85,0,100,100],-.08,'edge_right');}
  if(n==9)correction(base,[0,0,100,100],-.12,'daylight_continuity_review');
  if(n==14)correction(base,[43,0,60,45],-.06,'outside_blue');
  if(n==17){correction(base,[44,8,100,27],-.08,'veranda_background');correction(base,[14,18,38,65],.03,'inner_room');}
  if(n==18)correction(base,[0,0,100,27],-.06,'night_background');
  if(n==19)correction(base,[0,0,100,23],-.04,'night_background');
  if(n==20){var l=correction(base,[0,10,25,88],0,'morning_window');var e=l.property('ADBE Effect Parade').property(1).property('ADBE Exposure2-0003');e.setValueAtTime(0,0);e.setValueAtTime(.8,.05);ease(e);}
  if(n==21)correction(base,[60,0,100,68],-.04,'room_negative_space');
  if(n==24){var l=correction(base,[30,70,46,91],0,'paper_packet');var e=l.property('ADBE Effect Parade').property(1).property('ADBE Exposure2-0003');e.setValueAtTime(0,0);e.setValueAtTime(5,0);e.setValueAtTime(5.4,.07);e.setValueAtTime(D,.07);ease(e);}
  if(n==25){var l=correction(base,[64,20,80,49],0,'daughter_face');var e=l.property('ADBE Effect Parade').property(1).property('ADBE Exposure2-0003');e.setValueAtTime(0,0);e.setValueAtTime(6.4,0);e.setValueAtTime(6.8,.05);e.setValueAtTime(D,.05);ease(e);}
  var q=app.project.renderQueue.items.add(comp),om=q.outputModule(1),templates=om.templates,chosen='';for(var k=0;k<templates.length;k++)if(templates[k].indexOf('H.264')==0&&templates[k].indexOf('15Mbps')>=0)chosen=templates[k];if(!chosen)throw new Error('No H264 15Mbps template');om.applyTemplate(chosen);om.file=new File(OUT+'/scene_'+('0'+n).slice(-2)+'.mp4');
 }
 app.project.save(new File(PROJECT));writeReceipt('success|'+PROJECT);
}catch(e){writeReceipt('error|'+e.toString()+'|line='+e.line);}
app.endSuppressDialogs(false);app.scheduleTask('app.quit()',1000,false);
'''

def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    plan_file=RUN/'plan.json'
    plan=json.loads(plan_file.read_text()) if plan_file.exists() else build()
    aep=RUN/'scenes_01_25.aep';jsx=RUN/'scenes_01_25.jsx'
    if not aep.exists():
        text=JSX
        for key,value in [('PLAN',plan),('STATUS',jsx.with_suffix('.status.txt').as_posix()),('PROJECT',aep.as_posix()),('OUT',RUN.as_posix())]:
            text=re.sub(r'\b'+key+r'\b',lambda _:json.dumps(value),text)
        text='var W=1920,H=1080,FPS=24;\n'+text
        jsx.write_text(text,encoding='utf-8')
        # The optional UI recovery package is absent. Receipt errors/timeouts
        # remain fatal; never claim to have recovered a modal dialog.
        ae.continue_crash_recovery=lambda:False
        ae._run_afterfx_script(find_afterfx(),jsx,aep,timeout=240)
    status=[]
    for p in plan:
        n=p['n'];target=RUN/f'scene_{n:02d}.mp4'
        if not target.exists() or target.stat().st_size<10000:
            print(f'Rendering AE scene {n:02d}/25',flush=True)
            command([str(find_aerender()),'-project',str(aep),'-comp',f'scene_{n:02d}',
                     '-output',str(target)],RUN/f'render_{n:02d}.log')
        info=metadata(target)
        if abs(info['duration']-p['duration'])>1/FPS+.03 or tuple(info['size'])!=(W,H):
            raise RuntimeError(f'Scene {n} failed duration/resolution QA: {info}')
        samples=[]
        for j,t in enumerate([.2,p['duration']/2,p['duration']-.2]):
            frame=RUN/f'qa_{n:02d}_{j}.jpg'
            command([FF,'-hide_banner','-loglevel','error','-ss',str(t),'-i',str(target),
                     '-frames:v','1','-vf','scale=480:270','-y',str(frame)],RUN/'frame.log')
            samples.append(frame)
        status.append({'scene':n,'output':str(target),'duration':info['duration'],
                       'dimensions':info['size'],'fps':info['fps'],'status':'rendered_review_pending'})
        (RUN/'receipt.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
        print(f'AE scene {n:02d} complete: {info["duration"]}s',flush=True)
    for start in [1,6,11,16,21]:
        canvas=Image.new('RGB',(1440,1500),'#161616');draw=ImageDraw.Draw(canvas)
        for row,n in enumerate(range(start,start+5)):
            draw.text((10,row*300+4),f'AE SCENE {n:02d} / start, middle, end',fill='white')
            for j in range(3):canvas.paste(Image.open(RUN/f'qa_{n:02d}_{j}.jpg'),(j*480,row*300+25))
        canvas.save(RUN/f'contact_{start:02d}.jpg')
    print('25 AE scenes rendered; visual review and timing confirmation pending.',flush=True)

if __name__=='__main__':main()
