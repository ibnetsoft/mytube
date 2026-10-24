"""Explicit AE colour, small-radius blur and vignette compatibility via public commands.

Upstream binaries stay unmodified. Fractional Gaussian replacements are restricted
to static, opaque, unmasked stills; other affected cases must be reviewed.
"""
import json
import math
from pathlib import Path

VERSION = 'ae-rec709-blur-masks-linear-position-v4'
VIGNETTE_MARKER = '[AIR vignette-domain-v1]'
LIGHT_MASK_MARKER = '[AIR light-mask-domain-v1]'


def linear_position_replacements(project, declared_linear=False):
    """Repair implicit native auto paths only when the caller declares linear intent.

    The inspected AE references have spatial-auto=false and zero handles; the
    pinned native API instead defaults to auto=true and infers neighbour handles.
    Never infer user intent from zero stored handles alone: explicit auto curves
    also store zeros. Generated scene emitters/verified legacy importers opt in.
    Two-key paths remain unchanged, including the scene29 regression control.
    """
    if not declared_linear:
        return []
    fixes = []
    for item in project['items'].values():
        if item['kind'].get('type') != 'Comp':
            continue
        for index, layer in enumerate(item['kind'].get('layers', []), 1):
            transform = next((g for g in layer['props']['children'] if g['match'] == 'transform'), {})
            position = next((p for p in transform.get('children', []) if p['match'] == 'position'), {})
            keys = position.get('keys', [])
            if len(keys) < 3 or not position.get('spatial') or not any(k.get('spatial_auto') for k in keys):
                continue
            if (position.get('expression') or any(
                    k.get('in_interp') != 'Linear' or k.get('out_interp') != 'Linear'
                    or k.get('roving') or k.get('auto_bezier')
                    or any(v != 0 for field in ('spatial_in', 'spatial_out') for v in k.get(field, []))
                    for k in keys)):
                raise ValueError('Declared linear position has authored curves/expressions; requires review')
            fixes.append(dict(comp_id=item['id'], layer_index=index, layer=layer['name'],
                              property='ADBE Position', key_count=len(keys),
                              reason='AE linear spatial defaults; preserve key times/values and temporal interpolation'))
    return fixes


def smooth_mask_replacements(project):
    """Plan a bounded domain/unit conversion for generated static smooth masks.

    AE feather units were independently calibrated at 100, 200 and 400 pixels.
    Padding keeps coverage outside the visible solid alive until after feathering.
    Anchor and path move together, preserving world-space geometry and opacity.
    """
    result = []
    for item in project['items'].values():
        comp = item['kind']
        if comp.get('type') != 'Comp':
            continue
        for index, layer in enumerate(comp.get('layers', []), 1):
            vignette = layer['name'].startswith('ae_effect_subtle_vignette_')
            light = layer['name'].startswith('ae_effect_light_sweep_')
            if not (vignette or light):
                continue
            marker = VIGNETTE_MARKER if vignette else LIGHT_MASK_MARKER
            if marker in layer.get('comment', ''):
                continue
            groups = {g['match']: g for g in layer['props']['children']}
            masks = groups.get('masks', {}).get('children', [])
            solid = project['items'].get(str((layer.get('source') or {}).get('item')), {}).get('kind', {})
            if (solid.get('type') != 'Solid' or (vignette and solid.get('color') != [0, 0, 0])
                    or len(masks) != 1 or layer.get('parent') or layer.get('track_matte')
                    or layer.get('switches', {}).get('three_d')
                    or groups.get('effects', {}).get('children')):
                raise ValueError('Generated smooth-mask configuration requires explicit review')
            mask = masks[0]
            kind = mask['kind']
            params = {p['match']: p for p in mask['children']}
            shape = _static(params['path'])
            feather = _static(params['feather'])
            transform = {p['match']: p for p in groups['transform']['children']}
            anchor = _static(transform['anchor'])
            if (kind.get('mode') != 'Add' or kind.get('inverted') is not vignette
                    or kind.get('feather_falloff') != 'Smooth' or not mask.get('enabled', True)
                    or groups['masks'].get('enabled') is False
                    or _static(params['expansion']) != 0 or _static(params['opacity']) != 100
                    or not shape.get('closed') or shape.get('feather_points')
                    or any(not math.isfinite(f) or f < 0 for f in feather)
                    or [solid['width'], solid['height']] != [comp['width'], comp['height']]
                    or anchor[:2] != [comp['width']/2, comp['height']/2]
                    or (vignette and _static(transform['position'])[:2] != anchor[:2])
                    or _static(transform['scale']) != [100, 100, 100]
                    or _static(transform['rotation']) != 0):
                raise ValueError('Generated smooth-mask transform requires explicit review')
            native = [f * .75 for f in feather]
            padding = [math.ceil(f * 1.5) + 3 for f in native]
            width, height = [solid[k] + 2*p for k, p in zip(('width', 'height'), padding)]
            if max(width, height) > 16384 or width * height > 64_000_000:
                raise ValueError('Vignette padded domain exceeds supported allocation')
            result.append(dict(comp_id=item['id'], layer_id=layer['id'], layer_index=index,
                               layer=layer['name'], authored_feather=feather,
                               native_feather=native, padding=padding, width=width, height=height,
                               comment=layer.get('comment', '') + marker))
    return result


def vignette_replacements(project):
    return [r for r in smooth_mask_replacements(project)
            if r['layer'].startswith('ae_effect_subtle_vignette_')]


def calibrated_gaussian_kernel(amount, dimensions=0):
    """Measured AE 2026 static 1.2 response, not a general radius interpolation.

    Independent 64px impulse, Rec709 16bpc, response decoded with gamma 2.4.
    Symmetry averaging removes output dither; normalization preserves flat fields.
    Colored step/checker controls validate the response independently of scene 29.
    """
    if not math.isclose(amount, 1.2, rel_tol=0, abs_tol=1e-9) or dimensions != 0:
        raise ValueError('Uncalibrated Gaussian radius/dimensions')
    corner, edge, center = .0001510467921407114, .011715693634252854, .9525330382944257
    return [corner, edge, corner, edge, center, edge, corner, edge, corner]
AE_COLOR = {'workingSpace': 'rec709', 'outputSpace': 'rec709', 'bitDepth': 16,
            'linearize': False, 'blendLinear': False, 'colorEngine': 'adobe'}
# Three integer-box Gaussian passes have no nonzero radius below this amount.
SMALL_BLUR_LIMIT = 2 / math.sqrt(3)


def gaussian_kernel(amount, dimensions=0):
    if not math.isfinite(amount) or not 0 <= amount < SMALL_BLUR_LIMIT:
        raise ValueError('Fractional Gaussian amount outside the supported range')
    if dimensions not in (0, 1, 2):
        raise ValueError('Unsupported Gaussian dimensions')
    sigma = amount / 2
    side = math.exp(-.5 / sigma / sigma) if sigma > 0 else 0.
    weights = [side / (1 + 2 * side), 1 / (1 + 2 * side), side / (1 + 2 * side)]
    identity = [0., 1., 0.]
    x = identity if dimensions == 2 else weights
    y = identity if dimensions == 1 else weights
    return [a * b for a in y for b in x]


def _static(node):
    if node.get('keys') or node.get('expression'):
        raise ValueError('Animated compatibility property requires explicit review')
    return node['value']['v']


def _opaque_still(footage):
    from PIL import Image
    if footage.get('type') != 'Footage' or footage.get('kind') != 'Still':
        return False
    path = Path(footage['path'])
    if path.suffix.lower() == '.psd':
        from psd_tools import PSDImage
        psd = PSDImage.open(path)
        index = (footage.get('layer') or {}).get('index')
        if not isinstance(index, int) or index < 0 or index >= len(psd):
            return False
        layer = psd[index]
        if layer.bbox != (0, 0, psd.width, psd.height):
            return False
        picture = layer.composite()
        return picture is not None and picture.convert('RGBA').getchannel('A').getextrema() == (255, 255)
    with Image.open(path) as picture:
        return picture.convert('RGBA').getchannel('A').getextrema() == (255, 255)


def fractional_replacements(project):
    items = project['items']
    result = []
    for item in items.values():
        comp = item['kind']
        if comp.get('type') != 'Comp':
            continue
        for index, layer in enumerate(comp.get('layers', []), 1):
            groups = {g['match']: g for g in layer['props']['children']}
            if groups.get('effects', {}).get('enabled') is False:
                continue
            effects = groups.get('effects', {}).get('children', [])
            preceding = []
            for effect_index, effect in enumerate(effects, 1):
                if effect.get('enabled') is False:
                    continue
                if effect['match'] != 'ec.blur.gaussian':
                    preceding.append(effect)
                    continue
                params = {p['match']: p for p in effect['children']}
                radius = params['blurriness']
                if radius.get('keys') and not radius.get('expression'):
                    values = [radius['value']['v']]
                    for key in radius['keys']:
                        value = key['value']
                        values.append(value['v'] if isinstance(value, dict) else value)
                    if all(isinstance(v, (int, float)) and math.isfinite(v) and v >= SMALL_BLUR_LIMIT
                           and not math.isclose(v, 1.2, rel_tol=0, abs_tol=1e-9) for v in values):
                        preceding.append(effect)
                        continue
                amount = _static(params['blurriness'])
                if not math.isfinite(amount) or amount < 0:
                    raise ValueError('Invalid Gaussian amount')
                calibrated = math.isclose(amount, 1.2, rel_tol=0, abs_tol=1e-9)
                if amount == 0 or (amount >= SMALL_BLUR_LIMIT and not calibrated):
                    preceding.append(effect)
                    continue
                source = layer.get('source') or {}
                footage = items.get(str(source.get('item')), {}).get('kind', {})
                if preceding or groups.get('masks', {}).get('children') or not _opaque_still(footage):
                    raise ValueError('Fractional Gaussian needs an opaque unmasked still before other effects')
                dimensions = _static(params['dimensions'])
                kernel = calibrated_gaussian_kernel(amount, dimensions) if calibrated else gaussian_kernel(amount, dimensions)
                result.append({'comp_id': item['id'], 'layer_index': index,
                               'layer': layer['name'], 'effect_index': effect_index,
                               'amount': amount, 'dimensions': dimensions, 'kernel': kernel,
                               'working_gamma': 2.4 if calibrated else 1.,
                               'method': 'measured-ae-1.2-v1' if calibrated else 'fractional-discrete-gaussian',
                               'boundary': 'opaque-clamped-neighbourhood'})
                preceding.append(effect)
    return result


def prepare_project(cli, project, directory, execute, *, linear_positions=False):
    project, directory = Path(project), Path(directory)
    execute(cli, ['exec', 'file.projectSettings', '--params', json.dumps(AE_COLOR),
                  '--project', str(project), '--save', '--json'], directory, 'color-settings')
    positions = linear_position_replacements(json.loads(project.read_text(encoding='utf-8')), linear_positions)
    if positions:
        code = 'var fixes=' + json.dumps(positions, allow_nan=False) + ';\n'
        code += '''for(var n=0;n<fixes.length;n++) {
 var r=fixes[n],p=app.project.itemByID(r.comp_id).layer(r.layer_index)
 .property('ADBE Transform Group').property(r.property);
 for(var k=1;k<=p.numKeys;k++){
 p.setSpatialAutoBezierAtKey(k,false);p.setSpatialTangentsAtKey(k,[0,0,0],[0,0,0]);}
}
'''
        script = directory / 'linear-positions.jsx'
        script.write_text(code, encoding='utf-8')
        execute(cli, ['script', str(script), '--project', str(project), '--save', '--json'],
                directory, 'linear-positions')
    replacements = fractional_replacements(json.loads(project.read_text(encoding='utf-8')))
    if replacements:
        code = 'var fixes=' + json.dumps(replacements, allow_nan=False) + ';\n'
        code += '''for(var n=0;n<fixes.length;n++) {
 var r=fixes[n],layer=app.project.itemByID(r.comp_id).layer(r.layer_index);
 var effects=layer.property('ADBE Effect Parade'),original=effects.property(r.effect_index);
 if(r.working_gamma!==1){var decode=effects.addProperty('ec.color.levels');
 decode.name='AIR blur decode';decode.property('gamma').setValue(1/r.working_gamma);decode.moveTo(original.propertyIndex);}
 var filter=effects.addProperty('ec.color.cckernel');
 filter.name='AIR Gaussian compatibility ('+r.amount+')';
 for(var k=0;k<9;k++)filter.property('k'+(k+1)).setValue(r.kernel[k]);
 filter.property('scale').setValue(1);filter.property('offset').setValue(0);
 filter.moveTo(original.propertyIndex);original.enabled=false;
 if(r.working_gamma!==1){var encode=effects.addProperty('ec.color.levels');
 encode.name='AIR blur encode';encode.property('gamma').setValue(r.working_gamma);encode.moveTo(original.propertyIndex);}
}
'''
        script = directory / 'fractional-gaussian.jsx'
        script.write_text(code, encoding='utf-8')
        execute(cli, ['script', str(script), '--project', str(project), '--save', '--json'],
                directory, 'fractional-gaussian')
    vignettes = smooth_mask_replacements(json.loads(project.read_text(encoding='utf-8')))
    for number, fix in enumerate(vignettes):
        execute(cli, ['exec', 'layer.settings', '--params', json.dumps({
            'comp': fix['comp_id'], 'layer': fix['layer_id'], 'width': fix['width'],
            'height': fix['height'], 'affectAll': False}),
            '--project', str(project), '--save', '--json'], directory, 'vignette-solid-'+str(number))
    if vignettes:
        code = 'var fixes=' + json.dumps(vignettes, allow_nan=False) + ';\n'
        code += '''for(var n=0;n<fixes.length;n++) {
 var r=fixes[n],l=app.project.itemByID(r.comp_id).layer(r.layer_index);
 var a=l.property('ADBE Transform Group').property('ADBE Anchor Point'),v=a.value;
 v[0]+=r.padding[0];v[1]+=r.padding[1];a.setValue(v);
 var m=l.property('ADBE Mask Parade').property(1),p=m.property('ADBE Mask Shape'),s=p.value;
 var vertices=s.vertices;for(var i=0;i<vertices.length;i++){
 vertices[i][0]+=r.padding[0];vertices[i][1]+=r.padding[1];}
 s.vertices=vertices;p.setValue(s);m.property('ADBE Mask Feather').setValue(r.native_feather);
 l.comment=r.comment;
}
'''
        script = directory / 'vignette-domain.jsx'
        script.write_text(code, encoding='utf-8')
        execute(cli, ['script', str(script), '--project', str(project), '--save', '--json'],
                directory, 'vignette-domain')
    receipt = {'version': VERSION, 'color': AE_COLOR, 'fractional_gaussian': replacements,
               'linear_positions_declared': linear_positions, 'linear_positions': positions,
               'vignettes': [r for r in vignettes if r['layer'].startswith('ae_effect_subtle_vignette_')],
               'smooth_masks': vignettes,
               'upstream_binary_modified': False}
    (directory / 'compatibility-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    return receipt
