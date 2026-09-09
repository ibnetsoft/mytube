from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUBMIT_ROUTE = (ROOT / "auth-web" / "app" / "api" / "std" / "projects" / "[projectId]" / "submit" / "route.ts").read_text(encoding="utf-8")
RENDER_QUEUE = (ROOT / "auth-web" / "lib" / "stdRenderQueue.ts").read_text(encoding="utf-8")


def test_submit_archives_worker_generated_scene_images_before_asset_validation():
    assert "ensureStdGeneratedSceneAssetsArchived" in SUBMIT_ROUTE
    assert "assets = await ensureStdGeneratedSceneAssetsArchived(project, scenes || [], assets)" in SUBMIT_ROUTE
    assert SUBMIT_ROUTE.index("ensureStdGeneratedSceneAssetsArchived(project, scenes || [], assets)") < SUBMIT_ROUTE.index("const visualAssets")


def test_render_queue_archives_generated_supabase_images_to_drive_with_asset_records():
    assert "function generatedImageStorageSource(scene: any)" in RENDER_QUEUE
    assert "cowork_image_asset" in RENDER_QUEUE
    assert "isStdRequiredVideoScene(sceneNumber)" in RENDER_QUEUE
    assert "uploadStdDriveBuffer(" in RENDER_QUEUE
    assert "worker_generated_supabase_then_server_drive" in RENDER_QUEUE
    assert "const archivedAssets = await ensureStdGeneratedSceneAssetsArchived(project, scenes, assets)" in RENDER_QUEUE
