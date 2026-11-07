"""Execute bounded camera poses and heat bands frozen by the web editor."""
import json
import math

def validate(timeline):
    enabled=timeline.get('contract')=='wuxia_native_timeline/v5'
    if not enabled:
        if any('motion' in s for s in timeline.get('samples',[])):raise ValueError('Image motion requires native v5')
        return
    states={s['asset_id']:s for s in timeline.get('states',[])}
    def number(v,lo,hi):return type(v) in (int,float) and math.isfinite(v) and lo<=v<=hi
    for sample in timeline.get('samples',[]):
        f=sample.get('motion')
        if not isinstance(f,dict) or f.get('contract')!='wuxia_motion_samples/v1' or f.get('issues')!=[]:
            raise ValueError('Invalid frozen image motion')
        if not number(f.get('dx'),-.03,.03) or not number(f.get('dy'),-.03,.03) or not number(f.get('scale'),1,1.24):
            raise ValueError('Unbounded frozen camera motion')
        heat=f.get('heat')
        if not isinstance(heat,list) or len(heat) not in (0,48) or any(not number(v,-5,5) for v in heat):raise ValueError('Invalid heat displacement bands')
        if heat:
            state=states.get(sample.get('state'),{})
            boxes=state.get('heat_protection_boxes')
            if state.get('heat_face_reviewed') is not True or not isinstance(boxes,list):raise ValueError('Missing heat source review')
            if any(not isinstance(b,list) or len(b)!=4 or any(not number(v,0,1) for v in b) or b[0]>=b[2] or b[1]>=b[3] for b in boxes):raise ValueError('Invalid heat protection')
            for i,dx in enumerate(heat):
                if dx!=0 and any(i/48<b[3]+.025 and (i+1)/48>b[1]-.025 for b in boxes):raise ValueError('Heat displacement overlaps reviewed anatomy')

def jsx(timeline):
    if timeline.get('contract')!='wuxia_native_timeline/v5':return ''
    validate(timeline)
    data=json.dumps([{'at':s['at'],**s['motion']} for s in timeline['samples']],allow_nan=False)
    return '''
    var WMC='''+data+''';
    // Duplicate the complete source precomp, so mouths/ambient patches follow their artwork.
    // Lettering lives in comp and is never refracted by the strip masks.
    for(var bi=0;bi<48;bi++){
      var used=false;for(var fi=0;fi<WMC.length;fi++)if(WMC[fi].heat.length&&WMC[fi].heat[bi]!==0){used=true;break;}
      if(!used)continue;
      var band=view.duplicate();band.name='wuxia_heat_band_'+bi;
      var mask=band.property('ADBE Mask Parade').addProperty('ADBE Mask Atom');
      mask.property('ADBE Mask Shape').setValue(wshape([[0,bi*H/48],[W,bi*H/48],[W,(bi+1)*H/48],[0,(bi+1)*H/48]],true));
      // A duplicate is inserted just above view, underneath all authored lettering.
      var pos=band.property('ADBE Transform Group').property('ADBE Position');
      for(var fi=0;fi<WMC.length;fi++){var f=WMC[fi],dx=f.heat.length?f.heat[bi]:0;pos.setValueAtTime(f.at,[O.width/2+dx*O.width/1920,O.height/2]);}
      whold(pos);
    }
    var cameraChildren=[];
    for(var ci=1;ci<=comp.numLayers;ci++){var layer=comp.layer(ci);if(!layer.parent&&layer.name!=='fade_backing')cameraChildren.push(layer);}
    var cameraRig=comp.layers.addNull(S.duration);cameraRig.name='wuxia_opening_camera_rig';
    var mt=cameraRig.property('ADBE Transform Group');mt.property('ADBE Anchor Point').setValue([O.width/2,O.height/2]);mt.property('ADBE Position').setValue([O.width/2,O.height/2]);
    for(var ci=0;ci<cameraChildren.length;ci++)cameraChildren[ci].parent=cameraRig;
    for(var fi=0;fi<WMC.length;fi++){var f=WMC[fi];mt.property('ADBE Position').setValueAtTime(f.at,[O.width/2+f.dx*O.width,O.height/2+f.dy*O.height]);mt.property('ADBE Scale').setValueAtTime(f.at,[f.scale*100,f.scale*100]);}
    whold(mt.property('ADBE Position'));whold(mt.property('ADBE Scale'));
'''
