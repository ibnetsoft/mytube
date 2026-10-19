# Motion Studio / AE compatibility evidence

Inspected 2026-10-20. Existing AE remains the default production choice;
Motion Studio is an additional option. Script and render workers are retained.
This inventory is not a claim that Motion Studio can execute AE projects.

## Located local reference projects

- `ae_wuxia_fx/wuxia_ae_fx.aep`, with `create_wuxia_ae_fx.jsx` and
  `wuxia_ae_fx_report.txt`.
- `ae_layer_tests/layer_effect_tests.aep`, with
  `create_layer_effect_tests.jsx` and `effect_test_report.txt`.
- `output/ae-psd-wuxia-3285/wuxia-split-animation.aep`, with
  `create-layered-ae.jsx`, layered artwork and reference frames.
- `output/manga-ae-smoke/*/scene.aep` and accompanying `scene.jsx` files:
  wall impact/debris, kinetic titles, ink splat, glasses reflection, dialogue,
  body-following energy, backlit hand and triple reaction examples.

These are located files. Their binary project contents were not loaded into AE
or exhaustively extracted. Generated scripts and execution reports establish
the following dependencies, not a complete inventory of every AEP property.

| Existing dependency / evidence | Browser status |
| --- | --- |
| Layer transforms, camera motion | Implemented subset; not AE camera parity |
| Raster PSD masks | Grayscale, density, coordinates and disabled state supported; alpha baked at import |
| Shape paths and Trim Paths | Native polygonal strokes with animated trim start/end, color, width and glow; not arbitrary AE shape import |
| `ADBE Glo2` | Thresholded luminance/alpha seed, single additive blur, padded layer halo; calibrated violet-pulse preset; approximate algorithm |
| `ADBE Fast Blur`, `ADBE Gaussian Blur 2` | Native Canvas blur, animated strength and radius; approximate algorithm |
| `ADBE Fractal Noise` | Deterministic four-octave evolving value noise; approximate algorithm |
| `ADBE Turbulent Displace` | Evolving noise-driven WebGL mesh displacement; approximate algorithm |
| `ADBE Radial Wipe` | Animated clockwise radial reveal/removal |
| Feathered/vector masks, layer styles | Authored polygon mask, inversion, feather, outline and shadow; no automatic PSD style/vector import or animated path morph |
| Skeleton joints, IK, weighted mesh deformation | 12-bone full-body preset, hierarchical FK, up to 8 independent parented two-bone IK chains, angle limits, painted normalized four-influence grid skinning, animated radial pins/anchors; not AE Puppet equivalence |
| AE expressions, arbitrary AEP import, third-party binaries | No compatible runtime/importer |
| Existing render worker consumes browser composition | Not integrated |

`worker/manga_ae_templates.py` also contains shape construction, masks and parented
mouth/eye layers. These establish useful migration examples; parenting alone
does not establish a skeletal or Puppet rig implementation.

No third-party effect dependency or version has been established from the
inspected example reports. Installed `.aex` files alone do not prove project use.

## Acceptance requirements for further migration

1. Extract the actual dependency graph and parameters from each reference AEP
   into a separate report without overwriting the original.
2. Extend the implemented native rig/mesh/effect model for any further required
   constraints, finer weight/mesh solvers, animated path morphs and unsupported styles.
3. Port the listed effects and supported expression functions individually;
   unknown effects/expressions must be reported, never silently ignored.
4. Render the same scene/time/size in AE and the native engine and compare
   actual images and motion. Approximation must be described as approximation.
5. Integrate the native composition engine into the retained render worker,
   including asset identity, retries, narration/subtitle timing and output review.

AE expression objects and plug-in host APIs are specific to AE. Arbitrary native
plug-ins cannot be made web-compatible by loading their binaries as JavaScript.
Preserving the AE path remains necessary for exact unsupported behavior.

## Actual comparison and native animation verification

See `MOTION_NATIVE_VERIFICATION.md`. The retained AE MP4 and a web port of its
source JSX transforms/pulse are compared at 0, 1, 2, 3 and 95/24 seconds. This checks
one known project, not all listed projects or every effect. Native glow visibly
differs, although the pulse ROI error is reduced by 50.8% at the calibration time.
New rig/mesh output is rendered separately on the same real PSD because
the existing AE reference has no skeleton or Puppet animation to compare.
