import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "worker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WORKER) not in sys.path:
    sys.path.insert(0, str(WORKER))


def test_generated_result_page_has_persistent_script_editor():
    source = (ROOT / "worker" / "dashboard_app.py").read_text(encoding="utf-8")

    assert '@app.patch("/api/generated-results/{result_id}/script")' in source
    assert 'id="generated-script-editor"' in source
    assert "async function saveGeneratedScript()" in source
    assert "'PATCH'," in source
    assert "await loadGeneratedResults(resultId);" in source


def test_generated_script_patch_endpoint_returns_saved_and_sync_status(monkeypatch):
    from worker import dashboard_app

    monkeypatch.setattr(
        dashboard_app,
        "_save_generated_result_script",
        lambda result_id, script: {
            "result_id": result_id,
            "topic_queue_id": "3332",
            "script": script.strip(),
            "char_count": len(script.strip()),
            "edited_at": 1.0,
            "updated_files": ["result.json"],
            "updated_jobs": [],
        },
    )
    monkeypatch.setattr(
        dashboard_app,
        "_sync_edited_script_to_supabase",
        lambda topic_queue_id, script: {"status": "synced"},
    )

    response = TestClient(dashboard_app.app).patch(
        "/api/generated-results/final-1/script",
        json={"script": "  수정한 대본  "},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["script"] == "수정한 대본"
    assert response.json()["central_sync"]["status"] == "synced"


def test_topic_script_edit_updates_result_files_and_job_payloads(monkeypatch, tmp_path):
    from worker import dashboard_app

    autopilot_dir = tmp_path / "autopilot"
    hermes_dir = tmp_path / "hermes"
    autopilot_dir.mkdir()
    hermes_dir.mkdir()
    monkeypatch.setattr(dashboard_app, "AUTOPILOT_RESULTS_DIR", autopilot_dir)
    monkeypatch.setattr(dashboard_app, "HERMES_RESULTS_DIR", hermes_dir)

    result_path = hermes_dir / "script-job.json"
    result_path.write_text(
        json.dumps(
            {
                "job_type": "script_generate",
                "topic_queue_id": "3332",
                "status": "COMPLETED",
                "script": "예전 대본",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    jobs = [
        {
            "job_id": "metadata-job",
            "job_type": "publish_metadata_generate",
            "source": "autopilot",
            "status": "COMPLETED",
            "payload": {"topic_queue_id": "3332", "script": "예전 대본"},
        }
    ]
    updated_payloads = {}
    monkeypatch.setattr(dashboard_app.job_store, "list_jobs", lambda limit=5000: jobs)
    monkeypatch.setattr(
        dashboard_app.job_store,
        "update_job_payload",
        lambda job_id, payload: updated_payloads.__setitem__(job_id, payload),
    )

    saved = dashboard_app._save_generated_result_script("topic_3332", "육십몇만 원을 받았습니다.")

    persisted = json.loads(result_path.read_text(encoding="utf-8"))
    assert persisted["script"] == "육십몇만 원을 받았습니다."
    assert persisted["char_count"] == len(persisted["script"])
    assert persisted["manually_edited_source"] == "worker_dashboard"
    assert updated_payloads["metadata-job"]["script"] == persisted["script"]
    assert saved["char_count"] == len(persisted["script"])


def test_final_script_edit_survives_reloading_the_result_file(monkeypatch, tmp_path):
    from worker import dashboard_app

    autopilot_dir = tmp_path / "autopilot"
    hermes_dir = tmp_path / "hermes"
    autopilot_dir.mkdir()
    hermes_dir.mkdir()
    monkeypatch.setattr(dashboard_app, "AUTOPILOT_RESULTS_DIR", autopilot_dir)
    monkeypatch.setattr(dashboard_app, "HERMES_RESULTS_DIR", hermes_dir)
    monkeypatch.setattr(dashboard_app.job_store, "list_jobs", lambda limit=5000: [])

    result_path = autopilot_dir / "final-1.json"
    result_path.write_text(
        json.dumps(
            {
                "topic_queue_id": "local-auto-1",
                "script": "수정 전",
                "char_count": 4,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    dashboard_app._save_generated_result_script("final-1", "수정 후 대본")

    reloaded = dashboard_app._read_generated_result(result_path)
    assert reloaded["script"] == "수정 후 대본"
    assert reloaded["char_count"] == len("수정 후 대본")
