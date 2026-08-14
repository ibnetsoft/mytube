import asyncio
import json
import os
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

# Force this quality run onto the text provider selected for the current
# recovery pass. Set these before config.py loads .env.
os.environ["TOPIC_GENERATION_MODEL"] = "deepseek-chat"
os.environ["TITLE_GENERATION_MODEL"] = "deepseek-chat"
os.environ["SCRIPT_PLANNING_MODEL"] = "deepseek-chat"
os.environ["SCRIPT_GENERATION_MODEL"] = "deepseek-chat"
os.environ["IMAGE_PROMPT_MODEL"] = "deepseek-chat"

import job_store
from hermes_autopilot import HermesAutopilotManager
from shutdown_flag import clear_shutdown_flag, request_shutdown
from worker_config import OUTPUT_DIR


CATEGORY = "옛날이야기"
EXPECTED_SCRIPT_STYLE = "story"
EXPECTED_IMAGE_STYLE = "ghibli"
TARGET_COUNT = int(os.environ.get("TARGET_COUNT", "6"))


def _json_files() -> dict[str, Path]:
    result_dir = OUTPUT_DIR / "hermes_autopilot_results"
    result_dir.mkdir(parents=True, exist_ok=True)
    return {path.stem: path for path in result_dir.glob("*.json") if path.is_file()}


def _mostly_korean_script(script: str) -> bool:
    hangul = len(re.findall(r"[\uac00-\ud7a3]", script or ""))
    latin = len(re.findall(r"[A-Za-z]", script or ""))
    return hangul >= 1000 and latin <= max(80, hangul // 20)


def _expected_grid_count(scene_count: int) -> int:
    if scene_count < 4:
        return 0
    return scene_count // 4 + (1 if scene_count % 4 else 0)


def validate_result(path: Path) -> list[str]:
    errors: list[str] = []
    data = json.loads(path.read_text(encoding="utf-8"))
    structure = data.get("structure") or {}
    scenes = structure.get("scenes") or []
    script = str(data.get("script") or "")
    metadata = data.get("publish_metadata") or {}
    benchmark_analysis = data.get("benchmark_analysis") or {}
    category_text_blob = json.dumps(
        {
            "benchmark_candidates": benchmark_analysis.get("candidates"),
            "selected_candidate": benchmark_analysis.get("selected_candidate"),
            "web_research": benchmark_analysis.get("web_research"),
            "research_bundle": data.get("research_bundle"),
            "sources": data.get("sources"),
            "topic": data.get("topic"),
            "title": data.get("title") or data.get("upload_title"),
        },
        ensure_ascii=False,
    )

    if data.get("category") != CATEGORY:
        errors.append(f"category mismatch: {data.get('category')!r}")
    script_style = structure.get("script_style") or data.get("script_style") or data.get("assigned_script_style")
    if script_style not in (EXPECTED_SCRIPT_STYLE, None, ""):
        errors.append(f"script_style mismatch: {script_style!r}")
    image_style = structure.get("image_style") or data.get("image_style") or data.get("assigned_image_style")
    if image_style != EXPECTED_IMAGE_STYLE:
        errors.append(f"image_style mismatch: {image_style!r}")

    if structure.get("media_prompt_status") != "ready":
        errors.append(f"media_prompt_status is not ready: {structure.get('media_prompt_status')!r}")
    if structure.get("image_grid_prompt_status") != "ready":
        errors.append(f"image_grid_prompt_status is not ready: {structure.get('image_grid_prompt_status')!r}")
    if not scenes:
        errors.append("no scenes")

    if not _mostly_korean_script(script):
        hangul = len(re.findall(r"[\uac00-\ud7a3]", script))
        latin = len(re.findall(r"[A-Za-z]", script))
        errors.append(f"script language ratio suspicious: hangul={hangul}, latin={latin}, chars={len(script)}")
    if re.search(r"\b(At first|One small clue|As time passed|Auto-generated longform|intro scene|development scene)\b", script):
        errors.append("script contains scratch/fallback English template text")
    if CATEGORY == "옛날이야기" and re.search(
        r"(금값|코스피|환율|금리|주가|\bETF\b|부동산|\bPF\b|경제|물가|인플레이션|유가|달러|원화|투자|매수|매도|주식|채권|나스닥|비트코인)",
        category_text_blob,
        re.IGNORECASE,
    ):
        errors.append("off-category economy benchmark/research contamination detected")

    image_prompts: list[str] = []
    video_prompts: list[str] = []
    for index, scene in enumerate(scenes, start=1):
        image_prompt = str(scene.get("image_prompt") or "").strip()
        video_prompt = str(scene.get("video_prompt") or "").strip()
        image_prompts.append(image_prompt)
        video_prompts.append(video_prompt)
        if scene.get("media_prompt_status") != "ready":
            errors.append(f"scene {index} media_prompt_status={scene.get('media_prompt_status')!r}")
        if len(image_prompt) < 220:
            errors.append(f"scene {index} image_prompt too short/missing")
        if len(video_prompt) < 260:
            errors.append(f"scene {index} video_prompt too short/missing")
        if "Korean longform storytelling scene" in image_prompt:
            errors.append(f"scene {index} repeated scratch image prompt")
    if len(set(image_prompts)) != len(image_prompts):
        errors.append("duplicate image prompts")
    if len(set(video_prompts)) != len(video_prompts):
        errors.append("duplicate video prompts")

    grids = structure.get("image_grid_prompts") or []
    expected_grid_count = _expected_grid_count(len(scenes))
    if not isinstance(grids, list) or len(grids) != expected_grid_count:
        errors.append(f"image_grid_prompts count mismatch: expected={expected_grid_count}, actual={len(grids) if isinstance(grids, list) else 'not-list'}")
    else:
        seen_grid_prompts: set[str] = set()
        covered_scene_numbers: set[str] = set()
        for grid in grids:
            prompt = str(grid.get("prompt") or grid.get("grid_prompt") or "").strip() if isinstance(grid, dict) else ""
            scene_numbers = grid.get("scene_numbers") if isinstance(grid, dict) else None
            if not prompt:
                errors.append("blank image_grid_prompt")
            if prompt in seen_grid_prompts:
                errors.append("duplicate image_grid_prompt")
            seen_grid_prompts.add(prompt)
            if not isinstance(scene_numbers, list) or len(scene_numbers) != 4:
                errors.append(f"invalid grid scene_numbers: {scene_numbers!r}")
            else:
                covered_scene_numbers.update(str(number) for number in scene_numbers)
        for index, scene in enumerate(scenes, start=1):
            scene_number = str(scene.get("scene_order") or scene.get("scene_number") or index)
            if scene_number not in covered_scene_numbers:
                errors.append(f"scene {scene_number} is not covered by image_grid_prompts")

    if not metadata:
        errors.append("missing publish_metadata")
    if metadata.get("source") == "worker_fallback":
        errors.append("publish_metadata used worker_fallback")
    if not (metadata.get("description") and (metadata.get("tags") or metadata.get("hashtags"))):
        errors.append("publish_metadata incomplete")
    return errors


async def main() -> int:
    clear_shutdown_flag("hermes_worker")
    cancelled = job_store.cancel_nonterminal_jobs_by_source("autopilot", reason="old story quality run restart")
    print(json.dumps({"cancelled_autopilot_jobs": cancelled}, ensure_ascii=False), flush=True)

    before = _json_files()

    import hermes_worker

    worker_thread = threading.Thread(target=hermes_worker.run_forever, name="hermes-worker-old-story-quality", daemon=True)
    worker_thread.start()
    await asyncio.sleep(2)

    manager = HermesAutopilotManager()
    start_result = await manager.start({
        "mode": "target_limit",
        "target_limit": TARGET_COUNT,
        "min_buffer_per_category": 0,
        "active_categories": [CATEGORY],
        "force_generate": True,
    })
    print(json.dumps({"start_result": start_result}, ensure_ascii=False), flush=True)
    if not start_result.get("success"):
        request_shutdown("hermes_worker")
        raise RuntimeError(f"failed to start autopilot: {start_result}")

    validated: dict[str, str] = {}
    last_log_count = 0
    try:
        while manager.is_running:
            status = manager.get_status()
            logs = status.get("logs") or []
            new_logs = logs[last_log_count:]
            last_log_count = len(logs)
            for line in new_logs[-8:]:
                print(json.dumps({"log": line}, ensure_ascii=False), flush=True)

            current = _json_files()
            for result_id, path in sorted(current.items(), key=lambda item: item[1].stat().st_mtime):
                if result_id in before or result_id in validated:
                    continue
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if data.get("category") != CATEGORY:
                    continue
                errors = validate_result(path)
                if errors:
                    quarantine_dir = path.parent / "quarantine_failed_quality"
                    quarantine_dir.mkdir(parents=True, exist_ok=True)
                    target = quarantine_dir / path.name
                    path.replace(target)
                    print(json.dumps({"quality_failed": str(target), "errors": errors}, ensure_ascii=False), flush=True)
                    await manager.stop()
                    raise RuntimeError(f"quality validation failed for {path.name}: {errors}")
                validated[result_id] = str(path)
                structure = data.get("structure") or {}
                print(json.dumps({
                    "validated": result_id,
                    "path": str(path),
                    "title": data.get("title") or data.get("upload_title"),
                    "scene_count": len(structure.get("scenes") or []),
                    "grid_count": len(structure.get("image_grid_prompts") or []),
                }, ensure_ascii=False), flush=True)

            print(json.dumps({
                "status": status.get("current_step"),
                "category": status.get("current_category"),
                "topic": status.get("current_topic"),
                "stats": status.get("session_stats"),
                "last_run_status": status.get("last_run_status"),
                "last_error": status.get("last_error"),
                "validated_count": len(validated),
            }, ensure_ascii=False), flush=True)
            await asyncio.sleep(20)

        status = manager.get_status()
        print(json.dumps({"final_status": status}, ensure_ascii=False), flush=True)
        if status.get("last_run_status") != "completed":
            raise RuntimeError(f"autopilot failed: {status.get('last_error')}")

        current = _json_files()
        for result_id, path in sorted(current.items(), key=lambda item: item[1].stat().st_mtime):
            if result_id in before or result_id in validated:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("category") != CATEGORY:
                continue
            errors = validate_result(path)
            if errors:
                raise RuntimeError(f"final quality validation failed for {path.name}: {errors}")
            validated[result_id] = str(path)

        if len(validated) != TARGET_COUNT:
            raise RuntimeError(f"expected {TARGET_COUNT} validated results, got {len(validated)}: {validated}")

        print(json.dumps({"completed": list(validated.values())}, ensure_ascii=False, indent=2), flush=True)
        return 0
    finally:
        request_shutdown("hermes_worker")
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
