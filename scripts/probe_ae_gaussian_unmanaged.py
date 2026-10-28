"""Independent AE Gaussian kernel without working/output profile conversions."""
import json,subprocess,sys,time
from pathlib import Path
import imageio_ffmpeg
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'worker'))
from adobe_tools import find_afterfx,find_aerender
D=ROOT/'output/effectcraft/psd-3376-scene29-residual-fix-20261021'
q=lambda p:json.dumps(str(p).replace('\\','/'),ensure_ascii=True)
if 'project' in sys.argv:
    code=r'''app.beginSuppressDialogs();try{app.newProject();var p=app.project;p.workingSpace='';p.bitsPerChannel=8;
function add(cc,name){var rq=p.renderQueue.items.add(cc);rq.timeSpanStart=0;rq.timeSpanDuration=1/24;
var om=rq.outputModule(1),ok=false;for(var j=0;j<om.templates.length;j++)if(/Lossless|무손실/.test(om.templates[j])){om.applyTemplate(om.templates[j]);ok=true;break;}
if(!ok)throw new Error('Lossless missing');om.file=new File(__DIR__+'/'+name+'.avi');
var f=new File(__DIR__+'/output-settings.txt');f.open('w');f.write(om.getSettings(GetSettingsFormat.STRING).toSource());f.close();}
var amounts=[0,.7,1,1.2,1.4,2,3];for(var a=0;a<amounts.length;a++){
var c=p.items.addComp('unmanaged'+amounts[a],64,64,1,1,24),l=c.layers.add(p.importFile(new ImportOptions(new File(__IMPULSE__))));
var f=l.property('ADBE Effect Parade').addProperty('ADBE Gaussian Blur 2');f.property(1).setValue(amounts[a]);add(c,'ae-unmanaged'+amounts[a]);}
p.save(new File(__OUT__));var f=new File(__STATUS__);f.open('w');f.write('success');f.close();
}catch(e){var f=new File(__STATUS__);f.open('w');f.write('error|'+e.toString());f.close();}
try{app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);}catch(e){}app.endSuppressDialogs(false);app.scheduleTask('app.quit()',1000,false);
'''
    for token,path in [('DIR',D),('IMPULSE',D/'impulse.png'),('OUT',D/'unmanaged-controls.aep'),('STATUS',D/'unmanaged.status')]:code=code.replace('__'+token+'__',q(path))
    jsx=D/'unmanaged-controls.jsx';jsx.write_text(code,encoding='utf-8')
    subprocess.run(['node','-e',"new(require('node:vm').Script)(require('node:fs').readFileSync(process.argv[1],'utf8'))",str(jsx)],check=True)
    status=D/'unmanaged.status';status.unlink(missing_ok=True)
    subprocess.Popen([str(find_afterfx()),'-m','-r',str(jsx)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(180):
        if status.exists():
            print(status.read_text(),flush=True)
            if status.read_text()!='success':raise RuntimeError(status.read_text())
            break
        time.sleep(1)
    else:raise TimeoutError('Inspect AE diagnostic window')
else:
    with (D/'unmanaged-render.log').open('w') as log:subprocess.run([str(find_aerender()),'-project',str(D/'unmanaged-controls.aep')],stdout=log,stderr=log,check=True,timeout=300)
    import numpy as np
    from PIL import Image
    for x in [0,.7,1,1.2,1.4,2,3]:
        path=D/('ae-unmanaged'+str(x)+'.png');subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-i',str(path.with_suffix('.avi')),'-frames:v','1',str(path)],check=True)
        a=np.asarray(Image.open(path));print(x,a[32,28:37,0].tolist(),a[:,:,0].sum(),flush=True)
