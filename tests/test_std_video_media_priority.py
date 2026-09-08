from pathlib import Path


STD_PAGE = Path("auth-web/app/std/page.tsx").read_text(encoding="utf-8")
INIT_ROUTE = Path("auth-web/app/api/std/projects/[projectId]/assets/init/route.ts").read_text(encoding="utf-8")
COMPLETE_ROUTE = Path("auth-web/app/api/std/projects/[projectId]/assets/complete/route.ts").read_text(encoding="utf-8")
ASSET_FILE_ROUTE = Path("auth-web/app/api/std/projects/[projectId]/assets/file/route.ts").read_text(encoding="utf-8")
POLICY = Path("auth-web/lib/stdPolicy.ts").read_text(encoding="utf-8")
MEDIA_MIGRATION = Path("migrations/air_0246_std_supabase_primary_media.sql").read_text(encoding="utf-8")


def test_hook_scenes_remain_video_scenes():
    assert "export const STD_VIDEO_REQUIRED_UNTIL_SEC = 60" in POLICY
    assert "STD_REQUIRED_VIDEO_SCENE_COUNT" in POLICY


def test_existing_video_assets_are_preferred_over_scene_images():
    assert "const sceneId = String(scene?.id || scene?.metadata?.scene_id || '').trim()" in STD_PAGE
    assert "String(asset?.scene_id || '').trim() === sceneId" in STD_PAGE
    assert "const driveFileIdFromUrl" in STD_PAGE
    assert "const sceneVideoDriveProxy = projectAssetFileUrl" in STD_PAGE
    assert "const videoAsset = (assets || []).find" in STD_PAGE
    assert "const videoUrl = projectAssetFileUrl(projectId, videoAsset)" in STD_PAGE
    assert "if (isProjectAssetFileUrl(str)) return str" in STD_PAGE
    assert "video_url: restoredVideoUrl || runtimeAssetUrl(scene.video_url) || null" in STD_PAGE


def test_project_asset_stream_uses_drive_when_storage_copy_was_pruned():
    assert "const storagePath = String(asset?.metadata?.storage_path" in ASSET_FILE_ROUTE
    assert ".storage.from(storageBucket).download(storagePath)" in ASSET_FILE_ROUTE
    assert "Storage download failed; trying Drive" in ASSET_FILE_ROUTE
    assert "downloadStdDriveFile(targetDriveFileId)" in ASSET_FILE_ROUTE
    assert "X-STD-Media-Source" in ASSET_FILE_ROUTE
    assert "const imageUrl = projectAssetFileUrl(projectId, imageAsset)" in STD_PAGE


def test_new_visual_uploads_are_saved_to_supabase_then_drive():
    assert "createSignedUploadUrl(storagePath" in INIT_ROUTE
    assert "storage_upload_url: signedUpload.signedUrl" in INIT_ROUTE
    assert "storage_path: storagePath" in INIT_ROUTE
    assert "Scene media is retained in both Supabase Storage and Google Drive" in STD_PAGE
    assert "Google Drive에도 저장 중" in STD_PAGE
    assert "storage_bucket: initPayload.storage_bucket" in STD_PAGE
    assert "drive_file_id: drivePayload.id" in STD_PAGE
    assert "storage_public_url: storagePublicUrl" in COMPLETE_ROUTE
    assert "browser_supabase_then_drive" in COMPLETE_ROUTE
    assert "ALTER COLUMN drive_file_id DROP NOT NULL" in MEDIA_MIGRATION
