import sys,json,hashlib
from pathlib import Path
P=Path(__file__).resolve().parent.parent;ROOT=P.parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
import worker_config
from worker.codex_content_runner import CodexStagedContentRunner
script=json.loads((P/'script-final.json').read_text(encoding='utf-8'))
blocks=[{'index':i,'scene_id':s['id'],'kind':b['kind'],'speaker':b.get('speaker'),'source_text':b['text']} for i,(s,b) in enumerate([(s,b) for s in script['scenes'] for b in s['blocks']])]
out=P/'packaging'/'review-translation-th.json'
if out.exists():
 old=json.loads(out.read_text(encoding='utf-8'))
 if [b['source_text'] for b in old['blocks']]==[b['source_text'] for b in blocks]:print('matching Thai review translation reused');sys.exit(0)
runner=CodexStagedContentRunner();result=[]
for start in range(0,len(blocks),35):
 group=blocks[start:start+35]
 data=runner._stage('wuxia-ep01','03_th_review_'+str(start),{'target_language':'Thai','source_language':'Korean','blocks':group,'cast':script['cast']},
  'Translate EVERY source_text to natural Thai for human script/dialogue review. Preserve meaning, speakers, names consistently, original chronology, questions, threats and cliffhanger. No summary, merging, omissions or added events. Return JSON {blocks:[{index:exact source index,source_text:EXACT original Korean,translated_text:Thai translation}]}. One output for every input in exact order. This is review text, not timed audio.')
 rows=data.get('blocks',[]);assert len(rows)==len(group)
 for src,row in zip(group,rows):
  assert row['index']==src['index'] and row['source_text']==src['source_text'] and row['translated_text'].strip()
  result.append({**src,'translated_text':row['translated_text']})
 print('Thai review blocks',len(result),'/',len(blocks),flush=True)
out.write_text(json.dumps({'language':'th','status':'ready','source':'local_codex_cli_worker','timed':False,'blocks':result},ensure_ascii=False,indent=2),encoding='utf-8')
