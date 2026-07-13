"""
[AIR-0227E-P2 §3] Launches N copies of AIRWorker.exe concurrently (all
pointed at the same AIRWORKER_HOME) and reports how many Manager processes
survive after a settle period - the Named Mutex (worker/single_instance.py)
should let exactly one through and the other N-1 should each exit 1
immediately.

Usage: python _dev/test_mutex_concurrent.py --exe <path> --home <dir> --n 10
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True)
    parser.add_argument("--home", required=True)
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--settle-seconds", type=float, default=15.0)
    args = parser.parse_args()

    exe_path = Path(args.exe).resolve()
    home = Path(args.home)
    home.mkdir(parents=True, exist_ok=True)

    import os
    env = dict(os.environ, AIRWORKER_HOME=str(home))

    print(f"Launching {args.n} concurrent copies of {exe_path} ...")
    procs = []
    for i in range(args.n):
        p = subprocess.Popen([str(exe_path)], cwd=str(exe_path.parent), env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(p)

    print(f"Waiting {args.settle_seconds}s for mutex contention to resolve...")
    time.sleep(args.settle_seconds)

    exited = [p for p in procs if p.poll() is not None]
    still_running_bootstrap = [p for p in procs if p.poll() is None]
    print(f"Bootstrap-process poll(): {len(exited)} exited, {len(still_running_bootstrap)} still running (onefile bootstrap parents don't all exit - see note below)")

    # The launched processes here are onefile/onedir bootstrap invocations,
    # not necessarily the Manager itself (onefile spawns a child; onedir's
    # exe *is* the manager process directly) - the real signal is how many
    # OS-level AIRWorker.exe processes with NO --role argument (i.e.
    # Manager, not render_worker/hermes_worker/local_api) are alive after
    # settling, since only one of them should have survived mutex
    # contention.
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-CimInstance Win32_Process -Filter \"Name='AIRWorker.exe'\" -ErrorAction SilentlyContinue | "
         "Where-Object { $_.CommandLine -notmatch '--role' }).Count"],
        capture_output=True, text=True,
    )
    manager_count = result.stdout.strip()
    print(f"Manager-role AIRWorker.exe processes (no --role arg) still alive: {manager_count}")
    print("Expected: 1 (the winner) for onedir; for onefile this counts BOTH the surviving "
          "bootstrap parent and its re-executed Manager child, so 2 is the correct 'one winner' "
          "result there - see the P2 report for the exact number observed for each variant.")


if __name__ == "__main__":
    main()
