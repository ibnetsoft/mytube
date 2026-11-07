"""Execute the frozen editor schedule: state cuts, ambient patches, editable lettering."""
import copy,json
from pathlib import Path
from PIL import Image
from ambient_loop import digest,prepare_runtime,frame_index

def prepare(timeline,directory,fresh,download,duration,fps,audio=None):
 if timeline.get('contract') not in ('wuxia_native_timeline/v1','wuxia_native_timeline/v2','wuxia_native_timeline/v3'):raise ValueError('Invalid wuxia timeline')
 if any(s.get('dialogue_mouths') for s in timeline.get('states',[])) and timeline['contract'] not in ('wuxia_native_timeline/v2','wuxia_native_timeline/v3'):raise ValueError('Mouth patches require the updated native timeline contract')
 result=copy.deepcopy(timeline);directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
 states=result.get('states') or [];samples=result.get('samples') or []
 if not 1<=len(states)<=100 or len(samples)!=__import__('math').ceil(duration*fps):raise ValueError('Wuxia schedule does not match finalized timing')
 ids={s['asset_id'] for s in states}
 if len(ids)!=len(states):raise ValueError('Duplicate wuxia state')
 for i,sample in enumerate(samples):
  if abs(sample['at']-i/fps)>1e-7 or sample['state'] not in ids:raise ValueError('Invalid wuxia output frame clock')
 from wuxia_effects import validate_samples
 validate_samples(timeline)
 size=None
 for state in states:
  fresh();path=directory/(state['sha256']+'.png')
  if not path.exists() or digest(path)!=state['sha256']:download(state,path)
  if digest(path)!=state['sha256']:raise ValueError('Wuxia state checksum mismatch')
  with Image.open(path) as image:
   if image.format!='PNG' or getattr(image,'n_frames',1)!=1:raise ValueError('Wuxia source must remain a still PNG')
   if size and size!=image.size:raise ValueError('Wuxia state canvas mismatch')
   size=image.size
  state['file']=str(path.resolve())
  state['ambient_runtime']=prepare_runtime(path,state.get('ambient_loops',[]),directory/'ambient',fresh,download)
  from wuxia_mouth import prepare as prepare_mouths
  state['mouth_runtime']=prepare_mouths(path,state.get('dialogue_mouths',[]),directory/'mouths',fresh,download,audio)
 result['size']=list(size)
 return result

def jsx(timeline,duration,fps):
 states=[]
 for state in timeline['states']:
  keys=[];previous=False
  for sample in timeline['samples']:
   active=sample['state']==state['asset_id']
   if active!=previous:keys.append([sample['at'],100 if active else 0]);previous=active
  patches=[]
  for loop_id,loop in enumerate(state['ambient_runtime']):
   frame_keys=[[] for _ in loop['frames']];previous=None
   for sample in timeline['samples']:
    visible=next((a for a in sample.get('ambient',[]) if a['loop']==loop_id),None)
    current=visible['frame'] if sample['state']==state['asset_id'] and visible else None
    if current is not None and (type(current) is not int or not 0<=current<len(loop['frames'])):raise ValueError('Invalid frozen ambient frame')
    if current!=previous:
     if previous is not None:frame_keys[previous].append([sample['at'],0])
     if current is not None:frame_keys[current].append([sample['at'],100])
     previous=current
   patches.extend({'file':file,'keys':k} for file,k in zip(loop['files'],frame_keys))
  for mouth_id,mouth in enumerate(state.get('mouth_runtime',[])):
   pose_keys={p:[] for p in ('closed','half','open')};previous=None
   for sample in timeline['samples']:
    visible=next((m for m in sample.get('mouths',[]) if m['mouth']==mouth_id),None)
    current=visible['pose'] if sample['state']==state['asset_id'] and visible else None
    if current is not None and current not in pose_keys:raise ValueError('Invalid frozen mouth pose')
    if current!=previous:
     if previous is not None:pose_keys[previous].append([sample['at'],0])
     if current is not None:pose_keys[current].append([sample['at'],100])
     previous=current
   patches.extend({'file':mouth['files'][p],'keys':k} for p,k in pose_keys.items())
  states.append({'file':state['file'],'keys':keys,'patches':patches})
 graphics=[]
 for identity,g in timeline['graphics'].items():
  keys=[]
  for sample in timeline['samples']:
   pose=next((p for p in sample['graphics'] if p['id']==identity),None)
   keys.append([sample['at'],pose['opacity']*100 if pose else 0,pose['scale']*100 if pose else 100,pose['rotation'] if pose else 0])
  graphics.append({**g,'keys':keys})
 data=json.dumps({'states':states,'graphics':graphics,'effect_samples':[{'at':sample['at'],**({'dx':0,'dy':0,'scale':1,'overlays':[]}|sample.get('effects',{}))} for sample in timeline['samples']] if timeline.get('contract')=='wuxia_native_timeline/v3' else []},ensure_ascii=True,allow_nan=False)
 source_js='''
    var WT='''+data+''';
    function whold(p){for(var k=1;k<=p.numKeys;k++)p.setInterpolationTypeAtKey(k,KeyframeInterpolationType.HOLD,KeyframeInterpolationType.HOLD);}
    function wshape(vertices,closed){var sh=new Shape(),ins=[],outs=[];for(var k=0;k<vertices.length;k++){ins.push([0,0]);outs.push([0,0]);}sh.vertices=vertices;sh.inTangents=ins;sh.outTangents=outs;sh.closed=closed;return sh;}
    var wrig=null;
    if(WT.effect_samples.length){wrig=source.layers.addNull(S.duration);wrig.name='wuxia_art_impact_rig';var rt=wrig.property('ADBE Transform Group');rt.property('ADBE Anchor Point').setValue([W/2,H/2]);rt.property('ADBE Position').setValue([W/2,H/2]);}
    function wimage(d,name){var f=app.project.importFile(new ImportOptions(new File(d.file)));if(f.width!==W||f.height!==H)throw new Error('Wuxia source canvas mismatch');var l=source.layers.add(f);l.name=name;l.outPoint=S.duration;var op=l.property('Opacity');op.setValueAtTime(0,0);for(var k=0;k<d.keys.length;k++)op.setValueAtTime(d.keys[k][0],d.keys[k][1]);whold(op);if(wrig)l.parent=wrig;return l;}
    semanticLayers.original.enabled=false;
    for(var wi=0;wi<WT.states.length;wi++){var ws=WT.states[wi];wimage(ws,'wuxia_state_'+wi);for(var wp=0;wp<ws.patches.length;wp++)wimage(ws.patches[wp],'wuxia_ambient_'+wi+'_'+wp);}
    if(wrig){
      var tr=wrig.property('ADBE Transform Group'),pos=tr.property('ADBE Position'),sca=tr.property('ADBE Scale');
      for(var ei=0;ei<WT.effect_samples.length;ei++){
        var ef=WT.effect_samples[ei];pos.setValueAtTime(ef.at,[W/2+ef.dx*W/1920,H/2+ef.dy*H/1080]);sca.setValueAtTime(ef.at,[ef.scale*100,ef.scale*100]);
        for(var oi=0;oi<ef.overlays.length;oi++){
          var q=ef.overlays[oi],l=source.layers.addShape();l.name='wuxia_impact_vector_'+ei+'_'+oi;l.inPoint=ef.at;l.outPoint=Math.min(S.duration,ef.at+1/S.fps);l.property('Position').setValue([0,0]);
          var c=l.property('Contents').addProperty('ADBE Vector Group').property('Contents');
          if(q.kind==='ellipse'){var el=c.addProperty('ADBE Vector Shape - Ellipse');el.property('ADBE Vector Ellipse Size').setValue([q.rx*2*W/1920,q.ry*2*H/1080]);el.property('ADBE Vector Ellipse Position').setValue([q.cx*W/1920,q.cy*H/1080]);}
          else{var vertices=[];for(var pi=0;pi<q.points.length;pi++)vertices.push([q.points[pi][0]*W/1920,q.points[pi][1]*H/1080]);var sh=wshape(vertices,q.kind==='polygon');c.addProperty('ADBE Vector Shape - Group').property('Path').setValue(sh);}
          var rgb=[parseInt(q.color.substr(1,2),16)/255,parseInt(q.color.substr(3,2),16)/255,parseInt(q.color.substr(5,2),16)/255];
          if(q.kind==='line'||q.stroke){var st=c.addProperty('ADBE Vector Graphic - Stroke');st.property('Color').setValue(rgb);st.property('Stroke Width').setValue((q.width||q.stroke)*W/1920);}else c.addProperty('ADBE Vector Graphic - Fill').property('Color').setValue(rgb);
          l.property('Opacity').setValue(q.opacity*100);l.parent=wrig;
        }
      }whold(pos);whold(sca);
    }
'''
 graphic_js=r'''
    function wpose(l,g,center){var tr=l.property('ADBE Transform Group');tr.property('ADBE Anchor Point').setValue(center);tr.property('ADBE Position').setValue(center);var op=tr.property('ADBE Opacity'),sc=tr.property('ADBE Scale'),rot=tr.property('ADBE Rotate Z');for(var k=0;k<g.keys.length;k++){var a=g.keys[k];op.setValueAtTime(a[0],a[1]);sc.setValueAtTime(a[0],[a[2],a[2]]);rot.setValueAtTime(a[0],a[3]);}whold(op);whold(sc);whold(rot);}
    for(var gi=0;gi<WT.graphics.length;gi++){
      var g=WT.graphics[gi],speech=g.kind==='speech_bubble',c=[g.layout.center[0]*1920,g.layout.center[1]*1080],s=g.style||{};
      if(speech){var bubble=comp.layers.addShape();bubble.name='authored_bubble_'+gi;bubble.property('Position').setValue([0,0]);var group=bubble.property('Contents').addProperty('ADBE Vector Group').property('Contents'),shape=wshape(g.points,true);group.addProperty('ADBE Vector Shape - Group').property('Path').setValue(shape);group.addProperty('ADBE Vector Graphic - Fill').property('Color').setValue([1,.996,.969]);var stroke=group.addProperty('ADBE Vector Graphic - Stroke');stroke.property('Color').setValue([.082,.106,.133]);stroke.property('Stroke Width').setValue(3);if(g.bubble_style==='whisper'){var dash=stroke.property('ADBE Vector Stroke Dashes');dash.addProperty('ADBE Vector Stroke Dash 1').setValue(12);dash.addProperty('ADBE Vector Stroke Gap 1').setValue(8);}wpose(bubble,g,c);}
      var text=comp.layers.addText(g.lines.join('\r'));text.name='authored_'+g.kind+'_'+gi;var prop=text.property('Source Text'),doc=prop.value;doc.font=s.font||'NotoSansKR-Bold';doc.fontSize=g.font_size;doc.applyFill=true;doc.fillColor=s.fill||(speech?[.082,.106,.133]:[1,.949,.792]);doc.applyStroke=!speech;doc.strokeColor=s.stroke||[.082,.125,.165];doc.strokeWidth=s.stroke_width||2;doc.strokeOverFill=false;doc.justification=ParagraphJustification.CENTER_JUSTIFY;doc.autoLeading=false;doc.leading=g.font_size*1.16;prop.setValue(doc);var r=text.sourceRectAtTime(0,false);text.property('Anchor Point').setValue([r.left+r.width/2,r.top+r.height/2]);text.property('Position').setValue(c);
      var tr=text.property('ADBE Transform Group'),op=tr.property('ADBE Opacity'),sc=tr.property('ADBE Scale'),rot=tr.property('ADBE Rotate Z');for(var ki=0;ki<g.keys.length;ki++){var a=g.keys[ki];op.setValueAtTime(a[0],a[1]);sc.setValueAtTime(a[0],[a[2],a[2]]);rot.setValueAtTime(a[0],a[3]);}whold(op);whold(sc);whold(rot);
    }
'''
 return source_js,graphic_js
