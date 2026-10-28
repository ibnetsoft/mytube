"""Held-out colored step/checker control, independent of the scene and impulse fit."""
import argparse,json,subprocess,sys,time,shutil
from pathlib import Path
import numpy as np
from PIL import Image
import imageio_ffmpeg
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'worker'))
from effectcraft_render import binary,_execute
from effectcraft_compatibility import AE_COLOR,prepare_project
from adobe_tools import find_afterfx,find_aerender
D=ROOT/'output/effectcraft/psd-3376-scene29-residual-fix-20261021'
parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['project','render','ec']);args=parser.parse_args()
q=lambda p:json.dumps(str(p).replace('\\','/'),ensure_ascii=True)
if args.phase=='project':
    y,x=np.indices((128,256));a=np.zeros((128,256,3),dtype='uint8')
    a[:]=[24,80,144];a[:,128:]=[216,160,48]
    checker=((x//2+y//2)%2).astype(bool)&(y>=64);a[checker]=[200,224,232]
    Image.fromarray(a).save(D/'held-out-pattern.png')
    code=r'''app.beginSuppressDialogs();try{app.newProject();var p=app.project;p.workingSpace='Rec.709 Gamma 2.4';p.bitsPerChannel=16;p.linearizeWorkingSpace=false;p.linearBlending=false;
var source=p.importFile(new ImportOptions(new File(__IMAGE__)));
for(var i=0;i<2;i++){var c=p.items.addComp('heldout'+i,256,128,1,1,24),l=c.layers.add(source);
if(i){var fx=l.property('ADBE Effect Parade').addProperty('ADBE Gaussian Blur 2');fx.property(1).setValue(1.2);}
var rq=p.renderQueue.items.add(c);rq.timeSpanStart=0;rq.timeSpanDuration=1/24;var om=rq.outputModule(1),ok=false;
for(var j=0;j<om.templates.length;j++)if(/Lossless|무손실/.test(om.templates[j])){om.applyTemplate(om.templates[j]);ok=true;break;}
if(!ok)throw new Error('No lossless template');om.file=new File(__DIR__+'/ae-heldout'+i+'.avi');}
p.save(new File(__PROJECT__));var f=new File(__STATUS__);f.open('w');f.write('success');f.close();
}catch(e){var f=new File(__STATUS__);f.open('w');f.write('error|'+e.toString());f.close();}
try{app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);}catch(e){}app.endSuppressDialogs(false);app.scheduleTask('app.quit()',1000,false);
'''
    for token,path in [('IMAGE',D/'held-out-pattern.png'),('DIR',D),('PROJECT',D/'held-out.aep'),('STATUS',D/'held-out.status')]:code=code.replace('__'+token+'__',q(path))
    jsx=D/'held-out.jsx';jsx.write_text(code,encoding='utf8')
    subprocess.run(['node','-e',"new(require('node:vm').Script)(require('node:fs').readFileSync(process.argv[1],'utf8'))",str(jsx)],check=True)
    status=D/'held-out.status';status.unlink(missing_ok=True)
    subprocess.Popen([str(find_afterfx()),'-m','-r',str(jsx)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(180):
        if status.exists():
            print(status.read_text(),flush=True)
            if status.read_text()!='success':raise RuntimeError(status.read_text())
            break
        time.sleep(1)
    else:raise TimeoutError('Inspect AE diagnostic window')
elif args.phase=='render':
    with (D/'held-out-render.log').open('w') as log:subprocess.run([str(find_aerender()),'-project',str(D/'held-out.aep')],stdout=log,stderr=log,check=True,timeout=300)
    for i in range(2):subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-i',str(D/f'ae-heldout{i}.avi'),'-frames:v','1',str(D/f'ae-heldout{i}.png')],check=True)
    print('AE held-out controls rendered',flush=True)
else:
    project=D/'held-out.ecproj';cli=binary();_execute(cli,['script','--eval','null','--empty','--save-as',str(project),'--json'],D,'heldout-init')
    kernel=json.loads((D/'calibrated-blur-kernel.json').read_text())['kernel']
    code='var source=app.project.importFile(new ImportOptions(new File('+q(D/'held-out-pattern.png')+')));\n'
    code+="for(var i=0;i<3;i++){var c=app.project.items.addComp('heldout'+i,256,128,1,1,24),l=c.layers.add(source),e=l.property('ADBE Effect Parade');\n"
    code+="if(i==1){var f=e.addProperty('ADBE Gaussian Blur 2');f.property(1).setValue(1.2);}\n"
    code+="if(i==2){var before=e.addProperty('ec.color.levels');before.property('gamma').setValue(1/2.4);var f=e.addProperty('ec.color.cckernel'),weights="+json.dumps(kernel)+";for(var k=0;k<9;k++)f.property('k'+(k+1)).setValue(weights[k]);f.property('scale').setValue(1);f.property('offset').setValue(0);var after=e.addProperty('ec.color.levels');after.property('gamma').setValue(2.4);}}"
    jsx=D/'heldout-native.jsx';jsx.write_text(code,encoding='utf8')
    _execute(cli,['script',str(jsx),'--project',str(project),'--save','--json'],D,'heldout-build')
    _execute(cli,['exec','file.projectSettings','--params',json.dumps(AE_COLOR),'--project',str(project),'--save','--json'],D,'heldout-color')
    for i in range(3):_execute(cli,['render-frame',str(project),'--comp','heldout'+str(i),'--time','0','--out',str(D/f'ec-heldout{i}.png'),'--json'],D,'heldout-'+str(i))
    im=lambda p:np.asarray(Image.open(p).convert('RGB')).astype(float)
    aeoff,aeon=[im(D/f'ae-heldout{i}.png') for i in range(2)]
    off,before,after=[im(D/f'ec-heldout{i}.png') for i in range(3)]
    result=dict(off_mae=float(abs(aeoff-off).mean()),before_mae=float(abs(aeon-before).mean()),after_mae=float(abs(aeon-after).mean()),
                before_effect_delta_mae=float(abs((aeon-aeoff)-(before-off)).mean()),after_effect_delta_mae=float(abs((aeon-aeoff)-(after-off)).mean()))
    production=D/'held-out-production';production.mkdir(exist_ok=True)
    final=production/'scene.ecproj';shutil.copy2(project,final)
    prepare_project(cli,final,production,_execute)
    _execute(cli,['render-frame',str(final),'--comp','heldout1','--time','0','--out',str(production/'actual-worker.png'),'--json'],production,'actual-worker')
    actual=im(production/'actual-worker.png')
    result['actual_worker_mae']=float(abs(aeon-actual).mean())
    result['actual_worker_effect_delta_mae']=float(abs((aeon-aeoff)-(actual-off)).mean())
    assert result['actual_worker_mae'] < result['before_mae']*.05
    (D/'held-out-validation.json').write_text(json.dumps(result,indent=2));print(result,flush=True)
