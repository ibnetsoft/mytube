"""Lossless scene and independent blur controls for the preserved scene-29 comparison."""
import argparse,json,subprocess,sys,time
from pathlib import Path
import imageio_ffmpeg
from PIL import Image

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'worker'))
from adobe_tools import find_afterfx,find_aerender
from effectcraft_render import binary,_execute
OLD=ROOT/'output/effectcraft/psd-3376-scene29-effects-20261021'
FIX=ROOT/'output/effectcraft/psd-3376-scene29-vignette-fix-20261021'
D=ROOT/'output/effectcraft/psd-3376-scene29-residual-fix-20261021';D.mkdir(exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['project','ae','ec','analyze']);args=parser.parse_args()
times=[0,29/24,2.5,3.5,4,4.5,6.5,9,239/24]
q=lambda p:json.dumps(str(p).replace('\\','/'),ensure_ascii=True)
if args.phase=='project':
    im=Image.new('RGB',(64,64),'black');im.putpixel((32,32),(255,255,255));im.save(D/'impulse.png')
    code=r'''app.beginSuppressDialogs();try{
app.open(new File(__AEP__));var p=app.project,c=null;
for(var i=1;i<=p.numItems;i++)if(p.item(i).name==='ae_highlight_parallax_layered_scene')c=p.item(i);
if(!c)throw new Error('Missing original comp');
while(p.renderQueue.numItems)p.renderQueue.item(1).remove();
function add(cc,name,t){var rq=p.renderQueue.items.add(cc);rq.timeSpanStart=t;rq.timeSpanDuration=1/24;
var om=rq.outputModule(1),ok=false;for(var j=0;j<om.templates.length;j++)if(/Lossless|무손실/.test(om.templates[j])){om.applyTemplate(om.templates[j]);ok=true;break;}
if(!ok)throw new Error('Lossless template missing');om.file=new File(__DIR__+'/'+name+'.avi');}
var times=__TIMES__;for(var j=0;j<times.length;j++)add(c,'ae-rich-'+j,times[j]);
var off=c.duplicate();off.name='all_effects_off';for(var j=1;j<=off.numLayers;j++)if(off.layer(j).name.indexOf('ae_effect_')===0)off.layer(j).enabled=false;
add(off,'ae-baseline',4);off.layer('background').property('ADBE Effect Parade').property(1).enabled=false;add(off,'ae-blur-off',4);
var amounts=[0,.7,1,1.2,1.4,2];for(var a=0;a<amounts.length;a++){
var cc=p.items.addComp('impulse'+amounts[a],64,64,1,1,24),l=cc.layers.add(p.importFile(new ImportOptions(new File(__IMPULSE__))));
var fx=l.property('ADBE Effect Parade').addProperty('ADBE Gaussian Blur 2');fx.property(1).setValue(amounts[a]);add(cc,'ae-impulse'+amounts[a],0);}
p.save(new File(__OUT__));var f=new File(__STATUS__);f.open('w');f.write('success');f.close();
}catch(e){var f=new File(__STATUS__);f.open('w');f.write('error|'+e.toString());f.close();}
try{app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);}catch(e){}app.endSuppressDialogs(false);app.scheduleTask('app.quit()',1000,false);
'''
    for token,path in [('AEP',OLD/'rich-reference.aep'),('DIR',D),('IMPULSE',D/'impulse.png'),('OUT',D/'lossless-controls.aep'),('STATUS',D/'build.status')]:code=code.replace('__'+token+'__',q(path))
    code=code.replace('__TIMES__',json.dumps(times));jsx=D/'build-lossless-controls.jsx';jsx.write_text(code,encoding='utf-8')
    subprocess.run(['node','-e',"new (require('node:vm').Script)(require('node:fs').readFileSync(process.argv[1],'utf8'))",str(jsx)],check=True)
    status=D/'build.status';status.unlink(missing_ok=True)
    with (D/'launch.log').open('w') as log:
        p=subprocess.Popen([str(find_afterfx()),'-m','-r',str(jsx)],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        print('AE diagnostic PID',p.pid,flush=True)
        for _ in range(180):
            if status.exists():
                s=status.read_text();print(s,flush=True)
                if s!='success':raise RuntimeError(s)
                break
            time.sleep(1)
        else:raise TimeoutError('Inspect diagnostic AE window')
elif args.phase=='ae':
    if (D/'build.status').read_text()!='success':raise RuntimeError('AE project not ready')
    with (D/'ae-render.log').open('w') as log:subprocess.run([str(find_aerender()),'-project',str(D/'lossless-controls.aep')],stdout=log,stderr=log,check=True,timeout=900)
    for f in D.glob('ae-*.avi'):
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-i',str(f),'-frames:v','1',str(f.with_suffix('.png'))],check=True)
    print('AE lossless frames ready',flush=True)
elif args.phase=='ec':
    for i,t in enumerate(times):
        _execute(binary(),['render-frame',str(FIX/'scene.ecproj'),'--comp','ae_highlight_parallax_layered_scene','--time',str(t),'--out',str(D/f'ec-rich-{i}.png'),'--json'],D,'ec-rich-'+str(i))
    print('Native lossless frames ready',flush=True)
else:
    import numpy as np
    def im(f):return np.asarray(Image.open(f).convert('RGB')).astype(float)
    rows=[]
    for i,t in enumerate(times):
        a,b=im(D/f'ae-rich-{i}.png'),im(D/f'ec-rich-{i}.png');rows.append(dict(time=t,mae=float(abs(a-b).mean()),bias=(a-b).mean((0,1)).tolist()))
    for amount in [0,.7,1,1.2,1.4,2]:
        a=im(D/('ae-impulse'+str(amount)+'.png'));print('impulse',amount,a[32,29:36,0].tolist(),'sum',a[:,:,0].sum(),flush=True)
    (D/'lossless-metrics.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows),flush=True)
