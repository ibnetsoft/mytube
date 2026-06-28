Claude longform script-generation wrapper

- Keep the current output contract unchanged.
- Use a clean sectioned structure with explicit headings.
- Return JSON only when the downstream caller expects JSON.
- Keep pacing stable for longform scripts and avoid Gemini-specific wording.
