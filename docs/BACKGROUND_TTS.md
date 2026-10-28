# Background subtitle TTS

Subtitle Save + TTS saves subtitles first, then registers an immutable request in
`std_tts_jobs`. The browser polls status only. Closing the browser or switching
computers does not interrupt generation. Previously opened builds still use their
old browser loop: do not close an already running old job expecting it to migrate.
Use the new build for the next request; saved segment recordings are reusable.

Production Vercel Cron calls `/api/cron/tts` every minute using the existing
`CRON_SECRET`. No office worker or user computer is required. Initial dispatch may
take up to a minute. Each invocation claims a database lease, checkpoints groups
of 16 segments, then releases the job for a later invocation if necessary. Provider
generation remains limited to four simultaneous calls per invocation; cache
lookups are bounded at eight. Known cached segment metadata is fetched in bulk.
The old synchronous endpoint keeps groups of four for compatibility.

Jobs use a six-minute lease with a 300-second function limit. Interrupted groups
reuse stored clips; an expired lease can be reclaimed. Transient failures back off
and stop after three consecutive failures. Text, speaker/voice assignments and
saved subtitle/settings changes invalidate the frozen source. Final audio and
subtitle timing are saved server-side, and a job ID on the saved project allows
recovery after a crash between audio publication and queue completion. Existing
segment claims still prevent automatic duplicate spending on uncertain failures.

The table and claim RPC are service-role only. Web routes validate ownership,
saved subtitle/voice agreement, and speaker completeness. Only one active job per
project is allowed. Status replies omit request text and internal result data.
Completion refreshes saved editor state only when there are no unsaved edits.

Validation: `std-background-tts.cjs`, `std-stored-narration.cjs`,
`std-segment-audio-cache.cjs`, `std-tts-project-lookup.cjs`,
`std-tts-feedback.cjs`, TypeScript and Next build. Live DB checks cover role grants,
duplicate lease refusal and expired-lease recovery (rolled-back fixtures).
Throughput improvement is structural; provider latency and actual full-project
completion time must be measured separately, with no guaranteed speed multiplier.
