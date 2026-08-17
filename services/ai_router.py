"""
AI Provider Router.

Provider detection:
- model starts with "claude" -> Anthropic Claude
- model starts with "glm" -> GLM/Zhipu
- model starts with "deepseek" -> DeepSeek
- everything else -> Google Gemini
"""

from config import config
from services.claude_service import claude_service
from services.deepseek_service import deepseek_service
from services.gemini_service import gemini_service
from services.glm_service import glm_service

FALLBACK_GEMINI_MODEL = "gemini-3-flash-preview"
FALLBACK_DEEPSEEK_MODEL = "deepseek-chat"
FALLBACK_GLM_MODEL = "glm-5.2"
UNAVAILABLE_GEMINI_MODELS = {
    "gemini-2.0-flash",
    "gemini-2.5-pro",
}


def _has_glm_key() -> bool:
    return bool((getattr(config, "GLM_API_KEY", "") or "").strip())


def _has_deepseek_key() -> bool:
    return bool((getattr(config, "DEEPSEEK_API_KEY", "") or "").strip())


def fallback_text_model() -> str:
    if _has_deepseek_key():
        return FALLBACK_DEEPSEEK_MODEL
    return FALLBACK_GLM_MODEL if _has_glm_key() else FALLBACK_GEMINI_MODEL


def normalize_model(model: str) -> str:
    """Normalize text model choice without changing the requested provider."""
    selected = str(model or "").strip()
    selected_lower = selected.lower()
    if selected_lower in UNAVAILABLE_GEMINI_MODELS:
        return FALLBACK_GEMINI_MODEL
    return selected or fallback_text_model()


def detect_provider(model: str) -> str:
    selected = str(model or "").strip().lower()
    if selected.startswith("claude"):
        return "claude"
    if selected.startswith("deepseek"):
        return "deepseek"
    if selected.startswith("glm"):
        return "glm"
    return "gemini"


async def generate_text(
    prompt: str,
    model: str,
    *,
    temperature: float = 0.7,
    max_tokens: int = 8192,
    project_id: int = None,
    task_type: str = "text_gen",
    use_search: bool = False,
    json_mode: bool = False,
) -> str:
    """Route a text-generation call to the selected provider."""
    selected = normalize_model(model)
    provider = detect_provider(selected)

    if provider == "claude":
        try:
            print(f"[AI Router] Using Claude for {task_type} (model={selected})")
            return await claude_service.generate_text(
                prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                project_id=project_id,
                task_type=task_type,
                model=selected,
            )
        except Exception as exc:
            fallback_model = fallback_text_model()
            fallback_provider = detect_provider(fallback_model)
            print(f"[AI Router] Claude failed for {task_type}: {exc}")
            print(f"[AI Router] Falling back to {fallback_provider.upper()} (model={fallback_model})")
            if fallback_provider == "deepseek":
                return await deepseek_service.generate_text(
                    prompt,
                    model=fallback_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    task_type=task_type,
                    json_mode=json_mode,
                    project_id=project_id,
                )
            if fallback_provider == "glm":
                return await glm_service.generate_text(
                    prompt,
                    model=fallback_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    task_type=task_type,
                    json_mode=json_mode,
                    project_id=project_id,
                )
            return await gemini_service.generate_text(
                prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                project_id=project_id,
                task_type=task_type,
                model=fallback_model,
                use_search=use_search,
                json_mode=json_mode,
            )

    if provider == "deepseek":
        if use_search:
            print(
                f"[AI Router] DeepSeek does not support Gemini search grounding; "
                f"running plain text generation for {task_type}"
            )
        print(f"[AI Router] Using DeepSeek for {task_type} (model={selected})")
        return await deepseek_service.generate_text(
            prompt,
            model=selected,
            temperature=temperature,
            max_tokens=max_tokens,
            task_type=task_type,
            json_mode=json_mode,
            project_id=project_id,
        )

    if provider == "glm":
        if use_search:
            print(
                f"[AI Router] GLM does not support Gemini search grounding; "
                f"running plain text generation for {task_type}"
            )
        print(f"[AI Router] Using GLM for {task_type} (model={selected})")
        return await glm_service.generate_text(
            prompt,
            model=selected,
            temperature=temperature,
            max_tokens=max_tokens,
            task_type=task_type,
            json_mode=json_mode,
            project_id=project_id,
        )

    print(f"[AI Router] Using Gemini for {task_type} (model={selected})")
    return await gemini_service.generate_text(
        prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        project_id=project_id,
        task_type=task_type,
        model=selected,
        use_search=use_search,
        json_mode=json_mode,
    )
