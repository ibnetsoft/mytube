# Horizontal webtoon character motion

The active path is `/horizontal-webtoon` → local script worker direction → frozen
`register_std_horizontal_webtoon_pipeline` → native AE webtoon worker → final assembly.

Stored eligible video precedes PSD/image. Video is played from scene time zero at
original speed, with a continuous clock across panel cuts and reveals. A short
clip stops with scene number and measured/required duration; no hold, loop, or
speed change is permitted. Outdated voice-dependent mouth clips and source repair
derivatives are excluded. Finalized narration and subtitles remain authoritative.

A separated PSD can carry `layer_motion` in its prepared plan. Catalog indexes
refer to visible top-level composited layers in original stacking order. The
bottom layer must be a complete opaque background. Moving subjects must have
transparency. Unsupported clipping/blending or a failed rest-pose reconstruction
prevents layer animation. No guessed segmentation, duplicate flattened image,
background synthesis, or pose generation is used.

Each gesture specifies a pivot and two poses (`offset`, `rotation`) across the
immutable scene interval. Movement is bounded to 3% of source width/height and
four degrees. This permits restrained independent head/arm/character gestures
when those actual parts exist; it does not create walking or new anatomy.
Each panel crops the same animated source composition, preserving gesture time.

Flat images continue to support layout and camera zoom. The web UI distinguishes
existing video, separated character motion, and camera-only sources. Preparation
fingerprints include motion capability version 2, so old flattened plans must be
prepared again. Output AI review is skipped by the frozen submission policy,
with explicit skipped receipts; technical media errors still stop execution.

Verification: Python horizontal-webtoon tests, web plan/submission tests, a full
Next production build, and isolated native AE renders. The diagnostic PSD moves
its character approximately 56 output pixels with zero measured background change.
A two-cut video diagnostic matches source frame indexes 6/18/30/42 at four sample
times and produces 48 distinct frames. These are technical fixture measurements,
not content review or approval of a user's production film.
