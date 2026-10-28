import hashlib,json,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
for f in [ROOT/'.env',ROOT/'.env.local',ROOT/'auth-web/.env.local']:load_dotenv(f,override=False)
from worker.codex_content_runner import CodexStagedContentRunner,CodexContentConfig
from worker.codex_subtitle_translation import translate_blocks
OUT=ROOT/'output/codex-local-console/6ae46b7afca84070b36e9e13d7de0a6e/web-package'
rows=json.loads((OUT/'subtitles.json').read_text(encoding='utf-8'))
source=[{'index':i,'source_text':r['text']} for i,r in enumerate(rows)]
runner=CodexStagedContentRunner(CodexContentConfig.from_environment())
for language in ['ko','th']:
 target=OUT/f'translations-{language}.json'
 if target.exists():
  saved=json.loads(target.read_text(encoding='utf-8'))
  if saved.get('status')=='completed' and saved.get('source_hash')==hashlib.sha256(json.dumps(source,ensure_ascii=False).encode()).hexdigest():continue
 for_update={'language':language,'status':'running','source_blocks':len(source)}
 (OUT/'translation-status.json').write_text(json.dumps(for_update),encoding='utf-8')
 print(language,'starting',len(source),flush=True)
 result=translate_blocks(runner,'jp-life-final-'+language,source,language)
 assert len(result)==len(source)
 for s,t in zip(source,result):assert t['index']==s['index'] and t['source_text']==s['source_text'] and t['translated_text'].strip()
 target.write_text(json.dumps({'version':1,'language':language,'status':'completed','source_hash':hashlib.sha256(json.dumps(source,ensure_ascii=False).encode()).hexdigest(),'blocks':result},ensure_ascii=False,indent=2),encoding='utf-8')
 print(language,'completed',flush=True)
(OUT/'translation-status.json').write_text(json.dumps({'status':'completed','languages':['ko','th'],'blocks_per_language':len(source)}),encoding='utf-8')
