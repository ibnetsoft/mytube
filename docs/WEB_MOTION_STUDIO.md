# Motion Studio browser production

## Additional production option

Existing AE production is the default. `production_method` selects `ae` or
`motion_studio`; the editor shows the browser option only after explicit selection
and saves that choice before entering it. Active settings and the two independent
`alternatives` snapshots round-trip without overwriting the original AE recipe.
Old AE projects without a selection stay on AE. Existing saved browser projects
are recognized from their `web` marker until an explicit selection is saved.
Explicit `ae` takes precedence over any dormant browser settings. Script and
render workers remain installed and unchanged. Browser generation/review routes
reject AE-selected projects; the ordinary submission route keeps its AE behavior.

The active `auth-web/` editor can produce a final video without After Effects,
the office computer, a local Codex process, or a media worker. The browser parses
PSD pixels, composites scene frames, and encodes H.264/AAC MP4 with WebCodecs.
Keep the tab open until export finishes. This is browser rendering, not a cloud
render farm; available RAM, temporary disk quota and encoder support depend on
the user's device. Source layers load one scene at a time. Supported browsers
stream fragmented MP4 to private browser storage instead of accumulating the
whole file in RAM. Temporary files are released on editor teardown and old
abandoned exports are reaped on a later session. The in-memory fallback is
limited to two minutes. Narration/audio mixing still needs decoded audio RAM.

## Production path

`StdMotionStudio` lazily loads `StdWebMotionStudio`. The authenticated project
`web-motion` endpoint returns owned source assets and the finalized recording's
validated scene/subtitle timing. Original PSD files and output MP4s use existing
signed GCS upload claims. Layer/camera settings and chosen hybrid inserts are
saved in the project's motion draft. Stored final files can be reopened.

`stdWebMotion` supplies the same composition code for interactive preview and
offline, timestamped final export. Supported controls include independent layer
translation, scale, rotation and opacity; camera movement; light, particles,
impact effects; fades; captions; saved BGM/SFX windows; and template overlays.
Finalized narration is decoded, never regenerated. Audio mixing preserves its
timeline. Each output frame has an explicit timestamp, independent of tab FPS.

PSD input supports 8-bit RGB pixel layers, up to 80 visible layers, 150 MB,
24 million canvas pixels and 100 million total layer pixels. Unsupported masks,
clipping, layer styles and unsupported group blending must be rasterized in the
source first. Raster layer masks now support grayscale alpha, density, document
or layer-relative coordinates, outside-mask background and disabled masks.
Their alpha is baked once at import and moves with the layer; this is not an
editable animated mask path. Vector, feathered, group and real masks still
require the existing AE path or source rasterization.
The importer compares both stacking conventions against the
saved composite and refuses a reconstruction with mean error over 4%. It does
not invent pixels behind moving subjects or promise full Photoshop parity.

## Optional hybrid mode

Provider settings appear only in hybrid mode. API keys remain encrypted on the
server. Explicit generation requests create an owned job receipt before the
paid provider call. A hash of actual source bytes, prompt, duration and model
configuration prevents duplicate requests even after repeated source uploads.
Ambiguous calls require reconciliation; polling never creates another request.
Completed 3–5 second clips can replace selected scene intervals, preserving the
full original narration. Saved inserts are restored with the motion draft.

Output upload and administrator review are separate explicit actions. Review
registration adds the stored final to existing render history/admin queues;
it records `pending_admin_review`, never automatic approval or YouTube upload.
Legacy worker/AE controls remain in the advanced section for older jobs.

## Verification

Run `node --test tests/std-web-motion-api.cjs` and
`node tests/std-web-motion-browser.cjs` from `auth-web/`, followed by the web
production build. Browser tests exercise real PSD parsing, stacking checks,
independent motion, both output aspects, actual H.264/AAC export, cancellation,
audio mixing, and the editor upload/review flow with mocked HTTP endpoints.
An existing local three-layer PSD is also inspected when available. Diagnostic
video uses a calibration tone; it is not a customer narration audition. Live
paid generation is not part of these tests.

## Native joints, deformation and reference effects

PSD layer controls now include parented FK bones, two-bone IK, automatically
weighted WebGL mesh deformation and animated radial pins. The scene timeline
records pose keys at the selected time. Authored polygon masks, feather/inversion,
outlines, shadows, blur, glow, fractal noise, turbulent displacement, radial wipe
and trimmed glowing paths use the same renderer in preview and final output.
These controls are part of the optional browser recipe and do not alter the
existing AE or worker execution path. The importer still rejects unsupported
PSD features rather than claiming to translate arbitrary AE/Photoshop content.

See `MOTION_NATIVE_VERIFICATION.md` for reproducible tests, actual AE comparison
measurements, diagnostic output locations and the remaining compatibility limits.

Reviewed PSD packages attached to existing scene assets are recognized through
their `psd_layer_asset` metadata, not just directly uploaded `.psd` originals.
They are served by an authenticated, project-scoped, byte-hash-checked endpoint.
Glow exposes a bright/alpha seed threshold and soft knee; the optional AE-reference
glow button adds the calibrated pulse glow/blur recipe. These changes preserve
the finalized-audio identity gate and the existing AE/worker paths.

Selected bone, IK, root and pin tracks now have frame-based key editing,
linear/ease/hold interpolation, copy/paste and per-track undo/redo. Skeleton
angle limits and locked mesh pins reduce excessive bending and unwanted motion.
Artwork-backed handles record FK/IK/pin poses at the current frame. These are
native web tools; the AE option and existing script/render workers remain intact.
See the recorded-source verification section in `MOTION_NATIVE_VERIFICATION.md`
for the actual three-PSD/narration render scope and remaining limits.


The full-body preset adds pelvis/spine/neck/head and both arms/legs (12 bones),
with four independent parented two-bone IK chains. Native rigs support up to
8 non-overlapping chains. Bind joints must be fitted to the artwork; this does
not detect anatomy or invent hidden limbs. Skin grids support automatic weights,
selected-bone heatmaps, add/erase brushes, normalized four-influence weights and
stroke undo. Bone -1 denotes the unchanged bind artwork. Bilinear interpolation
keeps the painted weight field continuous.

Key tracks also expose a cubic Bezier graph with draggable handles and numeric
control points. X handles are monotonic in [0,1]; Y handles allow [-2,3] for
overshoot. The renderer solves the curve's time coordinate before evaluating
its value; preview/export use the same sampler.

The web-only visual clip timeline supports selection/project scrubbing, split,
drag or button reorder, adjacent boundary trimming, source scene replacement,
source animation in/out, removal with adjacent extension, and undo/redo. Its
persisted clips must cover the finalized narration duration without gaps. Audio
and subtitle timing stay fixed; visual reordering requires semantic review.
Animation recipes are shared by source scene, including split/repeated clips.
Full timeline preview follows recorded audio across clips. Edited timelines
also export in hybrid mode. AI insert settings use original scene seconds;
each clip intersects that source interval after trimming/splitting/repetition,
then maps it into its edited output duration. Generated-video offsets continue
from the appropriate source point and playback speed follows clip retiming.
Native motion resumes at the matching source animation time. The timeline marks
intersecting clips as AI mixed. Settings apply to all clips of that source scene.
Narration/subtitles are never retimed or replaced by the inserted video's audio.
Only used jobs are polled, once per scene/job per export; unused trimmed inserts
need no poll. Pending/short videos block output and never trigger generation.
The original AE selection/worker submission path is unchanged and does not
consume this optional web timeline. Timeline preview still shows native motion;
review generated inserts separately and the rendered final video for the mix.

## Form-preserving joints and full-length validation (2026-10-20)

New rigs use planar dual-quaternion blending to preserve thickness during large
joint rotations. The skeleton editor offers form-preserving or legacy linear
blending; recipes without a deformation field retain their previous behavior.
Rigid rigs use a finer adaptive render mesh. This reduces blend collapse but
cannot reconstruct occluded artwork or guarantee against arbitrary folds.

Prepared scene originals are available as an authenticated fallback with SHA256
verification before decoding. Saved sound cues now respect volume_db when a
linear volume is absent. Existing AE selection and worker execution are unchanged.

A 26:54, 100-scene project was exported at 1920x1080/24fps with the finalized
recording, 518 subtitles, three real PSDs and 97 prepared original images.
See MOTION_NATIVE_VERIFICATION.md for evidence and scope limitations.

## Joint pose correction and protected regions (2026-10-20)

The optional web rig now supports angle-driven shoulder/elbow/pelvis corrective
poses. Edit the selected joint's trigger angle (positive and negative poses are
separate), strength, elliptical influence radius, bind-space center, local scale
and offset. Drivers use solved local rotation after IK, so parent rotation does
not double-activate a child. Corrections respect bone ownership and locked pins.

Protected rectangles override skin influences with soft boundaries. Assign the
head bone to preserve facial shape while following the torso hierarchy, or bind
artwork (-1) to keep another character stationary. Later rectangles take priority.
The editor exposes bounds/feather and draws their outline over the weight canvas.
These are authored regions, not automatic anatomy recognition or hidden-pixel
reconstruction. They persist in the same validated web-only animation recipe.

Per-bone depth tracks order mesh triangles at overlaps. Larger values render in
front; use hold interpolation for intentional front/back switches. Rendering now
uses premultiplied source-over alpha so transparent foreground texels cannot erase
the background. Preview and export use the same corrected influences and ordering.
Old recipes have no corrections/regions/depth tracks and retain their settings.
AE selection and existing script/render workers remain independent.

See MOTION_NATIVE_VERIFICATION.md for real-source comparisons. Two PSD scenes
passed this bounded review; a third crossed-hand pose was rejected rather than
silently accepted. No universal AE/Puppet quality percentage is established.


## Dialogue direction and clip review (2026-10-20)

The web studio displays finalized dialogue overlapping the selected timeline clip.
Click dialogue to seek its absolute audio time, then add a direction cue. Cues
store normalized source-scene times and target either the camera or a PSD layer.
Push, reveal, and impact shake use the same deterministic renderer for preview
and MP4. They remain attached to the original scene when a clip is split, trimmed,
repeated, or moved. This does not generate facial expressions or new artwork.

Boundary buttons play 1.5 seconds on either side of the chosen cut using finalized
narration, stopping automatically at the end of the window. The selected clip can
be exported separately for review without regenerating original artwork or voice.
Its video/motion ranges, mixed audio, and overlapping subtitles are cropped and
rebased to zero. Partial review files cannot be stored/submitted as the full final
video. After repairs, export the full project to include the updated scene; this
is not a persistent encoded-segment cache or an automatic output approval system.

Validation: tests/std-webtoon-direction.cjs and
 tests/std-webtoon-direction-browser.cjs cover source-range preservation, cue
persistence, boundary playback, and actual 1080p partial MP4 decoding with audio
and subtitle timing. Existing PSD/full-project output tests remain applicable.
