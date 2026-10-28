"""Read the saved AE blend mode and measure mask coverage on independent white/black controls."""
import argparse,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'worker'))
from adobe_tools import find_afterfx,find_aerender
OLD=ROOT/'output/effectcraft/psd-3376-scene29-effects-20261021'
D=ROOT/'output/effectcraft/psd-3376-scene29-vignette-fix-20261021';D.mkdir(parents=True,exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['project','render','ec','analyze']);args=parser.parse_args()
q=lambda p:json.dumps(str(p).replace('\\','/'),ensure_ascii=True)
if args.phase=='project':
    code=r'''app.beginSuppressDialogs();try{
app.open(new File(__ORIGINAL__));var p=app.project,c=null;
for(var i=1;i<=p.numItems;i++)if(p.item(i).name==='ae_highlight_parallax_layered_scene')c=p.item(i);
if(!c)throw new Error('Missing original comp');
var f=new File(__SETTINGS__);f.open('w');f.write('linearBlending='+p.linearBlending+'\nworkingSpace='+p.workingSpace+'\nbitsPerChannel='+p.bitsPerChannel+'\nlinearizeWorkingSpace='+p.linearizeWorkingSpace);f.close();
var originalMask=c.layer('ae_effect_subtle_vignette_3').property('ADBE Mask Parade').property(1);
var path=originalMask.property('ADBE Mask Shape').value,feather=originalMask.property('ADBE Mask Feather').value;
p.linearBlending=false;while(p.renderQueue.numItems)p.renderQueue.item(1).remove();
function output(comp,name){var rq=p.renderQueue.items.add(comp);rq.timeSpanStart=0;rq.timeSpanDuration=1/24;var om=rq.outputModule(1),found=false;
for(var j=0;j<om.templates.length;j++)if(/Lossless|무손실/.test(om.templates[j])){om.applyTemplate(om.templates[j]);found=true;break;}
if(!found)throw new Error('Lossless template missing');om.file=new File(__DIR__+'/ae-'+name+'.avi');}
function matte(name){var m=p.items.addComp(name,1920,1080,1,1,24);m.layers.addSolid([0,0,0],'black',1920,1080,1,1);return m;}
var v=matte('vignette_matte'),l=v.layers.addSolid([1,1,1],'white',1920,1080,1,1),mask=l.property('ADBE Mask Parade').addProperty('ADBE Mask Atom');
mask.property('ADBE Mask Shape').setValue(path);mask.property('ADBE Mask Feather').setValue(feather);mask.inverted=true;output(v,'vignette-matte');
var amounts=[100,200,400];for(var a=0;a<amounts.length;a++){
var name='edge'+amounts[a],m=matte(name),l=m.layers.addSolid([1,1,1],'white',1920,1080,1,1),g=l.property('ADBE Mask Parade').addProperty('ADBE Mask Atom');
var s=new Shape();s.vertices=[[-5000,-5000],[960,-5000],[960,6000],[-5000,6000]];s.inTangents=[[0,0],[0,0],[0,0],[0,0]];s.outTangents=s.inTangents;s.closed=true;
g.property('ADBE Mask Shape').setValue(s);g.property('ADBE Mask Feather').setValue([amounts[a],100]);output(m,name);}
p.save(new File(__PROJECT__));var f=new File(__STATUS__);f.open('w');f.write('success');f.close();
}catch(e){var f=new File(__STATUS__);f.open('w');f.write('error|'+e.toString());f.close();}
try{app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);}catch(e){}app.endSuppressDialogs(false);app.scheduleTask('app.quit()',1000,false);
'''
    for token,path in [('ORIGINAL',OLD/'rich-reference.aep'),('SETTINGS',D/'ae-original-settings.txt'),('DIR',D),('PROJECT',D/'feather-controls.aep'),('STATUS',D/'feather-build.status')]:code=code.replace('__'+token+'__',q(path))
    jsx=D/'build-feather-controls.jsx';jsx.write_text(code,encoding='utf-8')
    subprocess.run(['node','-e',"new (require('node:vm').Script)(require('node:fs').readFileSync(process.argv[1],'utf8'))",str(jsx)],check=True)
    status=D/'feather-build.status';status.unlink(missing_ok=True)
    with (D/'feather-launch.log').open('w') as log:
        p=subprocess.Popen([str(find_afterfx()),'-m','-r',str(jsx)],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        print('AE control PID',p.pid,flush=True)
        for _ in range(180):
            if status.exists():
                result=status.read_text(encoding='utf-8',errors='replace');print(result,flush=True)
                if result!='success':raise RuntimeError(result)
                break
            time.sleep(1)
        else:raise TimeoutError('AE controls did not return; inspect diagnostic window')
elif args.phase=='render':
    if (D/'feather-build.status').read_text()!='success':raise RuntimeError('AE controls not ready')
    with (D/'feather-render.log').open('w') as log:subprocess.run([str(find_aerender()),'-project',str(D/'feather-controls.aep')],stdout=log,stderr=log,check=True,timeout=900)
    import imageio_ffmpeg
    for name in ['vignette-matte','edge100','edge200','edge400']:
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-v','error','-i',str(D/('ae-'+name+'.avi')),'-frames:v','1',str(D/('ae-'+name+'.png'))],check=True)
    print('AE feather controls rendered',flush=True)
elif args.phase=='ec':
    from effectcraft_render import binary,_execute
    from effectcraft_compatibility import prepare_project
    cli=binary();project=D/'ec-feather-controls.ecproj'
    _execute(cli,['script','--eval','null','--empty','--save-as',str(project),'--json'],D,'ec-initialize')
    code=r'''
var amounts=[100,200,400],factors=[1,.75];
for(var r=0;r<factors.length;r++)for(var a=0;a<amounts.length;a++){
var name='edge'+amounts[a]+'x'+factors[r],m=app.project.items.addComp(name,1920,1080,1,1,24);
m.layers.addSolid([0,0,0],'black',1920,1080,1,1);var l=m.layers.addSolid([1,1,1],'white',1920,1080,1,1);
var mask=l.property('ADBE Mask Parade').addProperty('ADBE Mask Atom'),s=new Shape();
s.vertices=[[-5000,-5000],[960,-5000],[960,6000],[-5000,6000]];s.inTangents=[[0,0],[0,0],[0,0],[0,0]];s.outTangents=s.inTangents;s.closed=true;
mask.property('ADBE Mask Shape').setValue(s);mask.property('ADBE Mask Feather').setValue([amounts[a]*factors[r],100]);}
'''
    jsx=D/'ec-feather-controls.jsx';jsx.write_text(code,encoding='utf-8')
    _execute(cli,['script',str(jsx),'--project',str(project),'--save','--json'],D,'ec-build')
    prepare_project(cli,project,D,_execute)
    for factor in [1,.75]:
        for amount in [100,200,400]:
            name='edge'+str(amount)+'x'+str(factor)
            _execute(cli,['render-frame',str(project),'--comp',name,'--time','0','--out',str(D/('ec-'+name+'.png')),'--json'],D,'ec-'+name)
    print('Native feather controls rendered',flush=True)
else:
    import numpy as np
    from PIL import Image
    result=[]
    for amount in [100,200,400]:
        im=np.asarray(Image.open(D/('ae-edge'+str(amount)+'.png')).convert('RGB')).astype(float)
        profile=im[400:680,:,0].mean(0)/255
        x=np.arange(1920)+.5
        lo=np.interp(.158655,profile[400:1500][::-1],x[400:1500][::-1]);hi=np.interp(.841345,profile[400:1500][::-1],x[400:1500][::-1])
        row=dict(feather=amount,sigma_from_profile=float((lo-hi)/2),sigma_per_feather=float((lo-hi)/(2*amount)))
        for factor in [1,.75]:
            file=D/('ec-edge'+str(amount)+'x'+str(factor)+'.png')
            if file.exists():
                e=np.asarray(Image.open(file).convert('RGB')).astype(float)[400:680,:,0].mean(0)/255
                le=np.interp(.158655,e[400:1500][::-1],x[400:1500][::-1]);he=np.interp(.841345,e[400:1500][::-1],x[400:1500][::-1])
                row['ec_factor_'+str(factor)]={'sigma':float((le-he)/2),'central_profile_mae_255':float(abs(profile[600:1320]-e[600:1320]).mean()*255)}
        result.append(row)
    (D/'ae-feather-profiles.json').write_text(json.dumps(result,indent=2));print((D/'ae-original-settings.txt').read_text());print(json.dumps(result),flush=True)
