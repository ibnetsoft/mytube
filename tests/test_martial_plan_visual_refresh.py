import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKER = ROOT / "worker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WORKER) not in sys.path:
    sys.path.insert(0, str(WORKER))

from worker import hermes_worker


def test_martial_repair_refreshes_leaked_visual_template_fields():
    structure = {
        "scenes": [
            {
                "scene_summary": "same martial beat",
                "scene_purpose": "same purpose",
                "retention_hook": "same hook",
                "visual_direction": f"Timed visual beat Scene {idx} visual_direction",
            }
            for idx in range(1, 15)
        ]
    }

    repaired = hermes_worker._repair_martial_scene_plan_repetition(
        structure,
        "martial hidden manual",
        "martial hidden manual",
    )
    refreshed = hermes_worker._refresh_martial_scene_visual_fields(
        repaired,
        "martial hidden manual",
        "martial hidden manual",
    )

    assert not hermes_worker._scene_plan_repetition_errors(refreshed)
