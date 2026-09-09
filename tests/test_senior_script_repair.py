import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "worker"))
from scripts import repair_existing_topic_scripts as repair
from senior_script_guard import PROFILE, CHECKS


def test_repair_never_saves_failed_self_review(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("Unapproved text must not reach database")
    monkeypatch.setattr(repair.requests, "patch", unexpected)
    with pytest.raises(repair.CodexContentError, match="unapproved repair"):
        repair._update_row("unused", {}, {"id": 1}, [{"scene_order": 1, "text": "어머니가 아들을 반갑게 맞이했습니다."}],
                           {"verdict": "revise", "score": 99})


def test_repair_feeds_independent_rejection_back_to_writer(monkeypatch, tmp_path):
    calls = []
    text = "어머니가 문을 열자 오랫동안 기다렸던 아들이 서 있었지요."
    def stage(self, job, name, context, task):
        calls.append((name, context))
        if name == "repair_script":
            return {"sections": [{"scene_order": 1, "text": text}]}
        report = {"profile": PROFILE, "verdict": "pass", "score": 90, "critical_issues": [],
                  "checks": {key: {"pass": True, "evidence": "첫 장면에서 어머니와 아들의 관계 및 재회의 결과를 확인했습니다."} for key in CHECKS}}
        if len(calls) == 2:
            report["verdict"] = "revise"
        return {"script_quality_report": report}
    monkeypatch.setattr(repair.CodexStagedContentRunner, "_stage", stage)
    row = {"id": 1, "category_id": 2, "topic": "돌아온 아들", "pregenerated_script": text,
           "pregenerated_structure": {"scenes": [{"scene_order": 1, "duration_seconds": 5, "scene_text": text}]}}
    sections, report = repair._repair_with_codex(row, "옛날이야기", tmp_path, "gpt-6-astra")
    assert len(calls) == 4
    assert calls[2][1]["independent_review"]["script_quality_report"]["verdict"] == "revise"
    assert sections[0]["text"] == text
    assert report["profile"] == PROFILE

