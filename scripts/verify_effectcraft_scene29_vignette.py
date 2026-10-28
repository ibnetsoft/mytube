"""Reproduce the scene-29 worker conversion and audit its isolated vignette."""
import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'worker'))
from effectcraft_render import binary, _execute
from effectcraft_compatibility import prepare_project, vignette_replacements

OLD = ROOT/'output/effectcraft/psd-3376-scene29-effects-20261021'
D = ROOT/'output/effectcraft/psd-3376-scene29-vignette-fix-20261021'
D.mkdir(parents=True, exist_ok=True)
cli = binary()
if '--render' in sys.argv:
    shutil.copy2(OLD/'rich.ecproj', D/'scene.ecproj')
    shutil.copy2(OLD/'rich/ae-reference.mp4', D/'ae-reference.mp4')
    prepare_project(cli, D/'scene.ecproj', D, _execute)
    _execute(cli, ['render', str(D/'scene.ecproj'), '--comp', 'ae_highlight_parallax_layered_scene',
                  '--out', str(D/'effectcraft.mp4'), '--format', 'h264', '--audio', 'off',
                  '--fps', '24', '--json'], D, 'render-fixed')

control = D/'control';control.mkdir(exist_ok=True)
project = control/'vignette.ecproj'
shutil.copy2(OLD/'controls/ec-subtle_vignette.ecproj', project)
receipt = prepare_project(cli, project, control, _execute)
_execute(cli, ['render-frame', str(project), '--comp', 'ae_highlight_parallax_layered_scene',
              '--time', '4', '--out', str(control/'ec-vignette.png'), '--json'], control, 'vignette')
assert not vignette_replacements(json.loads(project.read_text(encoding='utf-8')))

before = json.loads((OLD/'rich.ecproj').read_text(encoding='utf-8'))
after = json.loads((D/'scene.ecproj').read_text(encoding='utf-8'))
audits = []
for key, item in before['items'].items():
    if item['kind'].get('type') != 'Comp':continue
    actual = after['items'][key]['kind']['layers']
    original = item['kind']['layers']
    assert len(actual) == len(original)
    for a, b in zip(original, actual):
        if not a['name'].startswith('ae_effect_subtle_vignette_'):
            assert a == b, a['name']
            continue
        ga = {g['match']:g for g in a['props']['children']}
        gb = {g['match']:g for g in b['props']['children']}
        ta = {g['match']:g for g in ga['transform']['children']}
        tb = {g['match']:g for g in gb['transform']['children']}
        for prop in ta:
            if prop != 'anchor':assert ta[prop] == tb[prop], prop
        pa = {g['match']:g for g in ga['masks']['children'][0]['children']}
        pb = {g['match']:g for g in gb['masks']['children'][0]['children']}
        sa, sb = pa['path']['value']['v'], pb['path']['value']['v']
        for prop in ['in_tangents', 'out_tangents', 'closed']:assert sa[prop] == sb[prop]
        for va, vb in zip(sa['vertices'], sb['vertices']):
            assert np.allclose(np.array(va)-np.array(ta['anchor']['value']['v'][:2]),
                               np.array(vb)-np.array(tb['anchor']['value']['v'][:2]))
        normalized = copy.deepcopy(b)
        normalized['comment'] = a['comment'];normalized['source'] = a['source']
        ng = {g['match']:g for g in normalized['props']['children']}
        for i, child in enumerate(ng['transform']['children']):
            if child['match'] == 'anchor':ng['transform']['children'][i] = copy.deepcopy(ta['anchor'])
        for i, child in enumerate(ng['masks']['children'][0]['children']):
            if child['match'] in ('path', 'feather'):
                ng['masks']['children'][0]['children'][i] = copy.deepcopy(pa[child['match']])
        assert normalized == a, 'Unexpected vignette property change'
        audits.append(dict(comp=item['name'], layer=a['name'], opacity_and_timing_unchanged=True,
                           world_geometry_unchanged=True, all_other_layers_unchanged=True))

def pixels(path):return np.asarray(Image.open(path).convert('RGB')).astype(float)
ae = pixels(OLD/'controls/ae-subtle_vignette.png')
aoff = pixels(OLD/'controls/ae-baseline4.png')
eoff = pixels(OLD/'controls/ec-baseline4.png')
ec_before = pixels(OLD/'controls/ec-subtle_vignette.png')
ec_after = pixels(control/'ec-vignette.png')
results = {}
for name, ec in [('before', ec_before), ('after', ec_after)]:
    results[name] = dict(raw_mae_255=float(abs(ae-ec).mean()),
                         effect_delta_mae_255=float(abs((ae-aoff)-(ec-eoff)).mean()))
assert results['after']['effect_delta_mae_255'] < results['before']['effect_delta_mae_255']*.25
assert np.array_equal(ec_after, pixels(D/'padding-feather-probe.png')), 'Worker differs from probe'
sheet = Image.new('RGB', (1440, 588), '#151515');draw = ImageDraw.Draw(sheet)
for n, (label, arr) in enumerate([('AE',ae), ('EffectCraft before',ec_before), ('EffectCraft fixed',ec_after)]):
    sheet.paste(Image.fromarray(arr.astype('uint8')).resize((480,270)), (n*480,24))
    delta = (ae-aoff) if n == 0 else (arr-eoff)
    sheet.paste(Image.fromarray(np.clip(abs(delta)*12,0,255).astype('uint8')).resize((480,270)), (n*480,318))
    draw.text((n*480+10,7),label,fill='white')
    draw.text((n*480+10,301),'Isolated vignette magnitude x12',fill='white')
sheet.save(D/'vignette-before-after.jpg',quality=95)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
results.update(layer_audit=audits, calibration='ae-feather-profiles.json',
               ae_reference_reused=True, ae_reference_sha256=sha(D/'ae-reference.mp4'),
               original_ae_reference_sha256=sha(OLD/'rich/ae-reference.mp4'),
               source_psd_sha256=sha(OLD/'source.psd'), receipt=receipt)
(D/'vignette-validation.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in results.items() if k in ('before','after','layer_audit')},indent=2))
