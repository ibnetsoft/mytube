"""Observe this one job and create final-script packaging when generation finishes."""
import json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/pawnshop-series/episode-02'
JOB=json.loads((OUT/'job-receipt.json').read_text())['id']
BASE=ROOT/'output/codex-local-console'/JOB
last=None
while True:
 p=BASE/'job.json'
 if not p.exists():time.sleep(5);continue
 row=json.loads(p.read_text());state=(row['status'],row.get('stage'))
 if state!=last:print(json.dumps({'status':state[0],'stage':state[1]},ensure_ascii=False),flush=True);last=state
 if row['status'] in ('failed','interrupted'):
  print('GENERATION_REPAIR_REQUIRED; source and checkpoints preserved.',flush=True);sys.exit(2)
 if row['status'] in ('awaiting_approval','completed'):
  subprocess.run([sys.executable,str(ROOT/'_dev/pawnshop_episode02_packaging.py')],cwd=ROOT,check=True)
  print('PACKAGING_READY_FOR_THUMBNAIL',flush=True)
  subprocess.run([sys.executable,str(ROOT/'_dev/pawnshop_episode02_finish.py')],cwd=ROOT,check=True)
  sys.exit(0)
 time.sleep(10)
