"""
[AIR-0227A Stage 12] CLI status screen (Stage 8 management-UI skeleton).

docs/AIR_WORKER_ARCHITECTURE.md §6 / docs/AIR_WORKER_PROCESS_MODEL.md §6:
implemented as a CLI screen for this pass (lowest risk, fastest to QA);
everything it does is just polling/calling the Local API, so a real GUI
can be swapped in later without changing the Local API contract.

Usage:
    python cli_status.py                  # one-shot status dump
    python cli_status.py --watch          # refresh every 2s
    python cli_status.py --start render   # control commands
    python cli_status.py --stop hermes
    python cli_status.py --logs manager
    python cli_status.py --shutdown
    python cli_status.py --submit-fixture # [AIR-0227B] enqueue the local E2E fixture as a render_video job
    python cli_status.py --jobs           # list recent jobs
    python cli_status.py --job <job_id>   # job detail + transition history
    python cli_status.py --cancel <job_id>
    python cli_status.py --reissue-token  # [AIR-0227C] rotate the local API auth token
    python cli_status.py --token-info     # show which storage backend is active (never prints the token)
"""
import argparse
import time
from pathlib import Path

import requests

from local_api_token import get_or_create_token, reissue_token, storage_backend
from worker_config import LOCAL_API_HOST, LOCAL_API_PORT

BASE_URL = f"http://{LOCAL_API_HOST}:{LOCAL_API_PORT}"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixture" / "sample_render"


def _headers():
    # [AIR-0227C Stage 3] token is read directly from the local DPAPI-protected
    # store - never accepted as a CLI argument or URL query parameter, and
    # never printed by this script.
    return {"Authorization": f"Bearer {get_or_create_token()}"}


def _get(path):
    return requests.get(f"{BASE_URL}{path}", headers=_headers(), timeout=5).json()


def _post(path, json_body=None, timeout=25):
    return requests.post(f"{BASE_URL}{path}", json=json_body, headers=_headers(), timeout=timeout).json()


def print_status():
    try:
        snap = _get("/status")
    except requests.RequestException as e:
        print(f"[!] Could not reach Local API at {BASE_URL} ({e}) - is the Manager running?")
        return

    print(f"=== AIR Worker Status (worker_id={snap['worker_id']}) ===")
    print(f"Hermes paused: {snap['hermes_paused']}")
    print()
    header = f"{'PROCESS':<16}{'STATUS':<12}{'PID':<8}{'JOB':<24}{'PROGRESS':<10}{'RESTARTS':<10}"
    print(header)
    print("-" * len(header))
    for name, proc in snap["processes"].items():
        job = proc.get("current_job") or {}
        job_id = job.get("job_id", "-") if isinstance(job, dict) else "-"
        progress = proc.get("progress")
        progress_str = f"{progress}%" if progress is not None else "-"
        print(
            f"{name:<16}{proc['status']:<12}{str(proc['pid'] or '-'):<8}"
            f"{str(job_id):<24}{progress_str:<10}{proc['restart_count_total']:<10}"
        )
        if proc.get("disabled_reason"):
            print(f"    !! disabled: {proc['disabled_reason']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--start", choices=["render", "hermes"])
    parser.add_argument("--stop", choices=["render", "hermes"])
    parser.add_argument("--logs", default=None)
    parser.add_argument("--shutdown", action="store_true")
    parser.add_argument("--submit-fixture", action="store_true")
    parser.add_argument("--jobs", action="store_true")
    parser.add_argument("--job", default=None)
    parser.add_argument("--cancel", default=None)
    parser.add_argument("--reissue-token", action="store_true", help="Generate a new local API token, invalidating the previous one immediately")
    parser.add_argument("--token-info", action="store_true", help="Show token storage backend (never prints the token itself)")
    args = parser.parse_args()

    if args.reissue_token:
        reissue_token()
        print(f"Token reissued (backend={storage_backend()}). The previous token is no longer valid.")
        return
    if args.token_info:
        get_or_create_token()  # ensure one exists
        print(f"Token storage backend: {storage_backend()}")
        return

    if args.start:
        print(_post(f"/processes/{args.start}/start"))
        return
    if args.stop:
        print(_post(f"/processes/{args.stop}/stop"))
        return
    if args.logs:
        result = _get(f"/logs?process={args.logs}")
        for line in result.get("lines", []):
            print(line)
        return
    if args.shutdown:
        print(_post("/shutdown"))
        return
    if args.submit_fixture:
        if not (FIXTURE_DIR / "config.json").exists():
            print(f"[!] Fixture not found at {FIXTURE_DIR} - run: python fixture/build_fixture.py")
            return
        result = _post("/jobs/submit", {
            "job_type": "render_video",
            "priority": 100,
            "payload": {"source_path": str(FIXTURE_DIR)},
        })
        print(result)
        return
    if args.jobs:
        result = _get("/jobs")
        for job in result.get("jobs", []):
            print(f"{job['job_id']}  {job['job_type']:<12} {job['status']:<10} progress={job['progress']:>3}% retries={job['retry_count']}/{job['max_retries']}")
        return
    if args.job:
        print(_get(f"/jobs/{args.job}"))
        return
    if args.cancel:
        print(_post(f"/jobs/{args.cancel}/cancel", timeout=25))
        return

    if args.watch:
        try:
            while True:
                print("\033[2J\033[H", end="")  # clear screen
                print_status()
                time.sleep(2)
        except KeyboardInterrupt:
            pass
    else:
        print_status()


if __name__ == "__main__":
    main()
