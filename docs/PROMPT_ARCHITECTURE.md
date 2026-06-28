# Prompt Architecture

## Goal
Keep Longform Mode prompt handling explicit and provider-aware while Gemini remains the default and Claude remains opt-in.

## Prompt Families

### Script Plan
- Domain: `script_plan`
- Current code path:
  - `services/gemini_service.py::generate_script_structure`
  - `app/routers/gemini.py::generate_script_structure_api`
- Base prompt source:
  - `services/prompts.py::GEMINI_SCRIPT_STRUCTURE`
- Provider wrappers:
  - `prompts/longform/script_plan/gemini.md`
  - `prompts/longform/script_plan/claude.md`

### Script Generation
- Domain: `script_generation`
- Current code path:
  - `services/gemini_service.py::generate_deep_dive_script`
  - `app/routers/gemini.py::generate_deep_dive_script_api`
- Base prompt source:
  - `services/prompts.py::GEMINI_DEEP_DIVE_SCRIPT`
  - `services/prompts.py::GEMINI_DEEP_DIVE_DIALOGUE`
- Provider wrappers:
  - `prompts/longform/script_generation/gemini.md`
  - `prompts/longform/script_generation/claude.md`

### Image Prompt Generation
- Domain: `image_prompt`
- Current code path:
  - `services/gemini_service.py::generate_image_prompts_from_script`
  - `main.py::auto_generate_images`
- Base prompt source:
  - `services/prompts.py::GEMINI_IMAGE_PROMPTS`
- Provider wrappers:
  - `prompts/longform/image_prompt/gemini.md`
  - `prompts/longform/image_prompt/claude.md`

## Provider Rules
- `gemini` stays the default provider.
- `claude` is an opt-in provider.
- Invalid provider values fall back to `gemini`.
- The selected provider is stored with the project when the UI supports it.
- The runtime may use the same provider/model pair again on later generation runs.

## Claude Notes
- Claude benefits from stricter structure and less Gemini-specific wording.
- JSON-only output should remain explicit when the caller expects JSON.
- XML tags are not required in the current implementation.

## Gemini Notes
- Gemini prompts remain the baseline.
- Existing Gemini wording should not be broken while Claude wrappers evolve.

## Future Provider Support
To add another provider such as GPT:
1. Add a new wrapper file under each domain directory.
2. Extend provider normalization and selection.
3. Keep the base prompt contract stable.
4. Add tests for the new provider wrapper and routing.

## Current Scope Limits
- This task only organizes the longform prompt system.
- It does not rewrite every non-longform prompt in the repo.
- Many legacy prompt strings still live in `services/prompts.py` and are outside the current cleanup scope.
