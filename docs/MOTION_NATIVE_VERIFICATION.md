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
| 2 | 3.611 | 32.803 |
| 3.958333 | 3.167 | 35.362 |

The comparison sheet has AE, native and 4× absolute difference in each row.
The middle row visibly shows a different violet glow. Color conversion, encoded
video, resampling and effect differences all contribute to these measurements.
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
- `rig-mesh.mp4` / `rig-mesh-preview.png`: pattern deformation diagnostic.
- `real-psd-rig-demo.mp4` / `.png`: native animation on the real PSD.
- `layer-tools.png`: browser editor controls.

AE expressions, arbitrary AEP import, third-party plug-in execution, arbitrary
PSD styles, Puppet's exact deformation solver and automatic hidden-pixel repair
remain outside this implementation.
