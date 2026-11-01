import copy

import pytest

from worker.generation_validation import grounded_quote, validate_sections, validate_story_review, validated_stage, validate_registration_update, validate_registration_readback


def test_budget_failure_recovers_with_new_context_and_preserves_original():
    calls = []
    original = {'sections': [{'scene_order': 1, 'text': '短い'}]}
    context = {'scene_budgets': [{'min_chars': 3, 'max_chars': 10}]}
    def stage(name, supplied, task):
        calls.append(copy.deepcopy(supplied))
        return original if len(calls) == 1 else {'sections': [{'scene_order': 1, 'text': '帰った。'}]}
    result = validated_stage(stage, '02_script', context, 'write',
                             lambda raw: validate_sections(raw, context['scene_budgets']))
    assert result['sections'][0]['text'] == '帰った。'
    assert 'validation_retry' not in context
    assert calls[1]['validation_retry']['rejected_response'] == original
    assert original['sections'][0]['text'] == '短い'


def test_repeated_invalid_response_is_bounded_and_does_not_repeat_cache_key():
    calls = []
    def stage(name, context, task):
        calls.append(context)
        return {}
    with pytest.raises(ValueError, match='after 3 attempts'):
        validated_stage(stage, 'script', {}, '', lambda raw: validate_sections(raw, [{}]))
    assert len(calls) == 3 and calls[1] != calls[2]


def test_execution_failure_is_not_retried_as_validation_failure():
    calls = []
    def stage(*args):
        calls.append(args)
        raise RuntimeError('CLI unavailable')
    with pytest.raises(RuntimeError, match='CLI unavailable'):
        validated_stage(stage, 'script', {}, '', lambda raw: None)
    assert len(calls) == 1


@pytest.mark.parametrize('sections', [
    [{'scene_order': 2, 'text': 'valid'}],
    [{'scene_order': True, 'text': 'valid'}],
    [{'scene_order': 1, 'text': 123}],
    [{'scene_order': 1, 'text': ' '}],
])
def test_wrong_scene_identity_or_nontext_cannot_pass(sections):
    with pytest.raises(ValueError):
        validate_sections({'sections': sections}, [{'min_chars': 1, 'max_chars': 10}])


@pytest.mark.parametrize('quote,expected', [
    ('第一段。\n\n第三段。', True),
    ('第一段。\r\n \r\n第三段。', True),
    ('\n\n', False),
    ('第一段。\n\n架空。', False),
    ('第三段。\n\n第一段。', False),
])
def test_multparagraph_evidence_remains_verbatim_and_ordered(quote, expected):
    assert grounded_quote(quote, '第一段。\n\n第二段。\n\n第三段。') is expected


def test_review_requires_named_checks_and_honest_verdict():
    review = {'verdict': 'pass', 'critical_issues': [], 'quality_notes': [],
              'checks': {'custody': {'passed': True, 'evidence_quote': '第一段。'}}}
    validate_story_review(review, '第一段。', ['custody'])
    with pytest.raises(ValueError, match='every named'):
        validate_story_review(review, '第一段。', ['timeline'])
    review['checks']['custody']['passed'] = False
    with pytest.raises(ValueError, match='contradicts'):
        validate_story_review(review, '第一段。', ['custody'])


@pytest.mark.parametrize('change', [
    {'status': 'assigned'}, {'assigned_employee_email': 'worker@example.com'},
    {'progress_payload': {'scene_assets_ready': True}},
    {'progress_payload': {'scene_image_count': 1}},
    {'pregenerated_structure': {'scenes': [{'image_url': 'saved.png'}]}},
])
def test_registration_replay_preserves_claimed_or_delivered_topic(change):
    topic = {'status': 'pending', 'assigned_employee_email': '', **change}
    with pytest.raises(ValueError, match='Do not replace'):
        validate_registration_update(topic)


def test_equal_scene_count_is_insufficient_to_confirm_registration():
    expected = {'pregenerated_script': '原文', 'pregenerated_structure': {'scenes': [{'image_prompt': 'new'}]},
                'status': 'pending', 'language': 'ja',
                'progress_payload': {'local_script_job_id': 'job', 'script_sha256': 'hash'}}
    saved = copy.deepcopy(expected)
    validate_registration_readback(saved, expected)
    saved['pregenerated_structure']['scenes'][0]['image_prompt'] = 'old'
    with pytest.raises(ValueError, match='pregenerated_structure'):
        validate_registration_readback(saved, expected)
