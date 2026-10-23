"""Optional, pinned EffectCraft renderer. Never falls back to Adobe or discards unsupported features.

Only visual scenes are rendered here. Final recording, captions, sound mix and independent
actual-output review remain in the existing submitted production worker.
"""
from __future__ import annotations
import hashlib
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PIN=json.loads((ROOT/'auth-web/lib/effectcraftSource.json').read_text(encoding='utf-8'))

def sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()

def binary():
    configured=os.getenv('EFFECTCRAFT_CLI','').strip()
    default=ROOT/'output/effectcraft'/(platform.system().lower()+'-'+platform.machine().lower())/('effectcraft-cli.exe' if os.name=='nt' else 'effectcraft-cli')
    path=Path(configured).expanduser().resolve() if configured else default
    if not path.is_file():raise ValueError('EffectCraft 엔진이 설치되지 않았습니다. scripts/build_effectcraft.py로 이 워커용 엔진을 빌드하세요. 기존 AE로 자동 전환하지 않습니다.')
    manifest=path.parent/'build-manifest.json'
    if not manifest.is_file():raise ValueError('EffectCraft 빌드 영수증이 없습니다. 소스 버전과 바이너리를 확인해 주세요.')
    receipt=json.loads(manifest.read_text(encoding='utf-8'))
    if receipt.get('revision')!=PIN['revision'] or receipt.get('binaries',{}).get(path.name)!=sha(path):raise ValueError('EffectCraft 소스 버전 또는 실행 파일 해시가 다릅니다.')
    return path

def _execute(cli,arguments,directory,stage):
    # Each child receives its own isolated preferences and no provider credentials.
    env={k:v for k,v in os.environ.items() if k!='AIR_WORKER_ENV_FILE' and not any(s in k.upper() for s in ('TOKEN','SECRET','PASSWORD','API_KEY','CREDENTIAL','SUPABASE','GOOGLE','OPENAI','GEMINI','ANTHROPIC'))}
    env['EFFECTCRAFT_CONFIG_DIR']=str(directory/'engine-config')
    stdout=directory/(stage+'.stdout.json');stderr=directory/(stage+'.stderr.log')
    with stdout.open('w',encoding='utf-8') as out,stderr.open('w',encoding='utf-8') as err:
        result=subprocess.run([str(cli),*arguments],cwd=directory,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,timeout=3600,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0)
    if result.returncode:raise ValueError('EffectCraft '+stage+' 실패. 원본·프로젝트·로그를 보존했습니다. 미지원 기능을 기존 AE로 조용히 대체하지 않습니다.')
    try:response=json.loads(stdout.read_text(encoding='utf-8'))
    except (ValueError,OSError):raise ValueError('EffectCraft returned no validated JSON receipt')
    if isinstance(response,dict) and (response.get('error') or response.get('ok') is False):raise ValueError('EffectCraft command was rejected; inspect preserved engine logs')

def _scene_script(data):
    from ae_scene_animation import SCENE_JSX
    from ae_scene_effects import EFFECTS_JSX
    # Reuse our public-API scene emitter, not Adobe code. Exclude native AE process/file handling.
    begin='    var P=S.plan,W=P.width,H=P.height,O=P.output;'
    end='    var item=app.project.renderQueue.items.add(comp);'
    if SCENE_JSX.count(begin)!=1 or SCENE_JSX.count(end)!=1:raise ValueError('Scene emitter contract changed; EffectCraft adapter needs updating')
    helpers=SCENE_JSX[SCENE_JSX.index('  function linear('):SCENE_JSX.index('  var ownsProject=false;')].replace('/* SCENE_EFFECTS */',EFFECTS_JSX)
    body=SCENE_JSX.split(begin,1)[1].split(end,1)[0]
    body=begin+body
    body=body.replace('base=Math.max(O.width/W,O.height/H)','base=(S.fit==="contain"?Math.min:Math.max)(O.width/W,O.height/H)')
    if data.get('generic'):
        body=body.replace('    applySceneEffects(source,semanticLayers);','')
        # Generic effect coordinates are in the output viewport, unlike prepared PSD source coordinates.
        body+='\nW=O.width;H=O.height;applySceneEffects(comp,{original:view});\n'
        body+='\nfor(var o=0;o<S.opacity.length;o++){key(opacity,S.opacity[o].t,S.opacity[o].opacity);}linear(opacity);\n'
        if data.get('video_tail'):
            raise ValueError('Video frame holds are prohibited')
        if data.get('flash'):
            body+='\nvar flash=comp.layers.addSolid([1,1,1],"entry_flash",O.width,O.height,1,S.duration);var alpha=flash.transform.opacity;key(alpha,0,100);key(alpha,.08,0);linear(alpha);\n'
    return 'var S='+json.dumps(data,ensure_ascii=True,allow_nan=False)+';\n(function(){\n'+helpers+body+'\n})();\n'

def render_scene(snapshot,scene,plan,source,directory,fresh):
    cli=binary();directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=True)
    if snapshot.get('renderer',{}).get('revision')!=PIN['revision']:raise ValueError('Submitted EffectCraft revision differs from this worker')
    duration=scene['end']-scene['start'];motion=plan['scene'];fps=snapshot['motion']['fps']
    authored=snapshot['motion']['scenes'].get(str(scene['number']),{})
    if snapshot['motion'].get('web'):raise ValueError('Browser-only timelines and insert settings require their browser renderer')
    for candidate in (motion,authored):
        if any(candidate.get(k) for k in ('cues','finance')) or any(candidate.get('native',{}).get(k) for k in ('paths','effects')) or any(l.get('advanced') for l in candidate.get('layers',{}).values()):raise ValueError('EffectCraft adapter does not silently discard browser-only geometry or rigs')
    output={'width':1080,'height':1920} if snapshot['motion']['aspect']=='9:16' else {'width':1920,'height':1080}
    if scene['source_kind']=='psd':
        from ae_scene_production import load_preparation
        from ae_scene_animation import resolved_layers
        if not scene.get('preparation'):raise ValueError('검수한 PSD 레이어·연출 패키지가 필요합니다. 제출 전 대본워커에서 준비해 주세요.')
        prepared=load_preparation({'number':scene['number'],'ae_scene':scene['preparation']},directory/'preparation',fresh)
        if prepared['plan']['output']!=output:raise ValueError('Prepared PSD output differs from submitted orientation')
        data={'plan':prepared['plan'],'layers':resolved_layers(prepared['plan']),'files':{key:str(path.resolve()) for key,path in prepared['layers'].items()},'fit':'cover'}
    else:
        source=Path(source);local=directory/('original'+source.suffix.lower())
        if not local.exists():
            try:os.link(source,local)
            except OSError:shutil.copy2(source,local)
        video_tail=None
        if scene['source_kind']=='video':
            from moviepy import VideoFileClip
            with VideoFileClip(str(local),audio=False) as video:
                width,height=map(int,video.size)
                from services.video_playback_policy import require_video_duration
                require_video_duration(video.duration,duration,video.fps,scene['number'])
        else:
            from PIL import Image,ImageOps
            with Image.open(local) as image:
                oriented=ImageOps.exif_transpose(image).convert('RGBA');width,height=oriented.size
                local=directory/'original-normalized.png';oriented.save(local)
        if any(e['type']=='impact_shake' for e in motion['effects']) and any(k['scale']<1.03 for k in motion['keys']):raise ValueError('EffectCraft impact shake needs a prepared camera with at least 3% overscan')
        layers=[{'id':'original','role':'background','anchor':[.5,.5],'motion':[dict(t=t,x=0,y=0,scale=1,rotation=0,opacity=100) for t in (0,1)]}]
        from services.motion_render_service import pose_at
        opacity_times=sorted({k['t'] for k in motion['keys']}|({.08} if motion['transition']=='fade' else set()))
        opacity=[dict(t=t,opacity=pose_at(motion['keys'],t)['opacity']*(min(1,t/.08) if motion['transition']=='fade' else 1)) for t in opacity_times]
        data={'plan':{'width':width,'height':height,'output':output,'layers':layers,'camera':motion['keys'],'effects':[{**e,'reason':motion['direction'] or 'Saved scene direction'} for e in motion['effects']],
              'lights':[],'transition':{'in':'cut','out':'cut','fraction':.08}},'layers':layers,'files':{'original':str(local)},'fit':motion['fit'],'generic':True,'opacity':opacity,'flash':motion['transition']=='flash'}
        if video_tail:data['video_tail']=video_tail
    data.update(duration=duration,fps=fps)
    if plan.get('_supplemental_package'):
        from ec_supplemental_assets import attach
        data=attach(data,plan['_supplemental_package'],source,directory)
    script=directory/'scene.effectcraft.jsx';script.write_text(_scene_script(data),encoding='utf-8')
    from motion_media_storage import media_directory
    project=directory/'scene.ecproj';output_file=media_directory(directory)/'base.mp4'
    for prior in (project,output_file):
        if prior.is_file():prior.replace(prior.with_name(prior.stem+'-'+sha(prior)[:16]+'.previous'+prior.suffix))
    fresh();_execute(cli,['script','--eval','null','--empty','--save-as',str(project),'--json'],directory,'initialize-project')
    fresh();_execute(cli,['script',str(script),'--project',str(project),'--save','--json'],directory,'create-project')
    if not project.is_file():raise ValueError('EffectCraft did not save the editable project')
    fresh();_execute(cli,['render',str(project),'--comp','ae_scene','--out',str(output_file),'--format','h264','--audio','off','--fps',str(fps),'--json'],directory,'render-scene')
    if not output_file.is_file() or not output_file.stat().st_size:raise ValueError('EffectCraft produced no video')
    receipt={'engine':'effectcraft','revision':PIN['revision'],'project':project.name,'project_sha256':sha(project),'output_sha256':sha(output_file),'review_status':'rendered_requires_actual_review',
             'supplemental_fingerprint':(plan.get('_supplemental_package') or {}).get('fingerprint')}
    (directory/'effectcraft-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    fresh();return output_file
