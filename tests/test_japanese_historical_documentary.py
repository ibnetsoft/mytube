from worker.japanese_historical_documentary import PROFILE, prepare_request, enforce_package


def test_documentary_settings_and_existing_story_isolation():
    old = {'script_style': 'story', 'language': 'ko', 'duration_minutes': 15}
    assert prepare_request(old) is old
    configured = prepare_request({**old, 'script_style': PROFILE['key']})
    assert configured['language'] == 'ja'
    assert configured['duration_minutes'] == 30
    assert configured['image_style'] == 'sumi_e_ukiyo_e'
    assert '현대' not in configured['era_region']


def test_visual_contract_covers_nested_assets_and_is_idempotent():
    package = {'structure': {'scenes': [{'image_prompt': 'A historical room'}]},
               'image_grid_prompts': [{'shared_style': 'ink', 'panels': [{'panel_prompt': 'An elderly man'}]}],
               'thumbnail_image_prompt': 'An old samurai'}
    result = enforce_package(package, {'script_style': PROFILE['key']})
    enforce_package(result, {'script_style': PROFILE['key']})
    prompts = [result['structure']['scenes'][0]['image_prompt'], result['image_grid_prompts'][0]['shared_style'], result['image_grid_prompts'][0]['panels'][0]['panel_prompt'], result['thumbnail_image_prompt']]
    assert all(prompt.count(PROFILE['prompt']) == 1 for prompt in prompts)
    assert result['script_style'] == PROFILE['key']


def test_documentary_contract_wins_over_japanese_folktale_category():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
    import codex_content_runner as runner
    payload = {'category_id': 13, 'category': '日本昔話', 'script_style': PROFILE['key']}
    assert runner._category_narration_voice(payload) == PROFILE['narration_directive']
    assert runner._story_spine_contract(payload) == PROFILE['narration_directive']
    assert runner._resolve_script_style_directive(PROFILE['key']) == PROFILE['narration_directive']
    assert runner._category_narration_voice({'category_id': 13, 'script_style': 'story'}) != PROFILE['narration_directive']
