"""One-frame, per-effect controls; AE/EC share original scene/effect scripts."""
import argparse,copy,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from effectcraft_render import binary,_execute
from adobe_tools import find_afterfx,find_aerender
D=ROOT/'output/effectcraft/psd-3376-scene29-effects-20261021';C=D/'controls';C.mkdir(exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['ae-project','ae-render','ec']);args=parser.parse_args()
cases=[('light_sweep',4.),('warm_dust_motes',4.),('shock_ring',4.5),('subtle_vignette',4.),('baseline4',4.),('baseline45',4.5)]
q=lambda p:json.dumps(str(p).replace('\\','/'),ensure_ascii=True)
if args.phase=='ae-project':
    text=(D/'build-ae.jsx').read_text(encoding='utf-8');text=text.split('var rq=app.project.renderQueue.items.add(comp)',1)[0]
    text+='\nvar cases='+json.dumps(cases)+';\n'
    text+=r'''
for(var z=0;z<cases.length;z++){
 var name=cases[z][0],cc=comp.duplicate();cc.name=name;
 for(var l=1;l<=cc.numLayers;l++){
  var layer=cc.layer(l),label=String(layer.name);
  if(label.indexOf('ae_effect_')===0)layer.enabled=label.indexOf('ae_effect_'+name+'_')===0;
 }
 var item=app.project.renderQueue.items.add(cc);item.timeSpanStart=cases[z][1];item.timeSpanDuration=1/24;
 var om=item.outputModule(1),found=false;
 for(var t=0;t<om.templates.length;t++)if(/Lossless|무손실/.test(om.templates[t])){om.applyTemplate(om.templates[t]);found=true;break;}
 if(!found)throw new Error('Lossless template missing');
 om.file=new File(__DIR__+'/ae-'+name+'.avi');
}
app.project.save(new File(__AEP__));
var s=new File(__STATUS__);s.open('w');s.write('success');s.close();
}catch(e){var s=new File(__STATUS__);s.open('w');s.write('error|'+e.toString());s.close();}
try{app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);}catch(e){}
app.endSuppressDialogs(false);app.scheduleTask('app.quit()',1000,false);
'''
    for token,path in [('DIR',C),('AEP',C/'controls.aep'),('STATUS',C/'build.status')]:text=text.replace('__'+token+'__',q(path))
    jsx=C/'build-controls.jsx';jsx.write_text(text,encoding='utf-8')
    subprocess.run(['node','-e',"new (require('node:vm').Script)(require('node:fs').readFileSync(process.argv[1],'utf8'))",str(jsx)],check=True)
    status=C/'build.status';status.unlink(missing_ok=True)
    with (C/'launch.log').open('w') as log:
        proc=subprocess.Popen([str(find_afterfx()),'-m','-r',str(jsx)],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        print('Controls AE PID',proc.pid,flush=True)
        for _ in range(180):
            if status.exists():
                s=status.read_text(encoding='utf-8',errors='replace');print(s,flush=True)
                if s!='success':raise RuntimeError(s)
                break
            time.sleep(1)
        else:raise TimeoutError('Controls project not ready')
elif args.phase=='ae-render':
    if (C/'build.status').read_text()!='success':raise RuntimeError('Project not ready')
    with (C/'render.log').open('w') as log:
        subprocess.run([str(find_aerender()),'-project',str(C/'controls.aep')],stdout=log,stderr=log,check=True,timeout=900)
    import imageio_ffmpeg
    for name,t in cases:
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-v','error','-i',str(C/('ae-'+name+'.avi')),'-frames:v','1',str(C/('ae-'+name+'.png'))],check=True)
    print('AE lossless controls ready',flush=True)
elif args.phase=='ec':
    original=json.loads((D/'rich.ecproj').read_text(encoding='utf-8'));cli=binary()
    for name,t in cases:
        data=copy.deepcopy(original)
        for item in data['items'].values():
            if item['name']!='ae_highlight_parallax_layered_scene':continue
            for layer in item['kind']['layers']:
                if layer['name'].startswith('ae_effect_'):
                    layer['switches']['video']=layer['name'].startswith('ae_effect_'+name+'_')
        path=C/('ec-'+name+'.ecproj');path.write_text(json.dumps(data),encoding='utf-8')
        _execute(cli,['render-frame',str(path),'--comp','ae_highlight_parallax_layered_scene','--time',str(t),'--out',str(C/('ec-'+name+'.png')),'--json'],C,'ec-'+name)
    print('EC lossless controls ready',flush=True)
