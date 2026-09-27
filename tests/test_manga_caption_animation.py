from __future__ import annotations

import copy
import sys
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker"))

import codex_content_runner as planner
import manga_scene_qa as qa
from manga_ae_templates import write_manga_jsx
from manga_caption_animation import (prepare_caption_animation, prepare_sfx_text_animation,
                                    validate_caption_animation, validate_sfx_text_animation)


WORDS = [
    {"text": "그", "start_seconds": .30, "end_seconds": .52},
    {"text": "순간", "start_seconds": .55, "end_seconds": .91},
    {"text": "구역까지", "start_seconds": 1.1, "end_seconds": 1.58},
    {"text": "풀어놓은", "start_seconds": 1.6, "end_seconds": 2.06},
    {"text": "것이었죠", "start_seconds": 2.1, "end_seconds": 2.55},
    {"text": "여기에", "start_seconds": 2.75, "end_seconds": 3.08},
    {"text": "다", "start_seconds": 3.12, "end_seconds": 3.28},
    {"text": "있거든요", "start_seconds": 3.3, "end_seconds": 3.8},
]


def _voice(path: Path) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(b"\x00\x00" * 24000 * 4)


def _captions(path: Path) -> dict:
    _voice(path)
    return prepare_caption_animation(audio_path=path, words=WORDS, duration=4, captions=[
        {"preset": "punctuation_pop", "text": "그 순간", "accent_text": "순간", "position": [.72, .53]},
        {"preset": "brush_phrase", "text": "구역까지 풀어놓은 것이었죠", "accent_text": "구역까지"},
        {"preset": "floating_dialogue", "text": "여기에 다 있거든요", "position": [.7, .49]},
    ])


def test_selected_caption_presets_follow_approved_words_and_render_as_ae_layers(tmp_path):
    captions = _captions(tmp_path / "approved.wav")
    assert captions["captions"][0]["start_seconds"] == .3
    assert captions["captions"][0]["accent_at_seconds"] == .55
    assert captions["captions"][1]["end_seconds"] == 2.55
    assert validate_caption_animation(captions, duration=4) == []
    scene = {"scene_number": 1, "duration_seconds": 4, "scene_text": "주인공이 말한다.",
             "ae_template": "dialogue_closeup", "ae_caption_animation": captions}
    payload = {"character_anchors": {"main_character": {"character_key": "hero", "name": "주인공"}}}
    planner._plan_ae_effects_for_scenes([scene], payload)
    assert scene["ae_effect_plan"]["enabled"]
    assert scene["ae_effect_plan"]["caption_animation"] == captions
    assert qa.validate_scene_plan(scene, {"gcs_path": "scene.psd", "layers": ["background", "character"]}, 4)["passed"]
    jsx = tmp_path / "caption.jsx"
    write_manga_jsx(scene=scene, input_psd=tmp_path / "scene.psd",
                    project_path=tmp_path / "scene.aep", render_path=tmp_path / "scene.mp4",
                    jsx_path=jsx, comp_name="caption", width=1920, height=1080, fps=24, duration=4)
    script = jsx.read_text(encoding="utf-8")
    assert "animatedCaptions(comp);" in script
    assert '"punctuation_pop"' in script and '"brush_phrase"' in script


def test_caption_review_rejects_stale_audio_and_forged_timing(tmp_path):
    captions = _captions(tmp_path / "approved.wav")
    forged = copy.deepcopy(captions)
    forged["captions"][0]["start_seconds"] = .8
    assert any("cues" in issue for issue in validate_caption_animation(forged, duration=4))
    Path(captions["audio_path"]).write_bytes(b"new voice")
    assert any("changed" in issue for issue in validate_caption_animation(captions, duration=4))


def test_caption_matching_is_explicit_and_unambiguous(tmp_path):
    voice = tmp_path / "approved.wav"
    _voice(voice)
    with pytest.raises(ValueError, match="exactly one"):
        prepare_caption_animation(audio_path=voice, words=WORDS + [
            {"text": "그", "start_seconds": 3.82, "end_seconds": 3.88},
            {"text": "순간", "start_seconds": 3.9, "end_seconds": 3.96},
        ], duration=4, captions=[{"preset": "punctuation_pop", "text": "그 순간"}])
    scene = {"scene_number": 1, "duration_seconds": 4, "ae_caption_animation":
             prepare_caption_animation(audio_path=voice, words=WORDS, duration=4,
                                       captions=[{"preset": "headline_punch", "text": "그 순간", "accent_text": "순간"}])}
    with pytest.raises(ValueError, match="explicitly selected"):
        planner._plan_ae_effects_for_scenes([scene], {})


def test_headline_emphasis_starts_on_its_spoken_word(tmp_path):
    voice = tmp_path / "headline.wav"
    _voice(voice)
    plan = prepare_caption_animation(audio_path=voice, words=WORDS, duration=4,
                                     captions=[{"preset": "headline_punch", "text": "그 순간",
                                                "accent_text": "순간"}])
    assert plan["captions"][0]["accent_at_seconds"] == .55
    assert validate_caption_animation(plan, duration=4) == []
    with pytest.raises(ValueError, match="accent_text"):
        prepare_caption_animation(audio_path=voice, words=WORDS, duration=4,
                                  captions=[{"preset": "headline_punch", "text": "그 순간"}])


def test_sfx_onomatopoeia_is_timed_from_effect_event_and_rendered_in_ae(tmp_path):
    animation = prepare_sfx_text_animation(
        sfx_events=[{"id": "wall-hit-1", "label": "벽 충돌", "start_seconds": 1.2, "end_seconds": 1.55}],
        cues=[{"text": "쿵!", "preset": "sfx_impact", "sfx_event_id": "wall-hit-1",
               "offset_seconds": 0, "hold_seconds": .72, "position": [.56, .44]}],
        duration=4,
    )
    assert animation["method"] == "scene_sfx_event_timing"
    assert animation["cues"][0]["start_seconds"] == 1.2
    assert animation["cues"][0]["end_seconds"] == 1.92
    assert validate_sfx_text_animation(animation, duration=4) == []

    scene = {"scene_number": 1, "duration_seconds": 4, "scene_text": "주인공 앞에서 벽이 무너졌다.",
             "ae_template": "dialogue_closeup", "ae_sfx_text_animation": animation}
    payload = {"character_anchors": {"main_character": {"character_key": "hero", "name": "주인공"}}}
    planner._plan_ae_effects_for_scenes([scene], payload)
    plan = scene["ae_effect_plan"]
    assert plan["sfx_text_animation"] == animation
    assert qa.validate_scene_plan(scene, {"gcs_path": "scene.psd", "layers": ["background", "character"]}, 4)["passed"]
    jsx = tmp_path / "sfx-caption.jsx"
    write_manga_jsx(scene=scene, input_psd=tmp_path / "scene.psd",
                    project_path=tmp_path / "scene.aep", render_path=tmp_path / "scene.mp4",
                    jsx_path=jsx, comp_name="sfx", width=1920, height=1080, fps=24, duration=4)
    script = jsx.read_text(encoding="utf-8")
    assert "animatedSfxText(comp);" in script
    assert '"sfx_text_animation"' in script and '"sfx_impact"' in script


def test_sfx_onomatopoeia_rejects_missing_event_and_out_of_scene_timing():
    events = [{"id": "hit", "label": "타격", "start_seconds": 1, "end_seconds": 1.2}]
    with pytest.raises(ValueError, match="known sound-effect event"):
        prepare_sfx_text_animation(sfx_events=events, duration=3,
                                   cues=[{"text": "쿵", "preset": "sfx_impact", "sfx_event_id": "missing"}])
    with pytest.raises(ValueError, match="within the scene"):
        prepare_sfx_text_animation(
            sfx_events=[{"id": "hit", "label": "타격", "start_seconds": 2.8, "end_seconds": 3}],
            duration=3,
            cues=[{"text": "쿵", "preset": "sfx_impact", "sfx_event_id": "hit", "hold_seconds": .5}],
        )
