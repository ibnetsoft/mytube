import asyncio
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = ROOT / "worker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

from hermes_autopilot import HermesAutopilotManager  # noqa: E402


def test_title_selection_uses_highest_final_score_over_raw_model_recommendation(monkeypatch):
    manager = HermesAutopilotManager()
    manager._generation_model_trace = {"hermes_autopilot_title_eval": "gemini-test"}
    plan = {
        "title_candidates": [
            {"title": "점수가 더 높은 제목", "score": 90},
            {"title": "모델이 추천한 낮은 제목", "score": 70},
        ]
    }

    async def fake_generate(*_args, **_kwargs):
        return json.dumps(
            {
                "evaluations": [
                    {"title": "점수가 더 높은 제목", "ai_score": 90, "reason": "strong", "risk": "low"},
                    {"title": "모델이 추천한 낮은 제목", "ai_score": 80, "reason": "weaker", "risk": "medium"},
                ],
                "best_title": "모델이 추천한 낮은 제목",
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(manager, "_generate_title_text_with_fallback", fake_generate)

    selected = asyncio.run(manager._ai_evaluate_title_plan("한국사연", plan, []))

    assert selected["generated_title"] == "점수가 더 높은 제목"
    assert selected["selected_score"] == 90
    assert selected["ai_evaluation"]["model_recommended_title"] == "모델이 추천한 낮은 제목"
    assert selected["generation_models"]["hermes_autopilot_title_eval"] == "gemini-test"
