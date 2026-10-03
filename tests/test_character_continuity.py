import copy
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'worker'))
from character_continuity import (validate_character_identity, select_reference_characters,
                                 character_continuity_prompt, scene_continuity_prompt,
                                 LEGACY_REFERENCE_HAIR_LOCK, character_design_anchors)


def character(name, numbers):
    return {'name': name, 'aliases': [], 'scene_numbers': numbers,
            'visual_dna_en': f'{name} has a distinctive angular face.', 'wardrobe_en': 'Blue cotton robe.',
            'hair_design_en': f'{name}: broad shaved crown, straight boundary, short black side hair; narrow topknot high at rear.',
            'continuity_instruction': 'Preserve the approved face and hairstyle.'}


def census():
    cast = [['Lead', 'Elder son', 'Guard'], ['Lead', 'Elder son', 'Younger son'],
            ['Lead', 'Younger son', 'Aunt'], ['Lead', 'Aunt', 'Shopkeeper'], ['Lead', 'Shopkeeper']]
    all_names = list(dict.fromkeys(name for names in cast for name in names))
    definitions = [character(name, [i for i, names in enumerate(cast, 1) if name in names]) for name in all_names]
    return {'main_character': definitions[0], 'supporting_characters': definitions[1:],
            'scene_cast': [{'scene_number': i, 'characters': names} for i, names in enumerate(cast, 1)]}


SCENES = [{'scene_number': i, 'scene_text': 'The actual final script scene.'} for i in range(1, 6)]


def test_every_recurring_person_is_selected_beyond_three_and_single_scene_does_not_count_twice():
    identity = census()
    identity['scene_cast'][0]['characters'] += ['Guard', 'Guard']
    identity['supporting_characters'][1]['scene_numbers'] = [1, 1, 1]
    result = validate_character_identity(identity, SCENES)
    assert [c['name'] for c in select_reference_characters(result)] == [
        'Lead', 'Elder son', 'Younger son', 'Aunt', 'Shopkeeper']
    assert result['supporting_characters'][0]['scene_numbers'] == [1, 2]


def test_missing_recurring_character_is_rejected_not_silently_dropped():
    identity = census()
    identity['supporting_characters'] = identity['supporting_characters'][:2]
    with pytest.raises(ValueError, match='Missing recurring character designs'):
        validate_character_identity(identity, SCENES)


@pytest.mark.parametrize('change', ['missing_scene', 'duplicate_scene', 'unknown_scene', 'wrong_appearance', 'missing_hair'])
def test_incomplete_or_inconsistent_census_is_rejected(change):
    identity = census()
    if change == 'missing_scene':
        identity['scene_cast'].pop()
    elif change == 'duplicate_scene':
        identity['scene_cast'].append(copy.deepcopy(identity['scene_cast'][0]))
    elif change == 'unknown_scene':
        identity['scene_cast'][0]['scene_number'] = 999
    elif change == 'wrong_appearance':
        identity['main_character']['scene_numbers'] = [1]
    else:
        identity['main_character'].pop('hair_design_en')
    with pytest.raises(ValueError):
        validate_character_identity(identity, SCENES)


def test_approved_supporting_reference_is_retained_and_never_redesigned():
    identity = census()
    approved = {**character('Elder son', [1, 2]), 'hair_design_en': 'Approved short narrow topknot and exact horseshoe hairline.',
                'character_key': 'stable-son-key', 'image_url': '/approved-son.png'}
    absent = {**character('Old neighbor', [1]), 'image_url': '/neighbor.png'}
    existing = {'main_character': identity['main_character'], 'supporting_characters': [approved, absent]}
    result = validate_character_identity(identity, SCENES, existing)
    son = next(c for c in result['supporting_characters'] if c['name'] == 'Elder son')
    assert son['hair_design_en'] == approved['hair_design_en']
    assert son['character_key'] == 'stable-son-key' and son['image_url'] == '/approved-son.png'
    neighbor = next(c for c in result['supporting_characters'] if c['name'] == 'Old neighbor')
    assert neighbor['scene_numbers'] == [] and neighbor['image_url'] == '/neighbor.png'


def test_scene_lock_keeps_brothers_distinct_and_only_in_their_actual_scenes():
    anchors = validate_character_identity(census(), SCENES)
    prompt = scene_continuity_prompt(anchors, [1])
    assert 'Elder son: broad shaved crown' in prompt
    assert 'Younger son' not in prompt and 'Aunt' not in prompt
    assert 'Never swap' in character_continuity_prompt(anchors['main_character'])
    assert scene_continuity_prompt(anchors, [999]) == ''


def test_legacy_saved_references_without_census_are_preserved_without_limit():
    characters = [{key: value for key, value in character(str(i), []).items() if key != 'scene_numbers'} for i in range(6)]
    assert len(select_reference_characters({'main_character': characters[0], 'supporting_characters': characters[1:]})) == 6


def test_legacy_portrait_does_not_adopt_new_model_invented_hair_design():
    identity = census()
    old = {**identity['main_character'], 'image_url': '/existing-approved.png', 'character_key': 'existing-lead'}
    old.pop('hair_design_en')
    identity['main_character']['hair_design_en'] = 'New model invented long modern ponytail.'
    result = validate_character_identity(identity, SCENES, {'main_character': old})
    assert result['main_character']['hair_design_en'] == LEGACY_REFERENCE_HAIR_LOCK
    assert result['main_character']['image_url'] == '/existing-approved.png'
    assert 'modern ponytail' not in character_continuity_prompt(result['main_character'])
    anchors = character_design_anchors(result)
    assert anchors['character_image_generation']['status'] == 'pending'
    assert anchors['character_image_generation']['count'] == 1
    assert anchors['character_image_generation']['required_count'] == 5


def test_shared_identity_stage_retries_incomplete_census_before_any_media(monkeypatch):
    import codex_content_runner as runner
    from worker.content_language import resolve_setting
    calls = []
    def stage(self, job, name, context, task):
        calls.append(name)
        result = census()
        if len(calls) == 1:
            result['scene_cast'].pop()
        else:
            assert 'every final scene' in context['character_identity_validation_feedback']
        return result
    monkeypatch.setattr(runner.CodexStagedContentRunner, '_stage', stage)
    result = runner.CodexStagedContentRunner().finalize_character_identity('repair-test',
        {'script': 'Approved final script', 'scenes': SCENES, 'existing_character_anchors': {}}, resolve_setting({}))
    assert calls == ['02d_character_identity', '02d_character_identity']
    assert len(result['supporting_characters']) == 4
