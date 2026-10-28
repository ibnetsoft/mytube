"""Read-only live smoke; no production job, asset or publication writes."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'worker'))
from codex_content_runner import CodexStagedContentRunner
from worker.japanese_historical_documentary import prepare_sources, PROFILE

packet = prepare_sources(CodexStagedContentRunner(), 'documentary-readiness-utf8-20261022', {
    'script_style': PROFILE['key'], 'topic': '徳川家康の晩年と大坂の陣',
    'user_direction': '日本の公的機関・博物館・学術資料を優先。通説と異説を区別。裏づけのない私生活は描かない。',
})
out = ROOT / '_dev/artifacts/documentary_readiness_sources.json'
out.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'source_count': len(packet['historical_sources']), 'sources': [
    {'title': s['title'], 'url': s['url'], 'chars': len(s['text'])} for s in packet['historical_sources']
]}, ensure_ascii=True))
