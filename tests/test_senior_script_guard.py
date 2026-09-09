import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker"))
sys.path.insert(0, str(ROOT))
import codex_content_runner as runner
from senior_script_guard import text_issues, review_issues, contract, CHECKS, PROFILE


@pytest.mark.parametrize("script", ["", "  ", "At first, nobody knew how far this event would go.",
    "여기에 글로벌 금융 환경의 변화가 더해진다. " * 6,
    "intro 1. This is an English template rather than Korean narration."])
def test_real_failure_patterns_are_rejected(script):
    assert text_issues([{"scene_order": 1, "text": script}], {"language": "ko"})


def test_short_dialogue_refrain_is_not_automatically_rejected():
    assert not text_issues([{"scene_order": 1, "text": "어머니는 문을 열고 아들을 맞았습니다. 괜찮아. 괜찮아. 괜찮아."}], {"language": "ko"})


def test_wrong_section_order_is_rejected():
    assert text_issues([{"scene_order": 2, "text": "어머니는 문을 열고 아들을 맞았습니다."}], {})


@pytest.mark.parametrize("category,expected", [(2,"옛날이야기"),(3,"경제"),(4,"탈북사연"),(5,"한국사연"),(6,"해외감동"),(7,"무협"),(8,"노후금융"),(9,"황혼19금"),(12,"English Folktales"),(13,"日本昔話")])
def test_explicit_category_overrides_generic_story_style(category, expected):
    payload = {"category_id": category, "script_style": "story", "topic": "옛날이야기와 관련된 제목"}
    voice = runner._category_narration_voice(payload)
    assert expected in contract(payload)
    if category != 2:
        assert "Category narration voice: 옛날이야기" not in voice


@pytest.mark.parametrize("report", [None, {}, {"verdict": "pass", "score": 100, "critical_issues": []}])
def test_self_awarded_score_cannot_bypass_evidence_gate(report):
    assert review_issues(report)


def test_feedback_changes_cache_and_does_not_reuse_rejected_response(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "OUTPUT_DIR", tmp_path)
    outputs = []
    def fake_run(command, **kwargs):
        path = pathlib.Path(command[command.index("--output-last-message") + 1])
        outputs.append(path)
        path.write_text(json.dumps({"attempt": len(outputs)}), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    instance = runner.CodexStagedContentRunner(runner.CodexContentConfig("codex", "", 60))
    assert instance._stage("job", "02b_script_qa", {"script": "draft"}, "review")["attempt"] == 1
    assert instance._stage("job", "02b_script_qa", {"script": "draft"}, "review")["attempt"] == 1
    assert instance._stage("job", "02b_script_qa", {"script": "draft", "rejection": "bad relationship"}, "review")["attempt"] == 2
    assert outputs[0] != outputs[1]
