import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'worker/connection.env',override=False)
from worker.script_worker_store import ScriptStore
s=ScriptStore();r=s.request('GET','topics_queue',params={'select':'*','id':'eq.3427'})[0][0]
x=s.request('POST','rpc/std_user_web_topic_structure',body={'p_id':3427})[0]
assert len(x['scenes'])==144
assert len({v['image_url'] for v in x['scenes'] if v.get('image_url')})==144
p=ROOT/'output/pawnshop-series/episode-06';(p/'USER_WEB_TOPIC_READBACK.json').write_text(json.dumps(r,ensure_ascii=False));(p/'USER_WEB_STRUCTURE_READBACK.json').write_text(json.dumps(x,ensure_ascii=False));print('user-web source RPC: 144 unique scene image URLs')
