# Background music prompts from the script worker

Music prompts are optional and **off by default**. Only the explicit boolean
`generate_bgm_prompt: true` enables `07_bgm_prompt` after final script validation
for `script_generate`, `codex_content_generate`, and the local console's new-script
workflow. Missing flags, false, and non-boolean values skip the model call and
preserve existing saved prompts. The local console and legacy script dashboard
provide an unchecked "배경음악 생성 프롬프트 만들기" checkbox.
When enabled, Codex reads the complete story and writes:

- `structure.bgm_prompt.prompt_en`: English prompt suitable for a music generator.
- `structure.bgm_prompt.description_ko`: Korean explanation of the musical direction.
- `version`, `script_version`, `status`, `instrumental`, `audio_generated`.

The existing result/structure persistence carries this metadata into
`pregenerated_structure` and the claimed project's structure. It is never appended
to narration, captions, or TTS input. No Gemini, Lyria, or other audio generation
API is called. No music file is produced by this stage.

The prompt follows the story's setting and emotional arc, specifies instruments,
tempo and restrained dynamics, and requests instrumental, loop-friendly music with
space for speech. Named artist imitation, vocals, lyrics and sound effects are excluded.

An unchanged script reuses a valid saved prompt; the Codex stage cache also includes
input and instruction hashes. A rewritten script invalidates that prompt. Failure
is recorded as `failed` without discarding the completed story or fabricating a prompt.
Existing projects are not automatically backfilled. This is worker metadata;
there is no new web editor or music generation button in this change.

Verify with `python -m pytest tests/test_codex_bgm.py tests/test_codex_sfx.py -q`.
Packaged desktop workers must be rebuilt to include `worker.codex_bgm`.
