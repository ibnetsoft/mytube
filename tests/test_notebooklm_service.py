import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = str(ROOT / "worker")
if WORKER not in sys.path:
    sys.path.insert(0, WORKER)

import codex_content_runner
from services import notebooklm_service


def test_reference_script_adapter_uses_codex_and_maps_scene_contract(monkeypatch):
    calls = {}

    def fake_stage(self, job_id, stage, context, task):
        calls["title_stage"] = stage
        calls["title_task"] = task
        return {"title": "달빛 아래 비녀를 돌려준 아이"}

    def fake_generate(self, job_id, payload, *, script_only=False):
        calls["payload"] = payload
        calls["script_only"] = script_only
        return {
            "script": "아이의 선택으로 약속이 지켜졌습니다.",
            "narrative_blueprint": {"opening_hook": "비녀에 새겨진 이름은 누구의 것일까요?"},
            "structure": {"scenes": [
                {"scene_text": "아이가 비녀를 줍습니다.", "duration_seconds": 5,
                 "visual_type": "video", "video_generation_mode": "user_upload"},
                {"scene_text": "아이는 주인을 찾아 나섭니다.", "duration_seconds": 5,
                 "visual_type": "video", "video_generation_mode": "user_upload"},
            ]},
        }

    monkeypatch.setattr(codex_content_runner.CodexStagedContentRunner, "_stage", fake_stage)
    monkeypatch.setattr(codex_content_runner.CodexStagedContentRunner, "generate", fake_generate)

    result = asyncio.run(notebooklm_service.generate_notebooklm_project(
        "장터에서 비녀를 주운 아이에 관한 참고 메모", category="옛날이야기", duration_minutes=5
    ))

    assert calls["title_stage"] == "01_grounded_title"
    assert "natural Korean" in calls["title_task"]
    assert calls["script_only"] is True
    assert calls["payload"]["category_id"] == "2"
    assert calls["payload"]["target_duration_seconds"] == 300
    assert calls["payload"]["research_bundle"]["source_text"].startswith("장터에서")
    assert result["generator"] == "Codex CLI"
    assert result["dialogue_mode"] is False
    assert result["scenes"][0]["speaker"] == "나레이터"
    assert result["hook"] == "비녀에 새겨진 이름은 누구의 것일까요?"


def test_japanese_folktale_title_stage_requests_japanese(monkeypatch):
    calls = {}

    def fake_stage(self, job_id, stage, context, task):
        calls["task"] = task
        return {"title": "月夜にかんざしを返した娘"}

    def fake_generate(self, job_id, payload, *, script_only=False):
        calls["language"] = payload["language"]
        return {"script": "娘は持ち主にかんざしを返しました。", "structure": {"scenes": []}}

    monkeypatch.setattr(codex_content_runner.CodexStagedContentRunner, "_stage", fake_stage)
    monkeypatch.setattr(codex_content_runner.CodexStagedContentRunner, "generate", fake_generate)

    result = asyncio.run(notebooklm_service.generate_notebooklm_project(
        "かんざしを返した娘の昔話", category="日本昔話", duration_minutes=15
    ))

    assert "natural Japanese" in calls["task"]
    assert calls["language"] == "ja"
    assert result["title"] == "月夜にかんざしを返した娘"
