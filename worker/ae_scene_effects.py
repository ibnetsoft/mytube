"""Reviewed, bounded finishing effects for the web PSD scene renderer.

Effect times use the same normalized narration timeline as camera and layer keys.
No effect may replace source artwork or silently skip missing AE capabilities.
"""
import math

EFFECT_TYPES = frozenset({
    'atmospheric_haze', 'warm_dust_motes', 'focus_glow', 'light_sweep',
    'impact_flash', 'heat_distortion', 'subtle_vignette', 'speedline_burst',
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
        if kind == 'heat_distortion':
            target = effect.get('target_layer')
            if not isinstance(target, str) or layers.get(target, {}).get('role') not in ('background', 'prop'):
                raise ValueError('Heat distortion requires a separated background or prop, never a character')
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
function applySceneEffects(source,layers) {
  var effects=S.plan.effects||[];
  for(var e=0;e<effects.length;e++) {
    var E=effects[e],layer,fx,opacity,span=E.end-E.start;
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
      key(fx.property("ADBE Fractal Noise-0007"),E.start,0);key(fx.property("ADBE Fractal Noise-0007"),E.end,180);
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
