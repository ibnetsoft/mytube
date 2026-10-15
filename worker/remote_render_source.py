"""Run the current web renderer from source, with the local worker environment."""
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
import worker_config  # loads the shared local environment before the renderer
runpy.run_path(str(root / 'remote_drive_worker.py'), run_name='__main__')
