import copy

import pytest
from PIL import Image

from worker.character_model_sheet import ensure_model_sheet, has_model_sheet, sheet_instruction, sheet_profile


@pytest.mark.parametrize('style,expected', [('지브리', 'turnaround'), ('ghibli', 'turnaround'),
    ('애니메이션', 'turnaround'), ('jidaigeki_cel', 'turnaround'), ('실사', 'detailed_board'),
    ('realistic', 'detailed_board'), ('high detail anime illustration', 'detailed_board')])
def test_style_selects_requested_board_layout(style, expected):
    assert sheet_profile({'image_style': style}) == expected


def test_sheets_keep_animal_anatomy_and_story_costumes_instead_of_copying_example_identity():
    for profile in ('turnaround', 'detailed_board'):
        instruction = sheet_instruction(profile)
        assert 'species-appropriate' in instruction
        assert 'No captions' in instruction
    assert 'true left profile, true right profile' in sheet_instruction('turnaround')
    assert 'six facial expressions' in sheet_instruction('detailed_board')
    assert 'instead of inventing' in sheet_instruction('detailed_board')


def test_reuses_current_board_but_adds_missing_style_board_without_deleting_approved_assets(tmp_path):
    portrait = tmp_path / 'approved.png'
    Image.new('RGB', (512, 512), 'blue').save(portrait)
    original_bytes = portrait.read_bytes()
    old = {'type': 'expression', 'image_url': '/existing.png', 'status': 'ready'}
    character = {'character_key': 'lead', 'image_prompt': 'Approved face and costume.',
                 'visual_dna_en': 'Approved face', 'wardrobe_en': 'Approved clothing',
                 'character_sheet_assets': [copy.deepcopy(old)]}
    generated, saves = [], []
    class Generator:
        def generate(self, prompt, reference_path):
            assert reference_path == portrait
            generated.append(prompt)
            return portrait
    class Store:
        def publish_sheet(self, topic, char, kind, path):
            return {'type': kind, 'image_url': f'/board-{len(generated)}.png', 'status': 'ready'}
        def save_design(self, *args): saves.append(copy.deepcopy(args[1]))
    generator, store = Generator(), Store()
    payload = {'image_style': 'ghibli'}
    ensure_model_sheet(character, payload, portrait, generator, store, 42, 'identity')
    assert has_model_sheet(character, payload)
    assert character['character_sheet_profile'] == 'turnaround'
    ensure_model_sheet(character, payload, portrait, generator, store, 42, 'identity')
    assert len(generated) == 1
    ensure_model_sheet(character, {'image_style': 'realistic'}, portrait, generator, store, 42, 'identity')
    assert len(generated) == 2
    assert character['character_sheet_profile'] == 'detailed_board'
    assert old in character['character_sheet_assets']
    assert len(character['character_sheet_assets']) == 3
    assert portrait.read_bytes() == original_bytes
    assert len(saves) == 2
