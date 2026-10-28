"""Isolated synthetic AE fixture. Never opens or updates a user's project."""
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'worker'))
from directed_graphics import DIRECTED_GRAPHICS_JSX
from adobe_tools import find_afterfx, find_aerender

D=ROOT/'output/direction-policy-v2';D.mkdir(parents=True,exist_ok=True)
path=lambda p: str(p.resolve()).replace('\\','/')
script='''var W=1280,H=720,DUR=3,IMPACT_AT=1,PRIMARY=[640,360];
function setOpacity(layer,a,av,b,bv,c,cv){var p=layer.property("Opacity");p.setValueAtTime(a,av);p.setValueAtTime(b,bv);p.setValueAtTime(c,cv);}
'''+DIRECTED_GRAPHICS_JSX+'\napp.beginSuppressDialogs();try {app.newProject();\n'
for tail in ('left','right','none'):
    plan={'speech_bubbles':{'bubbles':[{'text':'やめてください。','position':[.5,.4], 'tail':tail,'style':'dialogue','start_seconds':.2,'end_seconds':2.8}]}}
    script+='var PLAN='+json.dumps(plan,ensure_ascii=True)+';\n'
    script+='var comp=app.project.items.addComp("bubble_'+tail+'",W,H,1,DUR,24);comp.layers.addSolid([.15,.17,.20],"background",W,H,1,DUR);makeDirectedSpeechBubbles(comp);\n'
    for t in (.22,.28,.4,1.5,2.75):
        script+='var item=app.project.renderQueue.items.add(comp);item.timeSpanStart='+str(int(t*24)/24)+';item.timeSpanDuration=1/24;item.outputModule(1).file=new File('+json.dumps(path(D/f'{tail}-{t}.avi'))+');\n'
script+='app.project.save(new File('+json.dumps(path(D/'fixture.aep'))+'));var done=new File('+json.dumps(path(D/'success.txt'))+');done.open("w");done.write("Synthetic bubble fixtures rendered");done.close();app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);app.scheduleTask("app.quit()",600,false);\n'
script+='}catch(e){var f=new File('+json.dumps(path(D/'failure.txt'))+');f.open("w");f.write(e.toString()+" line="+e.line);f.close();app.scheduleTask("app.quit()",600,false);}finally{app.endSuppressDialogs(false);}'
jsx=D/'fixture.jsx';jsx.write_text(script,encoding='utf-8')
subprocess.run(['node','-e','new (require("node:vm").Script)(require("node:fs").readFileSync(process.argv[1],"utf8"))',str(jsx)],check=True)
if __name__=='__main__':
    (D/'success.txt').unlink(missing_ok=True)
    (D/'failure.txt').unlink(missing_ok=True)
    exe=find_afterfx()
    if not exe: raise RuntimeError('After Effects is unavailable')
    process=subprocess.Popen([str(exe),'-m','-r',str(jsx)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    print(json.dumps({'pid':process.pid,'fixture':str(jsx)}),flush=True)
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        if (D/'failure.txt').is_file():raise RuntimeError((D/'failure.txt').read_text())
        if (D/'success.txt').is_file(): print('AE fixture project prepared',flush=True);break
        time.sleep(1)
    else:raise TimeoutError('Isolated AE fixture did not complete; user projects were not touched')
    with (D/'render.log').open('w') as log:
        subprocess.run([str(find_aerender()),'-project',str(D/'fixture.aep')],stdout=log,stderr=log,check=True,timeout=240)
    from ae_media_utils import ffmpeg
    for clip in [*D.glob('*.avi'), *D.glob('*.mp4')]:
        subprocess.run([ffmpeg(),'-v','error','-y','-i',str(clip),'-frames:v','1',str(clip.with_suffix('.png'))],check=True,timeout=30)
    assert len(list(D.glob('*.png'))) == 15
    print('15 actual AE bubble frames complete',flush=True)
