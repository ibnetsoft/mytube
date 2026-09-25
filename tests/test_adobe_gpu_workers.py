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


def test_premiere_worker_builds_srt_and_fcpxml(tmp_path):
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
    fcpxml = tmp_path / "air-premiere-final.fcpxml"
    worker._write_fcpxml([
        {
            "name": "scene-001-ae",
            "path": media,
            "duration_seconds": 1.5,
            "offset_frames": 0,
        }
    ], fcpxml)
    xml = fcpxml.read_text(encoding="utf-8")
    assert "<fcpxml" in xml
    assert "asset-clip" in xml
    assert "scene-001-ae" in xml


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
