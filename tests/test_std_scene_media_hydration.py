from pathlib import Path


PROJECT_ROUTE = Path(
    "auth-web/app/api/std/projects/[projectId]/route.ts"
).read_text(encoding="utf-8")
STD_PAGE = Path("auth-web/app/std/page.tsx").read_text(encoding="utf-8")


def test_project_scene_hydration_matches_assets_by_scene_id_before_scene_number():
    assert "function sceneMediaAsset" in PROJECT_ROUTE
    assert "String(asset?.scene_id || '').trim() === sceneId" in PROJECT_ROUTE
    assert "image_asset_id: imageAsset.id" in PROJECT_ROUTE
    assert "assetsAfterSave || []" in PROJECT_ROUTE


def test_project_scene_hydration_prefers_live_topic_supabase_media_before_drive_fallback():
    assert "function sceneSupabaseImageUrl" in PROJECT_ROUTE
    assert "const imageUrl = sceneSupabaseImageUrl(scene)" in PROJECT_ROUTE
    assert "|| sceneSupabaseImageUrl(sourceScene)" in PROJECT_ROUTE
    assert ".from('topics_queue')" in PROJECT_ROUTE
    assert "sourceSceneByNumber.get(sceneNumberOf(scene, index + 1))" in PROJECT_ROUTE
    assert "metadata?.storage_object_path" in PROJECT_ROUTE


def test_project_scene_hydration_prefers_supabase_video_before_drive_fallback():
    assert "function sceneSupabaseVideoUrl" in PROJECT_ROUTE
    assert "const coworkAsset = metadata?.cowork_video_asset" in PROJECT_ROUTE
    assert "metadata?.video_storage_object_path" in PROJECT_ROUTE
    assert "const videoUrl = sceneSupabaseVideoUrl(scene)" in PROJECT_ROUTE
    assert "|| sceneSupabaseVideoUrl(sourceScene)" in PROJECT_ROUTE


def test_media_restore_supports_legacy_assets_without_scene_number():
    assert "const sceneNumberById = new Map<string, number>(" in STD_PAGE
    assert "const linkedSceneNumberByAssetId = new Map<string, number>(" in STD_PAGE
    assert "const assetSceneNumber = (asset: any): number | null" in STD_PAGE
    assert "const sceneNumber = assetSceneNumber(entry.asset)" in STD_PAGE
