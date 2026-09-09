from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STD_PAGE = (ROOT / "auth-web" / "app" / "std" / "page.tsx").read_text(encoding="utf-8")


def test_project_list_requires_video_for_the_intro_scenes_before_submit():
    assert "const readyVisualScenes = scenes.filter" in STD_PAGE
    assert "isStdRequiredVideoScene(sceneNumber)" in STD_PAGE
    assert "? Boolean(scene?.video_url)" in STD_PAGE
    assert "const isImageDone = scenes.length > 0 && uploadedAssetsCount >= scenes.length" in STD_PAGE


def test_disabled_submit_button_explains_missing_requirements():
    assert "const submitBlockers = [" in STD_PAGE
    assert "'필수 영상/이미지'" in STD_PAGE
    assert "'TTS'" in STD_PAGE
    assert "'썸네일'" in STD_PAGE
    assert "완료 후 제출할 수 있습니다." in STD_PAGE
