import importlib
import json
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKER = ROOT / "worker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WORKER) not in sys.path:
    sys.path.insert(0, str(WORKER))


def test_adobe_tools_respects_explicit_paths(monkeypatch, tmp_path):
    premiere = tmp_path / "Adobe Premiere Pro.exe"
    afterfx = tmp_path / "AfterFX.com"
    aerender = tmp_path / "aerender.exe"
    ame = tmp_path / "Adobe Media Encoder.exe"
    for path in (premiere, afterfx, aerender, ame):
        path.write_text("", encoding="utf-8")

    monkeypatch.setenv("PREMIERE_PATH", str(premiere))
    monkeypatch.setenv("AE_AFTERFX_PATH", str(afterfx))
    monkeypatch.setenv("AE_AERENDER_PATH", str(aerender))
    monkeypatch.setenv("AME_PATH", str(ame))

    import adobe_tools
    adobe_tools = importlib.reload(adobe_tools)

    report = adobe_tools.capability_report()
    assert report["premiere_path"] == str(premiere)
    assert report["premiere_exists"] is True
    assert report["afterfx_path"] == str(afterfx)
    assert report["aerender_path"] == str(aerender)
    assert report["media_encoder_path"] == str(ame)


def test_premiere_worker_builds_srt_and_importable_xml(tmp_path):
    import premiere_final_worker as worker

    scenes = [
        {"scene_order": 1, "duration_seconds": 1.5, "scene_text": "첫 장면입니다."},
        {"scene_order": 2, "duration_seconds": 2.0, "scene_text": "두 번째 장면입니다."},
    ]
    srt = tmp_path / "air-subtitles.srt"
    worker._write_srt(scenes, srt)
    text = srt.read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:01,500" in text
    assert "00:00:01,500 --> 00:00:03,500" in text
    assert "두 번째 장면입니다." in text

    media = tmp_path / "scene-001.mp4"
    media.write_text("", encoding="utf-8")
    fcpxml = tmp_path / "air-premiere-final.xml"
    audio = tmp_path / "narration.wav"
    audio.write_bytes(b"test")
    worker._write_premiere_xml([
        {
            "name": "scene-001-ae",
            "path": media,
            "duration_seconds": 1.5,
            "offset_frames": 0,
        }
    ], fcpxml, audio)
    xml = fcpxml.read_text(encoding="utf-8")
    assert "<xmeml" in xml
    assert "<clipitem" in xml
    assert "scene-001-ae" in xml
    assert "air-narration" in xml

    relink = tmp_path / "relink.py"
    worker._write_relink_script(relink)
    assert "Relinked" in relink.read_text(encoding="utf-8")


def test_premiere_worker_requires_every_scene_media():
    import premiere_final_worker as worker

    assert worker._project_audio_ref({"audio_url": "gs://bucket/narration.wav"}) == worker.GcsRef("bucket", "narration.wav")
    assert worker._scene_media_ref({"scene_number": 1})[1] is None


def test_ame_bridge_writes_completion_driven_export(tmp_path):
    import ame_export_bridge as bridge

    script = tmp_path / "export.jsx"
    bridge.write_script(tmp_path / "source.mp4", tmp_path / "preset.epr",
                        tmp_path / "output", tmp_path / "status.txt", script)
    content = script.read_text(encoding="utf-8")
    assert 'addFileToBatch' in content
    assert 'onItemEncodeComplete' in content
    assert 'complete|' in content
    assert 'app.quit()' in content


def test_ame_bridge_does_not_take_over_running_session(monkeypatch, tmp_path):
    import ame_export_bridge as bridge

    executable = tmp_path / "Adobe Media Encoder.exe"
    executable.write_bytes(b"test")
    monkeypatch.setattr(bridge, "find_media_encoder", lambda: executable)
    monkeypatch.setattr(bridge, "_ame_running", lambda: True)
    import pytest
    with pytest.raises(bridge.AmeBridgeError, match="already running"):
        bridge.export(tmp_path / "source.mp4", tmp_path / "preset.epr",
                      tmp_path / "out", tmp_path / "status", tmp_path / "script.jsx")


def test_ae_worker_uses_submitted_project_structure():
    import ae_highlight_worker as worker

    row = {
        "id": "project-1", "title": "Submitted", "__source_type": "project",
        "project_payload": {"structure": {"scenes": [{
            "scene_number": 1,
            "image_url": "/api/std/assets/gcs-file?bucket=bucket&path=scene.png",
            "ae_motion_plan": {"enabled": True, "preset": "subtle_motion"},
        }]}},
    }
    jobs = worker._find_scene_jobs([row])
    assert len(jobs) == 1
    assert jobs[0].source_type == "project"
    assert jobs[0].source.path == "scene.png"


def test_ae_launcher_waits_for_async_project_after_process_exit(monkeypatch, tmp_path):
    import ae_highlight_worker as worker

    launcher = tmp_path / "AfterFX.com"
    launcher.write_bytes(b"test")
    script = tmp_path / "create.jsx"
    script.write_text("", encoding="utf-8")
    project = tmp_path / "effect.aep"

    class FinishedLauncher:
        returncode = 0

        def poll(self):
            return 0

    starts = []
    monkeypatch.setattr(worker.subprocess, "Popen", lambda *args, **kwargs: starts.append(args) or FinishedLauncher())
    monkeypatch.setattr(worker.time, "sleep", lambda seconds: project.write_bytes(b"a" * 2048))

    worker._run_afterfx_script(launcher, script, project, timeout=3)
    assert len(starts) == 1


def test_premiere_worker_finds_submitted_project_job():
    import premiere_final_worker as worker

    row = {
        "id": "project-1",
        "title": "테스트 프로젝트",
        "submitted_at": "2026-09-26T00:00:00Z",
        "project_payload": {
            "structure": {
                "scenes": [
                    {
                        "scene_order": 1,
                        "duration_seconds": 5,
                        "image_url": "/api/std/assets/gcs-file?bucket=air-studio-prod&path=projects%2Fproject-1%2Fscene-001.png",
                    }
                ]
            }
        },
        "progress_payload": {},
    }
    jobs = worker.find_project_jobs([row])
    assert len(jobs) == 1
    assert jobs[0].project_id == "project-1"

    row["project_payload"]["render_settings"] = {
        "premiere_final_asset": {"status": "package_ready"}
    }
    assert worker.find_project_jobs([row]) == []
    assert len(worker.find_project_jobs([row], force=True)) == 1
