import asyncio
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

async def main():
    worker_loop.running = True
    t = threading.Thread(target=worker_loop, daemon=True)
    t.start()

    category = "황혼19금"
    mgr = HermesAutopilotManager()
    
    settings = {
        "mode": "target_limit",
        "target_limit": 1,
        "min_buffer_per_category": 1,
        "active_categories": [category],
        "category_image_style_overrides": {},
        "target_duration_seconds_by_category": {category: 300},
        "force_generate": True,
        "quality_max_attempts": 3,
    }
    
    print(f"[*] Starting Hermes Autopilot for category: '{category}'...", flush=True)
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
    asyncio.run(main())
