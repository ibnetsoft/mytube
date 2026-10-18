"""Constrained, editable AE animation for reviewed PSD scene packages.

All authored times are normalized; final narration determines real seconds.
The v1 rig uses CC Bend It for separated hair/cloth, not automatic Puppet meshes.
"""
from __future__ import annotations

import copy
from ae_scene_effects import validate_effects, EFFECTS_JSX
import hashlib
import json
import math
import re
from decimal import Decimal
from pathlib import Path

CONTRACT = 'ae_scene/v1'
ROLES = {'background', 'character', 'hair', 'cloth', 'foreground', 'prop'}


def canonical_plan_sha256(plan: dict) -> str:
    def encoded(value):
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError('Canonical JSON cannot contain nonfinite numbers')
            if value == 0:
                return '0'
            # Match JSON.stringify's number spelling, including integer floats
            # and the decimal/scientific boundary used by JavaScript.
            if 1e-6 <= abs(value) < 1e21:
                decimal = format(Decimal(repr(value)), 'f')
                return decimal.rstrip('0').rstrip('.') if '.' in decimal else decimal
            mantissa, exponent = repr(value).lower().split('e')
            mantissa = mantissa[:-2] if mantissa.endswith('.0') else mantissa
            power = int(exponent)
            return mantissa + 'e' + ('+' if power >= 0 else '') + str(power)
        if isinstance(value, dict):
            return '{' + ','.join(json.dumps(key, ensure_ascii=False) + ':' + encoded(value[key]) for key in sorted(value)) + '}'
        if isinstance(value, list):
            return '[' + ','.join(encoded(item) for item in value) + ']'
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(encoded(plan).encode()).hexdigest()


def _number(value, lo, hi, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f'{name} must be finite within {lo}..{hi}')
    return value


def _point(value, name):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f'{name} needs two normalized coordinates')
    return [_number(v, 0, 1, name) for v in value]


def _keys(keys, name, ranges):
    if not isinstance(keys, list) or not 2 <= len(keys) <= 64:
        raise ValueError(f'{name} needs 2..64 keyframes')
    previous = -1
    for row in keys:
        if not isinstance(row, dict):
            raise ValueError(f'{name} keyframe must be an object')
        t = _number(row.get('t'), 0, 1, name + '.t')
        if t <= previous:
            raise ValueError(f'{name} keyframes must have strictly increasing times')
        previous = t
        for field, (lo, hi) in ranges.items():
            _number(row.get(field), lo, hi, name + '.' + field)
    if keys[0]['t'] != 0 or keys[-1]['t'] != 1:
        raise ValueError(f'{name} must cover the complete normalized timeline')


def camera_coverage(plan: dict) -> None:
    """Reject camera poses exposing outside the source, including interpolations.

    The JSX uses linear interpolation, so sampling each segment is predictable.
    A one-pixel tolerance covers floating point error at a static exact-fit crop.
    """
    width, height = plan['width'], plan['height']
    output = plan.get('output', {'width': 1920, 'height': 1080})
    base = max(output['width'] / width, output['height'] / height)
    for left, right in zip(plan['camera'], plan['camera'][1:]):
        for step in range(65):
            f = step / 64
            pose = {k: left[k] + (right[k] - left[k]) * f for k in ('x', 'y', 'scale', 'rotation')}
            theta = math.radians(pose['rotation'])
            # Axis-aligned extents of the inverse-rotated output rectangle.
            half_x = (abs(math.cos(theta)) * output['width'] + abs(math.sin(theta)) * output['height']) / (2 * base * pose['scale'])
            half_y = (abs(math.sin(theta)) * output['width'] + abs(math.cos(theta)) * output['height']) / (2 * base * pose['scale'])
            cx, cy = pose['x'] * width, pose['y'] * height
            if min(cx - half_x, cy - half_y, width - cx - half_x, height - cy - half_y) < -.01:
                raise ValueError('Camera path exposes pixels outside the prepared source canvas; increase scale or repair framing')


def validate_plan(plan: dict, width=None, height=None) -> dict:
    if not isinstance(plan, dict) or plan.get('contract') != CONTRACT:
        raise ValueError('Unsupported AE scene animation contract')
    result = copy.deepcopy(plan)
    if result.get('schema_version') != CONTRACT or result.get('timing') != 'normalized':
        raise ValueError('AE scene animation needs normalized timing')
    for key, expected in (('width', width), ('height', height)):
        value = _number(result.get(key), 16, 30000, key)
        if int(value) != value or (expected is not None and value != expected):
            raise ValueError('Plan canvas does not match the prepared PSD')
    output = result.setdefault('output', {'width': 1920, 'height': 1080})
    for key in ('width', 'height'):
        value = _number(output.get(key), 16, 3840, 'output.' + key)
        if int(value) != value or value % 2:
            raise ValueError('Output dimensions must be even integers')
    _keys(result.get('camera'), 'camera', {'x': (0, 1), 'y': (0, 1), 'scale': (1, 2), 'rotation': (-3, 3)})
    camera_coverage(result)
    layers = result.get('layers')
    if not isinstance(layers, list) or not 2 <= len(layers) <= 80:
        raise ValueError('A separated PSD needs 2..80 semantic layers')
    ids, orders = set(), set()
    for layer in layers:
        identity = layer.get('id')
        if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', identity) or identity in ids:
            raise ValueError('Layer IDs must be unique safe identifiers')
        ids.add(identity)
        if layer.get('role') not in ROLES:
            raise ValueError('Unrecognized semantic layer role')
        z_index = layer.get('z_index')
        if isinstance(z_index, bool) or not isinstance(z_index, int) or z_index in orders:
            raise ValueError('Layer stacking order must be unique integers')
        orders.add(z_index)
        _number(layer.get('parallax', 0), 0, 1, 'parallax')
        _point(layer.get('anchor', [.5, .5]), 'anchor')
        if layer.get('puppet') is not None:
            raise ValueError('Automatic Puppet meshes are not supported; author a reviewed bend rig')
        if layer.get('motion') is not None:
            _keys(layer['motion'], 'motion', {'x': (-.05, .05), 'y': (-.05, .05),
                   'scale': (.9, 1.1), 'rotation': (-8, 8), 'opacity': (0, 100)})
        if layer.get('bend') is not None:
            if layer['role'] not in ('hair', 'cloth'):
                raise ValueError('Bend deformation is restricted to separated hair or cloth')
            bend = layer['bend']
            start, end = _point(bend.get('start'), 'bend.start'), _point(bend.get('end'), 'bend.end')
            if math.hypot(start[0] - end[0], start[1] - end[1]) < .01:
                raise ValueError('Bend endpoints must be visibly separated')
            _keys(bend.get('keys'), 'bend', {'angle': (-8, 8)})
    backgrounds = [layer for layer in layers if layer['role'] == 'background']
    if len(backgrounds) != 1 or backgrounds[0]['z_index'] != min(orders):
        raise ValueError('Exactly one bottom background layer is required')
    background = backgrounds[0]
    if background.get('parallax', 0) or background.get('bend') or background.get('motion'):
        raise ValueError('Background plate must remain intact; animate the scene camera')
    lights = result.get('lights', [])
    if not isinstance(lights, list) or len(lights) > 8:
        raise ValueError('At most eight restrained light overlays are supported')
    for light in lights:
        if not isinstance(light.get('color'), list) or len(light['color']) != 3:
            raise ValueError('Light color needs RGB channels')
        for channel in light['color']:
            _number(channel, 0, 1, 'light.color')
        _point(light.get('center'), 'light.center')
        _number(light.get('radius'), .02, 1, 'light.radius')
        _keys(light.get('keys'), 'light', {'opacity': (0, 15)})
    transition = result.get('transition') or {}
    if transition.get('in') not in ('cut', 'fade') or transition.get('out') not in ('cut', 'fade'):
        raise ValueError('Only explicitly planned cuts and fades are supported')
    fraction = _number(transition.get('fraction'), 0, .15, 'transition.fraction')
    if 'fade' in (transition['in'], transition['out']) and fraction <= 0:
        raise ValueError('Fade duration must be positive')
    continuity = result.get('continuity') or {}
    for name in ('entry', 'exit', 'screen_direction', 'light_direction'):
        if not isinstance(continuity.get(name), str) or not continuity[name].strip():
            raise ValueError('Continuity requires explicit entry, exit, direction and lighting evidence')
    validate_effects(result)
    return result


def _interpolate(keys, t, fields):
    for left, right in zip(keys, keys[1:]):
        if left['t'] <= t <= right['t']:
            f = (t - left['t']) / (right['t'] - left['t'])
            return {k: left[k] + (right[k] - left[k]) * f for k in fields}
    return {k: keys[-1][k] for k in fields}


def resolved_layers(plan: dict) -> list[dict]:
    """Bake layer motion and camera-relative parallax into one coherent timeline."""
    output = []
    for original in sorted(plan['layers'], key=lambda layer: layer['z_index']):
        layer = copy.deepcopy(original)
        motion = layer.get('motion') or [dict(t=t, x=0, y=0, scale=1, rotation=0, opacity=100) for t in (0, 1)]
        times = sorted({key['t'] for key in motion + plan['camera']})
        initial = plan['camera'][0]
        keys = []
        for t in times:
            item = _interpolate(motion, t, ('x', 'y', 'scale', 'rotation', 'opacity'))
            camera = _interpolate(plan['camera'], t, ('x', 'y'))
            parallax = layer.get('parallax', 0)
            # Foreground follows opposite camera motion slightly more than background.
            item.update(t=t, x=item['x'] - (camera['x'] - initial['x']) * parallax * .15,
                        y=item['y'] - (camera['y'] - initial['y']) * parallax * .15)
            keys.append(item)
        layer['motion'] = keys
        output.append(layer)
    return output


def write_scene_jsx(plan: dict, layer_paths: dict[str, Path], project: Path, native: Path,
                    jsx: Path, duration: float, fps: int = 24) -> None:
    plan = validate_plan(plan)
    _number(duration, .1, 3600, 'duration')
    _number(fps, 1, 120, 'fps')
    for effect in plan.get('effects', []):
        if (effect['end'] - effect['start']) * duration * fps < 3:
            raise ValueError('AE effect window needs at least three final narration frames; repair its timing')
    data = {'plan': plan, 'layers': resolved_layers(plan),
            'files': {key: str(value.resolve()) for key, value in layer_paths.items()},
            'duration': duration, 'fps': fps, 'project': str(project.resolve()),
            'native': str(native.resolve()), 'status': str(jsx.with_suffix('.status.txt').resolve())}
    encoded = json.dumps(data, ensure_ascii=True, allow_nan=False)
    jsx.write_text('var S = ' + encoded + ';\n' + SCENE_JSX.replace('/* SCENE_EFFECTS */', EFFECTS_JSX), encoding='utf-8')


SCENE_JSX = r'''
(function () {
  function status(text) { var f=new File(S.status); f.encoding="UTF-8"; f.open("w"); f.write(text); f.close(); }
  function linear(property) {
    for (var k=1;k<=property.numKeys;k++) {
      property.setInterpolationTypeAtKey(k,KeyframeInterpolationType.LINEAR,KeyframeInterpolationType.LINEAR);
      if (property.isSpatial) {
        var zero=property.propertyValueType===PropertyValueType.ThreeD_SPATIAL?[0,0,0]:[0,0];
        property.setSpatialTangentsAtKey(k,zero,zero);
      }
    }
  }
  function key(property,time,value) { property.setValueAtTime(time*S.duration,value); }
  /* SCENE_EFFECTS */
  try {
    app.beginSuppressDialogs();
    app.newProject();
    var P=S.plan,W=P.width,H=P.height,O=P.output;
    var source=app.project.items.addComp("ae_scene_source",W,H,1,S.duration,S.fps);
    var comp=app.project.items.addComp("ae_scene",O.width,O.height,1,S.duration,S.fps);
    var semanticLayers={};
    for(var i=0;i<S.layers.length;i++) {
      var L=S.layers[i], f=new File(S.files[L.id]);
      if(!f.exists) throw new Error("Missing reviewed layer "+L.id);
      var footage=app.project.importFile(new ImportOptions(f));
      if(footage.width!==W || footage.height!==H) throw new Error("Layer canvas mismatch "+L.id);
      var layer=source.layers.add(footage); layer.name=L.role+"_"+L.id; layer.outPoint=S.duration;
      semanticLayers[L.id]=layer;
      var anchor=L.anchor||[.5,.5], transform=layer.property("ADBE Transform Group");
      transform.property("ADBE Anchor Point").setValue([anchor[0]*W,anchor[1]*H]);
      for(var j=0;j<L.motion.length;j++) {
        var M=L.motion[j];
        key(transform.property("ADBE Position"),M.t,[(anchor[0]+M.x)*W,(anchor[1]+M.y)*H]);
        key(transform.property("ADBE Scale"),M.t,[M.scale*100,M.scale*100]);
        key(transform.property("ADBE Rotate Z"),M.t,M.rotation);
        key(transform.property("ADBE Opacity"),M.t,M.opacity);
      }
      linear(transform.property("ADBE Position")); linear(transform.property("ADBE Scale"));
      linear(transform.property("ADBE Rotate Z")); linear(transform.property("ADBE Opacity"));
      if(L.bend) {
        var effects=layer.property("ADBE Effect Parade");
        if(!effects.canAddProperty("CC Bend It")) throw new Error("CC Bend It is required for "+L.id);
        var bend=effects.addProperty("CC Bend It");
        // Cycore HD manual pp18-19: Bend, Start, End, Render Prestart, Distort.
        // Inspect the installed effect instead of silently writing mismatched slots.
        if(bend.numProperties<5 || typeof bend.property(1).value!=="number" ||
           bend.property(2).value.length!==2 || bend.property(3).value.length!==2 ||
           typeof bend.property(4).value!=="number" || typeof bend.property(5).value!=="number")
          throw new Error("Unsupported installed CC Bend It parameter layout");
        bend.property(2).setValue([L.bend.start[0]*W,L.bend.start[1]*H]);
        bend.property(3).setValue([L.bend.end[0]*W,L.bend.end[1]*H]);
        bend.property(4).setValue(2); // Prestart Static: retain the fixed root
        bend.property(5).setValue(2); // Distort Extended: retain pixels beyond the end
        for(var b=0;b<L.bend.keys.length;b++) key(bend.property(1),L.bend.keys[b].t,L.bend.keys[b].angle);
        linear(bend.property(1));
      }
    }
    applySceneEffects(source,semanticLayers);
    for(var n=0;n<(P.lights||[]).length;n++) {
      var Q=P.lights[n], light=source.layers.addSolid(Q.color,"directed_light_"+n,W,H,1,S.duration);
      light.blendingMode=BlendingMode.SCREEN;
      var mask=light.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
      var shape=new Shape(),rx=Q.radius*W,ry=Q.radius*H,cx=Q.center[0]*W,cy=Q.center[1]*H,k=.55228475;
      shape.vertices=[[cx-rx,cy],[cx,cy-ry],[cx+rx,cy],[cx,cy+ry]];
      shape.inTangents=[[0,ry*k],[-rx*k,0],[0,-ry*k],[rx*k,0]];
      shape.outTangents=[[0,-ry*k],[rx*k,0],[0,ry*k],[-rx*k,0]];shape.closed=true;
      mask.property("ADBE Mask Shape").setValue(shape);
      mask.property("ADBE Mask Feather").setValue([rx*.5,ry*.5]);
      for(var q=0;q<Q.keys.length;q++) key(light.property("ADBE Transform Group").property("ADBE Opacity"),Q.keys[q].t,Q.keys[q].opacity);
      linear(light.property("ADBE Transform Group").property("ADBE Opacity"));
    }
    comp.layers.addSolid([0,0,0],"fade_backing",O.width,O.height,1,S.duration);
    var view=comp.layers.add(source),V=view.property("ADBE Transform Group"),base=Math.max(O.width/W,O.height/H);
    V.property("ADBE Position").setValue([O.width/2,O.height/2]);
    for(var c=0;c<P.camera.length;c++) {
      var C=P.camera[c];
      key(V.property("ADBE Anchor Point"),C.t,[C.x*W,C.y*H]);
      key(V.property("ADBE Scale"),C.t,[base*C.scale*100,base*C.scale*100]);
      key(V.property("ADBE Rotate Z"),C.t,C.rotation);
    }
    linear(V.property("ADBE Anchor Point"));linear(V.property("ADBE Scale"));linear(V.property("ADBE Rotate Z"));
    var opacity=V.property("ADBE Opacity"),T=P.transition;
    key(opacity,0,T.in==="fade"?0:100);
    if(T.in==="fade") key(opacity,T.fraction,100);
    if(T.out==="fade") key(opacity,1-T.fraction,100);
    key(opacity,1,T.out==="fade"?0:100);linear(opacity);
    var item=app.project.renderQueue.items.add(comp);item.outputModule(1).file=new File(S.native);
    app.project.save(new File(S.project));
    status("success|"+S.project);app.endSuppressDialogs(false);
  } catch(error) { status("error|"+String(error)+" line="+error.line);try{app.endSuppressDialogs(false);}catch(ignore){} }
})();
'''
