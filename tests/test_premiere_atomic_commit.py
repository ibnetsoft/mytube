"""The final worker must commit its asset without resending stale scene JSON."""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker"))


def _job(worker):
    payload = {
        "structure": {"scenes": [{"scene_number": 1, "ae_effect_status": "rendering"}]},
        "render_settings": {"comic": {"mode": "moving_comic"},
                            "premiere_final_asset": {"status": "retry_wait", "updated_at": "before"}},
    }
    return worker.ProjectJob("project-1", "story", {"progress_payload": {"other": True}},
                             payload, payload["structure"])


def test_premiere_commit_sends_only_final_asset_and_expected_version(monkeypatch):
    import premiere_final_worker as worker

    requests = []

    class Applied:
        def json(self):
            return {"applied": True}

    monkeypatch.setattr(worker, "_supabase", lambda: ("https://db.example", {"apikey": "test"}))
    monkeypatch.setattr(worker, "_request", lambda *args, **kwargs: requests.append((args, kwargs)) or Applied())
    asset = {"status": "ready", "updated_at": "after", "final_video": {"gcs_path": "final.mp4"}}
    worker._update_project(_job(worker), asset)

    args, kwargs = requests[0]
    assert args[0] == "POST"
    assert args[1] == "https://db.example/rest/v1/rpc/air_update_premiere_final_asset"
    assert kwargs["json"] == {
        "p_project_id": "project-1",
        "p_asset": asset,
        "p_expected_status": "retry_wait",
        "p_expected_updated_at": "before",
    }
    assert len(requests) == 1


def test_premiere_commit_rejects_concurrent_asset_change(monkeypatch):
    import premiere_final_worker as worker

    class Conflict:
        def json(self):
            return {"applied": False, "code": "asset_conflict"}

    monkeypatch.setattr(worker, "_supabase", lambda: ("https://db.example", {}))
    monkeypatch.setattr(worker, "_request", lambda *_args, **_kwargs: Conflict())
    with pytest.raises(worker.PremiereWorkerError, match="asset_conflict"):
        worker._update_project(_job(worker), {"status": "ready"})
