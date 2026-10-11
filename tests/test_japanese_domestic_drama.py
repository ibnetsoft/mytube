import copy
import pytest
from worker.japanese_domestic_drama import PROFILE,prepare_request,enforce_package,schedule
from worker.japanese_historical_documentary import prepare_request as prepare_profile,enforce_package as enforce_profile


def package():
    d=PROFILE['fiction_disclaimer']
    return {'script':d+'\n主人公は玄関で封筒を手にした。','sections':[{'text':d+'\n主人公は玄関で封筒を手にした。'}],
        'structure':{'scenes':[{'image_prompt':'A modern Japanese apartment','video_prompt':'old clip','video_prompt_required':True} for _ in range(36)]},
        'publish_metadata':{'description':'オリジナルの物語です。'},'thumbnail_image_prompt':'A quiet protagonist'}


def test_opt_in_localized_settings_and_still_schedule():
    old={'script_style':'story','language':'ko','duration_minutes':15}
    assert prepare_request(old) is old
    r=prepare_profile({**old,'script_style':PROFILE['key']})
    assert r['language']=='ja' and r['category']=='일본사건'
    assert r['required_video_scene_count']==0 and r['generate_bgm_prompt'] is True
    for minutes in (13,14,15):
        rows=schedule(prepare_request({**r,'duration_minutes':minutes})['target_duration_seconds'])
        assert len(rows)==36 and sum(s['duration_seconds'] for s in rows)==minutes*60
    assert 'jeonse' in r['notes'] and 'guaranteed court outcomes' in r['notes']


def test_disclaimer_and_watercolor_assets_are_idempotent():
    p=enforce_profile(package(),{'script_style':PROFILE['key']});enforce_profile(p,{'script_style':PROFILE['key']})
    assert p['publish_metadata']['description'].count(PROFILE['fiction_disclaimer'])==1
    assert p['structure']['scenes'][0]['image_prompt'].count(PROFILE['prompt'])==1
    assert all(not s['video_prompt_required'] and 'video_prompt' not in s for s in p['structure']['scenes'])
    assert p['video_scenes']==0 and 'No vocals' in p['structure']['music_direction']


def test_missing_actual_spoken_disclaimer_is_rejected():
    p=package();p['sections'][0]['text']='No disclaimer'
    with pytest.raises(ValueError):enforce_package(p,{'script_style':PROFILE['key']})
    p=package();p['script']='No disclaimer'
    with pytest.raises(ValueError):enforce_package(p,{'script_style':PROFILE['key']})


def test_staged_runner_plans_36_stills_and_uses_domestic_contract():
    from worker import codex_content_runner as r
    payload={'script_style':PROFILE['key'],'duration_minutes':15,'category':'일본사건','language':'ko'}
    assert 'shuraba' in r._category_narration_voice(payload)
    assert PROFILE['fiction_disclaimer'] in r._resolve_script_style_directive(PROFILE['key'])
    class Captured(Exception):pass
    runner=r.CodexStagedContentRunner.__new__(r.CodexStagedContentRunner)
    def stage(job,name,context,task):
        assert name=='01_plan' and 'exactly 36 scene plans' in task
        assert context['required_video_scene_count']==0 and context['language']=='ja'
        assert PROFILE['prompt'] in context['image_style']
        raise Captured()
    runner._stage=stage
    with pytest.raises(Captured):runner.generate('test',payload,script_only=True)


def test_source_bundle_contains_imported_profiles_without_credentials():
    from scripts.build_script_worker_bundle import files,ROOT
    names={p.relative_to(ROOT).as_posix() for p in files()}
    assert 'auth-web/lib/japaneseDomesticDramaStyle.json' in names
    assert 'auth-web/lib/japaneseHistoricalDocumentaryStyle.json' in names
    assert 'worker/connection.env' not in names
