"""
AI Provider Router

Centralizes Claude/Gemini provider selection so individual routers and services
do not need to inspect model names directly.

Provider detection rule:
  - model name starts with "claude" -> Anthropic Claude
  - everything else                 -> Google Gemini

Fallback rule:
  - Claude call fails -> retry with gemini-2.5-flash
"""

from config import config
from services.claude_service import claude_service
from services.gemini_service import gemini_service

FALLBACK_GEMINI_MODEL = "gemini-2.5-flash"


def detect_provider(model: str) -> str:
    """Return 'claude' or 'gemini' based on model name."""
    if str(model or "").strip().lower().startswith("claude"):
        return "claude"
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
) -> str:
    """Route a text-generation call to the correct provider.

    If model is empty, falls back to gemini-2.5-flash.
    If Claude is selected but fails, falls back to gemini-2.5-flash.
    """
    selected = (model or FALLBACK_GEMINI_MODEL).strip() or FALLBACK_GEMINI_MODEL
    provider = detect_provider(selected)

    if provider == "claude":
        try:
            print(f"🤖 [AI Router] Using Claude for {task_type} (model={selected})")
            return await claude_service.generate_text(
                prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                project_id=project_id,
                task_type=task_type,
                model=selected,
            )
        except Exception as e:
            print(f"⚠️ [AI Router] Claude failed for {task_type}: {e}")
            print(f"🤖 [AI Router] Falling back to Gemini (model={FALLBACK_GEMINI_MODEL})")
            return await gemini_service.generate_text(
                prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                project_id=project_id,
                task_type=task_type,
                model=FALLBACK_GEMINI_MODEL,
                use_search=use_search,
            )

    return await gemini_service.generate_text(
        prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        project_id=project_id,
        task_type=task_type,
        model=selected,
        use_search=use_search,
    )
