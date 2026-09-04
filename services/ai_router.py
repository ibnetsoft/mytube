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


class ProviderCreditExhaustedError(RuntimeError):
    """A provider rejected a request because its paid balance is unavailable.

    This is deliberately distinct from ordinary provider errors.  Callers use
    it to stop a job instead of silently changing the model/provider or
    manufacturing a fallback result.
    """

    def __init__(self, provider: str, cause: Exception | str):
        self.provider = str(provider or "AI provider")
        self.cause = str(cause or "")
        super().__init__(
            f"{self.provider} API 크레딧 또는 잔액이 부족합니다. "
            "충전 또는 결제 상태를 확인한 뒤 작업을 다시 실행하세요. "
            f"(provider error: {self.cause[:500]})"
        )


def is_credit_exhaustion_error(exc: Exception | str) -> bool:
    """Return true only for billing/credit exhaustion, never rate limits."""
    message = str(exc or "").lower()
    return (
        " 402" in message
        or "(402" in message
        or "status=402" in message
        or "status 402" in message
        or "insufficient balance" in message
        or "insufficient credit" in message
        or "credit exhausted" in message
        or "balance exhausted" in message
        or "billing hard limit" in message
        or "잔액 부족" in message
        or "크레딧 부족" in message
        or "余额不足" in message
    )


def raise_if_credit_exhausted(provider: str, exc: Exception) -> None:
    if is_credit_exhaustion_error(exc):
        raise ProviderCreditExhaustedError(provider, exc) from exc


def _has_glm_key() -> bool:
    return bool((getattr(config, "GLM_API_KEY", "") or "").strip())


def _has_deepseek_key() -> bool:
    return bool((getattr(config, "DEEPSEEK_API_KEY", "") or "").strip())


def fallback_text_model(exclude_provider: str | None = None) -> str:
    excluded = {str(exclude_provider or "").strip().lower()} if exclude_provider else set()
    if "deepseek" not in excluded and _has_deepseek_key():
        return FALLBACK_DEEPSEEK_MODEL
    if "glm" not in excluded and _has_glm_key():
        return FALLBACK_GLM_MODEL
    return FALLBACK_GEMINI_MODEL


def normalize_model(model: str) -> str:
    """Normalize an explicitly selected model; never choose a replacement."""
    selected = str(model or "").strip()
    if not selected:
        raise ValueError("No AI model selected; generation stopped because provider fallback is disabled")
    selected_lower = selected.lower()
    if selected_lower in UNAVAILABLE_GEMINI_MODELS:
        raise ValueError(f"Selected model is unavailable: {selected}")
    return selected


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
            raise_if_credit_exhausted("Claude", exc)
            raise RuntimeError(f"Claude generation failed for {task_type}; no provider fallback is allowed: {exc}") from exc

    if provider == "deepseek":
        if use_search:
            print(
                f"[AI Router] DeepSeek does not support Gemini search grounding; "
                f"running plain text generation for {task_type}"
            )
        print(f"[AI Router] Using DeepSeek for {task_type} (model={selected})")
        try:
            return await deepseek_service.generate_text(
                prompt,
                model=selected,
                temperature=temperature,
                max_tokens=max_tokens,
                task_type=task_type,
                json_mode=json_mode,
                project_id=project_id,
            )
        except Exception as exc:
            raise_if_credit_exhausted("DeepSeek", exc)
            raise RuntimeError(f"DeepSeek generation failed for {task_type}; no provider fallback is allowed: {exc}") from exc

    if provider == "glm":
        if use_search:
            print(
                f"[AI Router] GLM does not support Gemini search grounding; "
                f"running plain text generation for {task_type}"
            )
        print(f"[AI Router] Using GLM for {task_type} (model={selected})")
        try:
            return await glm_service.generate_text(
                prompt,
                model=selected,
                temperature=temperature,
                max_tokens=max_tokens,
                task_type=task_type,
                json_mode=json_mode,
                project_id=project_id,
            )
        except Exception as exc:
            raise_if_credit_exhausted("GLM", exc)
            raise

    print(f"[AI Router] Using Gemini for {task_type} (model={selected})")
    try:
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
    except Exception as exc:
        raise_if_credit_exhausted("Gemini", exc)
        raise
