"""Local AE-to-Premiere media survives worker restarts without a GCS round trip."""
from __future__ import annotations

import pathlib
import subprocess
import sys
from dataclasses import replace

import pytest
import imageio_ffmpeg

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker"))


def test_mp4_probe_rejects_truncated_timeline(tmp_path):
    from media_checkpoint import valid_mp4

    complete = tmp_path / "complete.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i",
                    "color=c=black:s=64x64:r=24", "-t", "2", "-c:v", "libx264",
                    "-movflags", "+faststart", str(complete)],
                   capture_output=True, check=True, timeout=60)
    truncated = tmp_path / "truncated.mp4"
    data = complete.read_bytes()
    truncated.write_bytes(data[:int(len(data) * 0.65)])
    assert valid_mp4(complete, 1.5)
    assert not valid_mp4(truncated, 1.5)


def test_project_ae_render_stays_local_and_resumes(monkeypatch, tmp_path):
    import ae_highlight_worker as ae
    import media_checkpoint

    monkeypatch.setattr(ae.worker_config, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(ae, "write_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(media_checkpoint, "valid_mp4", lambda path, *_args: path.is_file())
    monkeypatch.setattr(ae, "valid_mp4", lambda path, *_args: path.is_file())
    monkeypatch.delenv("AE_SCENE_DELIVERY", raising=False)
    executable = tmp_path / "adobe.exe"
    executable.write_bytes(b"app")
    monkeypatch.setattr(ae, "find_afterfx", lambda: executable)
    monkeypatch.setattr(ae, "find_aerender", lambda: executable)
    calls = {"download": 0, "project": 0, "render": 0, "upload": 0}

    def download(_ref, target):
        calls["download"] += 1
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"i" * 2048)

    def project(_app, _script, target, **_kwargs):
        calls["project"] += 1
        target.write_bytes(b"p" * 2048)

    def render(command, **_kwargs):
        calls["render"] += 1
        pathlib.Path(command[-1]).write_bytes(b"v" * 2048)

    monkeypatch.setattr(ae, "_download_gcs_file", download)
    monkeypatch.setattr(ae, "_run_afterfx_script", project)
    monkeypatch.setattr(ae, "_run_checked", render)
    def upload(_path, object_path, _mime):
        calls["upload"] += 1
        return "bucket", object_path, "gs://bucket/" + object_path

    monkeypatch.setattr(ae, "_upload_gcs_file", upload)
    scene = {"ae_motion_plan": {"enabled": True, "preset": "subtle_motion"}}
    job = ae.SceneJob("project", "wuxia", {"scenes": [scene]}, 0, scene, 1,
                      "motion", "subtle_motion", 2.0, ae.GcsRef("bucket", "scene.png"),
                      source_type="project")
    first = ae._render_job(job)
    second = ae._render_job(job)
    assert first["storage_provider"] == "local" and first["media_url"] == ""
    assert pathlib.Path(first["local_path"]).is_file()
    assert second["local_path"] == first["local_path"]
    assert calls == {"download": 1, "project": 1, "render": 1, "upload": 0}
    cloud = ae._render_job(replace(job, project_payload={"ae_scene_delivery": "gcs"}))
    assert cloud["storage_provider"] == "gcs" and cloud["media_url"].startswith("gs://")
    assert calls == {"download": 1, "project": 1, "render": 1, "upload": 1}
    scene["image_url"] = "/api/std/assets/gcs-file?bucket=bucket&path=scene.png"
    scene["metadata"] = {"ae_motion_asset": {**first, "status": "ready"}}
    row = {"id": "project", "__source_type": "project", "project_payload": {"structure": job.structure}}
    assert ae._find_scene_jobs([row]) == []
    pathlib.Path(first["local_path"]).unlink()
    assert len(ae._find_scene_jobs([row])) == 1


def test_topic_delivery_choice_overrides_host_default_and_requeues_changed_mode(monkeypatch, tmp_path):
    import ae_highlight_worker as ae
    import media_checkpoint

    monkeypatch.setattr(ae.worker_config, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(media_checkpoint, "valid_mp4", lambda path, *_args: path.is_file())
    monkeypatch.setenv("AE_SCENE_DELIVERY", "local")
    clip = tmp_path / "ae_highlight" / "topic" / "render" / "scene.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"clip" * 500)
    scene = {"ae_motion_plan": {"enabled": True},
             "image_url": "/api/std/assets/gcs-file?bucket=b&path=scene.png",
             "metadata": {"ae_motion_asset": {"storage_provider": "local", "status": "ready",
                                               "duration_seconds": 2, "local_path": str(clip)}}}
    payload = {"structure": {"scenes": [scene]}, "ae_scene_delivery": "local"}
    row = {"id": "project", "__source_type": "project", "project_payload": payload}
    assert ae._find_scene_jobs([row]) == []
    payload["ae_scene_delivery"] = "gcs"
    scene["ae_scene_delivery"] = "local"
    assert ae._scene_delivery("project", payload, payload["structure"], scene) == "gcs"
    assert ae._scene_delivery("topic", None, {"ae_scene_delivery": "local"}, {}) == "local"
    assert len(ae._find_scene_jobs([row])) == 1
    scene["metadata"]["ae_motion_asset"] = {"storage_provider": "gcs", "status": "ready"}
    scene["ae_motion_video_url"] = "/api/std/assets/gcs-file?bucket=b&path=scene.mp4"
    assert ae._find_scene_jobs([row]) == []


def test_final_worker_uses_verified_local_ae_and_rejects_missing_file(monkeypatch, tmp_path):
    import media_checkpoint
    import premiere_final_worker as final

    monkeypatch.setattr(final.worker_config, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(final, "PACKAGE_ROOT", tmp_path / "premiere_final")
    monkeypatch.setattr(final, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(final, "write_state", lambda *args, **kwargs: (tmp_path / "state.json").write_text("{}"))
    monkeypatch.setattr(final, "_update_project", lambda *_args: None)
    monkeypatch.setattr(final, "valid_mp4", lambda path, *_args: path.is_file())
    monkeypatch.setattr(media_checkpoint, "valid_mp4", lambda path, *_args: path.is_file())
    monkeypatch.setenv("PREMIERE_FINAL_BACKEND", "ffmpeg")
    source = tmp_path / "ae_highlight" / "project-001-motion" / "render" / "ae_highlight.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"video" * 500)
    asset = {"storage_provider": "local", "local_path": str(source), "local_bytes": source.stat().st_size,
             "duration_seconds": 2.0, "status": "ready"}
    scene = {"scene_number": 1, "duration_seconds": 5.0,
             "image_url": "/api/std/assets/gcs-file?bucket=b&path=still.png",
             "ae_motion_plan": {"enabled": True}, "metadata": {"ae_motion_asset": asset}}
    row = {"id": "project", "title": "wuxia", "submitted_at": "2026-09-26T00:00:00Z",
           "project_payload": {"structure": {"scenes": [scene]}}, "progress_payload": {}}
    job = final.find_project_jobs([row])[0]
    calls = {"download": 0, "render": 0}
    monkeypatch.setattr(final, "_download_gcs_file", lambda *_args: calls.__setitem__("download", calls["download"] + 1))

    def render(_clips, _audio, _srt, target):
        calls["render"] += 1
        target.write_bytes(b"final" * 500)

    monkeypatch.setattr(final, "_render_final_mp4", render)
    monkeypatch.setattr(final, "_upload_gcs_file", lambda _path, key, _mime: ("bucket", key, "gs://bucket/" + key))
    first = final.process_job(job)
    copied = next((tmp_path / "premiere_final").rglob("scene-001.mp4"))
    copied.write_bytes(b"broken" * 300)
    second = final.process_job(job)
    assert first["status"] == second["status"] == "ready"
    assert calls == {"download": 0, "render": 1}
    assert copied.stat().st_size == source.stat().st_size

    source.unlink()
    assert final.find_project_jobs([row]) == []


def test_transient_final_upload_outage_keeps_retrying_after_render_limit(monkeypatch):
    import premiere_final_worker as final

    row = {"id": "project", "project_payload": {"render_settings": {
        "premiere_final_asset": {"attempts": final.MAX_ATTEMPTS}}}, "progress_payload": {}}
    job = final.ProjectJob("project", "test", row, row["project_payload"], {"scenes": []})
    recorded = []
    monkeypatch.setattr(final, "_update_project", lambda _job, asset: recorded.append(asset))
    final._record_project_failure(job, final.GcsTransientUploadError("temporary GCS outage"))
    assert recorded[0]["status"] == "retry_wait"
    assert recorded[0]["attempts"] == final.MAX_ATTEMPTS + 1
