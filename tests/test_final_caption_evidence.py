import pytest
from worker.final_caption_evidence import caption_samples


def test_every_caption_is_visible_even_when_fixed_scene_fractions_miss_it():
    rows=[{'scene_number':1,'start':a,'end':b} for a,b in
          [(0,8.803),(8.803,15.099),(15.099,21.316),(21.316,27.481)]]
    samples=caption_samples(rows,{'number':1},24,59.167)
    middles={s['subtitle_index']:s['time'] for s in samples if s['phase']=='middle'}
    assert set(middles)=={0,1,2,3}
    assert 15.099<middles[2]<21.316
    for index,row in enumerate(rows):
        phases={s['phase']:s['time'] for s in samples if s['subtitle_index']==index}
        assert row['start']<phases['after_start']<phases['before_end']<row['end']
        if row['start']>0:assert phases['before_start']<row['start']
        assert phases['after_end']>row['end']


def test_filters_scene_and_never_seeks_outside_final_media():
    rows=[{'scene_number':1,'start':0,'end':1},{'scene_number':2,'start':1,'end':2}]
    samples=caption_samples(rows,{'number':2},24,2)
    assert all(s['subtitle_index']==1 and 0<=s['time']<2-1/24 for s in samples)
    assert not any(s['phase']=='after_end' for s in samples)


def test_invalid_recording_times_fail_closed():
    with pytest.raises(ValueError):
        caption_samples([{'scene_number':1,'start':1,'end':1}],{'number':1},24,2)


def test_terminal_sample_uses_an_existing_frame_when_audio_clock_is_fractional():
    total=970.6840816326533
    samples=caption_samples([{'scene_number':72,'start':968,'end':total}],{'number':72},24,total)
    last=next(s for s in samples if s['phase']=='before_end')
    assert last['time']==pytest.approx(970.5833333333334)
    assert all(s['time']*24==pytest.approx(round(s['time']*24)) for s in samples)
    assert max(s['time'] for s in samples)<=970.625
