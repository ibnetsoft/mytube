from pathlib import Path


STD_PAGE = Path("auth-web/app/std/page.tsx").read_text(encoding="utf-8")


def test_std_asset_upload_keeps_successful_local_file_when_drive_sync_fails():
    assert "Promise<'synced' | 'local' | false>" in STD_PAGE
    assert "if (objectUrl && localRelativePath)" in STD_PAGE
    assert "status: 'local'" in STD_PAGE
    assert "local_storage_mode: 'browser_directory'" in STD_PAGE
    assert "return 'local'" in STD_PAGE
    assert "URL.revokeObjectURL(objectUrl)" in STD_PAGE


def test_std_bulk_upload_reports_remote_and_local_results_separately():
    assert "let syncedCount = 0" in STD_PAGE
    assert "let localOnlyCount = 0" in STD_PAGE
    assert "if (result === 'synced') syncedCount += 1" in STD_PAGE
    assert "if (result === 'local') localOnlyCount += 1" in STD_PAGE
    assert "Drive ${syncedCount}개, 로컬만 ${localOnlyCount}개, 실패 ${failedCount}개입니다." in STD_PAGE
