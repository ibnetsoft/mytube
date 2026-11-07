"""Validate and execute the scene-boundary frames frozen by the web editor."""
import math
import json

KINDS={'none','wipe_left','wipe_right','wipe_up','wipe_down','flash','punch','snap_shake','dissolve','fade_out'}

def validate(timeline):
    samples=timeline.get('samples') or []
    enabled=timeline.get('contract')=='wuxia_native_timeline/v4'
    if not enabled and any('transition' in s for s in samples):
        raise ValueError('Scene transitions require wuxia native v4')
    if not enabled:return
    kind=None
    for sample in samples:
        f=sample.get('transition')
        if not isinstance(f,dict) or f.get('contract')!='wuxia_transition_samples/v1' or f.get('issues')!=[] or f.get('kind') not in KINDS:
            raise ValueError('Invalid frozen scene transition')
        if kind is not None and kind!=f['kind']:raise ValueError('Scene transition kind changed mid-scene')
        kind=f['kind']
        for key,lo,hi in [('dx',-1,1),('dy',-1,1),('scale',1,1.06),('opacity',0,1),('flash',0,.8),('backdrop',0,1)]:
            v=f.get(key)
            if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi:
                raise ValueError('Unsafe frozen transition '+key)

def jsx(timeline):
    if timeline.get('contract')!='wuxia_native_timeline/v4':return ''
    validate(timeline)
    data=json.dumps({'samples':[{'at':s['at'],**s['transition']} for s in timeline['samples']],
                     'backdrop':timeline.get('transition_source')},ensure_ascii=True,allow_nan=False)
    return '''
    var WTR='''+data+''';
    var transitionChildren=[];
    for(var ti=1;ti<=comp.numLayers;ti++){var tl=comp.layer(ti);if(!tl.parent&&tl.name!=='fade_backing')transitionChildren.push(tl);}
    var transitionRig=comp.layers.addNull(S.duration);transitionRig.name='wuxia_scene_transition_rig';
    var tt=transitionRig.property('ADBE Transform Group');tt.property('ADBE Anchor Point').setValue([O.width/2,O.height/2]);tt.property('ADBE Position').setValue([O.width/2,O.height/2]);
    for(var ti=0;ti<transitionChildren.length;ti++)transitionChildren[ti].parent=transitionRig;
    var back=null;
    if(WTR.backdrop){
      var bf=app.project.importFile(new ImportOptions(new File(WTR.backdrop.file)));back=comp.layers.add(bf);back.name='wuxia_transition_previous_still';back.outPoint=S.duration;
      var bt=back.property('ADBE Transform Group'),fit=Math.max(O.width/bf.width,O.height/bf.height)*100;
      bt.property('ADBE Position').setValue([O.width/2,O.height/2]);bt.property('ADBE Scale').setValue([fit,fit]);back.moveBefore(comp.layer('fade_backing'));
    }
    var flash=comp.layers.addSolid([1,1,1],'wuxia_transition_flash',O.width,O.height,1,S.duration);
    var originalOpacity=[];
    for(var ci=0;ci<transitionChildren.length;ci++){var values=[],op=transitionChildren[ci].property('Opacity');for(var ti=0;ti<WTR.samples.length;ti++)values.push(op.valueAtTime(WTR.samples[ti].at,false));originalOpacity.push(values);}
    for(var ti=0;ti<WTR.samples.length;ti++){
      var f=WTR.samples[ti];tt.property('ADBE Position').setValueAtTime(f.at,[O.width/2+f.dx*O.width,O.height/2+f.dy*O.height]);
      tt.property('ADBE Scale').setValueAtTime(f.at,[f.scale*100,f.scale*100]);
      // AE null opacity does not propagate to children. Freeze opacity on each visible child.
      for(var ci=0;ci<transitionChildren.length;ci++){var op=transitionChildren[ci].property('ADBE Transform Group').property('ADBE Opacity');op.setValueAtTime(f.at,originalOpacity[ci][ti]*f.opacity);}
      flash.property('Opacity').setValueAtTime(f.at,f.flash*100);
      if(back)back.property('Opacity').setValueAtTime(f.at,f.backdrop*100);
    }
    whold(tt.property('ADBE Position'));whold(tt.property('ADBE Scale'));whold(flash.property('Opacity'));
    for(var ci=0;ci<transitionChildren.length;ci++)whold(transitionChildren[ci].property('Opacity'));
    if(back)whold(back.property('Opacity'));
'''
