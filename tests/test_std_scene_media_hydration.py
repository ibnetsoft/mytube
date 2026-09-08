from pathlib import Path


PROJECT_ROUTE = Path(
    "auth-web/app/api/std/projects/[projectId]/route.ts"
).read_text(encoding="utf-8")
STD_PAGE = Path("auth-web/app/std/page.tsx").read_text(encoding="utf-8")


def test_project_scene_hydration_matches_assets_by_scene_id_before_scene_number():
    assert "function sceneMediaAsset" in PROJECT_ROUTE
    assert "String(asset?.scene_id || '').trim() === sceneId" in PROJECT_ROUTE
    assert "image_asset_id: imageAsset.id" in PROJECT_ROUTE
    assert "hydrateSceneMedia(scene, assets || [])" in PROJECT_ROUTE


def test_media_restore_supports_legacy_assets_without_scene_number():
    assert "const sceneNumberById = new Map<string, number>(" in STD_PAGE
    assert "const linkedSceneNumberByAssetId = new Map<string, number>(" in STD_PAGE
    assert "const assetSceneNumber = (asset: any): number | null" in STD_PAGE
    assert "const sceneNumber = assetSceneNumber(entry.asset)" in STD_PAGE
