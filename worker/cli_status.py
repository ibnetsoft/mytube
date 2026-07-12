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
"""
import argparse
import time

import requests

from config import LOCAL_API_HOST, LOCAL_API_PORT

BASE_URL = f"http://{LOCAL_API_HOST}:{LOCAL_API_PORT}"


def _get(path):
    return requests.get(f"{BASE_URL}{path}", timeout=5).json()


def _post(path):
    return requests.post(f"{BASE_URL}{path}", timeout=5).json()


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
    args = parser.parse_args()

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
