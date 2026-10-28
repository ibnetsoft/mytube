"""Non-publishing scene19 version matrix, preserving archived AE projects and PSDs."""
import argparse,copy,hashlib,json,shutil,subprocess,sys,time
from pathlib import Path
import imageio_ffmpeg,numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'worker'))
from effectcraft_render import binary,_execute,render_native_video
from effectcraft_compatibility import prepare_project,VERSION
from adobe_tools import find_afterfx,find_aerender
D=ROOT/'output/effectcraft/psd-3376-remaining-20261021';D.mkdir(parents=True,exist_ok=True)
CACHE=Path('C:/Users/kimse/AppData/Local/AIRStudio/AIRWorker/temp/ae_highlight')
CASES={'19-current-3s':'c5edad20c4799c05','19-oneway-7s':'9574ad511c54fe00','19-sustained-7s':'0a40698ba4820282'}
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
q=lambda p:json.dumps(str(p).replace('\\','/'),ensure_ascii=True)
probe=(ROOT/'scripts/probe_effectcraft_scene25_motion.py').read_text(encoding='utf8')
COMMON=probe.split("COMMON=r'''",1)[1].split("'''",1)[0]
phase=argparse.ArgumentParser();phase.add_argument('phase',choices=['prepare','ae-project','render','ae-render','analyze']);args=phase.parse_args()
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
if args.phase=='prepare':
    inventory=read(ROOT/'output/motion-final-production/3376-assets.json')
    assert sorted({a['scene_number'] for a in inventory['assets'] if a.get('metadata',{}).get('psd_layer_asset')})==[19,25,29]
    for name,suffix in CASES.items():
        src=CACHE/('3376-019-effect-'+suffix);out=D/name;out.mkdir(exist_ok=True)
        original=(src/'create_project.jsx').read_text(encoding='utf-8-sig');cfg=json.JSONDecoder().raw_decode(original.split('var CFG = ',1)[1])[0]
        times=sorted(set([0,.25,.5,.75,1,1.5,2,2.5,cfg['duration']-1/24]+([3,3.375,3.5,4,4.5,5,6] if cfg['duration']>3 else [])))
        manifest=dict(source=str(src),config=cfg,times=times,psd_sha256=sha(src/'input/scene.psd'),aep_sha256=sha(cfg['project']),compatibility=VERSION)
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
        shutil.copy2(src/'input/scene.psd',out/'source.psd');shutil.copy2(src/'create_project.jsx',out/'original-ae.jsx')
        cfg=dict(cfg,source=(out/'source.psd').as_posix())
        prefix=original[original.index('var W = CFG.width'):original.index('app.beginSuppressDialogs();\ntry {')]
        body=original.split('  var options = new ImportOptions(new File(CFG.source));',1)[1].split('  var rq = app.project.renderQueue.items.add(comp);',1)[0]
        script='var CFG = '+json.dumps(cfg,ensure_ascii=True)+';\n'+prefix+'\nvar options = new ImportOptions(new File(CFG.source));'+body+'\ncomp.name;'
        script=script.replace('catch (e) { return null; }','catch (e) { throw e; }')
        (out/'import.jsx').write_text(script,encoding='utf8')
    print('Inventory: 100 scenes, PSD scenes 19/25/29; remaining19, three archived direction versions',flush=True)
elif args.phase=='ae-project':
    code='app.beginSuppressDialogs();try{\n'+COMMON
    for name in CASES:
        out=D/name;m=read(out/'manifest.json');cfg=m['config']
        common=COMMON.replace('i<240','i<'+str(round(cfg['duration']*24)))
        code+='\n(function(){\n'+common+'\napp.open(new File('+q(cfg['project'])+'));var p=app.project,c=compNamed('+q(cfg['comp'])+');'
        code+='var text=dump(c),f=new File('+q(out/'ae-motion.tsv')+');f.open("w");f.write(text);f.close();'
        code+='while(p.renderQueue.numItems)p.renderQueue.item(1).remove();var times='+json.dumps(m['times'])+';'
        code+='for(var i=0;i<times.length;i++){var r=p.renderQueue.items.add(c);r.timeSpanStart=times[i];r.timeSpanDuration=1/24;var om=r.outputModule(1),ok=false;for(var k=0;k<om.templates.length;k++)if(/Lossless|무손실/.test(om.templates[k])){om.applyTemplate(om.templates[k]);ok=true;break;}if(!ok)throw new Error("No lossless");om.file=new File('+q(out)+'/"ae-"+i+".avi");}'
        # Separate full-video reference retains the archived AE output settings.
        code+='p.save(new File('+q(out/'reference.aep')+'));p.close(CloseOptions.DO_NOT_SAVE_CHANGES);})();'
    code+='var f=new File('+q(D/'ae.status')+');f.open("w");f.write("success");f.close();}catch(e){var f=new File('+q(D/'ae.status')+');f.open("w");f.write("error|"+e.toString());f.close();}try{app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);}catch(e){}app.endSuppressDialogs(false);app.scheduleTask("app.quit()",1000,false);'
    code=code.replace('"/"ae-"','"+"/ae-"')
    jsx=D/'build-reference.jsx';jsx.write_text(code,encoding='utf8')
    subprocess.run(['node','-e',"new(require('node:vm').Script)(require('node:fs').readFileSync(process.argv[1],'utf8'))",str(jsx)],check=True)
    (D/'ae.status').unlink(missing_ok=True)
    with (D/'ae-launch.log').open('w') as log:
        p=subprocess.Popen([str(find_afterfx()),'-m','-r',str(jsx)],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
    print('AE PID',p.pid,flush=True)
elif args.phase=='render':
    for name in CASES:
        out=D/name;m=read(out/'manifest.json');cfg=m['config']
        rows=[r.split('\t') for r in (out/'ae-motion.tsv').read_text().splitlines() if r.startswith('K\t') and '\tADBE Position\t' in r]
        assert rows and all(r[8]=='false' and all(float(x)==0 for x in (r[10]+','+r[11]).split(',')) for r in rows),'AE linear intent unverified'
        project=out/'scene.ecproj';cli=binary()
        _execute(cli,['script','--eval','null','--empty','--save-as',str(project),'--json'],out,'initialize')
        _execute(cli,['script',str(out/'import.jsx'),'--project',str(project),'--save','--json'],out,'import')
        shutil.copy2(project,out/'unmanaged.ecproj')
        prepare_project(cli,project,out,_execute,linear_positions=True)
        render_native_video(cli,project,cfg['comp'],out/'effectcraft.mp4',cfg['fps'],out)
        common=COMMON.replace('i<240','i<'+str(round(cfg['duration']*24)))
        jsx=out/'export-motion.jsx';jsx.write_text(common+'\ndump(compNamed('+q(cfg['comp'])+'));',encoding='utf8')
        _execute(cli,['script',str(jsx),'--project',str(project),'--json'],out,'motion')
        (out/'ec-motion.tsv').write_text(read(out/'motion.stdout.json')['result'],encoding='utf8')
        for i,t in enumerate(m['times']):
            _execute(cli,['render-frame',str(project),'--comp',cfg['comp'],'--time',str(t),'--out',str(out/f'ec-{i}.png'),'--json'],out,'frame-'+str(i))
        ff=imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run([ff,'-v','error','-y','-i',str(Path(m['source'])/'render/ae_highlight.mp4'),'-c','copy','-bsf:v','h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1',str(out/'ae-reference.mp4')],check=True)
        print(name,'native full render and controls complete',flush=True)
elif args.phase=='ae-render':
    assert (D/'ae.status').read_text()=='success'
    for name in CASES:
        out=D/name
        with (out/'ae-render.log').open('w') as log:subprocess.run([str(find_aerender()),'-project',str(out/'reference.aep')],stdout=log,stderr=log,check=True,timeout=900)
        for i in range(len(read(out/'manifest.json')['times'])):subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-i',str(out/f'ae-{i}.avi'),'-frames:v','1',str(out/f'ae-{i}.png')],check=True)
        print(name,'AE lossless controls complete',flush=True)
else:
    results=[]
    def samples(p):
        rows=[r.split('\t') for r in p.read_text().splitlines()]
        return {(r[1],r[2],round(float(r[3])*24)):np.array(list(map(float,r[4].split(',')))) for r in rows if r[0]=='S'}
    for name in CASES:
        out=D/name;m=read(out/'manifest.json');a,b=samples(out/'ae-motion.tsv'),samples(out/'ec-motion.tsv')
        a={k:v for k,v in a.items() if k[2]<round(m['config']['duration']*24)}
        assert a.keys()==b.keys()
        errors={prop:max(float(abs(a[k]-b[k]).max()) for k in a if k[1]==prop) for prop in ['ADBE Position','ADBE Scale','ADBE Rotate Z']}
        assert errors['ADBE Position']<.02 and errors['ADBE Scale']<.00001 and errors['ADBE Rotate Z']<.00001
        old,new=read(out/'unmanaged.ecproj'),read(out/'scene.ecproj');effect_audit=[]
        for item_id,item in old['items'].items():
            if item['kind'].get('type')!='Comp':continue
            for before,after in zip(item['kind']['layers'],new['items'][item_id]['kind']['layers']):
                assert {k:v for k,v in before.items() if k!='props'}=={k:v for k,v in after.items() if k!='props'}
                for group in before['props']['children']:
                    other=next(g for g in after['props']['children'] if g['match']==group['match'])
                    if group['match']=='effects':
                        for fx in group['children']:
                            actual=copy.deepcopy(next(f for f in other['children'] if f['uid']==fx['uid']))
                            actual['enabled']=fx['enabled'];assert actual==fx,'Original effect parameters changed'
                            effect_audit.append(dict(comp=item['name'],layer=before['name'],effect=fx['match'],parameters={p['match']:p.get('value') for p in fx['children']}))
                    else:
                        actual=copy.deepcopy(other)
                        if group['match']=='transform':
                            for bp,ap in zip(group['children'],actual['children']):
                                for bk,ak in zip(bp.get('keys',[]),ap.get('keys',[])):
                                    if 'spatial_auto' in bk:ak['spatial_auto']=bk['spatial_auto']
                        assert actual==group,'Authored transform/mask settings changed'
        for video in ['ae-reference.mp4','effectcraft.mp4']:
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(out/video),'-f','null','-'],check=True)
        rows=[];sheet=Image.new('RGB',(1440,len(m['times'])*294),'#171717');draw=ImageDraw.Draw(sheet)
        for i,t in enumerate(m['times']):
            ai=np.array(Image.open(out/f'ae-{i}.png').convert('RGB')).astype(float);bi=np.array(Image.open(out/f'ec-{i}.png').convert('RGB')).astype(float);delta=bi-ai
            rows.append(dict(time=t,mae=float(abs(delta).mean()),mean_rgb_bias=delta.mean(axis=(0,1)).tolist(),p99=float(np.quantile(abs(delta),.99))))
            for col,img in enumerate([ai,bi,np.minimum(abs(delta)*12,255)]):sheet.paste(Image.fromarray(img.astype('uint8')).resize((480,270)),(col*480,i*294+24))
            draw.text((5,i*294+4),str(t)+'s AE | EffectCraft | absolute difference x12',fill='white')
        sheet.save(out/'comparison.jpg',quality=90)
        assert sha(Path(m['source'])/'input/scene.psd')==m['psd_sha256'] and sha(m['config']['project'])==m['aep_sha256']
        result=dict(case=name,frames=round(m['config']['duration']*24),lossless_mean_mae=float(np.mean([r['mae'] for r in rows])),max_frame_mae=max(r['mae'] for r in rows),transform_max=errors,frames_compared=rows,source_preserved=True,authored_parameters_preserved=True,effects=effect_audit,full_video_decode_passed=True)
        (out/'validation.json').write_text(json.dumps(result,indent=2));results.append(result)
    (D/'validation.json').write_text(json.dumps(results,indent=2));print(json.dumps([{k:v for k,v in r.items() if k!='frames_compared'} for r in results],indent=2),flush=True)
