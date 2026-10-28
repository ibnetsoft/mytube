"""Read a preserved AE project and export diagnostic frames, without changing the original."""
import json,shutil,subprocess,sys,time
from PIL import Image
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'worker'))
from adobe_tools import find_afterfx
D=ROOT/'output/effectcraft/psd-3376-scene25-fix-20261021';D.mkdir(parents=True,exist_ok=True)
source=Path('C:/Users/kimse/AppData/Local/AIRStudio/AIRWorker/temp/ae_highlight/3376-025-effect-4f1f31dca3da0ae9/project/ae_highlight.aep')
impulse=Image.new('RGB',(64,64),'black');impulse.putpixel((32,32),(255,255,255));impulse.save(D/'impulse.png')
shutil.copy2(source,D/'ae-reference-copy.aep')
q=lambda p:json.dumps(str(p).replace('\\','/'),ensure_ascii=True)
code=r'''app.beginSuppressDialogs();
try {
 app.open(new File(__PROJECT__));
 var p=app.project, c=null;
 for(var i=1;i<=p.numItems;i++)if(p.item(i).name==='ae_highlight_parallax_layered_scene_sustained')c=p.item(i);
 if(!c)throw new Error('Missing reference comp');
 var report={workingSpace:p.workingSpace,bitsPerChannel:p.bitsPerChannel,linearizeWorkingSpace:p.linearizeWorkingSpace,blendGamma:p.blendingGamma,comp:c.name};
 var bg=c.layer('background'),fx=bg.property('ADBE Effect Parade').property(1);
 report.blurAmount=fx.property(1).value;report.blurEnabled=fx.enabled;
 var f=new File(__REPORT__);f.open('w');
 f.write('workingSpace='+report.workingSpace+'\n'+'bitsPerChannel='+report.bitsPerChannel+'\n'+'linearizeWorkingSpace='+report.linearizeWorkingSpace+'\n'+'blendGamma='+report.blendGamma+'\n'+'blurAmount='+report.blurAmount+'\n'+'blurEnabled='+report.blurEnabled);f.close();
 var queue=p.renderQueue;
 while(queue.numItems>0)queue.item(1).remove();
 var off=c.duplicate();off.name='blur_off_probe';off.layer('background').property('ADBE Effect Parade').property(1).enabled=false;
 function addFrame(comp,path,when){
  var item=queue.items.add(comp);item.timeSpanStart=when===undefined?1:when;item.timeSpanDuration=1/24;
  var om=item.outputModule(1),templates=om.templates,found=false;
  for(var k=0;k<templates.length;k++)if(/Lossless|무손실/.test(templates[k])){om.applyTemplate(templates[k]);found=true;break;}
  if(!found)throw new Error('Lossless template missing: '+templates.join(','));
  om.file=new File(path);
 }
 addFrame(c,__ON__);addFrame(off,__OFF__);
 var calibration=p.items.addComp('blur_impulse',64,64,1,1,24);
 var impulseLayer=calibration.layers.add(p.importFile(new ImportOptions(new File(__IMPULSE__))));
 var impulseBlur=impulseLayer.property('ADBE Effect Parade').addProperty('ADBE Gaussian Blur 2');impulseBlur.property(1).setValue(.35);
 addFrame(calibration,__CALIBRATION__,0);
 var zero=calibration.duplicate();zero.name='impulse_0';zero.layer(1).property('ADBE Effect Parade').property(1).property(1).setValue(0);addFrame(zero,__CAL0__,0);
 var half=calibration.duplicate();half.name='impulse_07';half.layer(1).property('ADBE Effect Parade').property(1).property(1).setValue(.7);addFrame(half,__CAL7__,0);
 var one=calibration.duplicate();one.name='impulse_1';one.layer(1).property('ADBE Effect Parade').property(1).property(1).setValue(1);addFrame(one,__CAL1__,0);
 var repeat=off.duplicate();repeat.name='blur_off_repeat';addFrame(repeat,__OFF_REPEAT__);
 queue.render();
 var s=new File(__STATUS__);s.open('w');s.write('success');s.close();
}catch(e){var s=new File(__STATUS__);s.open('w');s.write('error|'+e.toString());s.close();}
try {app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);}catch(closeError){}
app.endSuppressDialogs(false);app.scheduleTask('app.quit()',1000,false);
'''
for token,path in [('PROJECT',D/'ae-reference-copy.aep'),('REPORT',D/'ae-color-settings.txt'),('ON',D/'ae-lossless-blur-on.avi'),('OFF',D/'ae-lossless-blur-off.avi'),('IMPULSE',D/'impulse.png'),('CALIBRATION',D/'ae-impulse.avi'),('CAL0',D/'ae-impulse0.avi'),('CAL7',D/'ae-impulse07.avi'),('CAL1',D/'ae-impulse1.avi'),('OFF_REPEAT',D/'ae-lossless-blur-off-repeat.avi'),('STATUS',D/'ae-probe.status')]:code=code.replace('__'+token+'__',q(path))
jsx=D/'ae-probe.jsx';jsx.write_text(code,encoding='utf-8')
subprocess.run(['node','-e',"new (require('node:vm').Script)(require('node:fs').readFileSync(process.argv[1],'utf8'))",str(jsx)],check=True)
status=D/'ae-probe.status';status.unlink(missing_ok=True)
with (D/'ae-probe.log').open('w') as log:
    proc=subprocess.Popen([str(find_afterfx()),'-m','-r',str(jsx)],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
    print('AE probe PID',proc.pid,flush=True)
    for _ in range(180):
        if status.exists():
            result=status.read_text();print(result,flush=True)
            if not result.startswith('success'):raise RuntimeError(result)
            print((D/'ae-color-settings.txt').read_text(),flush=True);break
        time.sleep(1)
    else:raise TimeoutError('AE probe did not return a status; do not close other AE sessions')
