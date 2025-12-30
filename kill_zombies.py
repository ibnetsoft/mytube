
import os
import subprocess

pids = [
    21964, 16928, 36472, 39828, 40168, 9880, 42216, 11084, 
    35452, 21992, 20220, 40392, 10756, 31268, 35580, 44896, 40784
]

print(f"Killing {len(pids)} processes...")
for pid in pids:
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Killed {pid}")
    except Exception as e:
        print(f"Failed to kill {pid}: {e}")

print("Cleanup complete.")
