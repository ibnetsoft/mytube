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
