import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'worker')]
from codex_content_runner import CodexStagedContentRunner
from worker.japanese_historical_documentary import review_final_script

packet = json.loads((ROOT / '_dev/artifacts/documentary_readiness_sources.json').read_text(encoding='utf-8'))
sections = [
    {'scene_order': 1, 'text': '家康は慶長十年、西暦千六百五年に、息子の秀忠へ将軍職を譲りました。その後、大御所と呼ばれています。'},
    {'scene_order': 2, 'text': '慶長十九年、西暦千六百十四年の九月から十月にかけ、家康は諸大名に大坂への出陣を命じました。国立公文書館の解説が伝える動きです。'},
]
if '--negative' in sys.argv:
    sections[0]['text'] = sections[0]['text'].replace('千六百五年', '千五百五年')
    try:
        review_final_script(CodexStagedContentRunner(), 'documentary-live-negative-20261022', packet, sections)
    except ValueError as error:
        result = {'rejected': True, 'reason': str(error)}
        (ROOT / '_dev/artifacts/documentary_readiness_negative_review.json').write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'incorrect_year_rejected': True}))
        raise SystemExit(0)
    raise RuntimeError('Incorrect historical year was accepted')
report = review_final_script(CodexStagedContentRunner(), 'documentary-live-evidence-20261022', packet, sections)
(ROOT / '_dev/artifacts/documentary_readiness_evidence_review.json').write_text(
    json.dumps({'sections': sections, 'review': report}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'verdict': report['verdict'], 'scene_count': len(report['scene_evidence']),
                  'script_sha256': report['script_sha256']}, ensure_ascii=True))
