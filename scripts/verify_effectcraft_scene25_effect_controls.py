"""Per-effect cross-scene controls after the original scene25 regression run."""
import argparse,copy,json,subprocess,sys,time
from pathlib import Path
import imageio_ffmpeg,numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'worker'))
from adobe_tools import find_afterfx,find_aerender
from effectcraft_render import binary,_execute
D=ROOT/'output/effectcraft/psd-3376-scene25-v3-regression-20261021'
C=D/'effects';C.mkdir(exist_ok=True)
cases=[('light_sweep',4.),('warm_dust_motes',4.),('shock_ring',4.5),('subtle_vignette',4.)]
parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['ae-project','ae-render','ec','analyze']);args=parser.parse_args()
q=lambda p:json.dumps(str(p).replace('\\','/'),ensure_ascii=True)
if args.phase=='ae-project':
    code=r'''app.beginSuppressDialogs();try{app.open(new File(__SOURCE__));var p=app.project,rich=null;
for(var i=1;i<=p.numItems;i++)if(p.item(i).name==='scene25_rich')rich=p.item(i);
if(!rich)throw new Error('Missing experiment comp');while(p.renderQueue.numItems)p.renderQueue.item(1).remove();
var cases=__CASES__;for(var i=0;i<cases.length;i++){
var name=cases[i][0],c=rich.duplicate();c.name='control_'+name;
for(var j=1;j<=c.numLayers;j++){var l=c.layer(j),n=String(l.name);if(n.indexOf('ae_effect_')===0)l.enabled=n.indexOf('ae_effect_'+name+'_')===0;}
var rq=p.renderQueue.items.add(c);rq.timeSpanStart=cases[i][1];rq.timeSpanDuration=1/24;var om=rq.outputModule(1),ok=false;
for(var j=0;j<om.templates.length;j++)if(/Lossless|무손실/.test(om.templates[j])){om.applyTemplate(om.templates[j]);ok=true;break;}
if(!ok)throw new Error('Lossless template missing');om.file=new File(__DIR__+'/ae-'+name+'.avi');}
p.save(new File(__PROJECT__));var f=new File(__STATUS__);f.open('w');f.write('success');f.close();
}catch(e){var f=new File(__STATUS__);f.open('w');f.write('error|'+e.toString());f.close();}
try{app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);}catch(e){}app.endSuppressDialogs(false);app.scheduleTask('app.quit()',1000,false);
'''
    for token,path in [('SOURCE',D/'scene25-controls.aep'),('DIR',C),('PROJECT',C/'controls.aep'),('STATUS',C/'build.status')]:code=code.replace('__'+token+'__',q(path))
    code=code.replace('__CASES__',json.dumps(cases));jsx=C/'build.jsx';jsx.write_text(code,encoding='utf8')
    subprocess.run(['node','-e',"new(require('node:vm').Script)(require('node:fs').readFileSync(process.argv[1],'utf8'))",str(jsx)],check=True)
    status=C/'build.status';status.unlink(missing_ok=True)
    with (C/'launch.log').open('w') as log:
        p=subprocess.Popen([str(find_afterfx()),'-m','-r',str(jsx)],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(180):
            if status.exists():
                s=status.read_text();print(s,flush=True)
                if s!='success':raise RuntimeError(s)
                break
            time.sleep(1)
        else:raise TimeoutError('Inspect AE diagnostic window')
elif args.phase=='ae-render':
    if (C/'build.status').read_text()!='success':raise RuntimeError('AE controls not ready')
    with (C/'render.log').open('w') as log:subprocess.run([str(find_aerender()),'-project',str(C/'controls.aep')],stdout=log,stderr=log,check=True,timeout=300)
    for name,_ in cases:subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-i',str(C/('ae-'+name+'.avi')),'-frames:v','1',str(C/('ae-'+name+'.png'))],check=True)
    print('AE per-effect controls completed',flush=True)
elif args.phase=='ec':
    for version,source in [('before',D/'controls/rich-previous.ecproj'),('after',D/'rich/scene.ecproj')]:
        original=json.loads(source.read_text(encoding='utf8'))
        for name,t in cases:
            p=copy.deepcopy(original)
            c=next(i['kind'] for i in p['items'].values() if i['name']=='ae_highlight_parallax_layered_scene_sustained')
            for layer in c['layers']:
                if layer['name'].startswith('ae_effect_'):layer['switches']['video']=layer['name'].startswith('ae_effect_'+name+'_')
            project=C/('ec-'+version+'-'+name+'.ecproj');project.write_text(json.dumps(p),encoding='utf8')
            _execute(binary(),['render-frame',str(project),'--comp','ae_highlight_parallax_layered_scene_sustained','--time',str(t),'--out',str(C/('ec-'+version+'-'+name+'.png')),'--json'],C,'ec-'+version+'-'+name)
    print('Native per-effect controls completed',flush=True)
else:
    load=lambda p:np.asarray(Image.open(p).convert('RGB')).astype(float)
    results=[];sheet=Image.new('RGB',(1440,4*294),'#151515');draw=ImageDraw.Draw(sheet)
    for n,(name,t) in enumerate(cases):
        i=6 if name=='shock_ring' else 5
        a=load(C/('ae-'+name+'.png'));ao=load(D/'controls'/f'ae-baseline-{i}.png')
        b=load(C/('ec-before-'+name+'.png'));c=load(C/('ec-after-'+name+'.png'))
        bo=load(D/'controls'/f'ec-baseline-previous-{i}.png');co=load(D/'controls'/f'ec-baseline-{i}.png')
        da,db,dc=a-ao,b-bo,c-co
        row=dict(effect=name,time=t,before_pair_mae=float(abs(a-b).mean()),after_pair_mae=float(abs(a-c).mean()),before_effect_delta_mae=float(abs(da-db).mean()),after_effect_delta_mae=float(abs(da-dc).mean()),before_after_native_mae=float(abs(b-c).mean()))
        if name in ['warm_dust_motes','shock_ring']:assert np.array_equal(b,c),'Unchanged effect unexpectedly changed'
        if name=='warm_dust_motes':
            points=[];f=(4.-.8)/(9.-.8)
            for k in range(8):
                x=round((.82+np.sin(k*2.399)*.24*.7)*1920+1920*.015*f)
                y=round((.38+np.cos(k*2.399)*.24*.7)*1080-1080*.04*f)
                roi=(slice(max(0,y-5),min(1080,y+6)),slice(max(0,x-5),min(1920,x+6)))
                ae=float(abs(da[roi]).max());ec=float(abs(dc[roi]).max());assert ae>3 and ec>3
                points.append(dict(index=k,expected_xy=[x,y],ae_peak=ae,ec_peak=ec))
            row['particles_detected']=points
        results.append(row)
        for col,(label,delta) in enumerate([('AE',da),('EC previous',db),('EC current',dc)]):
            sheet.paste(Image.fromarray(np.clip(abs(delta)*12,0,255).astype('uint8')).resize((480,270)),(480*col,294*n+24));draw.text((480*col+8,294*n+7),name+' '+label+' delta x12',fill='white')
    sheet.save(C/'effect-delta-contact.jpg',quality=95);(C/'metrics.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2),flush=True)
