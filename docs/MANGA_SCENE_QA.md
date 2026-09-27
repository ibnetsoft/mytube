# Manga scene direction and review gate

Eight AE scene directions can be selected by an explicit `scene.ae_template` or
by a matching scene action. The script planner writes the renderer-facing
`scene.ae_effect_plan` with normalized 0–1 coordinates and times in seconds:

| Template | Required PSD layers | Direction data |
| --- | --- | --- |
| `dialogue_closeup` | `background`, `character`; plus `mouth_closed`, `mouth_half`, `mouth_open` when opted in | Explicit speaker key, final dialogue audio hash, registered mouth box, scene-relative word timings, and held mouth-pose cues. |
| `angled_triple_reaction` | `background`, `character_left`, `character_center`, `character_right` | Three `panels` with `role`, four-point `polygon`, and `enter_at`; timed panel beats. |
| `body_following_qi` | `background`, `character`, `talisman` | `qi_path` points over the character, normalized `talisman_target`, and timed attachment/trace/pulse beats. |
| `ink_splat_impact` | `background`, `character`, `talisman` | `impact` x/y, `at_seconds`, short text; timed strike, burst, and lettering beats. |
| `wall_impact_debris` | `background`, `character`, `wall_intact`, `wall_broken` | `impact` x/y and `at_seconds`; timed `wall_contact`, `wall_reveal`, `debris_burst`, and `debris_settle` beats. |
| `glasses_reflection` | `background`, `character`, `reflection_scene` | `reflection.left_lens` and `right_lens` each have `center` and `radius`; reveal time, glint, and camera push beats. |
| `kinetic_title_reveal` | `background`, `character`; also `training_prop` for `training_emphasis` | `title.text`, `accent_text`, `style`, `position`, and `at_seconds`; reveal, punch, and hold beats. |
| `backlit_hand_reveal` | `background`, `hand_foreground` | `light_origin` point; hand raise, light ignition, ray burst, and afterglow beats. |

Optional PSD layers include `speedlines`, `qi_overlay`, `ink_splat`, `debris`,
`lens_glint`, `title_backdrop`, `light_core`, and `light_rays` where used.
The PNG scene preview or a `psd_layer_plan` is not a substitute for the actual
layered PSD. Publish a `scene.metadata.psd_layer_asset` with a PSD GCS path and
its layer-name manifest. The downloaded PSD's layer table must be checked
against that manifest before AE runs. The planner requests the layers.
`cowork_scene_assets.py generate-layers` can create independent full-canvas
PNGs from verified character references; `prepare-layers` builds a PSD,
`approve-layers` records a visual asset review, and `publish` places the
approved PSD in GCS. See `docs/MANGA_LAYER_GENERATION.md` for the commands.

`worker/manga_scene_qa.py` exposes two JSON-serializable checks:

```python
plan_report = validate_scene_plan(scene, scene["metadata"], clip_seconds)
render_report = validate_render(scene, local_mp4, fps=24, duration_seconds=ae_job_seconds)
```

The first fails on missing or mislabeled PSD assets, malformed polygons,
off-screen coordinates, degenerate qi paths, invalid lens ellipses, missing
lettering, incorrect beat targets, or beats outside the clip. It requires the
panel reveal beat to match each panel's entry time, the qi trace to follow
talisman attachment, and the ink burst and lettering to follow the impact
within 0.2 seconds. For the four newer templates it also checks contact,
reflection, title, and light timing, including a visible end hold. A training
title requires a real `training_prop` PSD layer even if the plan omits that
requirement. The second decodes the MP4, checks duration, resolution, frame
rate, and sampled frames, and flags a completely blank export or an unchanged
frame pair around the planned ink impact, wall contact, lens reveal, title
reveal, or light ignition. A failed report
(`passed=false`) blocks that scene from being marked ready or uploaded. The
report is stored in `metadata.ae_effect_asset.manga_qa` with the local MP4
path and its SHA-256, so a restart and reviewer see the same result. A
standard scene without one of these templates is unaffected.

Both reports intentionally carry `review_required=true` even when the machine
checks pass. Frame changes do not prove that panel cuts avoid faces, qi follows
the body, a wall fracture matches the original wall, a reflection remains
inside both lenses, a title is legible, or light originates at the palm. Review
the sampled scene at full playback speed and at the marked event frame,
checking the report's `review_points`. In particular, verify Hangul font
rendering, safe margins, face visibility, layer order, and timing against narration before
approving a final sequence. In the local AE console, play each
`review_pending` clip, add a reviewer and note, then approve or reject it.
Approval verifies that the MP4 still matches its recorded hash. Premiere
accepts the clip only after approval; rejection leaves the scene needing
attention. Do not label `passed=true` as human approval.

Before starting the revised AE worker against a database, apply the
`20260926121548_atomic_manga_ae_scene.sql` and
`20260926132500_sync_manga_layer_assets.sql` migrations. Before publishing
CoWork image/PSD assets, apply
`20260926134000_atomic_topic_scene_asset_publish.sql` as well. Before starting
the revised Premiere worker, also apply
`20260926133000_premiere_final_asset_atomic.sql`. These row-locked RPCs
preserve other scene updates during rendering, review and final export.

Apply `supabase/migrations/20260926121548_atomic_manga_ae_scene.sql` before
running the updated AE worker or review console against Supabase. Its
service-role-only `air_update_ae_scene` RPC locks the project or topic row and
updates the selected scene's AE state, preserving concurrent changes to other
scenes and unrelated metadata. It covers both effect and motion jobs. A stale
worker status, render start time, or review hash returns a conflict; the
caller must refresh instead of writing its old copy of the whole structure.
For manga scenes, the worker leaves any GCS MP4 URL in asset metadata while
review is pending. Approval publishes the URL to the scene atomically;
rejection removes it.

To exercise all eight templates through the installed After Effects and
`aerender`, with self-contained placeholder art instead of production
character images, run:

```powershell
python experiments/manga_ae_smoke.py --force
python experiments/manga_ae_smoke.py --template kinetic_title_reveal --title-style threat_red --force
python experiments/manga_ae_smoke.py --template dialogue_closeup --force
```

Each template produces a layered PSD, `.aep`, four-second MP4 and JSON QA
report under `output/manga-ae-smoke/`. This verifies PSD import, timed AE
compositions, export, and machine QA locally. It does not verify cloud
credentials, image model quality, or a production project submission.

Run the focused checks with:

```powershell
python -m pytest tests/test_manga_scene_qa.py tests/test_manga_console_review.py tests/test_manga_lip_sync.py -q --basetemp=.pytest-manga-qa
```
