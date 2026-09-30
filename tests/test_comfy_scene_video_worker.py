import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker"))

from worker import comfy_scene_video_worker as worker


def test_wan22_api_workflow_uses_installed_models_and_five_second_video():
    graph = worker.build_wan22_i2v_prompt(
        "air_studio/project/scene_013.png", "A careful slow tracking shot follows the character.",
        "air_studio/project/scene_013_comfyui", seed=123,
    )

    assert graph["1"]["class_type"] == "UnetLoaderGGUF"
    assert graph["1"]["inputs"]["unet_name"] == "Wan2.2-TI2V-5B-Q4_K_M.gguf"
    assert graph["2"]["inputs"]["type"] == "wan"
    assert graph["8"]["inputs"]["length"] == 121
    assert abs(graph["8"]["inputs"]["width"] * 9 - graph["8"]["inputs"]["height"] * 16) < 256
    assert graph["11"]["inputs"]["fps"] == 24
    assert graph["12"]["inputs"]["format"] == "mp4"
    assert graph["12"]["inputs"]["codec"] == "h264"


def test_worker_selects_only_active_gcs_scene_images():
    assets = [
        {"scene_number": 13, "asset_type": "image", "status": "replaced", "metadata": {"gcs_path": "old.png"}},
        {"scene_number": 13, "asset_type": "image", "status": "assigned", "metadata": {"gcs_path": "scene.png", "gcs_bucket": "air-test"}},
        {"scene_number": 14, "asset_type": "video", "status": "assigned", "metadata": {"gcs_path": "scene.mp4"}},
    ]

    assert worker._scene_source(assets, 13) == ("air-test", "scene.png")
    assert worker._scene_source(assets, 14) is None
    assert worker._scene_source(assets, 19) is None


def test_scene_list_reads_project_structure_before_flat_compatibility_payload():
    project = {"project_payload": {"structure": {"scenes": [{"scene_number": 13}]}, "scenes": [{"scene_number": 2}]}}

    assert worker._scene_list(project) == [{"scene_number": 13}]


def test_comfyui_video_registration_preserves_ae_postprocess_plan():
    scene = {
        "scene_number": 13,
        "video_generation_mode": "comfyui",
        "ae_motion_plan": {"enabled": True, "preset": "ambient_lantern_motion",
                           "input_source": "comfyui_video_asset", "postprocess_after": "comfyui_video_ready"},
        "metadata": {"video_generation_mode": "comfyui"},
    }
    updated = worker._patch_scene_payload(scene, 13, "asset-13", "air-test", "std-projects/p/scene_013_comfyui.mp4")

    assert updated["ae_motion_plan"] == scene["ae_motion_plan"]
    assert updated["metadata"]["comfyui_video_asset"]["gcs_path"].endswith("scene_013_comfyui.mp4")
    assert updated["video_url"].endswith("scene_013_comfyui.mp4")
