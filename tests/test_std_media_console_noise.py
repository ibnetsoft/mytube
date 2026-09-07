from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STD_PAGE = (ROOT / "auth-web" / "app" / "std" / "page.tsx").read_text(encoding="utf-8")
ASSET_ROUTE = (ROOT / "auth-web" / "app" / "api" / "std" / "projects" / "[projectId]" / "assets" / "file" / "route.ts").read_text(encoding="utf-8")


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


def test_failed_drive_media_restore_does_not_emit_browser_404s():
    assert "const restoreHeaders = { ...headers, 'X-Std-Media-Restore': '1' }" in STD_PAGE
    assert "{ headers: restoreHeaders }" in STD_PAGE
    assert "if (!res.ok || res.status === 204) return null" in STD_PAGE
    assert "const isMediaRestoreRequest = req.headers.get('x-std-media-restore') === '1'" in ASSET_ROUTE
    assert "if (isMediaRestoreRequest)" in ASSET_ROUTE
    assert "return new NextResponse(null, { status: 204" in ASSET_ROUTE


def test_unlisted_cached_project_is_restored_without_a_failing_detail_request():
    assert "const preferredProjectIsListed" in STD_PAGE
    cache_restore = "if (rememberedPreferredProject && projectMatchesRequester(rememberedPreferredProject, email || user?.email))"
    server_fetch = "else if (preferredProjectId && preferredProjectIsListed)"
    assert cache_restore in STD_PAGE
    assert server_fetch in STD_PAGE
    assert STD_PAGE.index(cache_restore) < STD_PAGE.index(server_fetch)
