"""HTTP boundary for previewing and approving rendered manga AE scenes."""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "worker"))
from worker import codex_local_console as console
import ae_highlight_worker as ae
import worker_config


def _video(path: pathlib.Path) -> None:
    import imageio_ffmpeg

    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=s=640x360:r=24", "-t", "1.5",
                    "-c:v", "mpeg4", "-q:v", "5", str(path)],
                   check=True, capture_output=True, timeout=90)


@pytest.fixture
def review_api(monkeypatch, tmp_path):
    media_root = tmp_path / "ae_highlight"
    media_root.mkdir()
    clip = media_root / "scene.mp4"
    _video(clip)
    digest = hashlib.sha256(clip.read_bytes()).hexdigest()
    scene = {
        "scene_number": 1,
        "ae_effect_plan": {"enabled": True, "template": "ink_splat_impact"},
        "ae_effect_status": "review_pending",
        "metadata": {"ae_effect_asset": {
            "status": "review_pending", "storage_provider": "local",
            "review_local_path": str(clip), "local_path": str(clip),
            "render_sha256": digest,
            "manga_qa": {"plan": {"passed": True}, "render": {"passed": True}},
        }},
    }
    rows = {
        "std_projects": {"project-1": {"id": "project-1", "project_payload": {"structure": {"scenes": [scene]}}}},
        "topics_queue": {"topic-1": {"id": "topic-1", "pregenerated_structure": {"scenes": [scene]}}},
    }
    calls = []
    hooks = {"before_rpc": None}

    class Response:
        def __init__(self, data):
            self.data = data

        def json(self):
            return json.loads(json.dumps(self.data))

    def request(method, url, headers, **kwargs):
        table = "std_projects" if "/std_projects" in url else "topics_queue"
        identity = kwargs.get("params", {}).get("id", "").removeprefix("eq.")
        calls.append((method, table, identity, kwargs))
        if method == "GET":
            row = rows[table].get(identity)
            return Response([row] if row else [])
        assert method == "POST" and "/rpc/air_update_ae_scene" in url
        args = kwargs["json"]
        callback = hooks["before_rpc"]
        if callback:
            callback(rows)
        source = "std_projects" if args["p_source_type"] == "project" else "topics_queue"
        key = "project_payload" if source == "std_projects" else "pregenerated_structure"
        parent = rows[source][args["p_identity"]][key]
        structure = parent["structure"] if source == "std_projects" else parent
        selected = next(scene for scene in structure["scenes"] if scene["scene_number"] == args["p_scene_number"])
        asset = selected["metadata"]["ae_effect_asset"]
        if asset["status"] != "review_pending" or asset["render_sha256"] != args["p_expected_sha256"]:
            return Response({"applied": False, "code": "review_conflict"})
        status = "ready" if args["p_review_decision"] == "approved" else "needs_attention"
        asset["status"] = status
        asset["visual_review"] = {"decision": args["p_review_decision"],
                                  "reviewer": args["p_reviewer"], "note": args["p_note"],
                                  "render_sha256": args["p_expected_sha256"]}
        selected["ae_effect_status"] = status
        selected["asset_status"] = status
        if status == "ready" and asset.get("media_url"):
            selected["ae_video_url"] = selected["video_url"] = asset["media_url"]
        elif status == "needs_attention":
            selected.pop("ae_video_url", None)
            if selected.get("video_url") == asset.get("media_url"):
                selected.pop("video_url", None)
        return Response({"applied": True, "status": status, "scene": selected})

    monkeypatch.setattr(worker_config, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(ae, "_supabase", lambda: ("https://db.invalid", {"apikey": "test"}))
    monkeypatch.setattr(ae, "_request", request)
    client = TestClient(console.app, base_url=console.ORIGIN,
                        headers={"X-Codex-Local": console.TOKEN})
    return client, rows, calls, clip, digest, hooks


def _request(source_type="project", identity="project-1", digest="", decision="approved"):
    return {"source_type": source_type, "identity": identity, "scene_number": 1,
            "decision": decision, "reviewer": "편집자", "note": "인물·글자·타격 시점을 확인했습니다.",
            "render_sha256": digest}


def test_review_media_requires_local_token_and_valid_local_mp4(review_api):
    client, rows, calls, clip, digest, hooks = review_api
    path = "/api/ae-highlight/review-media/project/project-1/1"
    assert client.get(path, headers={"X-Codex-Local": ""}).status_code == 401
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.content == clip.read_bytes()

    outside = clip.parent.parent / "outside.mp4"
    outside.write_bytes(clip.read_bytes())
    rows["std_projects"]["project-1"]["project_payload"]["structure"]["scenes"][0]["metadata"]["ae_effect_asset"]["review_local_path"] = str(outside)
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("source_type,identity,table,column", [
    ("project", "project-1", "std_projects", "project_payload"),
    ("topic", "topic-1", "topics_queue", "pregenerated_structure"),
])
def test_review_approval_patches_only_selected_row_and_unblocks_scene(
    review_api, source_type, identity, table, column,
):
    client, rows, calls, clip, digest, hooks = review_api
    response = client.post("/api/ae-highlight/review", json=_request(source_type, identity, digest))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ready"
    rpc = [call for call in calls if call[0] == "POST"]
    assert len(rpc) == 1
    assert rpc[0][3]["json"]["p_operation"] == "review"
    assert rpc[0][3]["json"]["p_identity"] == identity
    assert rpc[0][3]["json"]["p_expected_sha256"] == digest
    structure = (rows[table][identity][column]["structure"] if source_type == "project"
                 else rows[table][identity][column])
    asset = structure["scenes"][0]["metadata"]["ae_effect_asset"]
    assert asset["status"] == "ready"
    assert asset["visual_review"]["render_sha256"] == digest
    assert structure["scenes"][0]["ae_effect_status"] == "ready"
    assert client.post("/api/ae-highlight/review", json=_request(source_type, identity, digest)).status_code == 409
    assert len([call for call in calls if call[0] == "POST"]) == 1


def test_review_rejection_and_changed_media_never_approve(review_api):
    client, rows, calls, clip, digest, hooks = review_api
    wrong = client.post("/api/ae-highlight/review", json=_request(digest="0" * 64))
    assert wrong.status_code == 409
    assert not any(method == "POST" for method, *_ in calls)

    clip.write_bytes(clip.read_bytes() + b"changed")
    changed = client.post("/api/ae-highlight/review", json=_request(digest=digest))
    assert changed.status_code == 409
    assert not any(method == "POST" for method, *_ in calls)

    clip.write_bytes(clip.read_bytes()[:-7])
    rejected = client.post("/api/ae-highlight/review", json=_request(digest=digest, decision="rejected"))
    assert rejected.status_code == 200
    scene = rows["std_projects"]["project-1"]["project_payload"]["structure"]["scenes"][0]
    assert scene["ae_effect_status"] == "needs_attention"
    assert scene["metadata"]["ae_effect_asset"]["visual_review"]["decision"] == "rejected"


def test_review_rejects_cross_origin_bad_identity_and_missing_note(review_api):
    client, rows, calls, clip, digest, hooks = review_api
    payload = _request(digest=digest)
    assert client.post("/api/ae-highlight/review", json=payload,
                       headers={"Origin": "https://evil.invalid"}).status_code == 403
    assert client.post("/api/ae-highlight/review", json={**payload, "identity": "bad.id"}).status_code == 409
    assert client.post("/api/ae-highlight/review", json={**payload, "note": ""}).status_code == 422
    assert client.post("/api/ae-highlight/review", json={**payload, "render_sha256": "invalid"}).status_code == 409
    assert not any(method == "POST" for method, *_ in calls)


def test_review_rejects_mismatched_database_row(review_api, monkeypatch):
    client, rows, calls, clip, digest, hooks = review_api

    class WrongRow:
        def json(self):
            return [rows["std_projects"]["project-1"] | {"id": "different-project"}]

    monkeypatch.setattr(ae, "_request", lambda *args, **kwargs: WrongRow())
    response = client.post("/api/ae-highlight/review", json=_request(digest=digest))
    assert response.status_code == 409
    assert "identity changed" in response.json()["detail"]


def test_review_rpc_preserves_concurrent_unrelated_scene_change(review_api):
    client, rows, calls, clip, digest, hooks = review_api
    structure = rows["std_projects"]["project-1"]["project_payload"]["structure"]
    structure["scenes"].append({"scene_number": 2, "metadata": {"ae_effect_asset": {"status": "rendering"}}})
    hooks["before_rpc"] = lambda current: current["std_projects"]["project-1"]["project_payload"]["structure"]["scenes"][1]["metadata"]["ae_effect_asset"].update(status="ready")
    response = client.post("/api/ae-highlight/review", json=_request(digest=digest))
    assert response.status_code == 200, response.text
    assert structure["scenes"][0]["ae_effect_status"] == "ready"
    assert structure["scenes"][1]["metadata"]["ae_effect_asset"]["status"] == "ready"


def test_review_rpc_rechecks_status_after_local_hash_verification(review_api):
    client, rows, calls, clip, digest, hooks = review_api
    hooks["before_rpc"] = lambda current: current["std_projects"]["project-1"]["project_payload"]["structure"]["scenes"][0]["metadata"]["ae_effect_asset"].update(status="ready")
    response = client.post("/api/ae-highlight/review", json=_request(digest=digest))
    assert response.status_code == 409
    assert "review_conflict" in response.json()["detail"]


def test_gcs_scene_url_is_published_only_by_review_approval(review_api):
    client, rows, calls, clip, digest, hooks = review_api
    scene = rows["std_projects"]["project-1"]["project_payload"]["structure"]["scenes"][0]
    scene["metadata"]["ae_effect_asset"]["media_url"] = "/api/std/assets/gcs-file?bucket=b&path=reviewed.mp4"
    assert "ae_video_url" not in scene and "video_url" not in scene
    response = client.post("/api/ae-highlight/review", json=_request(digest=digest))
    assert response.status_code == 200
    assert scene["ae_video_url"] == scene["metadata"]["ae_effect_asset"]["media_url"]
    assert scene["video_url"] == scene["ae_video_url"]


def test_ae_worker_patches_only_selected_manga_scene_via_rpc(monkeypatch):
    scene = {"scene_number": 1, "ae_effect_plan": {"enabled": True, "template": "body_following_qi"},
             "metadata": {"psd_layer_asset": {"qa_status": "approved", "gcs_path": "scene.psd"},
                          "ae_effect_asset": {"status": "rendering", "started_at": "t1"}}}
    other = {"scene_number": 2, "metadata": {"newer_image": "keep"}}
    structure = {"scenes": [scene, other]}
    job = ae.SceneJob(topic_id="project-1", topic_title="test", structure=structure,
                      scene_index=0, scene=scene, scene_number=1, plan_kind="effect",
                      preset="wuxia_body_qi", duration_seconds=4,
                      source=ae.GcsRef("bucket", "scene.psd"), source_type="project",
                      project_payload={"structure": structure})
    calls = []

    class Response:
        def __init__(self, value):
            self.value = value

        def json(self):
            return self.value

    monkeypatch.setattr(ae, "_supabase", lambda: ("https://db.invalid", {"apikey": "test"}))

    def request(method, url, headers, **kwargs):
        calls.append((method, url, kwargs))
        newer = {**scene, "metadata": {**scene["metadata"], "newer_image": "keep",
                                       "ae_effect_asset": {"status": "review_pending", "started_at": "t1"}}}
        return Response({"applied": True, "status": "review_pending", "scene": newer})

    monkeypatch.setattr(ae, "_request", request)
    ae._patch_job_structure(job, expected_status="rendering", expected_started_at="t1",
                            asset_patch={"render_sha256": "a" * 64}, next_status="review_pending")
    assert len(calls) == 1
    assert calls[0][0] == "POST" and "/rpc/air_update_ae_scene" in calls[0][1]
    assert calls[0][2]["json"]["p_expected_started_at"] == "t1"
    assert structure["scenes"][0]["metadata"]["newer_image"] == "keep"
    assert structure["scenes"][1] is other

    monkeypatch.setattr(ae, "_request", lambda *args, **kwargs: Response({"applied": False, "code": "worker_conflict"}))
    with pytest.raises(ae.AeSceneConflict, match="worker_conflict"):
        ae._patch_job_structure(job, expected_status="rendering", next_status="review_pending")


@pytest.mark.parametrize("plan_kind,plan_key,asset_key", [
    ("effect", "ae_effect_plan", "ae_effect_asset"),
    ("motion", "ae_motion_plan", "ae_motion_asset"),
])
def test_ordinary_ae_jobs_use_atomic_scene_rpc_too(monkeypatch, plan_kind, plan_key, asset_key):
    scene = {"scene_number": 1, plan_key: {"enabled": True},
             "metadata": {asset_key: {"status": "rendering", "started_at": "t1"}}}
    structure = {"scenes": [scene, {"scene_number": 2, "scene_text": "newer scene"}]}
    job = ae.SceneJob(topic_id="project-1", topic_title="test", structure=structure,
                      scene_index=0, scene=scene, scene_number=1, plan_kind=plan_kind,
                      preset="preset", duration_seconds=4, source=ae.GcsRef("bucket", "scene.png"),
                      source_type="project", project_payload={"structure": structure})
    requests = []

    class Response:
        def json(self):
            return {"applied": True, "status": "ready", "scene": json.loads(json.dumps(scene))}

    monkeypatch.setattr(ae, "_supabase", lambda: ("https://db.invalid", {"apikey": "test"}))
    monkeypatch.setattr(ae, "_request", lambda *args, **kwargs: requests.append((args, kwargs)) or Response())
    ae._patch_job_structure(job, expected_status="rendering", expected_started_at="t1",
                            asset_patch={"media_url": "/scene.mp4"},
                            next_status="ready", media_url="/scene.mp4")
    assert len(requests) == 1
    assert requests[0][0][0] == "POST"
    assert requests[0][1]["json"]["p_plan_kind"] == plan_kind
    assert requests[0][1]["json"]["p_next_status"] == "ready"
    assert structure["scenes"][1]["scene_text"] == "newer scene"


def test_manga_ae_queue_waits_for_approved_psd():
    scene = {"scene_number": 1, "image_url": "/api/std/assets/gcs-file?bucket=b&path=preview.png",
             "ae_effect_plan": {"enabled": True, "template": "ink_splat_impact",
                                "preset": "comic_ink_splat_impact", "duration_seconds": 4}}
    row = {"id": "project-1", "title": "test", "__source_type": "project",
           "project_payload": {"structure": {"scenes": [scene]}}}
    assert ae._find_scene_jobs([row]) == []
    scene["metadata"] = {"psd_layer_asset": {"qa_status": "approved", "gcs_path": "approved.psd", "gcs_bucket": "b"}}
    jobs = ae._find_scene_jobs([row])
    assert len(jobs) == 1
    assert jobs[0].source.path == "approved.psd"


def test_manga_render_does_not_publish_gcs_url_before_review(monkeypatch, tmp_path):
    scene = {"scene_number": 1, "ae_effect_plan": {"enabled": True, "template": "ink_splat_impact"},
             "metadata": {"ae_effect_asset": {}}}
    structure = {"scenes": [scene]}
    job = ae.SceneJob(topic_id="project-1", topic_title="test", structure=structure,
                      scene_index=0, scene=scene, scene_number=1, plan_kind="effect",
                      preset="comic_ink_splat_impact", duration_seconds=4,
                      source=ae.GcsRef("bucket", "scene.psd"), source_type="project",
                      project_payload={"structure": structure})
    captured = []

    def mark(job, status, **kwargs):
        scene["metadata"]["ae_effect_asset"] = {"status": status, "started_at": "claim-t1"}

    monkeypatch.setattr(ae, "_mark_scene", mark)
    monkeypatch.setattr(ae, "_render_job", lambda *args, **kwargs: {
        "review_required": True, "media_url": "/api/std/assets/gcs-file?bucket=b&path=scene.mp4",
        "render_sha256": "a" * 64,
    })
    monkeypatch.setattr(ae, "_patch_job_structure", lambda *args, **kwargs: captured.append(kwargs))
    monkeypatch.setattr(ae, "write_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(ae, "WORKER_STATE_FILE", tmp_path / "state.json")
    ae.process_job(job)
    assert captured[0]["next_status"] == "review_pending"
    assert captured[0]["media_url"] is None
    assert captured[0]["clear_media_url"] is True
    assert captured[0]["expected_started_at"] == "claim-t1"
    assert "ae_video_url" not in scene and "video_url" not in scene


def test_manga_claim_clears_older_public_review_url(monkeypatch):
    scene = {"scene_number": 1, "ae_effect_plan": {"enabled": True, "template": "ink_splat_impact"},
             "video_url": "/old.mp4", "ae_video_url": "/old.mp4",
             "metadata": {"ae_effect_asset": {"status": "ready", "media_url": "/old.mp4",
                                               "visual_review": {"decision": "approved"}}}}
    structure = {"scenes": [scene]}
    job = ae.SceneJob(topic_id="project-1", topic_title="test", structure=structure,
                      scene_index=0, scene=scene, scene_number=1, plan_kind="effect",
                      preset="comic_ink_splat_impact", duration_seconds=4,
                      source=ae.GcsRef("bucket", "scene.psd"), source_type="project",
                      project_payload={"structure": structure})
    calls = []
    monkeypatch.setattr(ae, "_patch_job_structure", lambda *args, **kwargs: calls.append(kwargs))
    ae._mark_scene(job, "rendering", started_at="new-claim")
    assert calls[0]["expected_status"] == "ready"
    assert calls[0]["clear_media_url"] is True
    assert calls[0]["asset_patch"]["started_at"] == "new-claim"


def test_migration_uses_row_lock_and_service_role_only():
    sql = (ROOT / "supabase/migrations/20260926121548_atomic_manga_ae_scene.sql").read_text(encoding="utf-8")
    assert "function public.air_update_ae_scene" in sql
    assert "security invoker" in sql
    assert sql.count("for update") == 2
    assert "array['scenes', v_index::text]" in sql
    assert "'ae_motion_asset'" in sql and "'ae_motion_plan'" in sql
    assert "'review_pending'" in sql and "'review_conflict'" in sql
    assert "p_media_url is not null" in sql and "p_review_decision = 'approved'" in sql
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql
    assert "pg_catalog.coalesce" not in sql and "pg_catalog.nullif" not in sql
