# AI Provider Strategy

## Goal
Keep Gemini as the safe default for Longform Mode while allowing Claude to be selected for prompt-heavy planning and generation work.

## Current Rule
- `gemini` is the default provider.
- `claude` is an opt-in provider.
- Invalid provider values normalize back to `gemini`.

## Scope
The provider selection path currently covers:
- script planning
- script generation
- image-prompt generation

## Stored Settings
Current project/admin settings use these values:
- `script_generation_provider`
- `script_generation_model`
- `image_prompt_provider`

The model value is intentionally configurable because Claude model names may change and should not be hardcoded everywhere.

## Runtime Behavior
- If `claude` is selected and the model is missing or invalid, the runtime falls back to a safe Claude default.
- If `gemini` is selected and the model is missing or invalid, the runtime falls back to Gemini defaults.
- If Claude generation fails, the runtime can fall back to Gemini so the worker flow does not stop on a provider outage.

## Prompt Tuning Notes
- Gemini prompts remain unchanged unless a provider-specific wrapper is needed later.
- Claude may benefit from tighter sectioning or JSON-only instructions in a later task.
- Current implementation prioritizes backward compatibility over prompt redesign.

## Open Questions
- Should image-prompt generation use its own separate model setting, or should it reuse the script-generation model by default?
- Should provider selection stay project-scoped only, or also expose a more global longform default in the admin UI?
