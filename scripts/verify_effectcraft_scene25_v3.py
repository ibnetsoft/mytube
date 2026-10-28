"""Cross-scene regression: original scene 25, separate four-effect copy and 1.2 probe."""
import argparse,copy,hashlib,json,shutil,subprocess,sys,time
from pathlib import Path
import imageio_ffmpeg
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from effectcraft_render import binary,_execute,render_native_video
from effectcraft_compatibility import prepare_project,AE_COLOR,VERSION
from ae_scene_animation import SCENE_JSX
from ae_scene_effects import EFFECTS_JSX
from adobe_tools import find_afterfx,find_aerender
OLD=ROOT/'output/effectcraft/psd-3376-scene25-20261021'
PREV=ROOT/'output/effectcraft/psd-3376-scene25-fix-20261021'
SCENE29=ROOT/'output/effectcraft/psd-3376-scene29-residual-fix-20261021'
D=ROOT/'output/effectcraft/psd-3376-scene25-v3-regression-20261021';D.mkdir(exist_ok=True)
COMP='ae_highlight_parallax_layered_scene_sustained'
TIMES=[0,.5,1,2,3,4,4.5,7,239/24]
PHASES=['prepare','ec','weak-controls','ae-project','ae-render','analyze']
parser=argparse.ArgumentParser();parser.add_argument('phase',choices=PHASES);args=parser.parse_args()
q=lambda p:json.dumps(str(p).replace('\\','/'),ensure_ascii=True)
ff=imageio_ffmpeg.get_ffmpeg_exe();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
cfg=json.loads((OLD/'original-config.json').read_text(encoding='utf8'))
def run(command):subprocess.run(command,check=True)
def syntax(path):run(['node','-e',"new(require('node:vm').Script)(require('node:fs').readFileSync(process.argv[1],'utf8'))",str(path)])
def image(p):return np.asarray(Image.open(p).convert('RGB')).astype(float)
def frame(cli,project,comp,t,out,stage):_execute(cli,['render-frame',str(project),'--comp',comp,'--time',str(t),'--out',str(out),'--json'],out.parent,stage)
def reference(source,target):
    run([ff,'-v','error','-y','-i',str(source),'-map','0:v:0','-c','copy','-bsf:v',
         'h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1:video_full_range_flag=0',
         '-colorspace','bt709','-color_trc','bt709','-color_primaries','bt709','-color_range','tv',str(target)])
if args.phase=='prepare':
    effects=json.loads((SCENE29.parent/'psd-3376-scene29-effects-20261021/experiment-effects.json').read_text())
    helpers=SCENE_JSX[SCENE_JSX.index('  function linear('):SCENE_JSX.index('  var ownsProject=false;')].replace('/* SCENE_EFFECTS */',EFFECTS_JSX)
    extra='var W=1920,H=1080,S='+json.dumps(dict(duration=10,plan=dict(effects=effects)))+';\n'+helpers+'\napplySceneEffects(comp,{background:comp.layer("background"),character:comp.layer("character"),foreground:comp.layer("foreground")});\n'
    (D/'extra-effects.jsx').write_text('var comp=null;for(var i=1;i<=app.project.numItems;i++)if(app.project.item(i).name==='+json.dumps(COMP)+')comp=app.project.item(i);if(!comp)throw new Error("Missing scene25 comp");\n'+extra,encoding='utf8')
    syntax(D/'extra-effects.jsx')
    (D/'experiment-effects.json').write_text(json.dumps(effects,indent=2))
    for mode in ['baseline','rich','controls']:(D/mode).mkdir(exist_ok=True)
    reference(OLD/'ae-reference.mp4',D/'baseline/ae-reference.mp4')
    code=r'''app.beginSuppressDialogs();try{
app.open(new File(__ORIGINAL__));var p=app.project,comp=null;
for(var i=1;i<=p.numItems;i++)if(p.item(i).name===__COMP__)comp=p.item(i);
if(!comp)throw new Error('Missing original scene25');
var info=new File(__DIR__+'/ae-settings.txt');info.open('w');info.write('workingSpace='+p.workingSpace+'\nbitsPerChannel='+p.bitsPerChannel+'\nlinearize='+p.linearizeWorkingSpace+'\nlinearBlending='+p.linearBlending+'\noriginalLayers='+comp.numLayers);info.close();
if(p.workingSpace!=='Rec.709 Gamma 2.4'||p.bitsPerChannel!==16||p.linearizeWorkingSpace||p.linearBlending)throw new Error('Unexpected reference color settings');
while(p.renderQueue.numItems)p.renderQueue.item(1).remove();
function addFrame(c,name,t){var rq=p.renderQueue.items.add(c);rq.timeSpanStart=t;rq.timeSpanDuration=1/24;
var om=rq.outputModule(1),found=false;for(var j=0;j<om.templates.length;j++)if(/Lossless|무손실/.test(om.templates[j])){om.applyTemplate(om.templates[j]);found=true;break;}
if(!found)throw new Error('Lossless template missing');om.file=new File(__DIR__+'/controls/ae-'+name+'.avi');}
var original=comp,times=__TIMES__;
for(var i=0;i<times.length;i++)addFrame(original,'baseline-'+i,times[i]);
addFrame(original,'baseline-repeat',1);
var off=original.duplicate();off.name='scene25_blur_off';off.layer('background').property('ADBE Effect Parade').property(1).enabled=false;addFrame(off,'blur-off',1);
var probe=original.duplicate();probe.name='scene25_blur12';probe.layer('background').property('ADBE Effect Parade').property(1).property(1).setValue(1.2);
var pt=[1,4,239/24];for(var i=0;i<pt.length;i++)addFrame(probe,'blur12-'+i,pt[i]);
comp=original.duplicate();comp.name='scene25_rich';
__EXTRA__
for(var i=0;i<times.length;i++)addFrame(comp,'rich-'+i,times[i]);
var rq=p.renderQueue.items.add(comp),om=rq.outputModule(1),found=false;
for(var j=0;j<om.templates.length;j++)if(/H\.?264/i.test(om.templates[j])){om.applyTemplate(om.templates[j]);found=true;break;}
if(!found)throw new Error('H264 template missing');om.file=new File(__DIR__+'/rich/ae-native.mp4');
p.save(new File(__PROJECT__));var f=new File(__STATUS__);f.open('w');f.write('success');f.close();
}catch(e){var f=new File(__STATUS__);f.open('w');f.write('error|'+e.toString());f.close();}
try{app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);}catch(e){}app.endSuppressDialogs(false);app.scheduleTask('app.quit()',1000,false);
'''
    for token,path in [('ORIGINAL',cfg['project']),('DIR',D),('PROJECT',D/'scene25-controls.aep'),('STATUS',D/'ae-build.status')]:code=code.replace('__'+token+'__',q(path))
    code=code.replace('__COMP__',json.dumps(COMP)).replace('__TIMES__',json.dumps(TIMES)).replace('__EXTRA__',extra)
    (D/'build-ae.jsx').write_text(code,encoding='utf8');syntax(D/'build-ae.jsx')
    (D/'provenance.json').write_text(json.dumps(dict(scene=25,project=3376,source_psd_sha256=sha(OLD/'source.psd'),original_ae_aep=cfg['project'],original_ae_aep_sha256=sha(cfg['project']),original_ae_mp4_sha256=sha(OLD/'ae-reference.mp4'),effects_scope='Separate four-effect experiment; original scene unchanged',version=VERSION),indent=2))
    print('Prepared original scene25 and separate unchanged-direction effect controls',flush=True)
elif args.phase=='ec':
    cli=binary()
    for mode,source in [('baseline',OLD/'scene.ecproj'),('rich',OLD/'scene.ecproj')]:
        out=D/mode;project=out/'scene.ecproj';shutil.copy2(source,project)
        if mode=='rich':_execute(cli,['script',str(D/'extra-effects.jsx'),'--project',str(project),'--save','--json'],out,'add-effects')
        receipt=prepare_project(cli,project,out,_execute)
        export=render_native_video(cli,project,COMP,out/'effectcraft.mp4',24,out)
        (out/'export-receipt.json').write_text(json.dumps(export,indent=2))
        for i,t in enumerate(TIMES):frame(cli,project,COMP,t,D/'controls'/f'ec-{mode}-{i}.png','ec-'+mode+'-'+str(i))
        print(mode,'full render completed',flush=True)
    # Retain the exact previous Gaussian/color path, with new effects still unconverted.
    previous=D/'controls/rich-previous.ecproj';shutil.copy2(PREV/'scene.ecproj',previous)
    _execute(cli,['script',str(D/'extra-effects.jsx'),'--project',str(previous),'--save','--json'],D/'controls','previous-add-effects')
    for i,t in enumerate(TIMES):
        frame(cli,PREV/'scene.ecproj',COMP,t,D/'controls'/f'ec-baseline-previous-{i}.png','ec-baseline-previous-'+str(i))
        frame(cli,previous,COMP,t,D/'controls'/f'ec-rich-previous-{i}.png','ec-rich-previous-'+str(i))
    raw=json.loads((OLD/'scene.ecproj').read_text(encoding='utf8'))
    def blur(p):
        c=next(i['kind'] for i in p['items'].values() if i['name']==COMP)
        l=next(l for l in c['layers'] if l['name']=='background')
        return next(g for g in l['props']['children'] if g['match']=='effects')['children'][0]
    blur(raw)['children'][0]['value']['v']=1.2
    for label in ['before','after']:
        out=D/'controls'/('blur12-'+label);out.mkdir(exist_ok=True)
        p=out/'scene.ecproj';p.write_text(json.dumps(raw),encoding='utf8')
        if label=='after':prepare_project(cli,p,out,_execute)
        else:_execute(cli,['exec','file.projectSettings','--params',json.dumps(AE_COLOR),'--project',str(p),'--save','--json'],out,'color')
        for i,t in enumerate([1,4,239/24]):frame(cli,p,COMP,t,D/'controls'/f'ec-blur12-{label}-{i}.png','ec-blur12-'+label+'-'+str(i))
    # Existing scene29 is a second-scene regression control, not a new submission.
    for i,t in [(0,0),(4,4),(8,239/24)]:frame(cli,SCENE29/'scene.ecproj','ae_highlight_parallax_layered_scene',t,D/'controls'/f'ec-scene29-{i}.png','ec-scene29-'+str(i))
    print('Previous/current and other-scene controls completed',flush=True)
elif args.phase=='weak-controls':
    cli=binary();rows=[]
    for amount in [.35,.7,1.]:
        p=json.loads((OLD/'scene.ecproj').read_text(encoding='utf8'))
        c=next(i['kind'] for i in p['items'].values() if i['name']==COMP)
        l=next(l for l in c['layers'] if l['name']=='background')
        e=next(g for g in l['props']['children'] if g['match']=='effects')['children'][0]
        e['children'][0]['value']['v']=amount
        out=D/'controls'/('weak-'+str(amount));out.mkdir(exist_ok=True)
        project=out/'scene.ecproj';project.write_text(json.dumps(p),encoding='utf8')
        prepare_project(cli,project,out,_execute)
        frame(cli,project,COMP,1,out/'current.png','weak-frame')
        a=image(PREV/('radius-'+str(amount))/'after.png');b=image(out/'current.png')
        assert np.array_equal(a,b),'Weak blur output regressed at '+str(amount)
        rows.append(dict(amount=amount,previous_current_mae=float(abs(a-b).mean()),changed_pixels=int(np.any(a!=b,axis=2).sum())))
    (D/'weak-blur-regression.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows),flush=True)
elif args.phase=='ae-project':
    syntax(D/'build-ae.jsx');status=D/'ae-build.status';status.unlink(missing_ok=True)
    with (D/'ae-launch.log').open('w') as log:
        p=subprocess.Popen([str(find_afterfx()),'-m','-r',str(D/'build-ae.jsx')],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        print('AE diagnostic PID',p.pid,flush=True)
        for _ in range(180):
            if status.exists():
                s=status.read_text();print(s,flush=True)
                if s!='success':raise RuntimeError(s)
                break
            if p.poll() is not None:raise RuntimeError('AE exited without status; inspect log/window')
            time.sleep(1)
        else:raise TimeoutError('Inspect diagnostic AE window')
elif args.phase=='ae-render':
    if (D/'ae-build.status').read_text()!='success':raise RuntimeError('AE project not ready')
    with (D/'ae-render.log').open('w') as log:subprocess.run([str(find_aerender()),'-project',str(D/'scene25-controls.aep')],stdout=log,stderr=log,check=True,timeout=1200)
    for f in (D/'controls').glob('ae-*.avi'):run([ff,'-v','error','-y','-i',str(f),'-frames:v','1',str(f.with_suffix('.png'))])
    reference(D/'rich/ae-native.mp4',D/'rich/ae-reference.mp4')
    print('AE lossless controls and richer 10-second reference completed',flush=True)
else:
    controls=D/'controls';results={};sheets=[]
    # Compare actual authored data, rather than inferring preservation from pixels.
    raw=json.loads((OLD/'scene.ecproj').read_text(encoding='utf8'))
    old_fixed=json.loads((PREV/'scene.ecproj').read_text(encoding='utf8'))
    base=json.loads((D/'baseline/scene.ecproj').read_text(encoding='utf8'))
    rich=json.loads((D/'rich/scene.ecproj').read_text(encoding='utf8'))
    def comp(p):return next(i['kind'] for i in p['items'].values() if i['name']==COMP)
    assert base['settings']==old_fixed['settings'],'Working/output color settings changed'
    assert rich['settings']==base['settings']
    def original_layers(p):return [l for l in comp(p)['layers'] if not l['name'].startswith('ae_effect_')]
    assert [l['name'] for l in original_layers(base)]==[l['name'] for l in original_layers(raw)]
    for original,current,experimental in zip(original_layers(raw),original_layers(base),original_layers(rich)):
        def without_effects(layer):
            v=copy.deepcopy(layer);v['props']['children']=[g for g in v['props']['children'] if g['match']!='effects'];return v
        assert without_effects(original)==without_effects(current)==without_effects(experimental)
    old_blur=json.loads((PREV/'compatibility-receipt.json').read_text())['fractional_gaussian'][0]
    new_receipt=json.loads((D/'baseline/compatibility-receipt.json').read_text())
    new_blur=new_receipt['fractional_gaussian'][0]
    for field in ['amount','dimensions']:assert old_blur[field]==new_blur[field]
    assert np.allclose(old_blur['kernel'],new_blur['kernel'],rtol=1e-12,atol=0)
    assert new_blur['amount']==.35 and new_blur['working_gamma']==1
    assert not new_receipt['smooth_masks'],'Masks were added to the original scene'
    rich_receipt=json.loads((D/'rich/compatibility-receipt.json').read_text())
    assert len(comp(base)['layers'])==3 and len(comp(rich)['layers'])==14
    assert len(rich_receipt['smooth_masks'])==2
    results['preservation_audit']=dict(color_settings_unchanged=True,original_artwork_motion_and_opacity_unchanged=True,
        original_blur035_kernel_unchanged=True,no_added_effects_in_original=True,baseline_layers=3,experiment_layers=14,
        experimental_effects=json.loads((D/'experiment-effects.json').read_text()))
    for mode in ['baseline','rich']:
        rows=[];sheet=Image.new('RGB',(1440,len(TIMES)*294),'#151515');draw=ImageDraw.Draw(sheet)
        for i,t in enumerate(TIMES):
            ae,before,after=[image(controls/f'{name}-{i}.png') for name in ['ae-'+mode,'ec-'+mode+'-previous','ec-'+mode]]
            if mode=='baseline':assert np.array_equal(before,after),'Original scene25 pixels regressed'
            rows.append(dict(time=t,before_mae=float(abs(ae-before).mean()),after_mae=float(abs(ae-after).mean()),previous_current_mae=float(abs(before-after).mean()),mean_rgb_bias=(ae-after).mean((0,1)).tolist()))
            for n,(label,im) in enumerate([('AE',ae),('EffectCraft previous',before),('EffectCraft current',after)]):
                sheet.paste(Image.fromarray(im.astype('uint8')).resize((480,270)),(n*480,i*294+24));draw.text((n*480+8,i*294+7),label+' '+str(round(t,3))+'s',fill='white')
        sheet.save(D/mode/'lossless-contact.jpg',quality=95)
        (D/mode/'lossless-metrics.json').write_text(json.dumps(rows,indent=2));results[mode]=dict(before_mean=float(np.mean([r['before_mae'] for r in rows])),after_mean=float(np.mean([r['after_mae'] for r in rows])),previous_current_mean=float(np.mean([r['previous_current_mae'] for r in rows])))
    blur=[]
    for i,t in enumerate([1,4,239/24]):
        a,b,c=[image(controls/f'{name}-{i}.png') for name in ['ae-blur12','ec-blur12-before','ec-blur12-after']]
        blur.append(dict(time=t,before_mae=float(abs(a-b).mean()),after_mae=float(abs(a-c).mean())))
    results['blur12']=blur
    results['ae_repeat_mae']=float(abs(image(controls/'ae-baseline-2.png')-image(controls/'ae-baseline-repeat.png')).mean())
    results['original_blur035_ae_on_off_mae']=float(abs(image(controls/'ae-baseline-2.png')-image(controls/'ae-blur-off.png')).mean())
    for i in [0,4,8]:assert np.array_equal(image(controls/f'ec-scene29-{i}.png'),image(SCENE29/f'ec-final-{i}.png')),'Scene29 control changed'
    results['scene29_regression']='Exact pixel equality at 0, 4, 239/24 seconds'
    for mode in ['baseline','rich']:
        for name in ['ae-reference.mp4','effectcraft.mp4']:
            p=D/mode/name;assert imageio_ffmpeg.count_frames_and_secs(str(p))==(240,10.)
            run([ff,'-v','error','-i',str(p),'-f','null','-'])
    provenance=json.loads((D/'provenance.json').read_text());assert sha(cfg['project'])==provenance['original_ae_aep_sha256'];assert sha(OLD/'source.psd')==provenance['source_psd_sha256']
    results['source_and_original_ae_unchanged']=True
    results['weak_blur_regression']=json.loads((D/'weak-blur-regression.json').read_text())
    for mode in ['baseline','rich']:
        reference_file=D/mode/'ae-reference.mp4'
        # Source metadata correction must reproduce explicit matrix decoding exactly.
        source=OLD/'ae-reference.mp4' if mode=='baseline' else D/'rich/ae-native.mp4'
        a=controls/(mode+'-explicit709.png');b=controls/(mode+'-tagged709.png')
        run([ff,'-v','error','-y','-ss','1','-i',str(source),'-vf','scale=in_color_matrix=bt709:out_color_matrix=bt709','-frames:v','1',str(a)])
        run([ff,'-v','error','-y','-ss','1','-i',str(reference_file),'-frames:v','1',str(b)])
        assert np.array_equal(image(a),image(b))
    results['ae_reference_metadata']='Tagged copies exactly match explicit BT709 decoding; no sample re-encode'
    (D/'regression-results.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2),flush=True)
