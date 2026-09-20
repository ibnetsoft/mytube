from worker.codex_sfx import validate_plan, plan_sfx
from services.sfx_timing import retime_sfx_cues


def test_planner_validates_library_confidence_and_preserves_text():
    units = [{'id':'s1','scene_number':1,'text':'덕수가 문을 열었습니다.'},
             {'id':'s2','scene_number':2,'text':'문설주를 붙들었습니다.'}]
    catalog = [{'id':'door','file_name':'door.mp3'}]
    raw = {'cues':[
        {'unit_index':0,'asset_id':'door','word_boundary':1,'confidence':.95,'reason':'실제로 문을 여는 행동'},
        {'unit_index':0,'asset_id':'door','word_boundary':2,'confidence':.95,'reason':'중복'},
        {'unit_index':1,'asset_id':'invented','word_boundary':0,'confidence':.95,'reason':'없는 파일'},
        {'unit_index':1,'asset_id':'door','word_boundary':0,'confidence':.3,'reason':'불확실'},
    ]}
    plan = validate_plan(raw, units, catalog)
    assert len(plan['cues']) == 1
    assert plan['cues'][0]['subtitle_text'] == units[0]['text']
    assert plan['cues'][0]['volume_db'] == -22
    assert not validate_plan(raw, units, catalog, protected=[1])['cues']


def test_planner_uses_supplied_catalog_only_and_empty_is_valid():
    class Runner:
        def _stage(self, job, stage, context, task):
            assert context['catalog'][0]['description_ko'] == '문 삐걱임'
            assert context['protected_scenes'] == [1]
            return {'cues': []}
    result = plan_sfx(Runner(), 'test', [{'text':'조용했습니다.','scene_number':1}],
                      [{'id':'door','file_name':'door.mp3','description_ko':'문 삐걱임'}],
                      [{'scene_number':1,'source':'manual','enabled':False}])
    assert result['status'] == 'ready' and result['cues'] == []


def test_render_retimes_after_final_audio_and_keeps_voice_unchanged():
    subtitles = [{'text':'문을 열었다','start':20,'end':24}, {'text':'걸었다','start':23,'end':25}]
    cues = [{'id':'a','source':'codex-sfx-v1','subtitle_index':0,'word_boundary':1,'start':2},
            {'id':'b','source':'codex-sfx-v1','subtitle_index':1,'word_boundary':0,'start':4}]
    result = retime_sfx_cues(cues, subtitles)
    assert len(result) == 1 and result[0]['start'] == 20
    assert subtitles[0]['start'] == 20 and subtitles[0]['end'] == 24
    assert retime_sfx_cues([{**cues[0],'subtitle_index':99}],subtitles) == []
