"""Generate requested review-language scene blocks only via the local Codex CLI."""
import json,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'worker/connection.env')
from worker.codex_content_runner import CodexStagedContentRunner
from worker.codex_subtitle_translation import translate_blocks
OUT=ROOT/'output/pawnshop-series/episode-01/production';source=json.loads((OUT.parent/'topic-registration-payload.json').read_text());scenes=source['pregenerated_structure']['scenes'];blocks=[{'index':s['scene_number'],'source_text':s['scene_text'],'source_sha256':hashlib.sha256(s['scene_text'].encode()).hexdigest()} for s in scenes]
for lang in ['ko','th']:
 p=OUT/f'scene-review-translations-{lang}.json'
 if p.exists():
  old=json.loads(p.read_text());assert [b['source_sha256'] for b in old['blocks']]==[b['source_sha256'] for b in blocks];print(lang,'reused',len(old['blocks']),flush=True);continue
 result=translate_blocks(CodexStagedContentRunner(),'pawnshop-3387-review-'+lang,blocks,lang,heartbeat=lambda:print(lang,'batch continuing',flush=True))
 assert len(result)==144
 p.write_text(json.dumps({'source':'local_codex_cli','kind':'scene_review_translation_not_timed_subtitles','language':lang,'blocks':result},ensure_ascii=False,indent=2));print(lang,'saved',len(result),flush=True)
