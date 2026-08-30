from pathlib import Path

import app.utils as utils


def test_get_project_output_dir_uses_stable_project_folder(monkeypatch, tmp_path):
    captured = {}

    monkeypatch.setattr(utils.db, "get_project", lambda project_id: {"id": project_id, "name": "My Sample Project"})
    monkeypatch.setattr(utils.db, "get_project_settings", lambda project_id: {})
    monkeypatch.setattr(utils.db, "get_tts", lambda project_id: None)
    monkeypatch.setattr(utils.db, "get_image_prompts", lambda project_id: [])
    monkeypatch.setattr(utils.db, "update_project_setting", lambda project_id, key, value: captured.update({
        "project_id": project_id,
        "key": key,
        "value": value,
    }))
    monkeypatch.setattr(utils.config, "OUTPUT_DIR", str(tmp_path), raising=False)

    abs_path, web_path = utils.get_project_output_dir(17)

    assert abs_path == str(tmp_path / "project_17_My_Sample_Project")
    assert web_path == "/output/project_17_My_Sample_Project"
    assert Path(abs_path).is_dir()
    assert captured == {
        "project_id": 17,
        "key": "output_folder_name",
        "value": "project_17_My_Sample_Project",
    }


def test_get_project_output_dir_reuses_existing_output_folder_from_saved_asset(monkeypatch, tmp_path):
    monkeypatch.setattr(utils.db, "get_project", lambda project_id: {"id": project_id, "name": "Different Name"})
    monkeypatch.setattr(utils.db, "get_project_settings", lambda project_id: {})
    monkeypatch.setattr(
        utils.db,
        "get_tts",
        lambda project_id: {"audio_path": str(tmp_path / "legacy_folder" / "tts_1.mp3")},
    )
    monkeypatch.setattr(utils.db, "get_image_prompts", lambda project_id: [])
    monkeypatch.setattr(utils.db, "update_project_setting", lambda *args, **kwargs: True)
    monkeypatch.setattr(utils.config, "OUTPUT_DIR", str(tmp_path), raising=False)

    abs_path, web_path = utils.get_project_output_dir(9)

    assert abs_path == str(tmp_path / "legacy_folder")
    assert web_path == "/output/legacy_folder"
