from services.prompt_store import prompt_store


def test_prompt_store_loads_claude_wrapper():
    prompt = prompt_store.build_prompt("script_plan", "claude", "BASE")
    assert "Claude longform script-plan wrapper" in prompt
    assert prompt.endswith("BASE")


def test_prompt_store_loads_gemini_wrapper():
    prompt = prompt_store.build_prompt("image_prompt", "gemini", "BASE")
    assert "Gemini longform image-prompt wrapper" in prompt
    assert prompt.endswith("BASE")


def test_prompt_store_falls_back_to_gemini_wrapper():
    prompt = prompt_store.build_prompt("script_generation", "unknown-provider", "BASE")
    assert "Gemini longform script-generation wrapper" in prompt
