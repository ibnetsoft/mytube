# Native Motion Studio verification — 2026-10-20

Existing AE is still the default. No worker source or worker process was changed.
Native options are saved in the Motion Studio recipe and use the same frame
renderer for preview and MP4 export. Method switching preserves separate recipes.

## Implemented native controls

- Up to 32 parented bones per PSD layer, bind positions and animated FK angles.
- Two-bone IK for a root and its child, animated target, bend reversal and
  unreachable-target clamping. This is not a general whole-body constraint solver.
- Automatic linear blend skinning using the nearest two bones; no weight-paint UI.
- Up to 32 animated deformation pins with radial falloff on a 2–24-cell mesh.
- WebGL texture mapping with premultiplied alpha and a shared GPU context. A
  transparent texture test checks for triangle cracks and alpha accumulation.
- Authored polygon masks, inverse/feather, outlines and drop shadows. Existing
  PSD vector masks/styles still require rasterization or the retained AE path.
- Blur, glow, evolving fractal noise, turbulent displacement and radial wipe.
  Glow now extracts a luminance/alpha threshold seed with a soft knee, applies
  one blur/add pass, and pads layer bounds so halos are not cut at layer edges.
  Default luminance threshold is 0.6; the editor exposes threshold, soft knee
  and luminance/alpha selection. Low-brightness pixels no longer brighten merely
  because a glow effect exists. This follows the bright-area/alpha basis described
  in [Adobe's Glow reference](https://helpx.adobe.com/after-effects/using/stylize-effects.html#glow_effect),
  without claiming Adobe's implementation or numerical defaults are reproduced.
  These are native implementations, not Adobe plug-in binaries or exact replicas.
- Polygonal glow strokes and animated trim start/end. The sword path preset uses
  the actual vertices in `ae_wuxia_fx/create_wuxia_ae_fx.jsx`.

Select a PSD layer, create the rig or pins, choose a time on the scene timeline,
then adjust the pose/target. Settings record a key at that normalized time.
Each channel supports up to 64 keys. Scene effects operate before captions and
template overlays so those remain readable. Long exports still require the tab
to remain open; the retained render worker does not yet consume this native data.

## Actual AE output comparison

Reference: `output/ae-psd-wuxia-3285/wuxia-split-animation.mp4`, an existing
1920×1080, 24 fps, four-second AE output. Its `create-layered-ae.jsx` supplies
the background and character transform keys, divider and violet pulse timing.
The test uses the original PSD, ports those transforms and pulse into the web
renderer, and extracts matching time points from the actual AE MP4 with FFmpeg.
It does not start AE, overwrite the original or enqueue a production job.

| Time (s) | RGB mean absolute difference (0–255) | PSNR (dB) |
| --- | --- | --- |
| 0 | 3.330 | 35.057 |
| 1 (holdout) | 3.218 | 35.274 |
| 2 (calibration) | 3.261 | 35.076 |
| 3 (holdout) | 3.205 | 35.277 |
| 3.958333 | 3.157 | 35.391 |

The comparison sheet has AE, native and 4× absolute difference in each row.
The paired `glow-before-after.png` sheet shows AE, the previous duplicate-source
glow and the corrected/calibrated output. The pulse region is document pixels
220–619 × 540–839. At two seconds its MAE falls from 11.891 to 5.848 (50.8%).
One-second holdout MAE falls from 8.798 to 5.015 (43.0%), and three-second MAE
from 7.376 to 4.860 (34.1%). The regression checks at least 35% improvement at the
calibration point; holdout measurements are reported rather than claimed equal.
The reference preset uses a 10% alpha-based glow at 10/1080 of the layer's short
edge followed by a 5/1080 blur. It was chosen from a 42-candidate comparison at
two seconds; it is a violet-pulse preset, not a universal AE calibration.
Color conversion, encoded video, resampling and effect differences all contribute.
The regression tolerance is MAE below 8 and fewer than 5% of RGB channels with
an error above 20. Passing this tolerance does not mean pixel parity or prove
equivalence for other projects/effects.

The reference has no skeletal/mesh deformation. New FK/IK and mesh behavior is
tested mathematically and through actual native MP4 export separately. A second
four-second MP4 applies torso/neck bones and a hair deformation pin to the real
PSD. These diagnostic videos are silent; they are not final narration reviews.

## Reproduce

From `auth-web/`:

```
node --test tests/std-motion-rig.cjs tests/std-motion-studio.cjs tests/std-web-motion-api.cjs
node tests/std-web-motion-browser.cjs
node tests/std-motion-advanced-browser.cjs
npm run typecheck
npm run build
```

The comparison test needs local Chrome, the reference assets and FFmpeg. Set
`MOTION_FFMPEG` to an installed executable if `ffmpeg-static` is not downloaded
and FFmpeg is not on PATH. API upload/review boundaries are mocked; no paid
provider request is made. A missing reference is reported explicitly in JSON.

Artifacts under `output/motion-native-comparison/`:

- `comparison.json`: measurements, reference provenance and limitations.
- `ae-native-difference.png`: actual output comparison sheet.
- `glow-before-after.png`: AE / previous / corrected pulse crops at five times.
- `rig-mesh.mp4` / `rig-mesh-preview.png`: pattern deformation diagnostic.
- `real-psd-rig-demo.mp4` / `.png`: native animation on the real PSD.
- `layer-tools.png`: browser editor controls.

AE expressions, arbitrary AEP import, third-party plug-in execution, arbitrary
PSD styles, Puppet's exact deformation solver and automatic hidden-pixel repair
remain outside this implementation.

## Existing production PSD packages

The browser route also recognizes reviewed `metadata.psd_layer_asset` packages
attached to scene image/video assets. Directly uploaded originals take precedence.
The PSD proxy checks ownership, ready/approved state, project-scoped GCS path,
size and actual downloaded byte hash. It does not change the AE source resolver.

Actual project 3376 scene 19/25/29 PSDs were checked against their recorded hashes
and parsed by the browser: all three are 1920×1080 with background, foreground
and character layers. The finalized-audio gate still applies independently.
No final production output is approved when the selected recording and current
subtitle/voice identity disagree.


## Webtoon key editing and recorded-source verification (2026-10-20)

The optional Motion Studio now exposes frame-snapped key tracks for selected
bone rotation, two-bone IK targets, root translation and mesh pin targets. Keys
can be added, moved by frame number, copied/pasted and deleted (endpoints remain).
Each track has 50-step key undo/redo; edits made outside that track reset its
history. Segment interpolation supports linear, smoothstep, quadratic ease-in,
quadratic ease-out and hold. Normalization preserves these settings and the
same sampler drives preview and export. This is not a Bezier graph editor or a
multi-scene clip editor.

Skeletons support optional local angle limits (also applied after the IK solve)
and animated root translation. A constrained IK chain can stop short of its
target. Locked mesh pins attenuate both bone and moving-pin displacement back
toward the bind artwork; they are radial anchors, not an AE Puppet solver.
Artwork-backed handles edit FK endpoints, IK targets and moving pins. Pin-only
artwork also gets the handle view. Bind coordinates, pose controls and a final
render preview remain separate so the artist can inspect deformation.

Actual project 3376 PSD scenes 19, 25 and 29 were exported with their own recorded
narration intervals: 13.401, 12.382 and 12.408 seconds. All are browser-rendered
1920x1080, 24fps H.264/AAC videos with timed Japanese subtitles. Source PSD SHA256
checks and the downloaded MP3's stored generation SHA256 passed. The original
recording has 518 subtitle rows and 1614.420 seconds. Current live voice choices
differ from that recording, so verification used a separate local snapshot with
recorded voices/directions/speed; every text/time row was first compared and the
existing strict narration identity/lip-sync validators passed. No project row,
AE selection, worker, or admin review state was changed.

The three encoded clips passed complete FFmpeg decoding. Comparing decoded AAC
against the original scene audio gives correlation >=0.999986, 0ms best lag at
1ms search resolution, and <=18ms trailing codec padding. Encoded beginning,
middle and ending frames were inspected for missing layers, tears, edges and
subtitle placement. The deliberately small torso/pin motion showed no obvious
new background gaps at those inspected poses. This is a 38.191-second source
validation reel, not a full 26-minute production render, anatomical character
rigging, listening review, or proof of AE deformation equivalence.

Local artifacts: `output/motion-final-production/recorded-motion-verification.json`,
`audio-render-check.json`, `encoded-contact-sheet.png`, `timeline-editor.png`,
and `scene-{19,25,29}-motion-recorded.mp4`. Required source manifests and media are
local private production assets and are not committed. To reproduce from those
manifests, set `MOTION_FFMPEG`, run `node scripts/verify_motion_recorded.cjs`, then
`python scripts/qa_motion_recorded.py` (NumPy required).

Additional checks: `node --test tests/std-motion-timeline.cjs` and
`node tests/std-motion-timeline-browser.cjs` from `auth-web/`. The browser test
covers add/move/copy/paste/delete, interpolation persistence, undo/redo, root
motion, limits, locked pins and a pointer-driven pose edit. Existing AE selection,
API ownership/queue protections and renderer regression suites are retained.


## Full-body, painted skin, Bezier and multi-scene clips (2026-10-20)

Superseding the prior feature limits: native full-body rigs, editable skin
weights, cubic Bezier segment graphs and multi-scene visual clip editing are now
implemented. This does not provide AE Puppet's solver, anatomy detection,
automatic occluded artwork repair or arbitrary AEP/expression/plugin execution.
The timeline locks the recorded audio/subtitle track; it is not an audio editor.

Math/schema regression tests cover four simultaneous limb targets below moving
FK parents/root translation, rectangular/square bind-pose preservation, painting
and erasing skin to the bind artwork, normalized weights, Bezier time inversion
and overshoot, invalid handles/shared IK bones, clip split ranges, reorder,
boundary trim, removal, duration/source rejection and AE-option round trips.
Browser controls verify 12-bone creation, four IK chains, Bezier coordinates,
skin painting/stroke undo and clip split/reorder/replace/trim/delete/undo.

`node scripts/verify_motion_fullbody.cjs` consumes the private frozen-source
manifests described above, checks original PSD/recording hashes and renders the
same actual scenes 19/25/29 with their exact recorded excerpts. Fitted body
joints, four chains, manually adjusted skin and Bezier targets are serialized,
normalized and rendered over a four-clip timeline (scene 19 split at a frame).
Output: `output/motion-fullbody-validation/fullbody-recorded-validation.mp4`,
1920x1080/24fps H.264/AAC, 38.191 seconds. `python scripts/qa_motion_fullbody.py`
checks complete decode and audio correlation. Source/output correlation is
0.9999863, best lag 0ms at 1ms resolution, trailing padding 16.96ms. Encoded
start/middle/end frames were inspected for layers, new gaps, tears and subtitles.
The source art crops out feet; it cannot validate visible-foot walking or a
complete anatomical performance. Four-limb mechanics are verified separately.

`node tests/std-motion-fullbody-production-browser.cjs` from `auth-web/` uses an
isolated API fixture containing these real source assets and the frozen recording
excerpts. The actual production Editor loads the PSD, previews recorded audio
across a clip split, saves all skin/Bezier/timeline settings, exports and downloads
`editor-recorded-final.mp4`, and passes FFmpeg decode. API data is a local fixture;
this is not a live account/admin publishing test. No project/voice row, AE method,
worker process, provider generation request or external upload was changed.
Additional local evidence: `verification.json`, `audio-qa.json`,
`editor-verification.json`, `encoded-contact-sheet.png`, `fullbody-editor.png`,
`actual-psd-rig-editor.png`, and `editor-export-result.png` in that directory.
Both scripts require `MOTION_FFMPEG`; Python QA requires NumPy. Private media and
frozen manifests are not committed. The 26-minute whole project remains outside
this bounded source validation.


## Edited hybrid timeline output (2026-10-20)

`stdMotionHybridTimeline.ts` plans source-time intersections for every visual
clip. Split/repeated/trimmed/reordered/retimed clips preserve the applicable AI
video offsets and native animation ranges, without changing the locked audio
or subtitle duration. The video decoder now accepts an explicit source-second
range independently of native animation progress. Job polls remain scoped to
each scene/job, not just job ID, and export does not create generation requests.

`node --test tests/std-motion-hybrid-timeline.cjs` covers split continuity,
repeated/reordered clips, speed changes, native continuation, unused trimmed
inserts, invalid ranges and gaps. Existing AE method/worker protections remain.
`node tests/std-motion-hybrid-production-browser.cjs` uses the actual Editor,
three real PSDs and their finalized recording excerpts in the isolated frozen
workspace. Scene 19 is split, source-trimmed, overlapping/repeated and retimed.
One receipt maps to two output intervals, is polled once and produces a
38.191-second 1080p/24fps H.264/AAC MP4. Pending and too-short fixture outputs
are tested to block downloads without automatic generation.

No AI-provider-generated clip was established in the project's stored asset
inventory. The insertion fixture is the same project's retained 3-second AE
parallax video (`parallax-oneway-scene-019-3s.mp4`), SHA256
`b90feb8c6becf8bcf7725184861deffe920eaf3e9d9441690485925660039297`.
This validates the AI result decoding/mapping/mixing/export path, not real paid
generation or provider visual quality. No provider generation, database writes,
worker changes, external upload or publishing was performed.

Local evidence is in `output/motion-fullbody-validation/`:
`edited-hybrid-recorded-final.mp4`, `hybrid-editor-verification.json`,
`hybrid-editor-export-result.png`, `hybrid-audio-frame-qa.json` and insertion
frame PNGs. `python scripts/qa_motion_hybrid.py` compares decoded audio against
the exact joined recording (correlation 0.9999863, 0ms lag at 1ms resolution,
16.96ms codec padding). Two encoded insertion frames match the planned source
positions with mean RGB error 1.67 and 1.80/255 above the subtitle region.
The original PSDs/recording and private frozen manifests remain uncommitted.
Set `MOTION_FFMPEG` for browser/QA scripts; Python QA also requires NumPy.
