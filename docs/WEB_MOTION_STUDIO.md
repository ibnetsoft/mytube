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
