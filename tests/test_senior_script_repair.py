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
            return {"sections": [{"scene_order": 1, "text": text}], "story_core": {"protagonist": "어머니"}, "narrative_blueprint": {"continuity_ledger": {"cast": ["어머니", "아들"]}}}
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


@pytest.mark.parametrize("change", ["topic", "project"])
def test_newer_or_manual_edits_are_not_overwritten(monkeypatch, tmp_path, change):
    monkeypatch.setattr(repair, "ROOT", tmp_path)
    original = "어머니는 아들의 편지를 펼쳐 보았습니다."
    revised = "어머니는 멀리 떠난 아들이 보낸 편지를 조심스레 펼쳤지요."
    row = {"id": 1, "pregenerated_script": original, "pregenerated_structure": {"scenes": [{"scene_order": 1}]}}
    fresh = {**row, "pregenerated_script": "new work"} if change == "topic" else row
    monkeypatch.setattr(repair, "_fetch_rows", lambda *a: [fresh])
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return [{"id": "project", "project_payload": {"script": "user edited", "original_worker_script": original}}]
    monkeypatch.setattr(repair.requests, "get", lambda *a, **k: Response())
    def unexpected(*args, **kwargs):
        raise AssertionError("No PATCH is allowed on conflict")
    monkeypatch.setattr(repair.requests, "patch", unexpected)
    report = {"profile": PROFILE, "verdict": "pass", "score": 90, "critical_issues": [],
              "checks": {key: {"pass": True, "evidence": "The original character relationship remains consistent in the final scene."} for key in CHECKS}}
    with pytest.raises(repair.CodexContentError, match="changed during generation|user-edited narration"):
        repair._update_row("unused", {}, row, [{"scene_order": 1, "text": revised}], report)
