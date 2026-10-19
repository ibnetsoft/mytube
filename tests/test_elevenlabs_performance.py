import copy
import pytest
from worker.elevenlabs_performance import validate_performance, plan_performance


def test_tags_are_separate_and_unicode_anchors_preserve_the_script():
    scenes = [{'scene_number': 1, 'scene_text': '🌙 静かに。ねえ、本当なの？'}]
    before = copy.deepcopy(scenes)
    plan = validate_performance({'scenes': [{'scene_number': 1, 'cues': [
        {'before': 'ねえ、本当なの？', 'occurrence': 1, 'tag': 'whispers', 'reason': 'A private question'}]}]}, scenes)
    assert scenes == before
    assert plan['scenes'][0]['cues'][0]['offset'] == 6
    assert plan['scenes'][0]['source_text'] == scenes[0]['scene_text']


@pytest.mark.parametrize('change', [{'tag': 'explosion'}, {'before': 'not in source'}, {'occurrence': 0}, {'reason': ''}])
def test_invalid_or_invented_directions_fail_closed(change):
    cue = {'before': 'hello', 'occurrence': 1, 'tag': 'curious', 'reason': 'A question'}
    with pytest.raises(ValueError):
        validate_performance({'scenes': [{'scene_number': 1, 'cues': [{**cue, **change}]}]}, [{'scene_number': 1, 'scene_text': 'hello'}])


def test_generation_repairs_invalid_stage_output_without_fabricating_tags():
    calls = []
    def stage(job, name, context, task):
        calls.append(context)
        return {'scenes': [{'scene_number': 1, 'cues': []}]} if len(calls) > 1 else {'scenes': []}
    plan = plan_performance(stage, 'new', [{'scene_number': 1, 'scene_text': 'hello'}], 'en')
    assert len(calls) == 2
    assert calls[1]['validation_feedback']
    assert plan['scenes'][0]['cues'] == []
