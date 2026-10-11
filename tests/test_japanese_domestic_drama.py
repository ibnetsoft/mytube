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
    assert r['required_video_scene_count']==18 and r['generate_bgm_prompt'] is True
    for minutes in (13,14,15):
        rows=schedule(prepare_request({'script_style':PROFILE['key'],'duration_minutes':minutes})['target_duration_seconds'])
        assert len(rows)!=36 and sum(s['duration_seconds'] for s in rows)==minutes*60
        assert all(s['duration_seconds']==5 for s in rows[:18])
    assert 'jeonse' in r['notes'] and 'guaranteed court outcomes' in r['notes']


def test_disclaimer_and_watercolor_assets_are_idempotent():
    p=enforce_profile(package(),{'script_style':PROFILE['key']});enforce_profile(p,{'script_style':PROFILE['key']})
    assert p['publish_metadata']['description'].count(PROFILE['fiction_disclaimer'])==1
    assert p['structure']['scenes'][0]['image_prompt'].count(PROFILE['prompt'])==1
    assert all(s['video_prompt_required'] and s['video_prompt']=='old clip' for s in p['structure']['scenes'][:18])
    assert all(not s['video_prompt_required'] for s in p['structure']['scenes'][18:])
    assert p['video_scenes']==18 and 'No vocals' in p['structure']['music_direction']


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
        assert name=='01_plan' and f'exactly {len(schedule(900))} scene plans' in task
        assert context['required_video_scene_count']==18 and context['language']=='ja'
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


def test_verified_original_seconds_override_manual_duration():
    r=prepare_request({'script_style':PROFILE['key'],'youtube_url':'https://youtu.be/abcdefghijk','source_duration_seconds':1007,'source_duration_verified':True,'duration_minutes':15})
    assert r['target_duration_seconds']==1007
    assert sum(s['duration_seconds'] for s in schedule(1007))==1007
    with pytest.raises(ValueError):prepare_request({'script_style':PROFILE['key'],'youtube_url':'https://youtu.be/abcdefghijk'})


def test_source_analysis_records_japanese_localization_and_runtime(tmp_path):
    from worker.web_topic_submissions import prepare_brief
    from worker.japanese_domestic_drama import PROFILE
    mapping=[{'source':'김민수 / 부산 / 전세','japanese':'佐藤 / 横浜 / 賃貸契約','kind':'setting','reason':'現代日本の住居と地名に合わせる'}]
    class Runner:
        def _stage(self,j,n,c,task):
            assert 'localization_map' in task and 'Do not preserve Korean names' in task
            return {'summary':'韓国の関係と事件の因果を日本の日常生活に置き換える。','localization_map':mapping}
    data={'story':'한국 사건 참고','transcript':'김민수가 부산에서 전세금을 되찾으려 했다.','youtube_url':'https://youtu.be/abcdefghijk','script_style':PROFILE['key'],'language':'ja','source_duration_seconds':1007,'source_duration_verified':True,'source_video_id':'abcdefghijk'}
    request={'web_brief':data,'web_topic_id':'test','language':'ja'}
    notes=prepare_brief(request,tmp_path,Runner(),lambda s:None)
    assert request['duration_seconds']==1007 and request['source_localization_map']==mapping
    assert '한국→일본 현지화 대응표' in notes


def test_video_keyframe_and_directorial_data_are_preserved():
    p=package();scene=p['structure']['scenes'][0]
    scene.update(video_keyframe_plan={'start_frame':{'scene_number':1},'end_frame':{'scene_number':2}},transition_to_next='continuous',scene_direction_plan={'contract':'scene_direction_plan/v1','timed_beats':[]})
    before=copy.deepcopy(scene)
    enforce_package(p,{'script_style':PROFILE['key']})
    for k in ('video_keyframe_plan','transition_to_next','scene_direction_plan'):assert scene[k]==before[k]


def test_second_enforcement_keeps_source_provenance():
    p=package();reference={'youtube_url':'https://youtu.be/abcdefghijk','source_duration_seconds':1007}
    mapping=[{'source':'부산','japanese':'横浜'}]
    enforce_package(p,{'script_style':PROFILE['key'],'source_reference':reference,'source_localization_map':mapping})
    enforce_package(p,{'script_style':PROFILE['key']})
    assert p['structure']['source_reference']==reference and p['structure']['source_localization_map']==mapping
