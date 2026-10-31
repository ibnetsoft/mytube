from worker.effect_scene_scope import normalize_scope, contains, chapter_scope
import pytest


def test_scope_and_legacy_behavior():
    scope = normalize_scope({'start': 19, 'end': 50})
    assert [contains(scope, n) for n in (18, 19, 50, 51)] == [False, True, True, False]
    assert contains(None, 100)
    assert contains(chapter_scope(scope, 50), 1) is False
    assert chapter_scope(scope, 25) == {'start': 1, 'end': 25}


@pytest.mark.parametrize('value', [{}, {'start': 19, 'end': 18}, {'start': True, 'end': 50}, {'start': 1, 'end': 1000}])
def test_invalid_range(value):
    with pytest.raises(ValueError):
        normalize_scope(value)
