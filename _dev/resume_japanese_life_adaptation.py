import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from worker.codex_local_console import jobs, StartRequest

identity = '6ae46b7afca84070b36e9e13d7de0a6e'
request = StartRequest(**json.loads((ROOT / 'output/codex-local-console' / identity / 'request.json').read_text(encoding='utf-8')))
jobs.start(request, None, retry_of=identity, identity=identity)
jobs.pool.shutdown(wait=True)
