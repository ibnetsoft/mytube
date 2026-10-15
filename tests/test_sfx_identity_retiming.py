from services.sfx_timing import retime_sfx_cues


def test_restored_subtitles_do_not_move_door_sound_to_old_index():
    rows = [dict(id='new', scene_number=10, text='身を寄せていたのです。', start=72.9, end=75.1),
            dict(id='door', scene_number=11, text='内側から足音がして、', start=79.726, end=83.67)]
    cue = dict(subtitle_id='door', subtitle_text=rows[1]['text'], scene_number=11,
               subtitle_index=0, word_boundary=0, start=73.14)
    result = retime_sfx_cues([cue], rows)
    assert result[0]['start'] == 79.726
    assert result[0]['subtitle_index'] == 1
    assert cue['subtitle_index'] == 0


def test_legacy_render_package_without_ids_resolves_text_and_scene():
    rows = [dict(scene_number=1, text='同じ', start=1, end=2),
            dict(scene_number=2, text='同じ', start=20, end=22)]
    cue = dict(subtitle_id='old', scene_number=2, subtitle_text='同じ', subtitle_index=0, word_boundary=0)
    assert retime_sfx_cues([cue], rows)[0]['start'] == 20


def test_deleted_or_ambiguous_identity_cannot_use_unrelated_index():
    cue = dict(subtitle_id='deleted', scene_number=1, subtitle_text='door', subtitle_index=0, word_boundary=0)
    rows = [dict(id='other', scene_number=1, text='door', start=1, end=2)]
    assert retime_sfx_cues([cue], rows) == []
    for row in rows:
        row.pop('id')
    assert retime_sfx_cues([cue], rows + rows) == []
