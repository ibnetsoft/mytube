"""Continue this authorized episode into immutable reviewed still publication."""
import hashlib,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'worker/connection.env')
from worker.script_worker_store import ScriptStore
JOB='acc3fd2d56b64672a80593c2d9cd4e66'
BASE=ROOT/'output/codex-local-console'/JOB
OUT=ROOT/'output/pawnshop-series/episode-06/image-production'
while not (BASE/'delivery/registration-receipt.json').exists():
    time.sleep(15)
receipt=json.loads((BASE/'delivery/registration-receipt.json').read_text())
assert receipt['source_job_id']==JOB
store=ScriptStore()
for attempt in range(100):
    try:
        rows,_=store.request('GET','topics_queue',params={'select':'*','id':'eq.'+str(receipt['topic_id'])})
        row=rows[0]
        assert row['progress_payload']['source_script_job_id']==JOB
        assert row['status']=='pending' and not row.get('assigned_employee_email')
        binding=json.loads((OUT/'narration-source-binding.json').read_text())
        assert hashlib.sha256(row['pregenerated_script'].encode()).hexdigest()==binding['script_sha256']
        scenes=row['pregenerated_structure']['scenes']
        assert [s.get('scene_text') or s.get('narration') for s in scenes]==[s['text'] for s in binding['scenes']]
        (OUT/'source-topic.json').write_text(json.dumps(row,ensure_ascii=False,indent=2))
        print('Episode06 registered topic',row['id'],'narration unchanged',len(scenes),'scenes',flush=True)
        break
    except AssertionError:
        raise
    except Exception:
        time.sleep(min(60,10*(attempt+1)))
else:
    raise RuntimeError('Registration readback unavailable')
os.execv(sys.executable,[sys.executable,'-u',str(ROOT/'_dev/pawnshop_episode06_publish.py'),'--episode','06'])
