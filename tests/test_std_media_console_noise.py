from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STD_PAGE = (ROOT / "auth-web" / "app" / "std" / "page.tsx").read_text(encoding="utf-8")


def test_std_media_api_urls_are_not_rendered_directly_after_restore_failures():
    assert "const isProjectAssetFileUrl" in STD_PAGE
    assert "const keepRenderableMediaUrl" in STD_PAGE
    assert "return isProjectAssetFileUrl(url) ? null : sanitizeAssetUrl(url)" in STD_PAGE
    assert "image_url: restoredImageUrl || keepRenderableMediaUrl(scene.image_url) || null" in STD_PAGE
    assert "video_url: restoredVideoUrl || keepRenderableMediaUrl(scene.video_url) || null" in STD_PAGE
    assert "assetDisplayUrl(projectId, thumbnailAsset)" not in STD_PAGE


def test_subtitle_scene_cards_do_not_restore_direct_asset_api_urls():
    assert "if (isProjectAssetFileUrl(str)) return null" in STD_PAGE
    assert "image_url: visual.image_url || runtimeAssetUrl(sub?.image_url || sub?.image) || ''" in STD_PAGE
    assert "video_url: visual.video_url || runtimeAssetUrl(sub?.video_url || sub?.video) || null" in STD_PAGE
    assert "group.image_url = visual.image_url || runtimeAssetUrl(sub?.image_url || sub?.image) || ''" in STD_PAGE
    assert "group.video_url = visual.video_url || runtimeAssetUrl(sub?.video_url || sub?.video) || null" in STD_PAGE
