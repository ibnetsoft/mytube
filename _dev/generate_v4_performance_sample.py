import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'worker'))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
from worker.codex_content_runner import CodexStagedContentRunner, CodexContentConfig
from worker.elevenlabs_performance import plan_performance

out = ROOT / '_dev/artifacts/v4-performance'
out.mkdir(parents=True, exist_ok=True)
runner = CodexStagedContentRunner(CodexContentConfig.from_environment())
draft = runner._stage('v4-performance-live-20261019', '02k_v4_short_sample_script',
    {'language': 'ko', 'topic': '작은 선물에 숨긴 비밀이 기쁜 소식으로 바뀌는 순간'},
    "Write a NEW short Korean two-line spoken script for a vocal performance smoke test. "
    "Line one is a quiet confidential secret, line two is a contrasting joyful announcement. "
    "Each line is one natural short sentence of 15-35 Korean characters. No headings, stage "
    "directions, speaker labels, brackets or tags inside spoken text. Return JSON "
    "{sections:[{scene_number:1,text:'...',scene_situation:'...',scene_emotion:'...'},"
    "{scene_number:2,text:'...',scene_situation:'...',scene_emotion:'...'}]}.")
sections = draft['sections']
assert len(sections) == 2
scenes = [{**section, 'scene_text': section['text'], 'narration': section['text']} for section in sections]
plan = plan_performance(runner._stage, 'v4-performance-live-20261019', scenes, 'ko')
assert len({cue['tag'] for scene in plan['scenes'] for cue in scene['cues']}) >= 2, 'Sample needs two contrasting AI-directed deliveries'
package = {'title': 'v4 연기 태그 신규 대본 검증', 'language': 'ko',
    'script': '\n\n'.join(s['scene_text'] for s in scenes),
    'structure': {'scenes': scenes, 'audio_performance': plan}}
(out / 'new-script.json').write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(package, ensure_ascii=False))
