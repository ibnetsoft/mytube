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
checkpoint=out.with_name('translation-checkpoint.json')
saved=json.loads(checkpoint.read_text(encoding='utf8')) if checkpoint.exists() else []
for start in range(0,len(blocks),10):
 group=blocks[start:start+10]
 cached=[r for r in saved if any(r['index']==b['index'] and r['source_text']==b['source_text'] for b in group)]
 if len(cached)==len(group):result.extend(cached);continue
 escaped=[{'index':b['index'],'kind':b['kind'],'speaker':b['speaker'],'korean_json_string':json.dumps(b['source_text'],ensure_ascii=True)} for b in group]
 data=runner._stage('wuxia-ep02','02_subtitle_translation_th_ascii_'+str(start),{'target_language':'Thai','source_language':'Korean','blocks':escaped},
  'Each korean_json_string is an ASCII JSON string literal. DECODE its unicode escapes to recover the intact original Korean. Translate EVERY decoded string to natural Thai for human script/dialogue review. Preserve meaning, speakers, names consistently, chronology, questions, threats and cliffhanger. No summary, merging, omissions or added events. Return JSON {blocks:[{index:exact source index,translated_text:Thai translation}]}. One output for every input in exact order. Review text, not timed audio.')
 rows=data.get('blocks',[]);assert len(rows)==len(group)
 for src,row in zip(group,rows):
  assert row['index']==src['index'] and row['translated_text'].strip()
  result.append({**src,'translated_text':row['translated_text']})
 checkpoint.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
 print('Thai review blocks',len(result),'/',len(blocks),flush=True)
out.write_text(json.dumps({'language':'th','status':'ready','source':'local_codex_cli_worker','timed':False,'blocks':result},ensure_ascii=False,indent=2),encoding='utf-8')
