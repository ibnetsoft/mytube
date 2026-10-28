"""Read actual AE/native key metadata and all 240 frame transforms, without editing sources."""
import argparse,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'worker'))
from adobe_tools import find_afterfx
from effectcraft_render import binary,_execute
D=ROOT/'output/effectcraft/psd-3376-scene25-motion-fix-20261021';D.mkdir(exist_ok=True)
P25=ROOT/'output/effectcraft/psd-3376-scene25-v3-regression-20261021/baseline/scene.ecproj'
P29=ROOT/'output/effectcraft/psd-3376-scene29-residual-fix-20261021/scene.ecproj'
A25=Path(json.loads((ROOT/'output/effectcraft/psd-3376-scene25-20261021/original-config.json').read_text(encoding='utf8'))['project'])
A29=ROOT/'output/effectcraft/psd-3376-scene29-effects-20261021/rich-reference.aep'
C25='ae_highlight_parallax_layered_scene_sustained';C29='ae_highlight_parallax_layered_scene'
parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['ae','ec']);args=parser.parse_args()
q=lambda p:json.dumps(str(p).replace('\\','/'),ensure_ascii=True)
COMMON=r'''
function vector(v){return v!==null&&typeof v.length==='number'?Array.prototype.slice.call(v,0,2).join(','):String(v);}
function dump(c){var rows=[],names=['foreground','character','background'],props=['ADBE Position','ADBE Scale','ADBE Rotate Z'];
for(var n=0;n<names.length;n++)for(var p=0;p<props.length;p++){
var layer=c.layer(names[n]),v=layer.property('ADBE Transform Group').property(props[p]);
for(var k=1;k<=v.numKeys;k++){
var sa='',sc='',tin='',tout='';if(v.isSpatial){sa=v.keySpatialAutoBezier(k);sc=v.keySpatialContinuous(k);tin=vector(v.keyInSpatialTangent(k));tout=vector(v.keyOutSpatialTangent(k));}
rows.push(['K',names[n],props[p],k,v.keyTime(k),vector(v.keyValue(k)),v.keyInInterpolationType(k),v.keyOutInterpolationType(k),sa,sc,tin,tout].join('\t'));}
for(var i=0;i<240;i++)rows.push(['S',names[n],props[p],i/24,vector(v.valueAtTime(i/24,false))].join('\t'));
}return rows.join('\n');}
function compNamed(name){for(var i=1;i<=app.project.numItems;i++)if(app.project.item(i).name===name)return app.project.item(i);throw new Error('Missing '+name);}
'''
if args.phase=='ae':
    code='app.beginSuppressDialogs();try{\n'+COMMON
    for source,comp,name in [(A25,C25,'25'),(A29,C29,'29')]:
        code+='app.open(new File('+q(source)+'));var text=dump(compNamed('+json.dumps(comp)+'));var file=new File('+q(D/('ae-'+name+'.tsv'))+');file.open("w");file.write(text);file.close();app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);\n'
    code+='var f=new File('+q(D/'ae.status')+');f.open("w");f.write("success");f.close();\n'
    code+='}catch(e){var f=new File('+q(D/'ae.status')+');f.open("w");f.write("error|"+e.toString());f.close();}\ntry{app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);}catch(e){}app.endSuppressDialogs(false);app.scheduleTask("app.quit()",1000,false);'
    jsx=D/'export-ae-motion.jsx';jsx.write_text(code,encoding='utf8')
    subprocess.run(['node','-e',"new(require('node:vm').Script)(require('node:fs').readFileSync(process.argv[1],'utf8'))",str(jsx)],check=True)
    status=D/'ae.status';status.unlink(missing_ok=True)
    with (D/'ae-launch.log').open('w') as log:
        p=subprocess.Popen([str(find_afterfx()),'-m','-r',str(jsx)],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        print('AE diagnostic PID',p.pid,flush=True)
        for _ in range(180):
            if status.exists():
                s=status.read_text();print(s,flush=True)
                if s!='success':raise RuntimeError(s)
                break
            time.sleep(1)
        else:raise TimeoutError('Inspect diagnostic AE window')
else:
    for project,comp,name in [(P25,C25,'25'),(P29,C29,'29')]:
        jsx=D/('export-ec-'+name+'.jsx');jsx.write_text(COMMON+'\ndump(compNamed('+json.dumps(comp)+'));',encoding='utf8')
        _execute(binary(),['script',str(jsx),'--project',str(project),'--json'],D,'ec-motion-'+name)
        receipt=json.loads((D/('ec-motion-'+name+'.stdout.json')).read_text(encoding='utf8'))
        (D/('ec-'+name+'.tsv')).write_text(receipt['result'],encoding='utf8')
    print('Native key metadata and per-frame transforms exported',flush=True)
