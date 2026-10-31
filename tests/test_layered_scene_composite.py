from PIL import Image
import pytest
from worker.layered_scene_composite import composite_scene


def test_composes_distinct_planes_and_preserves_sources(tmp_path):
    bg, person, out = [tmp_path / f'{name}.png' for name in ('bg', 'person', 'scene')]
    Image.new('RGBA', (8, 8), (10, 20, 30, 255)).save(bg)
    layer = Image.new('RGBA', (8, 8), (0, 0, 0, 0))
    layer.putpixel((2, 3), (200, 30, 40, 255))
    layer.save(person)
    source_bytes = (bg.read_bytes(), person.read_bytes())
    composite_scene(bg, [person], out)
    with Image.open(out) as result:
        assert result.getpixel((2, 3)) == (200, 30, 40)
        assert result.getpixel((0, 0)) == (10, 20, 30)
    assert (bg.read_bytes(), person.read_bytes()) == source_bytes
    with pytest.raises(FileExistsError):
        composite_scene(bg, [person], out)


def test_rejects_flattened_layer(tmp_path):
    bg, flat, out = [tmp_path / f'{name}.png' for name in ('bg', 'flat', 'scene')]
    Image.new('RGB', (8, 8)).save(bg)
    Image.new('RGB', (8, 8)).save(flat)
    with pytest.raises(ValueError, match='alpha'):
        composite_scene(bg, [flat], out)
    assert not out.exists()
