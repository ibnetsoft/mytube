from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STD_DRIVE = (ROOT / "auth-web" / "lib" / "stdGoogleDrive.ts").read_text(encoding="utf-8")
STD_RENDER_QUEUE = (ROOT / "auth-web" / "lib" / "stdRenderQueue.ts").read_text(encoding="utf-8")
REMOTE_DRIVE_WORKER = (ROOT / "remote_drive_worker.py").read_text(encoding="utf-8")


def test_std_render_submission_keeps_project_files_in_one_drive_folder():
    assert "const folders = await ensureStdProjectDriveFolders(project)" in STD_RENDER_QUEUE
    assert "upsertStdDriveJsonFile(folders.projectFolderId, 'script.json'" in STD_RENDER_QUEUE
    assert "'publish_metadata.json'" in STD_RENDER_QUEUE
    assert "upsertStdDriveJsonFile(folders.projectFolderId, 'config.json', renderConfig)" in STD_RENDER_QUEUE
    assert "drive_folder_id: folders.projectFolderId" in STD_RENDER_QUEUE
    assert "script_file_id: scriptFile.id" in STD_RENDER_QUEUE
    assert "publish_metadata_file_id: publishMetadataFile.id" in STD_RENDER_QUEUE


def test_drive_json_sidecars_are_upserted_not_duplicated_on_rerender():
    assert "export async function upsertStdDriveJsonFile" in STD_DRIVE
    assert "const existingFileId = await findFile(folderId, safeName, 'application/json')" in STD_DRIVE
    assert "method: 'PATCH'" in STD_DRIVE
    assert "drive_manifest_update_failed" in STD_DRIVE


def test_remote_render_outputs_use_manifest_project_folder_first():
    assert "manifest_folder_id = (metadata.get(\"drive_folder_id\")" in REMOTE_DRIVE_WORKER
    assert "google_drive_service.get_file_metadata(" in REMOTE_DRIVE_WORKER
    assert "return {\"id\": folder_meta.get(\"id\"), \"name\": folder_meta.get(\"name\") or \"std-project\"}" in REMOTE_DRIVE_WORKER
    assert "result_folder = self._resolve_result_folder(job)" in REMOTE_DRIVE_WORKER
    assert "folder_id=result_folder.get(\"id\")" in REMOTE_DRIVE_WORKER

