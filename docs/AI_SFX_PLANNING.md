# Script-worker SFX planning

New `script_generate` and `codex_content_generate` packages call `worker.codex_sfx`
after finalized scene narration. The versioned plan lives in `structure.sfx_plan`;
claiming a **new** project imports its selected shared assets and cues. Existing
projects are never backfilled automatically.

The dedicated local console also runs `finalize_sfx` automatically after final
script/dialogue validation for both **new** and **repair** candidates. Repairs
carry the updated scene structure (stable IDs/order), preserve manual placements
and deletion markers, reuse exact matching AI anchors, and disable unresolved
anchors with `needs_review`. Results include `candidate.json` and `sfx-plan.json`;
the result screen shows status/count/review count. Failures remain explicit in
the remaining-work list. This stage does not publish a local candidate: use the
existing approval/application process to transfer the same plan and link assets.
Music prompt generation stays independently opt-in (default off).

The subtitle editor's **AI 효과음 구성** queues `sfx_plan_generate`. The worker reads
the supplied script snapshot and catalog, produces an allow-listed, confidence-filtered
plan, and returns it through the existing worker protocol. **구성 적용** checks ownership,
editability, unchanged script and optimistic concurrency before saving. Manual cues and
disabled deletion markers protect their scenes from later automatic plans.

Catalog setup: `python -m scripts.publish_sfx_catalog --project-id <explicitly-approved-library-project>`.
Only readable Storage SFX references are published to `content-assets/sfx-library/catalog.json`.
No speech or SFX is synthesized. Keep source objects while library references use them.

Workers must have `sfx_plan_generate` in the provisioned token's allowed job types.
The updated Hermes worker handles it. A separate source launcher is available:
`venv/Scripts/python.exe -X utf8 scripts/run_sfx_worker.py`.
It uses the current worker configuration, isolated state, and claims only SFX jobs.
Packaged AIRWorker installations require rebuilding/updating their binary to get
the new automatic script stage and `services.sfx_timing` renderer changes.

Anchors are editorial metadata, never narration/subtitle text. Scene anchors map
through subtitle splitting only if the full scene text still matches. Modified or
unresolvable anchors remain visible as review items and are excluded from playback.
Without aligned word timestamps, AI cues use the anchored subtitle's start (shown
in the editor). The renderer resolves times again **after** final narration retiming.
Automatic cues are at most one per scene and spaced at least five seconds apart;
manual layers are retained. No TTS invalidation or narration delay is introduced.

Verification: `pytest tests/test_codex_sfx.py`, `node auth-web/tests/std-ai-sfx.cjs`,
`node auth-web/tests/std-sfx-cues.cjs`, and the auth-web production build.
