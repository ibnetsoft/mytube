"""Wait for the running episode, then continue its registered web-package work."""
import json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'output/codex-local-console/9a74a481741948aaa8bf4cf8bd27734b'
last=None
while True:
 row=json.loads((BASE/'job.json').read_text())
 state=(row['status'],row.get('stage'))
 if state!=last:print(json.dumps({'status':state[0],'stage':state[1]},ensure_ascii=False),flush=True);last=state
 if row['status'] in ('failed','interrupted'):
  print('GENERATION_REPAIR_REQUIRED; source and checkpoints preserved.',flush=True);sys.exit(2)
 if row['status'] in ('awaiting_approval','completed'):
  result=subprocess.run([sys.executable,str(ROOT/'_dev/pawnshop_episode01_finish.py')],cwd=ROOT)
  sys.exit(result.returncode)
 time.sleep(10)
