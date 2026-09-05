import sys
from pathlib import Path
import asyncio

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = ROOT / "worker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

import hermes_worker  # noqa: E402
from services.hermes_offline_harness import build_valid_sample_payload  # noqa: E402


class _FakeLog:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(("info", message))

    def warning(self, message):
        self.messages.append(("warning", message))


class _FakeResponse:
    status_code = 204
    text = ""


class _VisualPlanRouter:
    async def generate_text(self, *_args, **_kwargs):
        return """{
            "overall_vision": "A grounded visual sequence",
            "category_visual_grammar": "Natural documentary framing",
            "recurring_characters": ["Keep the lead consistent"],
            "recurring_locations": ["Keep the village consistent"],
            "continuity_anchors": ["Preserve wardrobe and props"],
            "palette": "Muted earth tones",
            "camera_language": ["Slow push-in", "GENTLE PAN"],
            "negative_prompt": "No text or logos"
        }"""


def test_visual_direction_plan_normalizes_approved_camera_language_case():
    plan = hermes_worker._build_visual_direction_plan(
        _VisualPlanRouter(),
        "test-model",
        "topic",
        "title",
        {"scenes": []},
        "realistic",
        "realistic image style",
        "ko",
    )

    assert plan["camera_language"] == ["slow push-in", "gentle pan"]


def test_scene_length_accepts_bounded_twenty_percent_variance():
    text = "가" * 60

    assert hermes_worker._ensure_scene_section_target_length(text, {}, 72) == text

    with pytest.raises(RuntimeError, match="minimum accepted 58"):
        hermes_worker._ensure_scene_section_target_length("가" * 57, {}, 72)


def test_remote_script_result_omits_large_media_structure():
    payload = {
        "topic_queue_id": "3290",
        "script": "완성 대본",
        "script_quality_report": {"verdict": "pass", "score": 90},
        "structure": {"scenes": [{"media_prompt": "x" * 1_000_000}]},
        "supporting_characters": ["large generated anchors"],
    }

    compact = hermes_worker._compact_remote_result_payload("script_generate", payload)

    assert compact["script"] == "완성 대본"
    assert compact["script_quality_report"]["verdict"] == "pass"
    assert "structure" not in compact
    assert "supporting_characters" not in compact


def test_script_plan_stage_rejects_repeated_scene_summaries():
    structure = {
        "scenes": [
            {
                "scene_summary": "같은 장면이 반복된다",
                "scene_purpose": f"목적 {idx}",
                "retention_hook": f"훅 {idx}",
            }
            for idx in range(4)
        ]
    }

    with pytest.raises(RuntimeError, match="script_plan quality gate failed"):
        hermes_worker._validate_script_plan_stage(
            structure,
            script_style="옛날이야기",
            topic="옛날 마을의 숨겨진 약속",
            upload_title="옛날 마을의 숨겨진 약속",
            image_style="folk tale",
        )


def test_script_plan_stage_rejects_repeated_scene_situations_and_visuals():
    structure = {
        "scenes": [
            {
                "scene_summary": f"unique summary {idx}",
                "scene_purpose": f"unique purpose {idx}",
                "retention_hook": f"unique hook {idx}",
                "scene_situation": (
                    "Timed visual beat 13 (60-75s, 15s). Keep it separate and advance the story: "
                    "the same woodcutter meets the same child in the same yard."
                ),
                "visual_direction": (
                    "Mandatory 15-second development phase cut. Use a distinct composition, action, "
                    "or camera beat. the same warm moonlit yard composition."
                ),
            }
            for idx in range(3)
        ]
    }

    with pytest.raises(RuntimeError, match="script_plan quality gate failed"):
        hermes_worker._validate_script_plan_stage(
            structure,
            script_style="old_story",
            topic="old mountain spirit tale",
            upload_title="woodcutter mountain spirit condition",
            image_style="folk tale",
        )


def test_japanese_folktale_plan_rejects_pension_scene_contamination():
    structure = {
        "scenes": [
            {
                "scene_summary": f"年金計算書を確認する場面 {idx}",
                "scene_situation": f"老夫婦が生活費と年金を計算する {idx}",
                "scene_purpose": f"年金制度を説明する {idx}",
                "retention_hook": f"受給額はいくらになるのか {idx}",
            }
            for idx in range(1, 4)
        ]
    }

    with pytest.raises(RuntimeError, match="finance/pension contamination"):
        hermes_worker._validate_script_plan_stage(
            structure,
            script_style="Japanese traditional folklore",
            topic="吹雪の夜に死んだ息子が帰ってきた",
            upload_title="吹雪の夜、三十年前に死んだ息子が戸を叩いた",
            image_style="Japanese folktale",
            category="日本昔話",
        )


def test_script_generate_stage_blocks_revise_quality_report():
    payload = build_valid_sample_payload("옛날이야기")
    payload["script_quality_report"] = {
        "verdict": "revise",
        "score": 42,
        "critical_issues": ["제목과 대본이 완전히 단절됨"],
    }

    with pytest.raises(RuntimeError, match="script quality report not passing"):
        hermes_worker._validate_script_generate_stage(payload, category="옛날이야기")


def test_script_plan_rejects_finance_content_before_model_generation():
    with pytest.raises(ValueError, match="finance/pension content is prohibited before generation"):
        hermes_worker._validate_script_plan_payload(
            {
                "topic_queue_id": "123",
                "topic": "국민연금 수령액을 바꾼 선택",
                "upload_title": "국민연금 수령액을 바꾼 선택",
            }
        )


def test_old_story_short_plan_places_midpoint_and_payoff_proportionally():
    title = "산속 우물에서 들린 아이의 노래와 나무꾼의 약속"
    structure = {
        "scenes": [
            {"scene_order": index, "scene_summary": f"{index}번째 사건", "scene_situation": f"{index}번째 사건"}
            for index in range(1, 16)
        ]
    }

    repaired = hermes_worker._apply_old_story_story_core_to_structure(structure, title, title)

    assert not hermes_worker._old_story_drama_plan_errors(repaired, title, title)


def test_old_story_four_scene_plan_has_reachable_midpoint_and_payoff():
    title = "장터에서 산 낡은 비녀가 알려 준 어머니의 약속"
    structure = {
        "scenes": [
            {"scene_order": index, "scene_summary": f"{index}번째 사건", "scene_situation": f"{index}번째 사건"}
            for index in range(1, 5)
        ]
    }

    repaired = hermes_worker._apply_old_story_story_core_to_structure(structure, title, title)

    assert repaired["scenes"][1]["dramatic_function"] == "midpoint reversal"
    assert repaired["scenes"][-1]["dramatic_function"] == "final payoff"
    assert repaired["story_core"]["acts"][-1]["scene_range"] == "4-4"
    assert not hermes_worker._old_story_drama_plan_errors(repaired, title, title)


def test_script_generate_stage_rejects_finance_content_for_every_category():
    payload = build_valid_sample_payload("무협")
    payload["script"] += " 국민연금 수령액을 확인했다."

    with pytest.raises(RuntimeError, match="finance/pension contamination is prohibited in every category"):
        hermes_worker._validate_script_generate_stage(payload, category="무협")


def test_script_generate_stage_rejects_missing_2x2_grid_prompts():
    payload = build_valid_sample_payload("옛날이야기")
    payload["structure"]["image_grid_prompts"] = []

    with pytest.raises(RuntimeError, match="image_grid_prompts"):
        hermes_worker._validate_script_generate_stage(payload, category="옛날이야기")


def test_script_language_stats_detects_excessive_latin():
    script = ("이 문장은 한국어 대본입니다. " * 80) + ("This English sentence should not dominate the Korean script. " * 40)

    assert hermes_worker._script_has_excessive_latin(script)


def test_script_revision_keeps_revise_verdict_even_without_critical_issues():
    assert hermes_worker._script_needs_revision(
        {"verdict": "revise", "score": 95, "critical_issues": []}
    )
    assert not hermes_worker._script_needs_revision(
        {"verdict": "manual_override", "score": 0, "critical_issues": ["approved"]}
    )


def test_deduplicate_script_text_handles_korean_words_ending_in_da():
    repeated_sentence = ("그는 바다 근처에서 단서를 찾으며 다음 선택을 고민했다 " * 24).strip() + "."
    source = f"{repeated_sentence} {repeated_sentence}"

    result = hermes_worker._deduplicate_script_text(
        source,
        [{"sentence": repeated_sentence, "count": 2}],
    )

    assert result == repeated_sentence


def test_cleanup_section_text_preserves_japanese_cjk_characters_and_punctuation():
    source = "彼は「海」へ行った。カタカナ、漢字。"

    assert hermes_worker._clean_section_text(source, is_multi=False) == source


def test_korean_language_rescue_script_passes_latin_gate():
    payload = build_valid_sample_payload("탈북사연")
    title = payload["generated_title"]

    script = hermes_worker._build_korean_language_rescue_script(
        title,
        title,
        payload["structure"],
    )
    stats = hermes_worker._script_language_stats(script)

    assert stats["hangul"] >= 1000
    assert not hermes_worker._script_has_excessive_latin(script)


@pytest.mark.parametrize(
    ("builder", "topic", "title"),
    [
        (hermes_worker._build_korean_language_rescue_script, "주제", "제목"),
        (hermes_worker._build_japanese_language_rescue_script, "テーマ", "タイトル"),
    ],
)
def test_language_rescue_scripts_honor_requested_minimum_length(builder, topic, title):
    assert len(builder(topic, title, {}, min_total_chars=10_000)) >= 10_000


def test_emotion_cue_normalizer_repairs_dialogue_and_long_narration():
    paragraphs = [
        "주인공은 오래된 편지를 펼치며 숨겨진 진실을 마주했습니다. 그는 한동안 아무 말도 하지 못했습니다.",
        '마침내 그는 고개를 들고 "제발 이제는 진실을 말해주세요!"라고 부탁했습니다.',
        "상대는 지난 선택을 후회했고, 두 사람은 서로의 눈을 피하지 않은 채 마지막 결정을 내렸습니다.",
    ] * 18
    source = "\n\n".join(paragraphs) + "\n\n(음악) (철수) 화면이 어두워집니다."

    normalized = hermes_worker._ensure_script_emotion_cues(source, "ko")

    assert "(음악)" not in normalized
    assert "(철수)" not in normalized
    assert hermes_worker._script_emotion_cue_count(normalized, "ko") >= hermes_worker._required_script_emotion_cue_count(normalized)
    assert not hermes_worker._script_emotion_cue_errors(normalized, "ko")
    quote_index = normalized.index('"제발 이제는 진실을 말해주세요!"')
    assert hermes_worker._has_trailing_script_emotion_cue(normalized[max(0, quote_index - 80):quote_index], "ko")


def test_emotion_cue_normalizer_preserves_existing_dialogue_cue_without_duplication():
    source = '(울먹이며) "제발 가지 마세요!" 그녀는 마지막 인사를 건넸습니다.'

    normalized = hermes_worker._ensure_script_emotion_cues(source, "ko")

    assert normalized.count("(울먹이며)") == 1
    assert '(울먹이며) "제발 가지 마세요!"' in normalized
    assert not hermes_worker._script_emotion_cue_errors(normalized, "ko")


@pytest.mark.parametrize(
    ("language", "source", "expected_cue"),
    [
        ("en", 'He finally said, "Tell me the truth!" The room went silent.', "(firmly)"),
        ("ja", '彼はようやく顔を上げて「真実を話してください！」と告げました。', "(きっぱりと)"),
    ],
)
def test_emotion_cue_normalizer_uses_output_language(language, source, expected_cue):
    normalized = hermes_worker._ensure_script_emotion_cues(source, language)

    assert expected_cue in normalized
    assert not hermes_worker._script_emotion_cue_errors(normalized, language)


def test_korean_money_uses_sino_korean_tens_without_changing_age_counters():
    source = "올해 예순다섯 살인 영애는 한 달에 예순몇만원, 남편은 예순다섯만원을 받았습니다."

    normalized = hermes_worker._ensure_script_emotion_cues(source, "ko")

    assert "예순다섯 살" in normalized
    assert "육십몇만 원" in normalized
    assert "육십오만 원" in normalized
    assert "예순몇" not in normalized


@pytest.mark.parametrize(
    ("category", "language", "expected"),
    [
        ("무협", "ko", "강호 chronicler"),
        ("옛날이야기", "ko", "fireside Korean folktale storyteller"),
        ("English Folktales", "en", "English fireside folktale narrator"),
        ("日本昔話", "ja", "mukashibanashi storyteller"),
    ],
)
def test_script_category_persona_varies_by_category(category, language, expected):
    instruction = hermes_worker._script_category_persona_instruction(category, language)

    assert expected in instruction
    assert "core Hermes identity" in instruction


def test_script_chunk_prompt_includes_category_persona_overlay():
    scenes = [
        {
            "scene_order": 1,
            "scene_situation": "낡은 객잔에서 검은 봉인이 발견된다.",
            "scene_purpose": "주인공이 강호의 위협을 처음 마주한다.",
        }
    ]
    budgets = [{"scene_order": 1, "duration_seconds": 30, "target_chars": 120, "min_chars": 80, "max_chars": 180}]
    persona = hermes_worker._script_category_persona_instruction("무협", "ko")

    prompt = hermes_worker._build_script_chunk_prompt(
        "검은 봉인의 비밀",
        scenes,
        budgets,
        False,
        False,
        [],
        "30초 분량으로 작성하세요.",
        "ko",
        upload_title="낡은 객잔에서 열린 검은 봉인",
        category_persona_instruction=persona,
    )

    assert "[헤르메스 카테고리 페르소나]" in prompt
    assert "강호 chronicler" in prompt
    assert prompt.index("[헤르메스 카테고리 페르소나]") < prompt.index("[WRITING RULES]")


def test_script_generate_stage_rejects_missing_emotion_cues_and_accepts_normalized_script():
    payload = build_valid_sample_payload("옛날이야기")
    payload["script"] = payload["script"].replace("(차분하게) ", "")

    with pytest.raises(RuntimeError, match="script emotion cues missing"):
        hermes_worker._validate_script_generate_stage(payload, category="옛날이야기")

    payload["script"] = hermes_worker._ensure_script_emotion_cues(payload["script"], "ko")
    report = hermes_worker._validate_script_generate_stage(payload, category="옛날이야기")

    assert report["status"] == "pass"


def test_web_script_cleaner_uses_shared_emotion_cue_normalization():
    template = (ROOT / "templates" / "pages" / "script_gen.html").read_text(encoding="utf-8")

    assert "normalizeScriptEmotionCues(text)" in template
    assert "SCRIPT_EMOTION_CUE_KEYWORDS" in template
    assert "const emotionTags =" not in template


def test_publish_metadata_stage_requires_script_quality_for_quality_gated_job():
    payload = build_valid_sample_payload("옛날이야기")
    payload.pop("script_quality_report", None)
    payload["defer_ready_until_quality_gate"] = True

    with pytest.raises(RuntimeError, match="missing script_quality_report"):
        hermes_worker._validate_publish_metadata_stage(payload, category="옛날이야기")


def test_publish_metadata_stage_accepts_complete_package():
    payload = build_valid_sample_payload("옛날이야기")
    payload["defer_ready_until_quality_gate"] = True

    report = hermes_worker._validate_publish_metadata_stage(payload, category="옛날이야기")

    assert report["status"] == "pass"
    assert report["stage"] == "publish_metadata"


def test_script_generate_defers_supabase_ready_sync_when_quality_gated(monkeypatch):
    import requests

    calls = []

    def fake_patch(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakeResponse()

    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role")
    monkeypatch.setattr(requests, "patch", fake_patch)

    payload = build_valid_sample_payload("옛날이야기")
    payload["topic_queue_id"] = "123"
    payload["defer_ready_until_quality_gate"] = True

    hermes_worker._save_result_to_supabase("script_generate", payload, _FakeLog())

    assert calls == []


def test_publish_metadata_syncs_full_prepared_package_even_when_quality_gated(monkeypatch):
    import requests

    calls = []

    def fake_patch(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakeResponse()

    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role")
    monkeypatch.setattr(requests, "patch", fake_patch)

    payload = build_valid_sample_payload("무협")
    payload.update(
        {
            "topic_queue_id": "3285",
            "topic": "버림받은 삼류무사가 사부의 낡은 검보를 펼친 날",
            "generated_title": "버림받은 삼류무사가 사부의 낡은 검보를 펼친 날",
            "upload_title": "버림받은 삼류무사가 사부의 낡은 검보를 펼친 날",
            "narrative_blueprint": {"protagonist": "삼류무사"},
            "defer_ready_until_quality_gate": True,
        }
    )
    payload["structure"]["main_character"] = {
        "name": "무진",
        "role": "protagonist",
        "visual_dna_en": "Korean swordsman with a lean build and tired eyes",
        "wardrobe_en": "worn gray martial robe",
    }
    payload["structure"]["supporting_characters"] = [
        {
            "name": "사부",
            "role": "mentor",
            "visual_dna_en": "elderly Korean master with white hair",
            "wardrobe_en": "plain dark robe",
        }
    ]

    hermes_worker._save_result_to_supabase("publish_metadata_generate", payload, _FakeLog())

    assert len(calls) == 1
    patch_payload = calls[0][1]["json"]
    assert patch_payload["status"] == "pending"
    assert patch_payload["pregenerated_script"] == payload["script"]
    assert patch_payload["pregenerated_script_status"] == "ready"
    assert patch_payload["pregenerated_structure"] == payload["structure"]
    assert patch_payload["pregenerated_structure_status"] == "ready"
    assert patch_payload["publish_metadata"] == payload["publish_metadata"]
    assert patch_payload["generated_title"] == payload["generated_title"]
    assert patch_payload["total_scenes"] == len(payload["structure"]["scenes"])
    assert patch_payload["progress_payload"]["prepared_topic_ready"] is True
    assert patch_payload["progress_payload"]["main_character"]["name"] == "무진"
    assert patch_payload["progress_payload"]["supporting_characters"][0]["name"] == "사부"
    assert patch_payload["progress_payload"]["character_anchors"]["max_character_anchors"] == 3


def test_short_scene_is_rejected_instead_of_being_padded_with_template_text():
    scene = {
        "scene_situation": "덕수는 어머니의 비녀가 사라진 방에서 낡은 장부를 발견한다",
        "character_choice": "덕수는 장부를 들고 마을 어른을 찾아간다",
        "emotional_shift": "의심이 두려움으로 바뀐다",
        "reveal_or_question": "장부에는 비녀를 맡긴 사람의 이름이 적혀 있다",
    }

    with pytest.raises(RuntimeError, match="will not be padded"):
        hermes_worker._ensure_scene_section_target_length(
            "덕수는 비녀가 사라진 자리를 한참 바라봤다.",
            scene,
            260,
            language="ko",
        )


def test_scene_length_helper_does_not_create_a_script_fallback():
    with pytest.raises(RuntimeError, match="will not be padded"):
        hermes_worker._ensure_scene_section_target_length("", {}, 80)


def test_scene_length_helper_allows_bounded_narration_variance():
    text = "가" * 98

    assert hermes_worker._ensure_scene_section_target_length(text, {}, 114) == text


def test_script_jobs_support_scoped_model_override_and_smaller_longform_chunks():
    import inspect

    source = inspect.getsource(hermes_worker._process_script_generate)
    assert 'get("ai_model_override")' in source
    assert "8 if len(scenes) >= 40 else 4" in source
    assert "model_override=job_model_override" in source
    rewrite_source = inspect.getsource(hermes_worker._revise_script_sections)
    assert '.get("min_chars") or 80' in rewrite_source


def test_script_quality_retries_malformed_json_response():
    class Router:
        def __init__(self):
            self.calls = 0
            self.kwargs = []

        async def generate_text(self, *_args, **_kwargs):
            self.calls += 1
            self.kwargs.append(_kwargs)
            if self.calls == 1:
                return "not-json"
            return '{"score": 90, "verdict": "pass", "critical_issues": [], "strengths": [], "revision_notes": []}'

    router = Router()
    report = asyncio.run(hermes_worker._evaluate_script_quality(
        router,
        "gemini-3-flash-preview",
        "topic",
        "title",
        {},
        {"scenes": []},
        "(차분하게) 충분히 구체적인 테스트 대본입니다.",
        "ko",
    ))

    assert router.calls == 2
    assert all(call["json_mode"] is True for call in router.kwargs)
    assert report["verdict"] == "pass"
