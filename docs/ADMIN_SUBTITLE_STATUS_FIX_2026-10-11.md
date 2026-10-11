# Admin subtitle status and speaker sync

The administrator queue now labels its visual step 영상, matching the user portal.
General subtitle saves previously sent subtitle_tts_completed=false even for
style-only saves. They now preserve the marker. Server saves invalidate it only
when subtitle speech text/voice/attribution changes; script edits already invalidate
it. Save + TTS stops when subtitle saving fails and only records completion after
saved narration succeeds, while checking that the active project has not changed.

Admin speaker progress now shares the user portal's quote/AI/manual attribution
rules and count helper. Compact DB status projection includes dialogue annotations
and manual dialogue overrides, which were absent for the unsaved initial dialogue
classification shown in the user editor. Verified the live compact projection
retains the original codex-ai annotations for the two latest active Japanese projects.
No historical completion flags were guessed or backfilled.

22 targeted subtitle persistence, speaker assignment/editor and status tests pass.
Production build passes. Full type checking retains existing unrelated errors.
A wider old speaker-confirmation integration harness has a missing ttsNoticeCopy
mock; the unchanged test fails on its retry path, unrelated to the new count helper.
