from pathlib import Path


STD_PAGE = Path("auth-web/app/std/page.tsx").read_text(encoding="utf-8")
COMPLETE_ROUTE = Path(
    "auth-web/app/api/std/projects/[projectId]/assets/complete/route.ts"
).read_text(encoding="utf-8")


def _upload_asset_body() -> str:
    return STD_PAGE.split("const uploadAsset = async", 1)[1].split(
        "const saveAssetToLocalDirectory = async", 1
    )[0]


def test_scene_assets_upload_directly_to_drive_before_completion():
    upload_asset = _upload_asset_body()

    init_pos = upload_asset.index("'/assets/init'")
    drive_pos = upload_asset.index("fetch(initPayload.upload_url")
    complete_pos = upload_asset.index("'/assets/complete'")

    assert init_pos < drive_pos < complete_pos
    assert "method: 'PUT'" in upload_asset
    assert "body: file" in upload_asset
    assert "drive_file_id: drivePayload.id" in upload_asset
    assert "'/assets/upload'" not in upload_asset


def test_scene_is_not_marked_ready_before_server_confirmation():
    upload_asset = _upload_asset_body()
    optimistic_section = upload_asset.split("const initRes = await fetch", 1)[0]
    confirmed_section = upload_asset.split("const persistedAsset = completePayload.asset", 1)[1]

    assert "video_url: actualAssetType === 'video' ? objectUrl" not in optimistic_section
    assert "image_url: actualAssetType === 'image' ? objectUrl" not in optimistic_section
    assert "video_url: actualAssetType === 'video' ? persistedUrl" in confirmed_section
    assert "asset_status: 'ready'" in confirmed_section


def test_drive_completion_is_idempotent_and_checks_project_persistence():
    assert ".eq('drive_file_id', metadata.id)" in COMPLETE_ROUTE
    assert "let asset = existingAsset" in COMPLETE_ROUTE
    assert "if (!asset)" in COMPLETE_ROUTE
    assert "upload_mode: 'browser_drive_resumable'" in COMPLETE_ROUTE
    assert "if (projectUpdateError)" in COMPLETE_ROUTE
