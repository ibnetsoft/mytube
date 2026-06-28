import asyncio
from unittest.mock import AsyncMock

from services.ai_provider import AISelection, normalize_provider, resolve_ai_selection
from services.gemini_service import gemini_service


def test_normalize_provider_defaults_to_gemini():
    assert normalize_provider(None) == "gemini"
    assert normalize_provider("claude") == "claude"
    assert normalize_provider("invalid-provider") == "gemini"


def test_resolve_ai_selection_prefers_project_settings(monkeypatch):
    monkeypatch.setattr("services.ai_provider.db.get_project_settings", lambda project_id: {
        "script_generation_provider": "claude",
        "script_generation_model": "claude-sonnet-4-6",
    })
    monkeypatch.setattr("services.ai_provider.db.get_global_setting", lambda key: None)
    selection = resolve_ai_selection("script_generation", project_id=123)
    assert selection.provider == "claude"
    assert selection.model == "claude-sonnet-4-6"


def test_generate_script_structure_forwards_provider_and_model(monkeypatch):
    async_mock = AsyncMock(return_value='{"hook":"hook","sections":[],"cta":"cta","style":"story","duration":60}')
    monkeypatch.setattr(gemini_service, "_generate_text_for_task", async_mock)
    monkeypatch.setattr("services.gemini_service.db.get_recent_projects", lambda limit=5: [])
    monkeypatch.setattr("services.gemini_service.db.get_recent_knowledge", lambda limit=10, script_style=None: [])
    monkeypatch.setattr("services.gemini_service.db.get_analysis", lambda project_id: None)
    monkeypatch.setattr("services.gemini_service.db.add_ai_log", lambda *args, **kwargs: None)
    monkeypatch.setattr("services.gemini_service.prompts.GEMINI_SCRIPT_STRUCTURE", "{topic_keyword}{user_notes}{specialized_instruction}{duration_seconds}{min_sections}{custom_prompt_section}{knowledge_instruction}{success_strategy_json}{target_language_context}{history_instruction}{available_image_styles_info}")
    monkeypatch.setattr("services.gemini_service.prompts.GEMINI_EXTRACT_STRATEGY", "{analysis_json}")
    monkeypatch.setattr("services.gemini_service.gemini_service._get_available_image_styles_info", lambda: "- realistic")

    result = asyncio.run(gemini_service.generate_script_structure(
        {"topic": "Test Topic", "duration": 60, "script_style": "story"},
        project_id=7,
        provider="claude",
        model="claude-sonnet-4-6",
    ))

    assert result["hook"] == "hook"
    assert async_mock.await_args.kwargs["provider"] == "claude"
    assert async_mock.await_args.kwargs["model"] == "claude-sonnet-4-6"


def test_generate_image_prompts_forwards_provider_and_model(monkeypatch):
    async_mock = AsyncMock(return_value='{"scenes":[{"scene_number":1,"scene_text":"A","prompt_en":"B"}]}')
    monkeypatch.setattr(gemini_service, "_generate_text_for_task", async_mock)
    monkeypatch.setattr("services.gemini_service.db.get_project_settings", lambda project_id: {"aspect_ratio": "16:9"})
    monkeypatch.setattr("services.gemini_service.prompt_assembler.assemble_scene_prompt", lambda **kwargs: {"prompt_en": "prompt"})
    monkeypatch.setattr("services.gemini_service.gemini_service._cleanup_prompt", lambda text: text)
    monkeypatch.setattr("services.gemini_service.db.add_ai_log", lambda *args, **kwargs: None)

    result = asyncio.run(gemini_service.generate_image_prompts_from_script(
        "script text",
        60,
        target_scene_count=1,
        project_id=8,
        provider="claude",
        model="claude-sonnet-4-6",
    ))

    assert isinstance(result, list)
    assert async_mock.await_args.kwargs["provider"] == "claude"
    assert async_mock.await_args.kwargs["model"] == "claude-sonnet-4-6"
