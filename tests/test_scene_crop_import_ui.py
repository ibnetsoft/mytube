from pathlib import Path


CROP_TEMPLATE = Path("templates/pages/image_crop.html")
IMAGE_TEMPLATE = Path("templates/pages/image_gen.html")


def test_crop_page_uses_project_and_sequential_scene_contract():
    source = CROP_TEMPLATE.read_text(encoding="utf-8")

    assert "cropParams.get('project_id')" in source
    assert "getTargetSceneNumber(fileIndex, panelIndex)" in source
    assert "scene_${String(sceneNumber).padStart(3, '0')}_crop.png" in source
    assert "getProjectScene(sceneNumber)" in source


def test_crop_page_imports_only_available_scene_slots():
    source = CROP_TEMPLATE.read_text(encoding="utf-8")

    assert "scene.image_url" in source
    assert "formData.append('scene_number', sceneNumber)" in source
    assert "formData.append('replace_existing', 'false')" in source
    assert "fetch('/api/image/upload-scene'" in source
    assert "Import all cropped panels into empty Scene slots" in source


def test_scene_review_links_to_project_aware_crop_page():
    source = IMAGE_TEMPLATE.read_text(encoding="utf-8")

    assert 'href="/image-crop?project_id=${encodeURIComponent(projectId || \'\')}&start_scene=1"' in source
