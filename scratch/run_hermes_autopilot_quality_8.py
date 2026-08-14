import asyncio
import json
import re
import sys
import threading
import time
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKER_DIR = PROJECT_ROOT / "worker"
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

import job_store
from hermes_autopilot import HermesAutopilotManager
from shutdown_flag import clear_shutdown_flag, request_shutdown
from worker_config import OUTPUT_DIR, STATE_DIR


CATEGORIES = ["탈북사연", "해외감동", "노후금융", "황혼19금", "옛날이야기", "한국사연", "무협", "경제"]
EXPECTED_STYLES = {
    "탈북사연": ("story", "watercolor"),
    "해외감동": ("story", "ghibli"),
    "노후금융": ("news", "watercolor forest story"),
    "황혼19금": ("story", "shadowed investigation"),
    "옛날이야기": ("story", "ghibli"),
    "한국사연": ("story", "classic vintage cinema"),
    "무협": ("mystery_thriller", "he moonlit hanok palace"),
    "경제": ("news", "rainy neon metropolis"),
}


def validate_result(path: Path, category: str) -> list[str]:
    errors: list[str] = []
    data = json.loads(path.read_text(encoding="utf-8"))
    structure = data.get("structure") or {}
    scenes = structure.get("scenes") or []
    script = str(data.get("script") or "")
    metadata = data.get("publish_metadata") or {}
    expected_script, expected_image = EXPECTED_STYLES[category]

    if data.get("category") != category:
        errors.append(f"category mismatch: {data.get('category')!r}")
    if structure.get("script_style") not in (expected_script, None):
        errors.append(f"script_style mismatch: {structure.get('script_style')!r} != {expected_script!r}")
    if structure.get("image_style") != expected_image:
        errors.append(f"image_style mismatch: {structure.get('image_style')!r} != {expected_image!r}")
    if structure.get("media_prompt_status") != "ready":
        errors.append(f"media_prompt_status is not ready: {structure.get('media_prompt_status')!r}")
    if not scenes:
        errors.append("no scenes")
    if re.search(r"\b(At first|One small clue|As time passed|Auto-generated longform|intro scene|development scene)\b", script):
        errors.append("script contains scratch/fallback English template text")
    hangul = len(re.findall(r"[\uac00-\ud7a3]", script))
    latin = len(re.findall(r"[A-Za-z]", script))
    if not script.strip() or hangul < 1000 or latin > max(80, hangul // 20):
        errors.append(f"script language ratio suspicious: hangul={hangul}, latin={latin}, chars={len(script)}")

    image_prompts = []
    video_prompts = []
    for index, scene in enumerate(scenes, start=1):
        image_prompt = str(scene.get("image_prompt") or "").strip()
        video_prompt = str(scene.get("video_prompt") or "").strip()
        image_prompts.append(image_prompt)
        video_prompts.append(video_prompt)
        if scene.get("media_prompt_status") != "ready":
            errors.append(f"scene {index} media_prompt_status={scene.get('media_prompt_status')!r}")
        if len(image_prompt) < 220:
            errors.append(f"scene {index} image_prompt too short")
        if len(video_prompt) < 260:
            errors.append(f"scene {index} video_prompt too short/missing")
        if "Korean longform storytelling scene" in image_prompt:
            errors.append(f"scene {index} repeated scratch image prompt")
    if len(set(image_prompts)) != len(image_prompts):
        errors.append("duplicate image prompts")
    if len(set(video_prompts)) != len(video_prompts):
        errors.append("duplicate video prompts")

    if not metadata:
        errors.append("missing publish_metadata")
    if metadata.get("source") == "worker_fallback":
        errors.append("publish_metadata used worker_fallback")
    if not (metadata.get("description") and (metadata.get("tags") or metadata.get("hashtags"))):
        errors.append("publish_metadata incomplete")
    return errors


async def run_category(manager: HermesAutopilotManager, category: str) -> Path:
    settings = {
        "mode": "target_limit",
        "target_limit": 1,
        "min_buffer_per_category": 0,
        "active_categories": [category],
        "force_generate": True,
    }
    start_result = await manager.start(settings)
    print({"category": category, "start_result": start_result}, flush=True)
    if not start_result.get("success"):
        raise RuntimeError(f"failed to start autopilot for {category}: {start_result}")

    while manager.is_running:
        status = manager.get_status()
        print(
            {
                "category": category,
                "step": status.get("current_step"),
                "stats": status.get("session_stats"),
                "last_error": status.get("last_error"),
            },
            flush=True,
        )
        await asyncio.sleep(20)

    status = manager.get_status()
    print({"category": category, "final_status": status}, flush=True)
    if status.get("last_run_status") != "completed":
        raise RuntimeError(f"{category} failed: {status.get('last_error')}")
    result_id = str(status.get("last_completed_result_id") or "")
    result_path = OUTPUT_DIR / "hermes_autopilot_results" / f"{result_id}.json"
    if not result_path.exists():
        raise RuntimeError(f"{category} result file missing: {result_path}")
    errors = validate_result(result_path, category)
    if errors:
        quarantine_dir = result_path.parent / "quarantine_failed_quality"
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        target = quarantine_dir / result_path.name
        result_path.replace(target)
        raise RuntimeError(f"{category} quality validation failed; quarantined {target}: {errors}")
    print({"category": category, "validated_result": str(result_path)}, flush=True)
    return result_path


async def main() -> int:
    clear_shutdown_flag("hermes_worker")
    cancelled = job_store.cancel_nonterminal_jobs_by_source("autopilot", reason="quality test restart")
    print({"cancelled_autopilot_jobs": cancelled}, flush=True)

    import hermes_worker

    worker_thread = threading.Thread(target=hermes_worker.run_forever, name="hermes-worker-quality", daemon=True)
    worker_thread.start()
    await asyncio.sleep(2)

    manager = HermesAutopilotManager()
    completed: list[str] = []
    try:
        for category in CATEGORIES:
            path = await run_category(manager, category)
            completed.append(str(path))
        print({"completed": completed}, flush=True)
        return 0
    finally:
        request_shutdown("hermes_worker")
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
