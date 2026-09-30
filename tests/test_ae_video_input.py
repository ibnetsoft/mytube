import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker"))

from worker import ae_highlight_worker


def test_ae_worker_prefers_layered_psd_for_template_jobs_when_available():
    source = ae_highlight_worker._gcs_ref_from_scene({
        "metadata": {
            "video_gcs_bucket": "air-test",
            "video_gcs_path": "std-projects/p/scene_013_comfyui.mp4",
            "psd_layer_asset": {"gcs_bucket": "air-test", "gcs_path": "std-projects/p/scene_013_layers.psd"},
        },
    })

    assert source.path.endswith(".psd")


def test_ae_worker_accepts_gcs_video_as_effect_footage():
    source = ae_highlight_worker._gcs_ref_from_scene({
        "metadata": {
            "video_gcs_bucket": "air-test",
            "video_gcs_path": "std-projects/p/scene_013_comfyui.mp4",
        },
    })

    assert source.bucket == "air-test"
    assert source.path.endswith("scene_013_comfyui.mp4")


def test_comfyui_scene_waits_for_registered_video_before_ae_postprocess():
    scene = {
        "scene_number": 13,
        "video_generation_mode": "comfyui",
        "ae_motion_plan": {"enabled": True, "input_source": "comfyui_video_asset"},
        "metadata": {"video_generation_mode": "comfyui"},
    }
    assert not ae_highlight_worker._scene_requires_comfyui(scene)
    row = {"id": "p", "__source_type": "project", "project_payload": {"structure": {"scenes": [scene]}}}
    assert ae_highlight_worker._find_scene_jobs([row]) == []

    scene["metadata"]["comfyui_video_asset"] = {
        "gcs_bucket": "air-test", "gcs_path": "std-projects/p/scene_013_comfyui.mp4",
    }
    jobs = ae_highlight_worker._find_scene_jobs([row])
    assert len(jobs) == 1
    assert jobs[0].source.path.endswith("scene_013_comfyui.mp4")


def test_ae_worker_does_not_run_image_only_plan_on_comfyui_scene_without_video():
    scene = {
        "scene_number": 13,
        "video_generation_mode": "comfyui",
        "ae_motion_plan": {"enabled": True, "local_source_path": r"C:\\image.png"},
    }
    row = {"id": "p", "__source_type": "project", "project_payload": {"structure": {"scenes": [scene]}}}
    assert ae_highlight_worker._find_scene_jobs([row]) == []


def test_user_upload_scene_waits_for_clip_then_ae_uses_uploaded_video():
    scene = {
        "scene_number": 1,
        "video_generation_mode": "user_upload",
        "ae_motion_plan": {"enabled": True, "input_source": "uploaded_video_asset"},
        "metadata": {"video_generation_mode": "user_upload"},
        "image_url": "/api/std/assets/gcs-file?bucket=air-test&path=scene-001.png",
    }
    row = {"id": "p", "__source_type": "project", "project_payload": {"structure": {"scenes": [scene]}}}
    assert ae_highlight_worker._find_scene_jobs([row]) == []

    scene["metadata"]["video_asset"] = {
        "gcs_bucket": "air-test", "gcs_path": "std-projects/p/scene_001_upload.mp4",
    }
    jobs = ae_highlight_worker._find_scene_jobs([row])
    assert len(jobs) == 1
    assert jobs[0].source.path.endswith("scene_001_upload.mp4")


def test_reviewed_upload_direction_can_hold_without_default_zoom(tmp_path):
    direction = {
        "source_video_review_status": "reviewed",
        "ae_operations": ["hold"],
        "timed_beats": [{"start_seconds": 0, "end_seconds": 5, "action": "hold", "target": "composition"}],
    }
    job = ae_highlight_worker.SceneJob(
        topic_id="topic", topic_title="Topic", structure={"scenes": []}, scene_index=0,
        scene={"ae_motion_plan": {"enabled": True, "motion": {"push": 0.05}, "directorial_plan": direction}},
        scene_number=1, plan_kind="motion", preset="slow_hold", duration_seconds=5,
        source=ae_highlight_worker.GcsRef("bucket", "scene-001.mp4"),
    )
    jsx = tmp_path / "scene.jsx"
    ae_highlight_worker._write_jsx(job, tmp_path / "scene.mp4", tmp_path / "scene.aep", tmp_path / "render.mp4", jsx)
    source = jsx.read_text(encoding="utf-8")

    assert "reviewedUploadedClip && !directorCameraMove ? 1.0" in source
    assert "reviewedUploadedClip && !directorCameraMove) { startX = W / 2" in source
