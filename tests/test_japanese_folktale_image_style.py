import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'worker'))

from services.japanese_folktale_style import STYLE_KEY, STYLE_PROMPT, category_style
from worker import hermes_autopilot, hermes_worker


def test_web_and_worker_share_visual_direction():
    preset = json.loads((ROOT / 'auth-web/lib/japaneseFolktaleStyle.json').read_text(encoding='utf-8'))
    assert preset == {'key': STYLE_KEY, 'prompt': STYLE_PROMPT}
    assert hermes_worker._resolve_image_style_directive(STYLE_KEY) == (STYLE_KEY, STYLE_PROMPT)


def test_category_defaults_preserve_custom_styles():
    for legacy in ('', 'realistic', 'cinematic'):
        assert category_style('日本昔話', legacy) == STYLE_KEY
    assert category_style('日本昔話', 'watercolor') == 'watercolor'
    assert category_style('English Folktales', 'realistic') == 'realistic'


def test_japanese_default_does_not_require_ai_or_remote_catalog():
    manager = object.__new__(hermes_autopilot.HermesAutopilotManager)
    manager.settings = {}
    result = asyncio.run(manager._select_image_style('日本昔話', '村の昔話', 'realistic'))
    assert result['assigned_image_style'] == STYLE_KEY
    assert result['selection_source'] == 'category_default'


def test_manual_override_still_wins(monkeypatch):
    manager = object.__new__(hermes_autopilot.HermesAutopilotManager)
    manager.settings = {'category_image_style_overrides': {'日本昔話': 'watercolor'}}
    monkeypatch.setattr(manager, '_available_image_styles', lambda: [{'key_code': 'watercolor'}])
    result = asyncio.run(manager._select_image_style('日本昔話', '村の昔話', 'realistic'))
    assert result['assigned_image_style'] == 'watercolor'
    assert result['selection_source'] == 'worker_manual_override'
