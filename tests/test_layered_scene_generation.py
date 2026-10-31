from pathlib import Path
from PIL import Image
from worker.layered_scene_generation import generate_scene_planes


class FakeGenerator:
    def __init__(self, root):
        self.root = root
        self.roles = []

    def generate(self, *, prompt, role, reference, work_dir):
        self.roles.append((role, reference))
        path = self.root / f'{len(self.roles)}.png'
        if role == 'background':
            Image.new('RGB', (512, 512), (10, 20, 30)).save(path)
        else:
            image = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
            image.paste((200, 20, 30, 255), (100, 100, 300, 400))
            image.save(path)
        return path


def test_generates_planes_before_composite(tmp_path):
    reference = tmp_path / 'reference.png'
    Image.new('RGB', (2, 2)).save(reference)
    generator = FakeGenerator(tmp_path)
    result = generate_scene_planes({'scene_number': 19, 'image_prompt': 'A person in a room',
        'characters': [{'key': 'person', 'reference_file': str(reference),
                        'placement_prompt': 'center'}]}, tmp_path / 'out', generator=generator)
    assert [role for role, _ in generator.roles] == ['background', 'character']
    assert generator.roles[1][1] == reference
    assert len(result['plane_files']) == 2
    assert Path(result['scene_file']).is_file()
