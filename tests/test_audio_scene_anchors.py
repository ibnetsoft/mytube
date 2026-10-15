import pytest
from services.bgm_timeline import retime_bgm_settings
from services.sfx_timing import retime_sfx_cues


def test_bgm_recalculates_legacy_scene_times_after_tts():
    settings = dict(bgm_start_scene=100, bgm_start_subtitle=2, bgm_end_scene=101, bgm_start=799, bgm_end=827)
    rows = [dict(scene_number=100, start=2000, end=2020), dict(scene_number=100, start=2020, end=2030),
            dict(scene_number=101, start=2030, end=2053)]
    actual = retime_bgm_settings(settings, rows, 2053)
    assert (actual['bgm_start'], actual['bgm_end']) == (2020, 2053)
    assert settings['bgm_start'] == 799


def test_deleted_scene_or_anchor_aborts_instead_of_reusing_old_seconds():
    with pytest.raises(ValueError, match='missing'):
        retime_bgm_settings(dict(bgm_start_scene=100, bgm_start=799), [], 2053)
    with pytest.raises(ValueError, match='anchor'):
        retime_bgm_settings(dict(bgm_start_scene=2, bgm_start_anchor={'scene_number':2,'source_text':'deleted','offset':0}), [], 2053)
    with pytest.raises(ValueError, match='anchor'):
        retime_sfx_cues([dict(word_boundary=0, subtitle_id='deleted', subtitle_text='door', scene_number=2)], [], strict=True)


def test_explicit_absolute_legacy_cues_remain_compatible():
    assert retime_sfx_cues([{'start':7}], []) == [{'start':7}]
    assert retime_bgm_settings({'bgm_start':8,'bgm_end':12}, [], 20) == {'bgm_start':8,'bgm_end':12}
