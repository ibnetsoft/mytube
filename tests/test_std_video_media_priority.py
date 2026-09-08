from pathlib import Path


STD_PAGE = Path("auth-web/app/std/page.tsx").read_text(encoding="utf-8")
INIT_ROUTE = Path("auth-web/app/api/std/projects/[projectId]/assets/init/route.ts").read_text(encoding="utf-8")
COMPLETE_ROUTE = Path("auth-web/app/api/std/projects/[projectId]/assets/complete/route.ts").read_text(encoding="utf-8")
POLICY = Path("auth-web/lib/stdPolicy.ts").read_text(encoding="utf-8")


def test_hook_scenes_remain_video_scenes():
    assert "export const STD_VIDEO_REQUIRED_UNTIL_SEC = 60" in POLICY
    assert "STD_REQUIRED_VIDEO_SCENE_COUNT" in POLICY


def test_existing_video_assets_are_preferred_over_scene_images():
    assert "const videoAsset = (assets || []).find" in STD_PAGE
    assert "|| projectAssetFileUrl(projectId, videoAsset)" in STD_PAGE
    assert "if (isProjectAssetFileUrl(str)) return str" in STD_PAGE
    assert "video_url: restoredVideoUrl || runtimeAssetUrl(scene.video_url) || null" in STD_PAGE


def test_new_visual_uploads_use_supabase_before_drive_fallback():
    assert "createSignedUploadUrl(storagePath" in INIT_ROUTE
    assert "storage_upload_url: signedUpload.signedUrl" in INIT_ROUTE
    assert "storage_path: storagePath" in INIT_ROUTE
    assert "Supabase Storage is the primary home for scene media" in STD_PAGE
    assert "storage_bucket: initPayload.storage_bucket" in STD_PAGE
    assert "storage_public_url: storagePublicUrl" in COMPLETE_ROUTE
