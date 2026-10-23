# Original video playback

New submissions use `original_speed_no_freeze_no_loop/v1`.

- Play original source video at its recorded speed from the beginning; cut at the fixed scene boundary.
- Never insert a held frame, repeated short motion, video loop, reverse loop, or slow/fast playback to fill narration.
- If footage is too short, fail with the scene number, available duration and required duration. Preserve finalized audio and subtitle timing; require an explicit replacement decision.
- Allow one frame of timestamp rounding, without adding any padding filter.
- Reject known prefix-and-hold derivatives; prefer an eligible original, and report when only derivatives exist.
- Validate before cache reuse, even when AI review is disabled. Previous video render caches require the new playback-policy marker.
- EC, AE video handling, MotionFrames and final FFmpeg composition enforce this policy. Image animation and background audio looping are separate.
- Tests render two actual moving clips through the final compositor and verify source time, hard cuts, duration and short-input failure.
