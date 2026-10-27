import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'worker'))
from ae_scene_effects import EFFECT_TYPES, validate_effects
from ae_scene_animation import write_scene_jsx
from ae_scene_review_contract import sample_times
from test_ae_scene_preparation import plan


def effect(kind='focus_glow'):
    if kind.startswith('depth_'):return dict(type=kind,start=.1,end=.9,intensity=.2,center=[.5,.5],color=[.7,.8,.9],radius=.5,reason='Separated depth plane supports a clear subject',target_layer='foreground' if kind=='depth_foreground_blur' else 'background',blur_pixels=6)
    if kind=='fireflies':return dict(type=kind,start=.1,end=.9,intensity=.2,center=[.2,.2],color=[1,.9,.3],radius=.15,reason='Actual firefly scene',story_quote='반딧불이 빛났다',count=8,size=.002,speed=.01,protected_regions=[])
    return dict(type=kind, start=.31, end=.39, intensity=.4, center=[.5, .5],
                color=[1, .8, .5], radius=.2, reason='Light from the visible lantern.')


def test_all_effects_validate_and_are_emitted_in_real_renderer(tmp_path):
    p = plan()
    p['camera'] = [dict(t=t, x=.5, y=.5, scale=1.04, rotation=0) for t in (0, 1)]
    p['layers'].append(dict(id='foreground',role='foreground',z_index=2,parallax=.3,anchor=[.5,.5],source_ids=['psd-003']))
    p['effects'] = [effect(kind) for kind in sorted(EFFECT_TYPES)]
    for item in p['effects']:
        if item['type'] == 'heat_distortion':
            item['target_layer'] = 'background'
    validate_effects(p, sorted(EFFECT_TYPES))
    target = tmp_path / 'scene.jsx'
    write_scene_jsx(p, {}, tmp_path / 'scene.aep', tmp_path / 'scene.mov', target, 8)
    jsx = target.read_text()
    assert 'function applySceneEffects' in jsx
    assert 'applySceneEffects(source,semanticLayers)' in jsx
    assert '/* SCENE_EFFECTS */' not in jsx
    assert 'Required AE effect unavailable' in jsx
    assert 'layer=layer.duplicate()' in jsx
    data = json.loads(jsx.split(';\n', 1)[0].removeprefix('var S = '))
    assert data['plan']['effects'] == p['effects']
    assert data['duration'] == 8


@pytest.mark.parametrize('change', [
    {'type': 'unknown'}, {'start': .5, 'end': .4}, {'start': -1}, {'intensity': float('nan')},
    {'intensity': True}, {'intensity': 2}, {'center': [0, 2]}, {'color': [1]},
    {'radius': 0}, {'reason': ''}, {'target_layer': 'character'},
])
def test_malformed_effect_is_rejected(change):
    p = plan()
    p['effects'] = [{**effect(), **change}]
    with pytest.raises(ValueError):
        validate_effects(p)


def test_character_distortion_duplicates_and_missing_selection_are_rejected():
    p = plan()
    p['effects'] = [{**effect('heat_distortion'), 'target_layer': 'character'}]
    with pytest.raises(ValueError, match='separated background or prop'):
        validate_effects(p)
    p['effects'] = [effect(), effect()]
    with pytest.raises(ValueError, match='Duplicate'):
        validate_effects(p)
    p['effects'] = [effect()]
    for requested in ([], ['impact_flash'], ['focus_glow', 'focus_glow']):
        with pytest.raises(ValueError, match='exactly match'):
            validate_effects(p, requested)


def test_impact_shake_requires_safe_camera_overscan():
    p = plan()
    p['effects'] = [effect('impact_shake')]
    with pytest.raises(ValueError, match='overscan'):
        validate_effects(p)
    p['camera'] = [dict(t=t, x=.5, y=.5, scale=1.04, rotation=0) for t in (0, 1)]
    validate_effects(p)


def test_short_effect_peak_is_sampled_at_final_narration_time():
    p = plan()
    p['effects'] = [effect()]
    times = sample_times(p, 10)
    assert round((.31 + (.39 - .31) * .15) * 10 * 24) / 24 in times
    assert round((.31 + (.39 - .31) * .7) * 10 * 24) / 24 in times
    assert sample_times(plan(), 10) == sample_times({**plan(), 'effects': []}, 10)


def test_effect_cannot_disappear_between_final_frames(tmp_path):
    p = plan()
    p['effects'] = [effect()]
    with pytest.raises(ValueError, match='three final narration frames'):
        write_scene_jsx(p, {}, tmp_path / 'scene.aep', tmp_path / 'scene.mov', tmp_path / 'scene.jsx', .5)


def test_web_and_worker_share_effect_ids_and_actual_frame_samples():
    import subprocess
    root = pathlib.Path(__file__).resolve().parents[1]
    p = plan()
    p['effects'] = [effect()]
    script = """
    const load = require('./tests/load-ts.cjs'), fs = require('fs'), path = require('path');
    const effects = load(path.resolve('lib/stdAeSceneEffects.ts'));
    const reviews = load(path.resolve('lib/stdAeSceneReview.ts'));
    const plan = JSON.parse(fs.readFileSync(0, 'utf8'));
    process.stdout.write(JSON.stringify({ids: effects.AE_SCENE_EFFECTS.map(e=>e.id).sort(),
      times: reviews.aeSceneReviewSampleTimes(plan, 10)}));
    """
    data = json.loads(subprocess.run(['node', '-e', script], cwd=root / 'auth-web',
        input=json.dumps(p), capture_output=True, text=True, check=True).stdout)
    assert data['ids'] == sorted(EFFECT_TYPES)
    assert data['times'] == sample_times(p, 10)


def test_ae_2026_three_dimensional_spatial_properties_accept_matching_tangents():
    import subprocess
    from ae_scene_animation import SCENE_JSX
    helper = SCENE_JSX.split('  function linear(property) {', 1)[1].split('  function key(', 1)[0]
    script = '''
    const assert=require('node:assert/strict');
    const PropertyValueType={ThreeD_SPATIAL:3,TwoD_SPATIAL:2};
    const KeyframeInterpolationType={LINEAR:1};
    function linear(property) {''' + helper + '''
    for (const dimensions of [2,3]) {
      let calls=0;
      linear({numKeys:2,isSpatial:true,propertyValueType:dimensions,
        setInterpolationTypeAtKey(){},setSpatialTangentsAtKey(k,left,right){
          assert.equal(left.length,dimensions);assert.equal(right.length,dimensions);calls++;
        }});
      assert.equal(calls,2);
    }
    '''
    subprocess.run(['node', '-e', script], check=True, capture_output=True, text=True)


def test_korean_ae_effect_properties_resolve_using_installed_match_names():
    import subprocess
    from ae_scene_effects import EFFECTS_JSX
    effects = [effect('atmospheric_haze'), {**effect('heat_distortion'), 'target_layer': 'background'}]
    script = '''
    const assert=require('node:assert/strict');
    const installed={
      'ADBE Fractal Noise':['ADBE Fractal Noise-0004','ADBE Fractal Noise-0005','ADBE Fractal Noise-0023'],
      'ADBE Turbulent Displace':['ADBE Turbulent Displace-0002','ADBE Turbulent Displace-0003','ADBE Turbulent Displace-0006']
    };
    const used=[];
    const generic={setValue(){},setValueAtTime(){},property(){return this;},addProperty(){return this;}};
    const fxGroup={canAddProperty(){return true;},addProperty(name){return {property(id){
      assert.ok(installed[name].includes(id),'Missing Korean AE property: '+id);used.push(id);return generic;
    }}}};
    const layer={property(name){return name==='ADBE Effect Parade'?fxGroup:generic;},duplicate(){return this;}};
    const source={layers:{addSolid(){return layer;}}};
    const BlendingMode={SCREEN:1},W=640,H=360;
    function Shape(){}
    function key(property,t,value){property.setValueAtTime(t,value);}
    function linear(){}
    const S={duration:24,plan:{effects:''' + json.dumps(effects) + '''}};
    ''' + EFFECTS_JSX + '''
    applySceneEffects(source,{background:layer});
    for(const ids of Object.values(installed)) for(const id of ids) assert.ok(used.includes(id));
    '''
    subprocess.run(['node', '-e', script], check=True, capture_output=True, text=True)
