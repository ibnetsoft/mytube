from worker.codex_local_console import StartRequest
import pytest


def test_concentrated_range_is_new_request_only_and_configurable():
    request = StartRequest(mode='new', concentrated_scene_effects=True,
        image_layer_scene_start=19, image_layer_scene_end=50)
    assert (request.image_layer_scene_start, request.image_layer_scene_end) == (19, 50)
    assert StartRequest(mode='repair').concentrated_scene_effects is False
    assert StartRequest(mode='new', concentrated_scene_effects=True,
        image_layer_scene_start=25, image_layer_scene_end=60).image_layer_scene_end == 60


def test_concentrated_range_must_follow_video_scenes():
    with pytest.raises(ValueError):
        StartRequest(mode='new', concentrated_scene_effects=True,
                     image_layer_scene_start=18, image_layer_scene_end=50)
