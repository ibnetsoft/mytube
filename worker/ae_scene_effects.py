"""Reviewed, bounded finishing effects for the web PSD scene renderer.

Effect times use the same normalized narration timeline as camera and layer keys.
No effect may replace source artwork or silently skip missing AE capabilities.
"""
import math

EFFECT_TYPES = frozenset({
    'atmospheric_haze', 'warm_dust_motes', 'focus_glow', 'light_sweep',
    'impact_flash', 'heat_distortion', 'subtle_vignette', 'speedline_burst',
    'impact_shake', 'shock_ring', 'energy_trail', 'particle_burst', 'debris_burst', 'fireflies',
})


def validate_effects(plan, requested=None):
    effects = plan.get('effects', [])
    if not isinstance(effects, list) or len(effects) > len(EFFECT_TYPES):
        raise ValueError('AE effects must be a bounded list')
    layers = {layer['id']: layer for layer in plan.get('layers', [])}
    seen = set()

    def number(value, lo, hi):
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and lo <= value <= hi

    for effect in effects:
        if not isinstance(effect, dict) or not isinstance(effect.get('type'), str) or effect['type'] not in EFFECT_TYPES:
            raise ValueError('Unsupported AE scene effect')
        kind = effect['type']
        if kind in seen:
            raise ValueError('Duplicate AE scene effect')
        seen.add(kind)
        if not number(effect.get('start'), 0, 1) or not number(effect.get('end'), 0, 1) or effect['end'] <= effect['start']:
            raise ValueError('AE effect needs an increasing normalized time window')
        if not number(effect.get('intensity'), .05, 1):
            raise ValueError('AE effect intensity must be within 0.05..1')
        for key, length in (('center', 2), ('color', 3)):
            value = effect.get(key)
            if not isinstance(value, list) or len(value) != length or not all(number(v, 0, 1) for v in value):
                raise ValueError('AE effect needs normalized ' + key)
        if not number(effect.get('radius'), .02, 1):
            raise ValueError('AE effect radius must be within 0.02..1')
        if not isinstance(effect.get('reason'), str) or not effect['reason'].strip():
            raise ValueError('AE effect needs a scene-grounded reason')
        if kind == 'fireflies':
            from submitted_video_postwork import FIREFLY_WORDS
            if not FIREFLY_WORDS.search(str(effect.get('story_quote') or '')):raise ValueError('Fireflies need an explicit narrative cue')
            count=effect.get('count')
            if isinstance(count,bool) or not isinstance(count,int) or not 4<=count<=24:raise ValueError('Firefly count must be 4..24')
            if not number(effect.get('size'),.001,.004) or not number(effect.get('speed'),.005,.03) or not number(effect.get('radius'),.05,.4) or not number(effect.get('intensity'),.05,.35):raise ValueError('Fireflies must use restrained size, speed, radius and intensity')
            protected=effect.get('protected_regions')
            if not isinstance(protected,list) or len(protected)>40 or any(not isinstance(b,list) or len(b)!=4 or not all(number(v,0,1) for v in b) or b[2]<=b[0] or b[3]<=b[1] for b in protected):raise ValueError('Firefly face/text protection regions are invalid')
        if kind == 'heat_distortion':
            target = effect.get('target_layer')
            if not isinstance(target, str) or layers.get(target, {}).get('role') not in ('background', 'prop'):
                raise ValueError('Heat distortion requires a separated background or prop, never a character')
        elif kind == 'impact_shake':
            camera = plan.get('camera') or []
            if not all(isinstance(key, dict) and key.get('scale', 0) >= 1.03 for key in camera):
                raise ValueError('Impact shake requires at least 3% camera overscan')
            if effect.get('target_layer') is not None:
                raise ValueError('Overlay effects use source-canvas coordinates, not target layers')
        elif effect.get('target_layer') is not None:
            raise ValueError('Overlay effects use source-canvas coordinates, not target layers')
    if requested is not None:
        if (not isinstance(requested, list) or any(not isinstance(v, str) or v not in EFFECT_TYPES for v in requested)
                or len(set(requested)) != len(requested) or set(requested) != seen):
            raise ValueError('Requested AE effects must exactly match the reviewed plan')
    return effects


# Inserted inside the renderer's closure; key(), linear(), S, W, H are shared.
EFFECTS_JSX = r'''
function sceneFx(layer, name) {
  var effects=layer.property("ADBE Effect Parade");
  if(!effects.canAddProperty(name)) throw new Error("Required AE effect unavailable: "+name);
  return effects.addProperty(name);
}
function effectEnvelope(property,E,peak) {
  var span=E.end-E.start;
  key(property,E.start,0);key(property,E.start+span*.15,peak);
  key(property,E.start+span*.7,peak);key(property,E.end,0);linear(property);
}
function effectMask(layer,E,invert) {
  var mask=layer.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
  var shape=new Shape(),rx=E.radius*W,ry=E.radius*H,cx=E.center[0]*W,cy=E.center[1]*H,k=.55228475;
  shape.vertices=[[cx-rx,cy],[cx,cy-ry],[cx+rx,cy],[cx,cy+ry]];
  shape.inTangents=[[0,ry*k],[-rx*k,0],[0,-ry*k],[rx*k,0]];
  shape.outTangents=[[0,-ry*k],[rx*k,0],[0,ry*k],[-rx*k,0]];shape.closed=true;
  mask.property("ADBE Mask Shape").setValue(shape);
  mask.property("ADBE Mask Feather").setValue([rx*.6,ry*.6]);
  mask.inverted=Boolean(invert);
}
function effectSolid(source,E,index) {
  var layer=source.layers.addSolid(E.color,"ae_effect_"+E.type+"_"+index,W,H,1,S.duration);
  layer.blendingMode=BlendingMode.SCREEN;
  return layer;
}
function effectShape(source,name) {
  var layer=source.layers.addShape();layer.name=name;layer.blendingMode=BlendingMode.SCREEN;return layer;
}
function effectParticle(source,E,index,kind) {
  var layer=effectShape(source,"ae_effect_"+kind+"_"+index),contents=layer.property("ADBE Root Vectors Group");
  var group=contents.addProperty("ADBE Vector Group"),inner=group.property("ADBE Vectors Group");
  var shape=inner.addProperty(kind==="debris_burst"?"ADBE Vector Shape - Rect":"ADBE Vector Shape - Ellipse");
  var size=Math.max(3,W*(kind==="debris_burst"?.008:.004)*(0.5+E.intensity));
  shape.property(kind==="debris_burst"?"ADBE Vector Rect Size":"ADBE Vector Ellipse Size").setValue([size,size*(kind==="debris_burst"?.65:1)]);
  var fill=inner.addProperty("ADBE Vector Graphic - Fill");fill.property("ADBE Vector Fill Color").setValue(E.color);
  var angle=index*2.3999632297, distance=E.radius*(.25+(index%5)*.15), x=E.center[0]*W, y=E.center[1]*H;
  var transform=layer.property("ADBE Transform Group");
  key(transform.property("ADBE Position"),E.start,[x,y]);
  key(transform.property("ADBE Position"),E.end,[x+Math.cos(angle)*W*distance,y+Math.sin(angle)*H*distance]);
  key(transform.property("ADBE Rotate Z"),E.start,0);key(transform.property("ADBE Rotate Z"),E.end,kind==="debris_burst"?180:0);
  effectEnvelope(transform.property("ADBE Opacity"),E,70*E.intensity);linear(transform.property("ADBE Position"));
}
function applySceneEffects(source,layers) {
  var effects=S.plan.effects||[];
  for(var e=0;e<effects.length;e++) {
    var E=effects[e],layer,fx,opacity,span=E.end-E.start;
    if(E.type==="fireflies") {
      var made=0,protect=(E.protected_regions||[]).concat([[0,.78,1,1]]);
      for(var attempt=0;attempt<240 && made<E.count;attempt++) {
        var angle=attempt*2.3999632297,dist=E.radius*Math.sqrt(((attempt*37)%101)/101);
        var px=E.center[0]+Math.cos(angle)*dist,py=E.center[1]+Math.sin(angle)*dist;
        var dx=Math.sin(attempt*1.7)*E.speed,dy=-E.speed*(.4+(attempt%5)*.12),safe=true;
        if(Math.min(px,px+dx)<.01 || Math.max(px,px+dx)>.99 || Math.min(py,py+dy)<.01 || Math.max(py,py+dy)>.77)continue;
        for(var pr=0;pr<protect.length;pr++){var B=protect[pr],pad=E.size*4;
          if(Math.max(px,px+dx)+pad>B[0]&&Math.min(px,px+dx)-pad<B[2]&&Math.max(py,py+dy)+pad>B[1]&&Math.min(py,py+dy)-pad<B[3])safe=false;}
        if(!safe)continue;
        layer=source.layers.addShape();layer.name="ae_effect_firefly_"+made;
        var contents=layer.property("ADBE Root Vectors Group"),size=Math.max(1,Math.min(W,H)*E.size);
        for(var halo=0;halo<2;halo++) {
          var group=contents.addProperty("ADBE Vector Group"),shapes=group.property("ADBE Vectors Group");
          var ellipse=shapes.addProperty("ADBE Vector Shape - Ellipse");ellipse.property("ADBE Vector Ellipse Size").setValue([size*(halo?1:3),size*(halo?1:3)]);
          var fill=shapes.addProperty("ADBE Vector Graphic - Fill");fill.property("ADBE Vector Fill Color").setValue(E.color);fill.property("ADBE Vector Fill Opacity").setValue(halo?100:15);
        }
        layer.blendingMode=BlendingMode.SCREEN;
        var tr=layer.property("ADBE Transform Group");key(tr.property("ADBE Position"),E.start,[px*W,py*H]);key(tr.property("ADBE Position"),E.end,[(px+dx)*W,(py+dy)*H]);linear(tr.property("ADBE Position"));
        var op=tr.property("ADBE Opacity"),steps=Math.max(4,Math.ceil((E.end-E.start)*S.duration*3));
        for(var pulse=0;pulse<=steps;pulse++){var at=E.start+(E.end-E.start)*pulse/steps;key(op,at,(pulse===0||pulse===steps)?0:E.intensity*(35+65*(.5+.5*Math.sin(pulse*1.6+made*2.1))));}linear(op);made++;
      }
      if(made!==E.count)throw new Error("Firefly region cannot avoid protected faces/text; repair direction");
      continue;
    }
    if(E.type==="heat_distortion") {
      layer=layers[E.target_layer];
      if(!layer) throw new Error("Missing reviewed distortion target");
      // A masked duplicate preserves untouched source pixels outside the heat region.
      layer=layer.duplicate();layer.name="ae_effect_heat_distortion_"+e;
      effectMask(layer,E,false);
      effectEnvelope(layer.property("ADBE Transform Group").property("ADBE Opacity"),E,100);
      fx=sceneFx(layer,"ADBE Turbulent Displace");
      effectEnvelope(fx.property("ADBE Turbulent Displace-0002"),E,4*E.intensity);
      fx.property("ADBE Turbulent Displace-0003").setValue(35);
      key(fx.property("ADBE Turbulent Displace-0006"),E.start,0);key(fx.property("ADBE Turbulent Displace-0006"),E.end,90);
      continue;
    }
    if(E.type==="impact_shake") {
      // This is intentionally small and requires the director to leave camera overscan.
      var amplitude=Math.max(2,Math.round(W*(.002+.008*E.intensity)));
      for(var layerId in layers) if(layers.hasOwnProperty(layerId)) {
        layer=layers[layerId];var position=layer.property("ADBE Transform Group").property("ADBE Position");
        var times=[E.start,E.start+(E.end-E.start)*.22,E.start+(E.end-E.start)*.48,E.start+(E.end-E.start)*.74,E.end];
        for(var q=0;q<times.length;q++) { var atTime=times[q]*S.duration,base=position.valueAtTime(atTime,false),sign=q%2?1:-1;
          position.setValueAtTime(atTime,[base[0]+sign*amplitude,base[1]-sign*amplitude*.55]); }
        linear(position);
      }
      continue;
    }
    if(E.type==="shock_ring") {
      layer=effectShape(source,"ae_effect_shock_ring_"+e);var ringContents=layer.property("ADBE Root Vectors Group");
      var ring=ringContents.addProperty("ADBE Vector Shape - Ellipse"),ringIndex=ring.propertyIndex;
      var ringStroke=ringContents.addProperty("ADBE Vector Graphic - Stroke");
      // Adding to an indexed AE group invalidates earlier Property references.
      ring=ringContents.property(ringIndex);
      ringStroke.property("ADBE Vector Stroke Color").setValue(E.color);ringStroke.property("ADBE Vector Stroke Width").setValue(Math.max(2,W*.003*E.intensity));
      layer.property("ADBE Transform Group").property("ADBE Position").setValue([E.center[0]*W,E.center[1]*H]);
      key(ring.property("ADBE Vector Ellipse Size"),E.start,[W*E.radius*.12,H*E.radius*.12]);
      key(ring.property("ADBE Vector Ellipse Size"),E.end,[W*E.radius*2,H*E.radius*2]);
      effectEnvelope(layer.property("ADBE Transform Group").property("ADBE Opacity"),E,80*E.intensity);continue;
    }
    if(E.type==="energy_trail") {
      layer=effectShape(source,"ae_effect_energy_trail_"+e);var trailContents=layer.property("ADBE Root Vectors Group");
      // Vertices below already use composition coordinates, so do not add the default shape-layer center.
      layer.property("ADBE Transform Group").property("ADBE Position").setValue([0,0]);
      var trailPath=trailContents.addProperty("ADBE Vector Shape - Group"),trailShape=new Shape(),cx=E.center[0]*W,cy=E.center[1]*H,r=E.radius*Math.min(W,H);
      trailShape.vertices=[[cx-r*.8,cy+r*.35],[cx-r*.16,cy-r*.42],[cx+r*.18,cy+r*.1],[cx+r*.9,cy-r*.32]];
      trailShape.inTangents=[[0,0],[0,0],[0,0],[0,0]];trailShape.outTangents=[[0,0],[0,0],[0,0],[0,0]];trailShape.closed=false;
      trailPath.property("ADBE Vector Shape").setValue(trailShape);var trailStroke=trailContents.addProperty("ADBE Vector Graphic - Stroke");
      trailStroke.property("ADBE Vector Stroke Color").setValue(E.color);trailStroke.property("ADBE Vector Stroke Width").setValue(Math.max(3,W*.006*E.intensity));
      var trim=trailContents.addProperty("ADBE Vector Filter - Trim");key(trim.property("ADBE Vector Trim End"),E.start,0);key(trim.property("ADBE Vector Trim End"),E.end,100);
      effectEnvelope(layer.property("ADBE Transform Group").property("ADBE Opacity"),E,85*E.intensity);continue;
    }
    if(E.type==="particle_burst" || E.type==="debris_burst") {
      var burstCount=Math.round((E.type==="debris_burst"?7:12)+E.intensity*(E.type==="debris_burst"?8:16));
      for(var b=0;b<burstCount;b++) effectParticle(source,E,b+(e*31),E.type);
      continue;
    }
    if(E.type==="warm_dust_motes" || E.type==="speedline_burst") {
      var count=E.type==="warm_dust_motes"?Math.round(4+8*E.intensity):12;
      for(var p=0;p<count;p++) {
        layer=source.layers.addShape();layer.name="ae_effect_"+E.type+"_"+e+"_"+p;
        var contents=layer.property("ADBE Root Vectors Group"),angle=(p/count)*Math.PI*2;
        if(E.type==="warm_dust_motes") {
          var ellipse=contents.addProperty("ADBE Vector Shape - Ellipse");
          ellipse.property("ADBE Vector Ellipse Size").setValue([2+W*.001,2+W*.001]);
          var fill=contents.addProperty("ADBE Vector Graphic - Fill");fill.property("ADBE Vector Fill Color").setValue(E.color);
          var x=(E.center[0]+Math.sin(p*2.399)*E.radius*.7)*W;
          var y=(E.center[1]+Math.cos(p*2.399)*E.radius*.7)*H;
          key(layer.property("ADBE Transform Group").property("ADBE Position"),E.start,[x,y]);
          key(layer.property("ADBE Transform Group").property("ADBE Position"),E.end,[x+W*.015,y-H*.04]);
        } else {
          var path=contents.addProperty("ADBE Vector Shape - Group"),shape=new Shape();
          shape.vertices=[[Math.cos(angle)*W*E.radius*.35,Math.sin(angle)*H*E.radius*.35],
                          [Math.cos(angle)*W*E.radius,Math.sin(angle)*H*E.radius]];
          shape.inTangents=[[0,0],[0,0]];shape.outTangents=[[0,0],[0,0]];shape.closed=false;
          path.property("ADBE Vector Shape").setValue(shape);
          var stroke=contents.addProperty("ADBE Vector Graphic - Stroke");
          stroke.property("ADBE Vector Stroke Color").setValue(E.color);stroke.property("ADBE Vector Stroke Width").setValue(Math.max(1,W*.001));
          layer.property("ADBE Transform Group").property("ADBE Position").setValue([E.center[0]*W,E.center[1]*H]);
          key(layer.property("ADBE Transform Group").property("ADBE Scale"),E.start,[85,85]);
          key(layer.property("ADBE Transform Group").property("ADBE Scale"),E.end,[110,110]);
        }
        layer.blendingMode=BlendingMode.SCREEN;
        effectEnvelope(layer.property("ADBE Transform Group").property("ADBE Opacity"),E,35*E.intensity);
      }
      continue;
    }
    layer=effectSolid(source,E,e);
    opacity=layer.property("ADBE Transform Group").property("ADBE Opacity");
    if(E.type==="atmospheric_haze") {
      fx=sceneFx(layer,"ADBE Fractal Noise");
      fx.property("ADBE Fractal Noise-0004").setValue(120);fx.property("ADBE Fractal Noise-0005").setValue(-45);
      key(fx.property("ADBE Fractal Noise-0023"),E.start,0);key(fx.property("ADBE Fractal Noise-0023"),E.end,180);
      effectMask(layer,E,false);effectEnvelope(opacity,E,15*E.intensity);
      key(layer.property("ADBE Transform Group").property("ADBE Position"),E.start,[W*.49,H*.5]);
      key(layer.property("ADBE Transform Group").property("ADBE Position"),E.end,[W*.51,H*.49]);
    } else if(E.type==="subtle_vignette") {
      // Black overlay with a feathered hole, rather than a color wash.
      layer.remove();layer=source.layers.addSolid([0,0,0],"ae_effect_subtle_vignette_"+e,W,H,1,S.duration);
      effectMask(layer,E,true);
      effectEnvelope(layer.property("ADBE Transform Group").property("ADBE Opacity"),E,25*E.intensity);
    } else {
      effectMask(layer,E,false);
      effectEnvelope(opacity,E,(E.type==="impact_flash"?25:15)*E.intensity);
      if(E.type==="light_sweep") {
        key(layer.property("ADBE Transform Group").property("ADBE Position"),E.start,[W*.35,H*.5]);
        key(layer.property("ADBE Transform Group").property("ADBE Position"),E.end,[W*.65,H*.5]);
      }
    }
  }
}
'''
