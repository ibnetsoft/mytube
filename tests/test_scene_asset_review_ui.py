from pathlib import Path


TEMPLATE = Path("templates/pages/image_gen.html")


def test_scene_asset_review_panel_is_rendered_from_scene_data():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert 'id="scene-asset-review"' in source
    assert "renderSceneAssetReview(data);" in source
    assert "Final clip order" in source
    assert "Continue to TTS" in source


def test_scene_upload_does_not_clear_the_opposite_media_slot():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert (
        "prompts[index].video_url = result.url;\n"
        "                    prompts[index].image_url = null;"
    ) not in source
    assert (
        "prompts[index].image_url = result.url;\n"
        "                    prompts[index].video_url = null;"
    ) not in source
    assert (
        "prompts[index].video_url = url;\n"
        "                    prompts[index].image_url = null;"
    ) not in source
    assert (
        "prompts[index].image_url = url;\n"
        "                    prompts[index].video_url = null;"
    ) not in source
