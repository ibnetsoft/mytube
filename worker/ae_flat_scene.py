"""Execute saved flat-image/video camera and effects in Adobe AE, without a substitute renderer."""
import copy
import json
import math
from saved_scene_execution import validate_lights
from pathlib import Path

VERSION = 'adobe_flat_scene/v1'

def prepare(source, scene, motion, direction):
    source = Path(source)
    duration = float(scene['end']) - float(scene['start'])
    if not math.isfinite(duration) or not .1 <= duration <= 3600:
        raise ValueError('Invalid finalized scene duration')
    if scene['source_kind'] == 'video':
        from ae_scene_production import _video_info
        info = _video_info(source)
        width, height = info['width'], info['height']
        if info['duration'] + .001 < duration:
            raise ValueError('Source video is shorter than finalized narration; AE will not freeze, loop or retime it')
    else:
        from PIL import Image
        with Image.open(source) as image:
            width, height = image.size
    if not 1 <= width <= 30000 or not 1 <= height <= 30000:
        raise ValueError('Unsupported source canvas')
    keys = copy.deepcopy(direction['keys'])
    if not 2 <= len(keys) <= 8 or keys[0]['t'] != 0 or keys[-1]['t'] != 1:
        raise ValueError('AE camera needs saved keys spanning the entire scene')
    limits = {'t':(0,1),'x':(0,1),'y':(0,1),'scale':(1,2),'rotation':(-8,8),'opacity':(0,100)}
    for i, key in enumerate(keys):
        for name, (lo, hi) in limits.items():
            v = key.get(name)
            if isinstance(v, bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not lo <= v <= hi:
                raise ValueError('Invalid saved camera key: ' + name)
        if i and key['t'] <= keys[i-1]['t']:
            raise ValueError('AE camera keys must increase')
    if direction['fit'] not in ('contain','cover'):
        raise ValueError('Invalid saved fit')
    fps = motion['fps']
    if fps not in (24,30):
        raise ValueError('Unsupported final frame rate')
    size = (1080,1920) if motion['aspect'] == '9:16' else (1920,1080)
    identity = [{'t':t,'x':0,'y':0,'scale':1,'rotation':0,'opacity':100} for t in (0,1)]
    runtime=scene.get('_mouth_runtime') or {}
    if runtime.get('enabled'):
        from ae_mouth import digest
        for speaker in runtime.get('speakers',[]):
            for pose in ('closed','half','open'):
                if digest(Path(speaker['layers'][pose]))!=speaker['layer_sha256'][pose]:raise ValueError('Reviewed mouth patch changed before AE rendering')
    plan = {'width':width,'height':height,'output':{'width':size[0],'height':size[1]},
            'camera':keys,'fit':direction['fit'],'layers':[{'id':'original','role':'background','motion':identity}],
            'effects':copy.deepcopy(direction.get('effects',[])),'lights':validate_lights(direction.get('lights',[])),
            'mouth_runtime':copy.deepcopy(scene.get('_mouth_runtime')),
            'transition':{'in':'none','out':'none','fraction':0}}
    from ae_scene_effects import validate_effects
    validate_effects(plan)
    return {'plan':plan,'layers':{'original':source},'flat_media':True,'video_source':scene['source_kind']=='video','fps':fps}

def write_jsx(plan, layer_paths, project, native, jsx, duration, fps=24):
    from ae_scene_animation import SCENE_JSX
    from ae_scene_effects import EFFECTS_JSX
    for effect in plan['effects']:
        if (effect['end']-effect['start'])*duration*fps < 3:
            raise ValueError('Saved AE effect must span at least three output frames')
    data = {'plan':plan,'layers':plan['layers'],'files':{k:str(Path(v).resolve()) for k,v in layer_paths.items()},
            'duration':duration,'fps':fps,'project':str(project.resolve()),'native':str(native.resolve()),
            'status':str(jsx.with_suffix('.status.txt').resolve())}
    script = SCENE_JSX.replace('/* SCENE_EFFECTS */', EFFECTS_JSX)
    if plan.get('mouth_runtime'):
        from ae_mouth import mouth_jsx
        script=script.replace('var footage=app.project.importFile(new ImportOptions(f));', 'var footage=app.project.importFile(new ImportOptions(f)); footage=(function(footage){var DUR=S.duration,FPS=S.fps;'+mouth_jsx(plan['mouth_runtime'])+' return footage;})(footage);')
    # Original footage remains at 1x; only saved camera transforms are animated.
    script = script.replace('layer.outPoint=S.duration;', 'layer.outPoint=S.duration; if(layer.hasAudio) layer.audioEnabled=false;')
    if plan['fit'] == 'contain':
        script = script.replace('base=Math.max(O.width/W,O.height/H)', 'base=Math.min(O.width/W,O.height/H)')
    start = script.index('    var opacity=V.property("ADBE Opacity"),T=P.transition;')
    end = script.index('    var item=app.project.renderQueue.items.add(comp);', start)
    script = script[:start] + '''    var opacity=V.property("ADBE Opacity");
    for(var a=0;a<P.camera.length;a++) key(opacity,P.camera[a].t,P.camera[a].opacity);
    linear(opacity);
''' + script[end:]
    if plan.get('speech_bubbles'):
        from speech_bubble_shapes import BUBBLE_JSX
        script=script.replace('    var item=app.project.renderQueue.items.add(comp);', BUBBLE_JSX+'\n    var item=app.project.renderQueue.items.add(comp);')
    jsx.write_text('var S = '+json.dumps(data,ensure_ascii=True,allow_nan=False)+';\n'+script,encoding='utf-8')
