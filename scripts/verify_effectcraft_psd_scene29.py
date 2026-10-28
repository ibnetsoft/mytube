"""Archived scene 29 baseline and a separately labelled identical-effects AE/EC experiment."""
import argparse,hashlib,json,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from effectcraft_render import binary,_execute
from effectcraft_compatibility import prepare_project
from ae_scene_animation import SCENE_JSX
from ae_scene_effects import EFFECTS_JSX
from adobe_tools import find_afterfx,find_aerender
SRC=Path('C:/Users/kimse/AppData/Local/AIRStudio/AIRWorker/temp/ae_highlight/3376-029-effect-68f7d6ef62a70b2c')
D=ROOT/'output/effectcraft/psd-3376-scene29-effects-20261021'
D.mkdir(parents=True,exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['prepare','ec','ae-project','ae-render']);args=parser.parse_args()
q=lambda p:json.dumps(str(p).replace('\\','/'),ensure_ascii=True)
def syntax(path):subprocess.run(['node','-e',"new (require('node:vm').Script)(require('node:fs').readFileSync(process.argv[1],'utf8'))",str(path)],check=True)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
if args.phase=='prepare':
    text=(SRC/'create_project.jsx').read_text(encoding='utf-8-sig')
    cfg=json.JSONDecoder().raw_decode(text.split('var CFG = ',1)[1])[0]
    for name in ['baseline','rich']:(D/name).mkdir(exist_ok=True)
    shutil.copy2(SRC/'input/scene.psd',D/'source.psd')
    shutil.copy2(SRC/'render/ae_highlight.mp4',D/'baseline/ae-reference.mp4')
    shutil.copy2(SRC/'create_project.jsx',D/'original-ae.jsx')
    (D/'original-config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
    cfg['source']=(D/'source.psd').as_posix()
    prefix=text[text.index('var W = CFG.width'):text.index('app.beginSuppressDialogs();\ntry {')]
    body=text.split('  var options = new ImportOptions(new File(CFG.source));',1)[1].split('  var rq = app.project.renderQueue.items.add(comp);',1)[0]
    common='var CFG='+json.dumps(cfg,ensure_ascii=True)+';\n'+prefix+'\nvar options=new ImportOptions(new File(CFG.source));'+body
    common=common.replace('catch (e) { return null; }','catch (e) { throw e; }').replace('catch (ignoreBlur) {}','catch (ignoreBlur) { throw ignoreBlur; }')
    (D/'baseline.jsx').write_text(common+'\nnull;',encoding='utf-8')
    effects=[dict(type='light_sweep',start=.12,end=.65,intensity=.65,radius=.32,center=[.5,.55],color=[1,.82,.55],reason='Controlled engine comparison: moving warm light'),
             dict(type='warm_dust_motes',start=.08,end=.9,intensity=.5,radius=.24,center=[.82,.38],color=[1,.86,.6],reason='Controlled comparison: deterministic small particles'),
             dict(type='shock_ring',start=.35,end=.6,intensity=.45,radius=.22,center=[.5,.65],color=[1,.8,.45],reason='Controlled comparison: animated vector stroke'),
             dict(type='subtle_vignette',start=.02,end=.98,intensity=.45,radius=.72,center=[.5,.5],color=[0,0,0],reason='Controlled comparison: inverted feathered mask')]
    helpers=SCENE_JSX[SCENE_JSX.index('  function linear('):SCENE_JSX.index('  var ownsProject=false;')].replace('/* SCENE_EFFECTS */',EFFECTS_JSX)
    extra='\nvar S='+json.dumps(dict(duration=cfg['duration'],plan=dict(effects=effects)),ensure_ascii=True)+';\n'+helpers+'\napplySceneEffects(comp,{background:comp.layer("background"),character:comp.layer("character"),foreground:comp.layer("foreground")});\n'
    rich=common+extra
    (D/'rich.jsx').write_text(rich+'\nnull;',encoding='utf-8')
    (D/'experiment-effects.json').write_text(json.dumps(effects,indent=2),encoding='utf-8')
    (D/'provenance.json').write_text(json.dumps(dict(cache=str(SRC),psd_sha256=sha(D/'source.psd'),ae_baseline_sha256=sha(D/'baseline/ae-reference.mp4'),original_script_sha256=sha(D/'original-ae.jsx'),scope='Original baseline plus separate controlled extra-effects experiment; no production mutation'),indent=2),encoding='utf-8')
    # AE uses the exact same art/motion/effect code; process and save wrappers differ.
    ae='''app.beginSuppressDialogs();\ntry {\napp.newProject();app.project.bitsPerChannel=16;app.project.workingSpace='Rec.709 Gamma 2.4';app.project.linearizeWorkingSpace=false;\n'''+rich
    ae+=r'''
var rq=app.project.renderQueue.items.add(comp),om=rq.outputModule(1),found=false,template='';
for(var t=0;t<om.templates.length;t++)if(/H\.?264/i.test(om.templates[t])){template=om.templates[t];om.applyTemplate(template);found=true;break;}
var output=__MP4__;
if(!found){for(var t=0;t<om.templates.length;t++)if(/Lossless|무손실/.test(om.templates[t])){template=om.templates[t];om.applyTemplate(template);found=true;break;}output=__AVI__;}
if(!found)throw new Error('No supported native output template');
om.file=new File(output);app.project.save(new File(__AEP__));
var f=new File(__STATUS__);f.open('w');f.write('success|'+output+'|'+template+'|'+app.project.workingSpace+'|'+app.project.bitsPerChannel);f.close();
}catch(e){var f=new File(__STATUS__);f.open('w');f.write('error|'+e.toString());f.close();}
try{app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);}catch(e){}
app.endSuppressDialogs(false);app.scheduleTask('app.quit()',1000,false);
'''
    for token,path in [('MP4',D/'rich/ae-native.mp4'),('AVI',D/'rich/ae-native.avi'),('AEP',D/'rich-reference.aep'),('STATUS',D/'ae-project.status')]:ae=ae.replace('__'+token+'__',q(path))
    (D/'build-ae.jsx').write_text(ae,encoding='utf-8')
    for name in ['baseline.jsx','rich.jsx','build-ae.jsx']:syntax(D/name)
    print('Prepared identical source and effect scripts; syntax passed',flush=True)
elif args.phase=='ec':
    cli=binary();cfg=json.loads((D/'original-config.json').read_text(encoding='utf-8'))
    for mode in ['baseline','rich']:
        directory=D/mode;project=D/(mode+'.ecproj')
        _execute(cli,['script','--eval','null','--empty','--save-as',str(project),'--json'],directory,'initialize')
        _execute(cli,['script',str(D/(mode+'.jsx')),'--project',str(project),'--save','--json'],directory,'create')
        prepare_project(cli,project,directory,_execute)
        _execute(cli,['render',str(project),'--comp',cfg['comp'],'--out',str(directory/'effectcraft.mp4'),'--format','h264','--audio','off','--fps',str(cfg['fps']),'--json'],directory,'render')
        print(mode+' EffectCraft completed',flush=True)
elif args.phase=='ae-project':
    syntax(D/'build-ae.jsx');status=D/'ae-project.status';status.unlink(missing_ok=True)
    with (D/'ae-build.log').open('w') as log:
        process=subprocess.Popen([str(find_afterfx()),'-m','-r',str(D/'build-ae.jsx')],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        print('AE diagnostic PID',process.pid,flush=True)
        for _ in range(180):
            if status.exists():
                result=status.read_text(encoding='utf-8',errors='replace');print(result,flush=True)
                if not result.startswith('success|'):raise RuntimeError(result)
                break
            time.sleep(1)
        else:raise TimeoutError('AE project status missing; inspect this diagnostic instance')
elif args.phase=='ae-render':
    status=(D/'ae-project.status').read_text(encoding='utf-8',errors='replace')
    if not status.startswith('success|'):raise RuntimeError(status)
    native=Path(status.split('|')[1]);cfg=json.loads((D/'original-config.json').read_text(encoding='utf-8'))
    with (D/'rich/ae-render.log').open('w') as log:
        subprocess.run([str(find_aerender()),'-project',str(D/'rich-reference.aep'),'-comp',cfg['comp'],'-output',str(native)],stdout=log,stderr=log,check=True,timeout=1200)
    if not native.is_file():raise RuntimeError('Native AE output missing')
    target=D/'rich/ae-reference.mp4'
    if native.suffix=='.mp4':shutil.copy2(native,target)
    else:
        import imageio_ffmpeg
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-v','error','-i',str(native),'-an','-c:v','libx264','-crf','16','-pix_fmt','yuv420p','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709',str(target)],check=True)
    print('AE richer-effects render completed',flush=True)
