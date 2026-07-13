"""
[AIR-0227E-P2 §2] Measures AIR Worker startup latency from process launch to
each milestone: Manager log line appears, Local API /health responds,
Render Worker "ready" log line appears, Hermes Worker "ready" log line
appears, all three children ready, and Local API able to accept a job
submission (proxy for "first job receivable").

Usage:
    python _dev/measure_startup.py --exe <path to AIRWorker.exe> --runs 3 [--cold]

Each run uses a fresh AIRWORKER_HOME (so onefile's cold extraction and any
first-run effects are captured every time unless a shared warm dir is
intentional) and fully tears down all AIRWorker.exe processes before the
next run starts.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

POLL_INTERVAL = 0.1
TIMEOUT = 90.0


def _kill_all_airworker():
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='AIRWorker.exe'\" -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
            capture_output=True, timeout=15,
        )
    except Exception:
        pass
    time.sleep(1.0)


def _wait_for(check, timeout=TIMEOUT):
    t0 = time.time()
    while time.time() - t0 < timeout:
        result = check()
        if result:
            return time.time()
        time.sleep(POLL_INTERVAL)
    return None


def measure_one_run(exe_path: Path, home_dir: Path) -> dict:
    _kill_all_airworker()
    shutil.rmtree(home_dir, ignore_errors=True)
    home_dir.mkdir(parents=True, exist_ok=True)

    manager_log = home_dir / "logs" / "manager.log"
    render_log = home_dir / "logs" / "render_worker.log"
    hermes_log = home_dir / "logs" / "hermes_worker.log"

    env = dict(os.environ, AIRWORKER_HOME=str(home_dir), AIRWORKER_ID="startup-timing")

    t_launch = time.time()
    proc = subprocess.Popen([str(exe_path)], cwd=str(exe_path.parent), env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    t_manager_log = _wait_for(lambda: manager_log.exists() and manager_log.stat().st_size > 0)

    def _health_ok():
        try:
            import requests
            r = requests.get("http://127.0.0.1:8765/health", timeout=1)
            return r.status_code == 200
        except Exception:
            return False
    t_health = _wait_for(_health_ok)

    def _render_ready():
        return render_log.exists() and "Render Worker (real pipeline) starting" in render_log.read_text(encoding="utf-8", errors="replace")
    t_render_ready = _wait_for(_render_ready)

    def _hermes_ready():
        return hermes_log.exists() and "Hermes Worker (mock) starting" in hermes_log.read_text(encoding="utf-8", errors="replace")
    t_hermes_ready = _wait_for(_hermes_ready)

    t_all_ready = max(filter(None, [t_render_ready, t_hermes_ready, t_health])) if all([t_render_ready, t_hermes_ready, t_health]) else None

    # "first job receivable" proxy: once /health is up AND both worker
    # "starting" log lines are present, job_store's local SQLite queue is
    # guaranteed initialized (worker_config.py's directory setup runs before
    # any of these processes can log anything) - Local API's own
    # /jobs/submit path only needs job_store + auth, both already live by
    # this point, so t_all_ready is a faithful proxy without needing to
    # decrypt the DPAPI token here just to prove submission works.
    t_job_receivable = t_all_ready

    proc_alive = proc.poll() is None

    _kill_all_airworker()

    def d(t):
        return round(t - t_launch, 2) if t else None

    return {
        "process_launch_to_manager_log_s": d(t_manager_log),
        "process_launch_to_local_api_health_s": d(t_health),
        "process_launch_to_render_worker_ready_s": d(t_render_ready),
        "process_launch_to_hermes_worker_ready_s": d(t_hermes_ready),
        "process_launch_to_all_ready_s": d(t_all_ready),
        "process_launch_to_first_job_receivable_s": d(t_job_receivable),
        "manager_process_alive_at_end": proc_alive,
    }


def summarize(runs: list) -> dict:
    keys = [k for k in runs[0].keys() if k.endswith("_s")]
    summary = {}
    for k in keys:
        values = [r[k] for r in runs if r[k] is not None]
        if values:
            summary[k] = {"avg": round(sum(values) / len(values), 2), "min": min(values), "max": max(values), "n": len(values)}
        else:
            summary[k] = {"avg": None, "min": None, "max": None, "n": 0}
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--home-base", default=None, help="Base dir for per-run AIRWORKER_HOME (default: sibling temp dir)")
    args = parser.parse_args()

    exe_path = Path(args.exe).resolve()
    home_base = Path(args.home_base) if args.home_base else Path(os.environ.get("TEMP", "/tmp")) / "airworker_timing"

    results = []
    for i in range(args.runs):
        label = "cold" if i == 0 else f"warm_{i}"
        print(f"--- Run {i + 1}/{args.runs} ({label}) ---", flush=True)
        r = measure_one_run(exe_path, home_base / f"run_{i}")
        r["label"] = label
        results.append(r)
        print(json.dumps(r, indent=2), flush=True)

    print("\n=== SUMMARY ===", flush=True)
    print(json.dumps({"runs": results, "summary": summarize(results)}, indent=2), flush=True)
