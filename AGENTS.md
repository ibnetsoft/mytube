# Project guidance

## Production status communication

- Identify the actual assigned workflow and current stage before reporting. A script worker prepares scripts and directions; do not claim it generates footage, require it to connect a video model, or present video generation or any other later production task as its missing output unless the user explicitly assigned that task to the worker. Scene-level video direction is not itself an instruction for the script worker to generate video.
- Do not introduce tasks outside the assigned process or describe later stages as incomplete, missing, failed, blocked, or not started. Do not repeat a previously reported condition unless it has materially changed and is relevant to the assigned work. Report an actual failure only when it occurred in that work, with the concrete effect; answer direct deliverable questions accurately without implying a later stage was due now.
- When the user asks about script or video production progress, lead with the current stage, work completed, and the next step. Normal later stages are not delays or failures: do not describe them as "아직 ... 안 됐다", "아직 시작되지 않았다", "미완료", or equivalent negative status language merely because the workflow has not reached them. For example, say "대본 검토 중이며 다음은 이미지 제작입니다" instead of "이미지 제작은 아직 시작되지 않았습니다."
- Report actual execution failures, material uncertainty, or required user action clearly and truthfully. Never imply an output exists or is complete when it does not, and give an accurate answer if the user specifically asks whether a particular deliverable exists or has finished.

- When confirming user-web registration, name the exact completed stage and deliverables. A script, image prompt, or scene direction is not an image file. Claim image completion only after checking that the expected image assets exist and are readable from the user-facing project.

## Product and deployment target

- The active AIR Studio product is the web application in `auth-web/`, deployed to Vercel (project `mytube`). For web changes, update the web application, verify the relevant build, and deploy through the Vercel production workflow or its connected `main` branch.
- The Windows desktop/installer application is retired and is not a deployment target. Do not build, publish, update, or otherwise modify Windows packages or GitHub Releases for routine product work.
- Do not create or push `v*` Windows release tags, and do not run `tools/build_windows.ps1`, `tools/release_github.ps1`, or `.github/workflows/windows-release.yml`, unless the user explicitly asks to revive or release the Windows application.
- Before changing behavior, trace the active web execution path under `auth-web/`. A similarly named Python service under `services/` may belong to the retired desktop application and does not by itself implement the web feature.

## Production database investigation

- Project payloads can contain tens of megabytes of compressed JSON. During an incident on 2026-11-03, a diagnostic query repeatedly expanded a project payload for every subtitle and ran for 103 seconds while the database was recovering. Do not repeat that query pattern.
- Keep production investigation read-only and bounded: scope to known IDs, use a short statement timeout where supported, and materialize each selected JSON field once before expanding arrays. Avoid repeated references to a large payload inside per-row expressions, unbounded scans, and running diagnostic queries concurrently against the same large project. Check query plans or use a representative local copy when practical.

## Subtitle review translation

- Subtitle review translations (including the `KO` text beside Japanese subtitles) must run through the local Codex CLI script worker on this computer. Do not call Gemini or OpenAI model APIs for these translations.
- The web app queues translation requests in the database and reads their results. The local script worker claims requests and publishes validated translations. Preserve existing translations for unchanged subtitle text.
- Normalize punctuation-only subtitle fragments after quote and AI dialogue splitting, and when reopening saved subtitles. Fixing initial text-length splitting alone is insufficient. Preserve the preceding speaker and recorded narration timing when attaching punctuation.

## Codex-supervised submission automation

- The user explicitly authorized Codex to perform AE direction approval and output review on 2026-10-06. This supersedes user-click approval requirements above for the supervised submission flow. Codex must inspect actual source imagery, finalized narration, scene directions, and rendered output before approving; uncertainty must trigger repair or escalation, never blind approval.
- The local thread heartbeat monitors submitted AE jobs every 15 minutes, preserves reusable audio and source assets, repairs recoverable interruptions, and continues through final render. Administrator publishing and YouTube uploads remain separate.
- Use `node scripts/std_continue_submission.cjs PROJECT_ID` to inspect current jobs. After evidence-based approval, `--enqueue` validates current fingerprints and reviewed assets, records the render queue ID, and avoids registering the same reviewed job again. Confirm render completion separately.

## Complete production and record quality findings

- On 2026-10-28 the user requested that quality concerns never block production. Continue through final assembly with the existing source and saved direction; keep actual failed or uncertain review results truthful and record them separately as quality notes. This supersedes the earlier quality-approval stopping rule for submitted media production.
- Preserve cancellation, ownership, source integrity and actual file/timing checks. Execution failures remain queued for automatic recovery with backoff and reusable assets preserved; never mark an absent or broken output complete.
- Final delivery must include the quality-notes report and retain administrator publishing/YouTube upload as separate actions.

## Camera preference

- On 2026-10-29 the user required different facial identities across topics and among different characters within a topic. Compare actual stored reference imagery across all categories; hair, clothes, expression and wrinkles alone do not establish distinctness. Redesign similar new faces and preserve existing topic assets. Keep each character's approved identity consistent within its own topic.

- On 2026-10-29 the user prohibited slow zooms. Never add slow or whole-scene gentle zooms. Prefer a fixed camera; when motivated, use a clearly visible medium-speed zoom with a short movement window and holds. Preserve uploaded footage; this rule governs added direction, not source footage already containing camera movement.

## Confirm settings before new scripts

- Before starting a new script, ask the user to choose or confirm the production/script type, subject/category/reference, duration/chapter length, language/country/era, image/direction style, parallax/layer/video-scene scope, scene-state changes, and music-prompt/additional requests. Show the final effective settings and wait for an explicit start action. Saved defaults alone are not confirmation.
- Apply this to new script creation, including agent-initiated creation. Continue already running or recovering jobs with their existing settings; do not interrupt them to repeat the questions.

## Current-affairs production defaults

- For current-affairs or economic documentary productions, read `docs/current-affairs-production-defaults.md` and apply its defaults to the proposed settings and production. Confirm the effective settings and receive an explicit start action for each new script as required above; defaults do not replace confirmation. User overrides take precedence.
- For authorized supervised production, continue through final assembly without waiting for user review or approval; inspect evidence, preserve truthful quality notes and recover execution failures as described above. Do not automatically publish or upload.

## Wuxia webtoon production defaults

- For 무협 웹툰 productions, read `docs/wuxia-webtoon-production-defaults.md` and apply the defaults to the proposed settings and production. Confirm the effective settings and receive an explicit start action for each new script as required above; user overrides take precedence.
- For the authorized `나 혼자 무공을 진화시킨다` series, follow `docs/WUXIA_SERIES_DELIVERY.md`. The user defined episode completion on 2026-11-04 as the complete episode package registered to the user web with readback verification. An explicit next-episode start inherits the already confirmed series settings. Do not end after script, artwork or a local preview and ask the user to restart the next authorized stage. Final voice, AE rendering, administrator publishing and YouTube upload are separate from this delivery endpoint.

- For new wuxia episodes, the script worker automatically reviews actual state artwork and prepares mouth poses only for sufficiently large, fully visible speaking mouths. Zero eligible cuts is a normal `not_required` result, with no quota. Final voice save queues exact-recording timing binding and patch checks; the integrated worker consumes the frozen result for AE rendering/output review. Preserve existing manually approved episodes, and distinguish waiting for source images/audio from tool failures. Follow `docs/wuxia-webtoon-production-defaults.md`; never replace generation failures with a zero-cut success.

- New wuxia webtoon scripts must separate image-only `visual_action` from audible `spoken_blocks`. Use the `wuxia_visual_narration/v1` audiovisual script review, not audio-only narration quotas. Review every narration block against the same cut's planned visuals; remove grounded visible-action repetition while retaining image instructions, essential new information, dialogue, continuity and silent cuts. Image prompts consume both channels; TTS consumes speech only. Planned-visual review is not actual artwork/audio verification. Do not automatically rewrite existing finalized episodes.

- Wuxia impacts: follow the short, source-reviewed impact contract in `docs/wuxia-webtoon-production-defaults.md`. Keep faces and lettering clear, move mouth patches with artwork, and freeze identical editor-clock effect samples for integrated-worker AE. Distinguish tests, live preview and actual rendered-file verification.

- New wuxia productions automatically consider sparse popup close-up panels for motivated eye, mouth or hand emphasis. Follow the popup contract and preparation tool in `docs/wuxia-webtoon-production-defaults.md`: maximum one per six scenes and five per episode, no adjacent use, source-reviewed placement clear of faces and lettering, and no forced quota. Preserve finalized episodes.

- Wuxia popup panels use a readable 1.8–3.2s window (default 2.2s), with optional brief fade or left/down edge exit, rather than the earlier 0.9s disappearance. Inspect the entire travel envelope. For artwork, verify each character's anatomical left/right hand continuously from shoulder through wrist and thumb base; never approve swapped hands from finger counts alone. Preserve source-SHA-bound review and repair evidence.

- Wuxia visible actions use selective editable action typography (e.g. “꾸욱”) instead of redundant spoken action reports. Use existing `thought` cloud bubbles for inner thoughts, keeping screen-only text out of speech/mouth animation. Stationary, restrained blinking diagonal accents are optional via `worker.wuxia_hatch`; protect faces, hands and lettering and follow production defaults.

- Wuxia typography wording must be chosen from the actual depicted event, contact mode, materials and timing, never copied from example wording. Record `event`, `materials`, `word_reason` and the reviewed source/timing anchor; “꾸욱” is not a universal default. Follow the production-defaults typography correction.

- Wuxia impact debris starts at the actual reviewed collision point and travels outward. Match fragments, dust, spread and distance to materials and impact strength; do not substitute an incoming light beam or a lone yellow line. Apply selectively to motivated collisions, protect characters/text, and follow the source/timing/review contract in production defaults.

- For 「나 혼자 무공을 진화시킨다」 character props, read `docs/wuxia-props/PROP_BIBLE.md` and its reference manifest before artwork. Use each present prop's fixed design/owner ID and actual reference image, preserving blade silhouette, handle, fittings, sheath side and episode custody. Do not generate from generic “dagger” alone or attach absent props to every scene. Preserve finalized episode assets.

- For Seojin/Jangho weapons, use the approved-source extracted sheets in `docs/wuxia-props/reference-manifest.json` as actual image attachments. Build tool arguments with `worker.wuxia_prop_references.imagegen_arguments` and pass returned `referenced_image_paths` to image_gen together with character references. Approved crop geometry overrides speculative text design details; never claim a prompt-only path was attached.

- Wuxia narrative pacing is a primary quality requirement: use the revised 1–50 plan in `docs/WUXIA_SERIES_PLAN_03_50.md`. Each episode resolves a consequential event and changes the story state; cut/merge repetitive injury, vigilance, visible-action narration and empty resolves. Make discoveries, relationships and martial growth cause concrete actions/results, compress necessary recovery/training with elapsed time, and preserve finalized episodes. Apply the detailed episode-turn/removal review in production defaults.

- Wuxia action accents follow visible swing/downstroke/throw/incoming motion → actual contact → selectively chosen flash/outward debris/impact shake. Prepare source layers/clean plates or pose states as needed; prevent duplicate stationary objects and effects before contact. Apply the source/timing/protection review in production defaults, not an all-scenes effect bundle. A local preview does not establish web/AE production integration.

- Wuxia image production must follow the fixed-asset/structure-based contract in `docs/wuxia-webtoon-production-defaults.md` (2026-11-17). Do not default to independently regenerating each complete shot from reference sheets. Version approved character views/costumes, props and event states; broken weapons need an actual approved broken-state asset, not an intact reference plus contradictory text. Plan reusable space/props, articulated poses/contact and cameras before AI finishing and compatible layer compositing. Preserve fixed geometry where possible; inspect actual consecutive cuts for anatomy, identity, prop proportions/state and environment continuity. Reference attachment is not geometry enforcement, and saving this policy is not implementation or output verification. Preserve finalized script/audio and existing episode assets unless authorized.

- Preserve the final 2D Korean wuxia webtoon style when using structure-based production. 3D blocks/rigs are internal pose, geometry and camera guides, not permission for a 3D-rendered final look. Use coherent ink lines, simplified color shapes and cel shadows across characters, props and backgrounds; avoid accumulating photoreal textures, glossy/PBR surfaces and volumetric gradient shading during repairs. Attach and record an approved style reference separately from identity/costume references, and review actual consecutive artwork for style drift. See the 2026-11-17 final-2D-style section in the wuxia production defaults.

- User priority instruction (2026-11-18): anatomically failed, uncertain or required-but-unreviewed wuxia artwork must not be used in web preview or AE, including as a static fallback. This supersedes carrying known anatomy defects into output with quality notes alone. Inspect head/neck, torso, shoulders/arms/wrists/hands/digits and pelvis/legs/knees/ankles/feet/toes; rewrite prompts from actual defects, regenerate versioned candidates through built-in image_gen and re-review the new pixels before use. Bound retries, preserve approved identity/costume/prop state and 2D style, invalidate old source-bound patches, and retain exclusion on failure/refusal. Preserve script/audio and continue unaffected work; see the 2026-11-18 anatomy-use section in production defaults.

## Wuxia correction loop and actual image inputs (2026-11-24)

- The executable current baseline is `docs/wuxia-generation-rules.json` plus explicit local operator updates managed by `worker.wuxia_generation_gate`. `load_production_guidance()` includes its current fingerprint on every generation step. Prompt drafts, actual image input preparation, pixel review and final use are different states; never call them interchangeable approvals.
- Before **any new manual wuxia scene image_gen call**, use `worker.wuxia_generation_gate.prepare_scene_imagegen_arguments(scene, prompt, plan)`. Do not call image_gen directly using only text plus reference sheets. Persist the returned preparation receipt and pass the actual returned reference paths. A rejected/missing preflight means prepare actual source/state/pose assets first; do not manufacture files, observations, approvals or SHA values to satisfy it. This applies to Codex-supervised tool calls as well as worker automation; existing finalized episode assets remain unchanged.
- Inspect the actual previous episode/cut before defining a target. Record where the observed structure is, what moves, what contact does, and the consequence. Do not invent a wrist pivot behind a visually ambiguous stone sleeve. First show the target/structure, then contact, then the stopped motion and escape; redesign the causal device if the actual source does not support it.
- Record discovered failures under the affected scene's `quality_control` with the exact source SHA and rule ID. Known failures/uncertainty stay excluded. Resolving a prose finding does not approve an image; review repaired pixels independently with all required checks. Recompute evidence after every source change. Do not repeat the same full-shot generation with longer prompts as a substitute for asset/state/structure repair.
- The local UI exposes current execution rules, per-scene preparation checks and problem records, plus explicit operator-authored rule updates. A model or image output cannot promote a new instruction to active policy by itself. User-requested corrections in this chat authorize Codex to record the issue and update the relevant rule, without asking the user to repeat it in Markdown.
- For the current manual worker, the job-bound authoritative input path is `POST /api/jobs/{id}/scene-quality` with `action: prepare_arguments` and the current `expected_hash`. Save the scene plan first with `save_plan`. This checks unresolved findings as well as `prepare_scene_imagegen_arguments`; use the returned arguments and receipt, never a freshly reconstructed prompt-only call. See `docs/WUXIA_GENERATION_GATE.md` for scope and limits.
- Persistent pre-generation enforcement: every new wuxia image plan must provide `rule_applications` for every current rule, recording actual `observation`, concrete `input_action`, and `verify_after_generation`. Read the current production documents and previous corrections first; never fabricate these records or copy generic acknowledgments as evidence. `prepare_arguments` must reject missing/stale plans. An excluded previous image cannot seed continuation; an explicit repair target is only diagnostic input, never an approved style/structure/continuity asset. Compare shoulder–elbow–wrist–thumb and the approved weapon's handle–guard–blade axis in the new pixels before reuse. Baseline rules and this contract must ship with worker distributions, not live only in a one-off job folder.
- Before each wuxia image, identify the single focal event and visible subject IDs in `render_focus`; keep `one_instant:true` and `cut_count:1` per tool call. Do not turn every action beat into an obligatory image or draw everyone mentioned in narration. Keep offscreen continuity in the plan, but attach only the actually needed subject references and pass only visible-subject context to image_gen. A user-requested statue-only cut uses statue references, not human identity/hand sheets. Preserve excluded defective images as evidence; choosing a new subject-only composition does not repair them.

## Script-worker user-web delivery

- For user-authorized script/artwork preparation and user-web registration, follow `docs/SCRIPT_WORKER_WEB_DELIVERY.md`. Preserve prior versions, map explicit cut IDs, review actual source pixels, verify storage hashes and database readback, and inspect the authenticated user-web result. Respect manual stage approvals and separately assigned audio/video/AE execution. The shared guidance loader includes this document in new request and manual-stage context; other computers must update the checkout and restart long-running workers before use. Do not claim remote adoption from a Git push alone.
