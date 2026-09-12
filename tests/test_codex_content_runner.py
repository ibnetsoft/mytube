import json
import pathlib
import subprocess
import sys
import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKER = ROOT / "worker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WORKER) not in sys.path:
    sys.path.insert(0, str(WORKER))

import codex_content_runner as runner_module
from senior_script_guard import PROFILE, CHECKS


def _review_report():
    return {"profile": PROFILE, "verdict": "pass", "score": 90, "critical_issues": [],
            "checks": {key: {"pass": True, "evidence": "Scene 1 introduces the protagonist; later scenes resolve the established conflict."} for key in CHECKS}}


def _package():
    return {
        "generated_title": "비밀의 우물에서 시작된 약속",
        "title_generation": {"title_candidates": [{"title": "비밀의 우물에서 시작된 약속"}]},
        "structure": {"scenes": [{"scene_order": 1, "image_prompt": "x", "video_prompt": "y", "scene_text": "가" * 220}]},
        "script": "가" * 220,
        "narrative_blueprint": {"hook": "hook"},
        "script_quality_report": _review_report(),
        "publish_metadata": {"title": "비밀의 우물에서 시작된 약속", "description": "설명", "tags": ["태그"]},
        "main_character": {"name": "연화"},
        "supporting_characters": [],
        "character_anchors": {"main_character": {"name": "연화"}},
        "sfx_cues": [],
    }


def test_codex_runner_requests_read_only_structured_content(monkeypatch, tmp_path):
    monkeypatch.setattr(runner_module, "OUTPUT_DIR", tmp_path)
    captured = {}

    def fake_run(command, **kwargs):
        response_path = pathlib.Path(command[command.index("--output-last-message") + 1])
        if "02c_senior_review" in response_path.name:
            response_path.write_text(json.dumps({"script_quality_report": _review_report()}), encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "", "")
        captured["command"] = command
        response_path.write_text(json.dumps(_package(), ensure_ascii=False), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    output = runner_module.CodexContentRunner(
        runner_module.CodexContentConfig("codex", "", 60)
    ).generate("job-1", {"topic": "seed"})

    assert output["generated_title"] == "비밀의 우물에서 시작된 약속"
    assert "--sandbox" in captured["command"]
    assert captured["command"][captured["command"].index("--sandbox") + 1] == "read-only"
    assert "--output-schema" not in captured["command"]
    assert "TITLE UNIQUENESS IS A HARD REQUIREMENT" in captured["command"][-1]
    prompt = captured["command"][-1]
    assert "Do not generate images or video" in prompt
    assert "Do not do fresh web/YouTube research" in prompt


def test_codex_runner_rejects_incomplete_package(monkeypatch, tmp_path):
    monkeypatch.setattr(runner_module, "OUTPUT_DIR", tmp_path)

    def fake_run(command, **kwargs):
        response_path = pathlib.Path(command[command.index("--output-last-message") + 1])
        response_path.write_text('{"generated_title":"only"}', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    try:
        runner_module.CodexContentRunner(
            runner_module.CodexContentConfig("codex", "", 60)
        ).generate("job-2", {})
    except runner_module.CodexContentError as exc:
        assert "omitted required fields" in str(exc)
    else:
        raise AssertionError("incomplete Codex package was accepted")


def test_legacy_five_minute_pacing_is_12_micro_scenes_then_16_development_scenes():
    schedule = runner_module._pacing_schedule(300)

    assert len(schedule) == 28
    assert [item["duration_seconds"] for item in schedule[:12]] == [5] * 12
    assert [item["duration_seconds"] for item in schedule[12:]] == [15] * 16


def test_legacy_pacing_uses_sixty_second_cuts_after_fifteen_minutes():
    schedule = runner_module._pacing_schedule(960)

    assert [item["duration_seconds"] for item in schedule[:12]] == [5] * 12
    assert [item["duration_seconds"] for item in schedule[-1:]] == [60]
    assert sum(item["duration_seconds"] for item in schedule) == 960


@pytest.mark.parametrize("review_failure", [None, "verdict", "evidence"])
def test_staged_runner_preserves_plan_script_media_dependency(monkeypatch, tmp_path, review_failure):
    monkeypatch.setattr(runner_module, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(
        runner_module,
        "_resolve_script_style_directive",
        lambda style: "[Writing Style Directive]\n구수한 테스트 문체\nApply this style strictly throughout the script.",
    )
    calls = []
    import codex_character_assets
    def fake_characters(context, payload, config, output_dir):
        calls.append(("02e_character_images", context))
        return {"main_character": {"name": "연화", "character_key": "yeonhwa", "image_url": "https://assets.example/portrait.png"},
                "supporting_characters": [], "character_image_generation": {"status": "ready"}}
    monkeypatch.setattr(codex_character_assets, "generate_character_references", fake_characters)

    def fake_stage(self, job_id, name, context, task):
        calls.append((name, context))
        if name == "01_plan":
            return {
                "narrative_blueprint": {"logline": "테스트 이야기"},
                "main_character": {"name": "연화"},
                "supporting_characters": [],
                "story_core": {"protagonist": "연화"},
                "scenes": [
                    {"scene_summary": f"사건 {i}", "scene_situation": f"상황 {i}", "scene_purpose": "전진", "scene_emotion": "긴장", "character_choice": "선택", "emotional_shift": "변화", "reveal_or_question": "의문"}
                    for i in range(1, 29)
                ],
            }
        if name in {"02_script", "02b_script_qa"}:
            return {
                "sections": [
                    {"scene_order": i, "text": f"{i}번째 날, 연화는 편지에서 어머니의 흔적을 찾았지요." + (f" 그날의 기록 {i}장을 이웃과 확인하자 헤어졌던 이유가 드러났습니다. 연화는 {i}번째 기록을 듣고 다시 집으로 돌아갈 용기를 얻었지요." if i > 12 else "")}
                    for i in range(1, 29)
                ],
                "script_quality_report": {"verdict": "pass", "score": 90, "critical_issues": []},
            }
        if name == "02c_senior_review":
            report = _review_report()
            if review_failure == "verdict":
                report["verdict"] = "revise"
            elif review_failure == "evidence":
                report["checks"]["relationships"]["evidence"] = ""
            return {"script_quality_report": report}
        if name == '02e_dialogue':
            return {'scenes': [{'scene_number': i, 'spans': []} for i in range(1, 29)]}
        if name.startswith('02f_listener_'):
            assert set(context) == {'title', 'sections'}
            return {'verdict': 'pass', 'issues': [], 'strengths': [{'scene_order': 1,
                'quote': context['sections'][0]['text'], 'reason': 'The protagonist and action are understandable.'}]}
        if name == "03_media":
            assert context["character_anchors"]["character_image_generation"]["status"] == "ready"
            positions = ("Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right")
            grids = []
            for grid_number, start in enumerate(range(1, 29, 4), 1):
                numbers = list(range(start, start + 4))
                grids.append({
                    "grid_number": grid_number,
                    "scene_numbers": numbers,
                    "shared_style": "period folktale visual world with consistent wardrobe, warm lantern lighting, and muted earth palette",
                    "negative_prompt": "no text, no words, no letters, no labels, no captions, no watermarks, No borders, NO grid lines, no dividers, correct anatomy, no extra limbs",
                    "panels": [
                            {"scene_number": number, "position": positions[index], "panel_prompt": f"Scene {number}: a distinct English story beat with a visible action, period setting, emotional expression, lighting direction, and a unique physical prop for continuity."}
                        for index, number in enumerate(numbers)
                    ],
                })
            return {"scenes": [
                    {"scene_order": i, "image_prompt": (f"Scene {i}: Detailed English image prompt with concrete subject action, period setting, lighting, composition, emotion, continuity wardrobe, and unique prop. " * 2), **({"video_prompt": (f"Scene {i}: A continuous period-drama shot showing a character discovering a concrete clue in a lantern-lit courtyard; slow push-in follows restrained hand movement, drifting smoke and fabric respond naturally, focus settles on the clue, then the character holds a stable final pose. no dialogue, no narration, no subtitles, no captions, no music, no sound effects, no audio.")} if i <= 12 else {})}
                for i in range(1, 29)
            ], "image_grid_prompts": grids}
        if name == "05_thumbnail_copy":
            return {
                "thumbnail_hook_texts": ["우물의 비밀", "약속의 진실", "결말의 반전"],
                "thumbnail_hook_reasoning": "핵심 갈등과 반전을 짧게 압축했습니다.",
                "thumbnail_image_prompt": "A cinematic Korean folktale well at night, a frightened young woman holding a worn letter, lantern glow, dramatic close composition, high contrast, no text, no letters, no words, no captions, no watermark",
            }
        return {"publish_metadata": {"description": "테스트 설명입니다. 이 문장은 메타데이터 길이 기준을 만족시키기 위한 충분히 긴 설명이며, 이야기의 갈등과 감정선과 결말의 여운을 자연스럽게 소개합니다. 시청자가 내용을 기대할 수 있도록 인물의 선택과 반전의 분위기를 함께 담았습니다.", "tags": ["옛날이야기"], "hashtags": ["#옛날이야기"]}}

    monkeypatch.setattr(runner_module.CodexStagedContentRunner, "_stage", fake_stage)
    if review_failure:
        with pytest.raises(runner_module.CodexContentError, match="senior listening contract"):
            runner_module.CodexStagedContentRunner().generate("rejected", {"target_duration_seconds": 300, "category_id": 2})
        assert [name for name, _ in calls].count("02b_script_qa") == 2
        assert not any(name == "03_media" for name, _ in calls)
        assert "independent_review_feedback" in next(context for name, context in reversed(calls) if name == "02b_script_qa")
        return
    package = runner_module.CodexStagedContentRunner().generate("staged-job", {"target_duration_seconds": 300, "upload_title": "테스트 제목", "title_generation": {"title_candidates": [{"title": "테스트 제목"}]}, "category_name": "옛날이야기", "script_style": "story"})

    scenes = package["structure"]["scenes"]
    assert [name for name, _ in calls] == ["01_plan", "02_script", "02b_script_qa", "02c_senior_review", "02f_listener_naturalness", "02f_listener_engagement", "02e_dialogue", "02d_character_identity", "02e_character_images", "03_media", "04_metadata", "05_thumbnail_copy"]
    assert package['structure']['dialogue_annotations']['model'] == 'gpt-6-astra'
    assert package["structure"]["character_reference_status"] == "ready"
    assert package["character_anchors"]["character_image_generation"]["status"] == "ready"
    assert package["structure"]["image_grid_prompts"][0]["character_references"][0]["image_url"]
    assert len(scenes) == 28
    assert [scene["duration_seconds"] for scene in scenes[:12]] == [5] * 12
    assert [scene["duration_seconds"] for scene in scenes[12:]] == [15] * 16
    assert all(scene["scene_text"] for scene in scenes)
    assert all(scene.get("video_prompt") for scene in scenes[:12])
    assert all("video_prompt" not in scene for scene in scenes[12:])
    assert "연화" in next(context for name, context in calls if name == '02e_dialogue')["script"]
    assert "Category narration voice: 옛날이야기" in calls[0][1]["category_narration_voice"]
    assert "구수한 테스트 문체" in calls[1][1]["script_style_directive"]
    assert "Script rhythm QA contract" in calls[2][1]["script_rhythm_contract"]
    assert package["thumbnail_hook_texts"] == ["우물의 비밀", "약속의 진실", "결말의 반전"]
    assert package["thumbnail_copy_source"] == "codex-cli"
    assert package["thumbnail_image_prompt"].startswith("A cinematic Korean folktale")
