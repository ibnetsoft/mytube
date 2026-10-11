"""User-defined, bounded region motion. No generated JSX from free-form commands."""
from __future__ import annotations
import json
import math
import uuid
from pathlib import Path


def validate_input(data):
    duration = data['timeline']['duration']
    if not isinstance(duration, (int, float)) or not math.isfinite(duration) or not .1 <= duration <= 300:
        raise ValueError('Invalid scene duration')
    regions = data.get('regions')
    if not isinstance(regions, list) or not 1 <= len(regions) <= 32:
        raise ValueError('Select 1-32 regions')
    def number(v, lo, hi):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and lo <= v <= hi
    def point(p):
        return isinstance(p, list) and len(p) == 2 and all(number(v, 0, 1) for v in p)
    ids = set()
    for r in regions:
        if not r.get('id') or r['id'] in ids:
            raise ValueError('Duplicate region')
        ids.add(r['id'])
        p = r.get('polygon')
        if not isinstance(p, list) or not 3 <= len(p) <= 32 or not all(point(v) for v in p) or not point(r.get('anchor')):
            raise ValueError('Invalid region boundary or anchor')
        area = abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(p, p[1:]+p[:1]))) / 2
        if not .0001 <= area <= .7:
            raise ValueError('Region area must be 0.01%-70%')
        if r.get('action') not in ('horizontal', 'vertical', 'rotate', 'scale', 'bend', 'walk', 'hold'):
            raise ValueError('Unsupported motion')
        if not number(r.get('amplitude'), .1, 120 if r['action'] in ('rotate', 'bend', 'walk') else 15) or not number(r.get('period'), .2, 30):
            raise ValueError('Invalid amplitude or period')
        if not isinstance(r.get('cycles'), int) or not 1 <= r['cycles'] <= 30:
            raise ValueError('Invalid repetition count')
        if not number(r.get('restAngle', 0), -180, 180) or not number(r.get('phaseOffset', 0), 0, 1) or r.get('walkPart', 'upper') not in ('upper', 'lower') or r.get('direction', 1) not in (-1, 1):
            raise ValueError('Invalid joint angle or gait')
        if not isinstance(r.get('parentId', ''), str):
            raise ValueError('Invalid parent joint')
        cue = next((s for s in data['timeline']['subtitles'] if s['id'] == r.get('subtitleId')), None)
        if not cue or not number(r.get('start'), 0, duration) or abs(cue['start'] - r['start']) > .001 or r['start'] + r['cycles'] * r['period'] > duration + .001:
            raise ValueError('Motion exceeds scene or subtitle changed')
    by_id = {r['id']: r for r in regions}
    for r in regions:
        seen = {r['id']}
        parent = r.get('parentId')
        while parent:
            if parent in seen or parent not in by_id:
                raise ValueError('Missing parent or cyclic joint hierarchy')
            seen.add(parent)
            parent = by_id[parent].get('parentId')
        if r['action'] in ('bend', 'walk') and not r.get('parentId'):
            raise ValueError('Joint motion requires a parent')
    return data


def phase(region, time):
    elapsed = time - region['start']
    return 0 if elapsed <= 0 or elapsed >= region['period'] * region['cycles'] else math.sin(2 * math.pi * elapsed / region['period'])


def prepare_layers(source: Path, directory: Path, data: dict):
    raise ValueError('검수·승인된 레이어 패키지 없이 자동 분할 또는 배경 복원을 실행하지 않습니다.')


def write_jsx(runtime, project: Path, output: Path, jsx: Path):
    # All user values are JSON-encoded data, never executable expressions or paths.
    payload = json.dumps({**runtime, 'project':str(project.resolve()), 'output':str(output.resolve()), 'status':str(jsx.with_suffix('.status.txt').resolve())},ensure_ascii=True)
    script = r'''
var D=__DATA__;
app.exitAfterLaunchAndEval=true;
app.beginSuppressDialogs();
function receipt(text){var f=new File(D.status);if(f.open('w')){f.write(text);f.close();}}
function footage(path){var o=new ImportOptions(new File(path));return app.project.importFile(o);}
try {
 app.newProject();
 var c=app.project.items.addComp('AIR_REGION_MOTION',D.width,D.height,1,D.duration,24);
 c.layers.add(footage(D.background)).name='Repaired background';
 var layers={}, bases={};
 // Create every layer at rest before parenting, so AE preserves canvas coordinates.
 for(var i=0;i<D.regions.length;i++){
  var r=D.regions[i],l=c.layers.add(footage(r.path));l.name=r.name;
  var a=[r.anchor[0]*D.width,r.anchor[1]*D.height];
  var tr=l.property('ADBE Transform Group');
  tr.property('ADBE Anchor Point').setValue(a);tr.property('ADBE Position').setValue(a);
  tr.property('ADBE Scale').setValue([100,100]);layers['region:'+r.id]=l;
 }
 for(var i=0;i<D.regions.length;i++){
  var r=D.regions[i],l=layers['region:'+r.id];
  if(r.parentId)l.parent=layers['region:'+r.parentId];
  bases['region:'+r.id]=l.property('ADBE Transform Group').property('ADBE Position').value;
 }
 // Array order is back-to-front, independent of hierarchy.
 for(var i=0;i<D.regions.length;i++){
  var r=D.regions[i],l=layers['region:'+r.id],a=bases['region:'+r.id];
  var tr=l.property('ADBE Transform Group');
  tr.property('ADBE Rotate Z').setValue(r.restAngle||0);
  if(r.action=='hold')continue;
  var angular=r.action=='rotate'||r.action=='bend'||r.action=='walk';
  var propertyName=angular?'ADBE Rotate Z':r.action=='scale'?'ADBE Scale':'ADBE Position';
  var prop=tr.property(propertyName);
  if(prop.matchName!=propertyName)throw new Error('Unexpected AE transform property');
  // Start in the rest pose even when this joint begins after its parent.
  prop.setValueAtTime(0,angular?(r.restAngle||0):r.action=='scale'?[100,100]:a);
  var steps=r.cycles*24;
  for(var k=0;k<=steps;k++){
   var t=r.start+r.period*r.cycles*k/steps;
   var wave=(k==0||k==steps)?0:Math.sin(2*Math.PI*(r.cycles*k/steps+(angular?(r.phaseOffset||0):0)));
   if(r.action=='walk'&&r.walkPart=='lower')wave=Math.max(0,wave);
   var v=wave*r.amplitude*(angular?(r.direction||1):1);
   var value;
   if(angular){value=(r.restAngle||0)+v;}
   else if(r.action=='scale'){value=[100+v,100+v];}
   else if(r.action=='horizontal'){value=[a[0]+v*D.width/100,a[1]];}
   else{value=[a[0],a[1]+v*D.height/100];}
   prop.setValueAtTime(t,value);
  }
  for(var j=1;j<=prop.numKeys;j++)prop.setInterpolationTypeAtKey(j,KeyframeInterpolationType.LINEAR,KeyframeInterpolationType.LINEAR);
 }
 var q=app.project.renderQueue.items.add(c);q.outputModule(1).file=new File(D.output);
 app.project.save(new File(D.project));
 receipt('success|'+D.project);
 app.scheduleTask('app.quit()',1200,false);
} catch(e){receipt('error|'+e.toString());app.scheduleTask('app.quit()',1200,false);throw e;}
finally{app.endSuppressDialogs(false);}
'''.replace('__DATA__',payload)
    jsx.with_suffix('.status.txt').unlink(missing_ok=True)
    jsx.write_text(script,encoding='utf-8')


def rendered_media(requested):
    # AE output-module presets may replace the requested extension (e.g. H.264).
    candidates = [p for p in requested.parent.glob(requested.stem + '.*')
                  if p.suffix.lower() in ('.avi', '.mp4', '.mov', '.mxf') and p.stat().st_size > 0]
    if len(candidates) != 1:
        raise RuntimeError('AE did not produce one supported video file: ' + str(requested))
    return candidates[0]


def render(source, directory, data, prepared_runtime=None):
    import ae_highlight_worker as ae
    from ae_media_utils import ffmpeg, run
    from media_checkpoint import valid_mp4
    if not prepared_runtime:
        raise ValueError('검수·승인된 레이어 패키지가 필요합니다.')
    runtime=prepared_runtime
    project,raw,output,jsx=[directory/name for name in ('region-motion.aep','native-'+uuid.uuid4().hex+'.avi','region-motion.mp4','region-motion.jsx')]
    afterfx=ae.find_afterfx();aerender=ae.find_aerender()
    if not afterfx or not aerender:raise RuntimeError('After Effects executable not found')
    write_jsx(runtime,project,raw,jsx)
    ae._run_afterfx_script(afterfx,jsx,project)
    ae._run_checked([str(aerender),'-project',str(project),'-comp','AIR_REGION_MOTION','-output',str(raw)],timeout=1200)
    raw=rendered_media(raw)
    run([ffmpeg(),'-y','-i',str(raw),'-an','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(output)])
    if not valid_mp4(output,data['timeline']['duration']*.95):raise RuntimeError('AE output duration is invalid')
    return output
