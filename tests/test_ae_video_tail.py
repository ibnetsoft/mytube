import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
from ae_video_tail import recorded_scene_duration, video_tail_jsx, pending_video_tail, VIDEO_TAIL_POLICY
from worker import ae_highlight_worker as ae


def test_recorded_timing_replaces_five_second_draft():
    assert recorded_scene_duration({'subtitles': [
        {'scene_number': 14, 'start_num': 95.55, 'end_num': 99},
        {'scene_number': 14, 'start_num': 99, 'end_num': 103.49},
        {'scene_number': 15, 'start_num': 103.49, 'end_num': 110},
    ]}, 14, 5) == 103.49 - 95.55
    assert recorded_scene_duration({}, 14, 5) == 5


def test_submission_schedules_tail_once_and_waits_for_review():
    scene={'scene_number':14,'visual_type':'video','duration_seconds':5,'ae_motion_plan':{'enabled':True}}
    payload={'subtitles':[{'scene_number':14,'start':10,'end':18}]}
    assert pending_video_tail(scene,payload)
    scene['metadata']={'ae_motion_asset':{'status':'review_pending','duration_seconds':8,'video_tail_policy':VIDEO_TAIL_POLICY}}
    assert not pending_video_tail(scene,payload)
    payload['subtitles'][0]['end']=19
    assert pending_video_tail(scene,payload)
    payload['subtitles'][0]['dialogue_kind']='dialogue'
    assert not pending_video_tail(scene,payload)


def test_video_jsx_keeps_speed_and_holds_last_frame_then_zooms(tmp_path):
    job = ae.SceneJob(topic_id='topic', topic_title='Topic', structure={'scenes': []},
        scene_index=0, scene={'ae_motion_plan': {'enabled': True}}, scene_number=14,
        plan_kind='motion', preset='hold', duration_seconds=7.94,
        source=ae.GcsRef('bucket', 'source.mp4'))
    jsx = tmp_path / 'tail.jsx'
    ae._write_jsx(job, tmp_path/'source.mp4', tmp_path/'project.aep', tmp_path/'render.mp4', jsx)
    script = jsx.read_text(encoding='utf-8')
    assert 'var DUR = 7.940;' in script
    assert video_tail_jsx() in script
    assert 'bg.stretch = 100' in script
    assert 'remap.setValueAtTime(sourceEnd, sourceEnd)' in script
    assert 'remap.setValueAtTime(DUR, sourceEnd)' in script
    assert 'videoScale.setValueAtTime(sourceDuration, [scale, scale])' in script
    assert 'needsTail && !mouthRuntime.video_source && (mouthRuntime.enabled || false)' in script
    assert 'mouthRuntime.enabled || true' in video_tail_jsx(True)


def test_automatic_tail_approval_requires_real_source_and_output_checks():
    from ae_video_tail import automatic_tail_review
    payload={'ae_mouth':{'enabled':True}}
    result={'video_tail_policy':VIDEO_TAIL_POLICY,'render_sha256':'a'*64,
            'directorial_plan':{'source_video_review_status':'reviewed','qa_assertions':['identity']},
            'scene_visual_qa':{'passed':True,'critical_issues':[],
                'checks':[{'assertion':'identity','passed':True,'evidence':'The same woman is visible throughout the sampled frames.'}]}}
    assert automatic_tail_review(payload,result)['decision']=='approved'
    assert automatic_tail_review({},result) is None
    result['scene_visual_qa']['checks'][0]['passed']=False
    assert automatic_tail_review(payload,result) is None
