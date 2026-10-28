"""v4 straight-position repair: full scene25 render, dense AE controls, scene29 regression."""
import argparse,copy,hashlib,json,shutil,subprocess,sys,time
from pathlib import Path
import imageio_ffmpeg,numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'worker'))
from effectcraft_render import binary,_execute,render_native_video
from effectcraft_compatibility import prepare_project,linear_position_replacements
from adobe_tools import find_afterfx,find_aerender
D=ROOT/'output/effectcraft/psd-3376-scene25-motion-fix-20261021';D.mkdir(exist_ok=True)
PREV=ROOT/'output/effectcraft/psd-3376-scene25-v3-regression-20261021'
P29=ROOT/'output/effectcraft/psd-3376-scene29-residual-fix-20261021'
COMP='ae_highlight_parallax_layered_scene_sustained'
TIMES=[0,.25,.5,.75,1,1.5,2,2.5,3,3.375,3.5,3.625,4,4.5,5,6,7,8,9,239/24]
parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['render','ae-project','ae-render','analyze']);args=parser.parse_args()
q=lambda p:json.dumps(str(p).replace('\\','/'),ensure_ascii=True)
ff=imageio_ffmpeg.get_ffmpeg_exe();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def im(p):return np.asarray(Image.open(p).convert('RGB')).astype(float)
def run(command):subprocess.run(command,check=True)
def frame(project,comp,t,out,stage):_execute(binary(),['render-frame',str(project),'--comp',comp,'--time',str(t),'--out',str(out),'--json'],out.parent,stage)
if args.phase=='render':
    for name,source,comp,ae in [('25',PREV/'baseline/scene.ecproj',COMP,PREV/'baseline/ae-reference.mp4'),
                                ('29',P29/'scene.ecproj','ae_highlight_parallax_layered_scene',P29/'ae-reference.mp4')]:
        out=D if name=='25' else D/'scene29';out.mkdir(exist_ok=True)
        project=out/'scene.ecproj';shutil.copy2(source,project);shutil.copy2(ae,out/'ae-reference.mp4')
        receipt=prepare_project(binary(),project,out,_execute,linear_positions=True)
        assert len(receipt['linear_positions'])==(3 if name=='25' else 0)
        export=render_native_video(binary(),project,comp,out/'effectcraft.mp4',24,out)
        (out/'export-receipt.json').write_text(json.dumps(export,indent=2))
        print('Scene',name,'full render completed',flush=True)
    for i,t in enumerate(TIMES):
        frame(D/'scene.ecproj',COMP,t,D/f'fixed-{i}.png','fixed-'+str(i))
        frame(PREV/'baseline/scene.ecproj',COMP,t,D/f'before-{i}.png','before-'+str(i))
    # Evaluate all frames with the same public API used during initial diagnosis.
    _execute(binary(),['script',str(D/'export-ec-25.jsx'),'--project',str(D/'scene.ecproj'),'--json'],D,'ec-motion-25-fixed')
    data=json.loads((D/'ec-motion-25-fixed.stdout.json').read_text(encoding='utf8'))
    (D/'ec-25-fixed.tsv').write_text(data['result'],encoding='utf8')
    for i,t in [(0,0),(4,4),(8,239/24)]:frame(D/'scene29/scene.ecproj','ae_highlight_parallax_layered_scene',t,D/'scene29'/f'current-{i}.png','current-'+str(i))
    # The v3 effect geometry, color and blur correction must survive the path fix.
    rich=D/'rich-controls';rich.mkdir(exist_ok=True);shutil.copy2(PREV/'rich/scene.ecproj',rich/'scene.ecproj')
    prepare_project(binary(),rich/'scene.ecproj',rich,_execute,linear_positions=True)
    for index,t in [(1,.5),(6,4.5),(7,7)]:frame(rich/'scene.ecproj',COMP,t,rich/f'fixed-{index}.png','rich-'+str(index))
elif args.phase=='ae-project':
    cfg=json.loads((ROOT/'output/effectcraft/psd-3376-scene25-20261021/original-config.json').read_text(encoding='utf8'))
    code=r'''app.beginSuppressDialogs();try{app.open(new File(__SOURCE__));var p=app.project,c=null;
for(var i=1;i<=p.numItems;i++)if(p.item(i).name===__COMP__)c=p.item(i);
if(!c)throw new Error('Missing original scene25');while(p.renderQueue.numItems)p.renderQueue.item(1).remove();
var times=__TIMES__;for(var i=0;i<times.length;i++){
var rq=p.renderQueue.items.add(c);rq.timeSpanStart=times[i];rq.timeSpanDuration=1/24;var om=rq.outputModule(1),ok=false;
for(var k=0;k<om.templates.length;k++)if(/Lossless|무손실/.test(om.templates[k])){om.applyTemplate(om.templates[k]);ok=true;break;}
if(!ok)throw new Error('No lossless template');om.file=new File(__DIR__+'/ae-'+i+'.avi');}
p.save(new File(__PROJECT__));var f=new File(__STATUS__);f.open('w');f.write('success');f.close();
}catch(e){var f=new File(__STATUS__);f.open('w');f.write('error|'+e.toString());f.close();}
try{app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);}catch(e){}app.endSuppressDialogs(false);app.scheduleTask('app.quit()',1000,false);
'''
    for token,path in [('SOURCE',cfg['project']),('DIR',D),('PROJECT',D/'motion-reference.aep'),('STATUS',D/'ae-build.status')]:code=code.replace('__'+token+'__',q(path))
    code=code.replace('__COMP__',json.dumps(COMP)).replace('__TIMES__',json.dumps(TIMES));jsx=D/'build-motion-reference.jsx';jsx.write_text(code,encoding='utf8')
    run(['node','-e',"new(require('node:vm').Script)(require('node:fs').readFileSync(process.argv[1],'utf8'))",str(jsx)])
    status=D/'ae-build.status';status.unlink(missing_ok=True)
    with (D/'ae-frame-launch.log').open('w') as log:
        subprocess.Popen([str(find_afterfx()),'-m','-r',str(jsx)],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(180):
            if status.exists():
                result=status.read_text();print(result,flush=True)
                if result!='success':raise RuntimeError(result)
                break
            time.sleep(1)
        else:raise TimeoutError('Inspect diagnostic AE window')
elif args.phase=='ae-render':
    if (D/'ae-build.status').read_text()!='success':raise RuntimeError('AE reference not ready')
    with (D/'ae-frame-render.log').open('w') as log:subprocess.run([str(find_aerender()),'-project',str(D/'motion-reference.aep')],stdout=log,stderr=log,check=True,timeout=900)
    for i in range(len(TIMES)):run([ff,'-v','error','-y','-i',str(D/f'ae-{i}.avi'),'-frames:v','1',str(D/f'ae-{i}.png')])
    print('Dense AE motion frames completed',flush=True)
else:
    def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
    old=read(PREV/'baseline/scene.ecproj');new=read(D/'scene.ecproj')
    # Only the implicit spatial-auto flags may change: no keys, images or effects are fitted.
    normal=copy.deepcopy(new)
    for key,item in old['items'].items():
        if item['kind'].get('type')!='Comp':continue
        for a,b in zip(item['kind']['layers'],normal['items'][key]['kind']['layers']):
            ga={g['match']:g for g in a['props']['children']};gb={g['match']:g for g in b['props']['children']}
            pa=next(p for p in ga['transform']['children'] if p['match']=='position');pb=next(p for p in gb['transform']['children'] if p['match']=='position')
            for ak,bk in zip(pa.get('keys',[]),pb.get('keys',[])):bk['spatial_auto']=ak['spatial_auto']
            assert a==b,a['name']+' unexpected authored-data change'
    assert normal['items']==old['items'] and normal['settings']==old['settings']
    assert not linear_position_replacements(new,True),'Position fix is not idempotent'
    def samples(path):
        rows=[r.split('\t') for r in Path(path).read_text().splitlines()]
        return {(r[1],r[2],round(float(r[3])*24)):np.array([float(v) for v in r[4].split(',')]) for r in rows if r[0]=='S'}
    a,b,c=[samples(D/file) for file in ['ae-25.tsv','ec-25.tsv','ec-25-fixed.tsv']]
    transforms=[]
    for layer in ['foreground','character','background']:
        keys=[k for k in a if k[0]==layer and k[1]=='ADBE Position']
        transforms.append(dict(layer=layer,frames=len(keys),before_max_axis_px=float(max(abs(a[k]-b[k]).max() for k in keys)),after_max_axis_px=float(max(abs(a[k]-c[k]).max() for k in keys))))
        for k in keys:
            if k[2]>=96:assert np.array_equal(c[k],c[layer,'ADBE Position',96]),'Hold segment drifts'
    assert max(r['after_max_axis_px'] for r in transforms)<.02
    rows=[];sheet=Image.new('RGB',(1440,len(TIMES)*294),'#151515');draw=ImageDraw.Draw(sheet)
    for i,t in enumerate(TIMES):
        ae,before,after=[im(D/f'{label}-{i}.png') for label in ['ae','before','fixed']]
        rows.append(dict(time=t,before_mae=float(abs(ae-before).mean()),after_mae=float(abs(ae-after).mean()),mean_rgb_bias=(ae-after).mean((0,1)).tolist()))
        for j,(name,picture) in enumerate([('AE',ae),('EC previous',before),('EC corrected',after)]):
            sheet.paste(Image.fromarray(picture.astype('uint8')).resize((480,270)),(480*j,294*i+24));draw.text((480*j+8,294*i+7),name+' '+str(round(t,4))+'s',fill='white')
    sheet.save(D/'motion-before-after-contact.jpg',quality=95)
    (D/'lossless-motion-metrics.json').write_text(json.dumps(rows,indent=2))
    # Unchanged 29 project data and independently rendered output controls.
    assert read(P29/'scene.ecproj')['items']==read(D/'scene29/scene.ecproj')['items']
    for i in [0,4,8]:assert np.array_equal(im(D/'scene29'/f'current-{i}.png'),im(P29/f'ec-final-{i}.png'))
    regression=[]
    for folder,name in [(P29,'previous'),(D/'scene29','current')]:
        out=D/'scene29'/('decoded-'+name+'.framemd5')
        run([ff,'-v','error','-y','-i',str(folder/'effectcraft.mp4'),'-an','-f','framemd5',str(out)])
        regression.append([s for s in out.read_text().splitlines() if not s.startswith('#')])
    assert regression[0]==regression[1],'Scene29 encoded-frame output changed'
    rich=[]
    for i in [1,6,7]:
        a=im(PREV/'controls'/f'ae-rich-{i}.png');b=im(PREV/'controls'/f'ec-rich-{i}.png');c=im(D/'rich-controls'/f'fixed-{i}.png')
        rich.append(dict(time=[.5,4.5,7][[1,6,7].index(i)],before_mae=float(abs(a-b).mean()),after_mae=float(abs(a-c).mean())))
    for folder in [D,D/'scene29']:
        for name in ['ae-reference.mp4','effectcraft.mp4']:
            assert imageio_ffmpeg.count_frames_and_secs(str(folder/name))==(240,10.)
            run([ff,'-v','error','-i',str(folder/name),'-f','null','-'])
    result=dict(transform_comparison=transforms,frames_per_layer=240,dense_lossless_samples=len(rows),
                before_mean_mae=float(np.mean([r['before_mae'] for r in rows])),after_mean_mae=float(np.mean([r['after_mae'] for r in rows])),
                hold_exact=True,authored_times_values_effects_color_unchanged=True,scene29_all_240_decoded_frames_identical=True,rich_scene25_controls=rich)
    provenance=read(PREV/'provenance.json')
    source=ROOT/'output/effectcraft/psd-3376-scene25-20261021/source.psd'
    assert sha(source)==provenance['source_psd_sha256']
    assert sha(provenance['original_ae_aep'])==provenance['original_ae_aep_sha256']
    assert sha(D/'scene29/effectcraft.mp4')==sha(P29/'effectcraft.mp4')
    result.update(source_psd_sha256=sha(source),original_ae_aep_sha256=sha(provenance['original_ae_aep']),
                  source_and_original_ae_unchanged=True,scene29_mp4_sha256_identical=True)
    (D/'validation-summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2),flush=True)
