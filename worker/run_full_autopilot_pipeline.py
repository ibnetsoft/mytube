import asyncio
import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "worker"))
os.chdir(str(ROOT / "worker"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)

import hermes_worker
import job_store
from hermes_autopilot import HermesAutopilotManager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CoWork에서 Codex 콘텐츠 파이프라인으로 한 편을 생성합니다."
    )
    parser.add_argument(
        "--category",
        required=True,
        help='생성 카테고리. 예: "옛날이야기"',
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=300,
        help="목표 길이(초). 기본값: 300 (5분)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="기존 버퍼 수와 관계없이 한 편 생성을 요청합니다.",
    )
    parser.add_argument(
        "--image-style",
        default="",
        help='이 카테고리에 이번 생성 동안 적용할 이미지 스타일. 예: "realistic"',
    )
    args = parser.parse_args()
    if args.duration < 60:
        parser.error("--duration은 60초 이상이어야 합니다.")
    return args

# Background thread to process local job_store jobs
def worker_loop():
    print("[Worker Thread] Started", flush=True)
    while getattr(worker_loop, "running", True):
        try:
            job = job_store.claim_next_job(hermes_worker.SUPPORTED_JOB_TYPES, os.getpid())
            if job:
                print(f"[Worker Thread] Claimed {job.get('job_type')} ({job.get('job_id')})", flush=True)
                hermes_worker.process_one_job(job)
                print(f"[Worker Thread] Finished {job.get('job_id')}", flush=True)
            else:
                time.sleep(1.0)
        except Exception as e:
            print(f"[Worker Thread Error] {e}", flush=True)
            time.sleep(1.0)

async def main(args: argparse.Namespace):
    # CoWork 진입점은 Gemini/Hermes의 창작 경로를 허용하지 않는다.
    # 주제 후보 검증은 YouTube API/웹 데이터, 창작 산출물은 Codex로 처리한다.
    os.environ["CONTENT_GENERATION_ENGINE"] = "codex"
    worker_loop.running = True
    t = threading.Thread(target=worker_loop, daemon=True)
    t.start()

    category = args.category.strip()
    mgr = HermesAutopilotManager()
    
    settings = {
        "mode": "target_limit",
        "target_limit": 1,
        "min_buffer_per_category": 1,
        "active_categories": [category],
        "category_image_style_overrides": (
            {category: args.image_style.strip()}
            if args.image_style.strip()
            else {}
        ),
        "target_duration_seconds_by_category": {category: args.duration},
        "force_generate": args.force,
        "quality_max_attempts": 3,
    }
    
    print(
        f"[*] Starting CoWork Codex pipeline | category='{category}' | "
        f"duration={args.duration}s | force={args.force}",
        flush=True,
    )
    res = await mgr.start(settings)
    print(f"[*] Autopilot start result: {res}", flush=True)
    
    last_step = ""
    while mgr.is_running:
        await asyncio.sleep(3)
        st = mgr.get_status()
        cur_step = st.get("current_step") or ""
        if cur_step != last_step or st.get("last_error"):
            last_step = cur_step
            print(f"[Autopilot Progress] Step: {cur_step} | Topic: {st.get('current_topic')} | Error: {st.get('last_error')}", flush=True)

    worker_loop.running = False
    final_st = mgr.get_status()
    print("=" * 60, flush=True)
    print(f"[Final Result] Status: {final_st.get('last_run_status')}", flush=True)
    print(f"[Final Result] Topic: {final_st.get('current_topic')}", flush=True)
    print(f"[Final Result] Last Error: {final_st.get('last_error')}", flush=True)
    print(f"[Final Result] Completed ID: {final_st.get('last_completed_result_id')}", flush=True)
    print("=" * 60, flush=True)

if __name__ == "__main__":
    asyncio.run(main(parse_args()))
