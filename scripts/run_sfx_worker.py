"""Run just SFX planning with the existing script-worker engine and credentials.
Does not claim narration, image, topic, or render jobs. Stop with Ctrl+C.
"""
import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'worker'))
import worker_config

# Isolate state/logs from the installed render worker, retaining configured auth.
os.environ['AIRWORKER_HOME'] = str(worker_config.BASE_DIR / 'sfx-planner')
importlib.reload(worker_config)
import hermes_worker

if __name__ == '__main__':
    hermes_worker.SUPPORTED_JOB_TYPES = ['sfx_plan_generate']
    hermes_worker.main()
