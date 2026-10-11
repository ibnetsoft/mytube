# AIR Studio Supabase egress audit — 2026-10-11

The large recurring traffic comes from status endpoints downloading complete
project/source JSON and generation receipts, not recent video uploads.

## Evidence

For 2026-10-10, 00:00–24:00 Asia/Seoul, gateway logs show:

- 6,646 reads of the same project's project/source payload for generated speaker receipts.
- 6,645 reads of its topic's generation structure.
- 6,059 whole-project reads from the speaker-coordinate status endpoint.
- 645 admin topic-list requests fell back to `*,categories(*)` because four
  `generated_by_worker_*` columns do not exist in the deployed database.

This is request-count evidence. Gateway response sizes are missing for many DB
responses, so these counts cannot reproduce the billing total. Current JSON
sizes demonstrate why repeated requests can transfer many GB despite a small DB.

| Current project response | Whole row | Status context | Reduction |
| --- | ---: | ---: | ---: |
| Largest row | 9,495,780 bytes | 355,037 bytes | 96.3% |
| Frequently polled row | 7,096,085 bytes | 499,708 bytes | 93.0% |

Supabase Storage still contains historical PNGs (1.365 GB) and videos (0.240 GB).
Latest retained image creation was September 29 KST; video creation September 21.
The October 10 Storage gateway sample contains about 4 MB of PNG responses.
The current DB has one embedded media data URL, about 74 KB, in template settings.
Some active legacy assets still reference Supabase. They remain readable so old
projects and source media are not lost; this change does not delete old files.

## Changes

- A server-only, security-invoker RPC projects the status data before transmission.
  It excludes long image prompts and redundant structures, and replaces repeated
  receipt casts with a DB-checked `cast_matches` flag. Original stored payloads
  and cast identity used for source-bound approvals are preserved.
- Coordinate status and generated-asset enrichment share the projected context.
  Admin work information reads project IDs first and reuses this same context.
- Admin lists no longer request nonexistent worker columns or fall back to whole rows.
- Speaker-coordinate polling runs once per minute, pauses in hidden tabs and
  prevents overlapping requests. Initial reads and explicit actions stay immediate.
- Local thumbnail publishing uses GCS. Web image/video/audio uploads already use
  GCS. `content-assets.allowed_mime_types` now accepts only JSON and plain text,
  blocking future binary uploads even from older one-off scripts.
- New template overlay bitmaps are uploaded to GCS; Supabase keeps the reference.
  Legacy base64 overlays remain renderable and migrate when settings are saved.

## Verification

44 related Node tests and 23 image-worker tests pass; transparent template preview
and saved render input also pass the browser test. The Next.js production build
passes. Project-wide TypeScript checking has existing errors in unrelated routes;
no diagnostics were reported for the changed modules.

The status RPC is executable only by `service_role`, with a fixed empty search
path and no security-definer privileges. SQL checks verify the deployed response
sizes, grants and bucket MIME restriction. Subsequent billing usage is required
to measure the actual total egress reduction; past billed usage is unchanged.

## Browser/server/worker cache follow-up

- The September 25 KST log window had 267,329 database requests. Ready-topic
  structure polling accounted for tens of thousands of requests (28,587 for
  limit 40, another 4,058 for limit 20), matching the local AE worker path.
- AE polling now reads small candidate manifests containing DB-computed payload
  fingerprints. Only new/changed payloads are downloaded and saved atomically to
  a per-Supabase-project disk cache, surviving `--once` worker restarts.
- Project GET authenticates and checks ownership before conditional reads or
  server cache. A server-only DB fingerprint includes project, scenes, assets,
  topic generation data and render history. Unchanged browser requests receive
  HTTP 304 without reloading full project rows. Concurrent changes during response
  assembly prevent cache tagging. Explicit refresh bypasses both caches.
- Browser IndexedDB stores at most 20 project responses for one hour, scoped by
  a hash of session identity and impersonation (credentials are never stored).
  Reopening validates permissions and the latest fingerprint before using cached
  data. Cache/quota failures fall back to normal live requests.
- Server responses are gzip-compressed with version/owner scoped keys and a
  60-second TTL. Redis command size is capped at 900KB, network timeout at 2s,
  and per-instance memory at 64 entries. Text remains in Supabase; no project
  JSON was moved to GCS. GCS media already has private browser cache headers.
- Production has no Redis credentials or Marketplace installation. Attempted
  Upstash free plan, Tokyo region, eviction on, automatic paid upgrade off.
  Vercel requires the human user's Marketplace terms acceptance; no resource
  was created. Until acceptance/provisioning, server memory and browser caching
  operate normally. Redis cannot yet be described as active.
- Verified actual browser IndexedDB persistence across reload, changed versions,
  separate sessions, explicit refresh and revoked access; unit-tested compressed
  cache corruption, unavailable IndexedDB, and authorization before cache access.
  Worker cache and GCS upload regression tests pass. Production build passes;
  full TypeScript check still has pre-existing unrelated errors, with no errors
  in the new cache libraries or changed project route.
