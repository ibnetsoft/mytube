import json
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKER = ROOT / "worker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WORKER) not in sys.path:
    sys.path.insert(0, str(WORKER))

from worker import hermes_worker, render_worker


def test_hermes_state_file_omits_large_current_job_payload(tmp_path, monkeypatch):
    state_file = tmp_path / "hermes_worker.json"
    monkeypatch.setattr(hermes_worker, "STATE_FILE", state_file)

    hermes_worker.write_state(
        "running",
        {
            "job_id": "job-1",
            "job_type": "script_generate",
            "source": "autopilot",
            "status": "CLAIMED",
            "payload": {"upload_title": "큰 대본", "structure": {"scenes": [{"x": "y"}] * 300}},
        },
        progress=25,
        job_id="job-1",
    )

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["current_job"]["job_id"] == "job-1"
    assert state["current_job"]["project_name"] == "큰 대본"
    assert "payload" not in state["current_job"]


def test_render_state_file_omits_large_current_job_payload(tmp_path, monkeypatch):
    state_file = tmp_path / "render_worker.json"
    monkeypatch.setattr(render_worker, "STATE_FILE", state_file)

    render_worker.write_state(
        "running",
        {
            "job_id": "render-1",
            "job_type": "render_video",
            "source": "local",
            "payload": {"project_name": "렌더 작업", "frames": list(range(500))},
        },
        progress=40,
        job_id="render-1",
    )

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["current_job"]["job_id"] == "render-1"
    assert state["current_job"]["project_name"] == "렌더 작업"
    assert "payload" not in state["current_job"]
