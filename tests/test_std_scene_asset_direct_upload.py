from pathlib import Path


STD_PAGE = Path("auth-web/app/std/page.tsx").read_text(encoding="utf-8")
COMPLETE_ROUTE = Path(
    "auth-web/app/api/std/projects/[projectId]/assets/complete/route.ts"
).read_text(encoding="utf-8")
INIT_ROUTE = Path(
    "auth-web/app/api/std/projects/[projectId]/assets/init/route.ts"
).read_text(encoding="utf-8")
SERVER_UPLOAD_ROUTE = Path(
    "auth-web/app/api/std/projects/[projectId]/assets/upload/route.ts"
).read_text(encoding="utf-8")


def _upload_asset_body() -> str:
    return STD_PAGE.split("const uploadAsset = async", 1)[1].split(
        "const saveAssetToLocalDirectory = async", 1
    )[0]


def test_scene_assets_are_uploaded_to_storage_before_completion():
    upload_asset = _upload_asset_body()

    init_pos = upload_asset.index("'/assets/init'")
    storage_pos = upload_asset.index("fetch(initPayload.storage_upload_url")
    complete_pos = upload_asset.index("'/assets/complete'")

    assert init_pos < storage_pos < complete_pos
    assert "method: 'PUT'" in upload_asset
    assert "body: file" in upload_asset
    assert "storage_bucket: initPayload.storage_bucket" in upload_asset
    assert "storage_path: initPayload.storage_path" in upload_asset
    assert "drive_file_id: drivePayload?.id || null" in upload_asset
    assert "keeping Supabase asset" in upload_asset


def test_scene_is_not_marked_ready_before_server_confirmation():
    upload_asset = _upload_asset_body()
    optimistic_section = upload_asset.split("const initRes = await fetch", 1)[0]
    confirmed_section = upload_asset.split("persistedAsset = completePayload.asset", 1)[1]

    assert "video_url: actualAssetType === 'video' ? objectUrl" not in optimistic_section
    assert "image_url: actualAssetType === 'image' ? objectUrl" not in optimistic_section
    assert "const persistedUrl = assetDisplayUrl(selectedProject.project.id, persistedAsset) || objectUrl" in confirmed_section
    assert "video_url: actualAssetType === 'video' ? persistedUrl" in confirmed_section
    assert "asset_status: 'ready'" in confirmed_section


def test_dual_store_completion_is_idempotent_and_checks_project_persistence():
    assert ".eq('drive_file_id', metadata?.id || '')" in COMPLETE_ROUTE
    assert "let asset = existingAsset" in COMPLETE_ROUTE
    assert "if (!asset)" in COMPLETE_ROUTE
    assert "browser_supabase_then_drive" in COMPLETE_ROUTE
    assert "storage_public_url: storagePublicUrl" in COMPLETE_ROUTE
    assert "if (projectUpdateError)" in COMPLETE_ROUTE


def test_drive_archive_failure_does_not_block_a_storage_upload():
    assert "resumable Drive URL to the browser causes a CORS-blocked PUT" in INIT_ROUTE
    assert "upload_url: ''" in INIT_ROUTE
    assert "storage_upload_url: signedUpload.signedUrl" in INIT_ROUTE
    assert "Drive archive copy failed; keeping Supabase asset" in SERVER_UPLOAD_ROUTE
    assert ".upload(storagePath, buffer" in SERVER_UPLOAD_ROUTE
    assert "drive_file_id: driveFile?.id || null" in SERVER_UPLOAD_ROUTE
    assert "server_supabase_storage" in SERVER_UPLOAD_ROUTE
    assert "archiveSupabaseAssetToDrive" in COMPLETE_ROUTE
    assert "browser_supabase_then_server_drive" in COMPLETE_ROUTE


def test_thumbnail_upload_uses_the_same_supabase_first_flow():
    thumbnail_upload = STD_PAGE.split("const uploadThumbnailBgToDrive = async", 1)[1].split(
        "const markThumbnailConfirmed", 1
    )[0]

    assert "initPayload.storage_upload_url" in thumbnail_upload
    assert "storageRes = await fetch(initPayload.storage_upload_url" in thumbnail_upload
    assert "storage_bucket: initPayload.storage_bucket" in thumbnail_upload
    assert "drive_file_id: drivePayload?.id || null" in thumbnail_upload
    assert "keeping Supabase asset" in thumbnail_upload
