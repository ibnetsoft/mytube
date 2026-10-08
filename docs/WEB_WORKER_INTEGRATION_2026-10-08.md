# Web and worker integration — 2026-10-08

The integration starts at main `a68ed83e`, merges `codex/region-motion-th` (`409b87fd`, including `89892780`), then `codex/tracked-video-mouth` (`e970038d`). Both histories are retained; no force push or branch replacement is required.

## Resolutions

- Keep main's localized persistent save/submission notices, project-switch guards, duplicate-submit protection, explicit template background choices and saved-audio-only subtitle preview.
- Keep dialogue assignment, recorded TTS timing, speaker coordinates, region layer preparation/reuse and Thai region controls.
- A 202 AE postprocessing response is shown as pending processing/review, not as an already queued final render. Do not reopen the editor or overwrite ongoing edits on this response.
- Keep tracked video mouth rendering and reviewed freeze/zoom tails. Coordinate analysis remains its own supervisor role; region and tail workers are also available.
- Point final rendering to the tracked repository-root `remote_drive_worker.py`; the prior `worker/remote_render_source.py` entry did not exist in the repository.
- Discover AE-enabled projects waiting for final submission as well as already-submitted projects, excluding canceled/approved projects. This prevents tail processing from waiting for a submission that is itself waiting for AE review.

## Verification

- Production Next.js build passes.
- Python tests cover region masks/reuse, tracked video movement and identity rejection, mouth rendering workflow, coordinate analysis and supervisor commands.
- Web tests cover AE review gating, finalized TTS selection/timing, region layers, Thai copy, saved-audio preview, submission feedback, BGM and GCS asset preparation.
- Read-only production database query confirms eligible AE projects are discoverable.
- Full TypeScript checking still reports pre-existing repository errors (including unrelated API export/target errors and the existing `saveComicSettings` reference). The configured production build skips full type/lint checks; it is not a clean full-repository type-check claim.

## Windows source worker rollout

The Windows source checkout must also contain the integrated main commit. Website deployment alone does not update a running local Python worker. Verify the working folder and preserve local changes before pulling. Stop the supervisor gracefully and wait for active work to finish; update the clean checkout with `git fetch origin` followed by `git merge --ff-only origin/main`. This works from either merged feature branch because main now contains both histories. Restart the existing source worker with the same environment and credentials.

Use `python worker/local_media_supervisor.py --status` to inspect the supervisor. Do not run duplicate standalone region/mouth workers alongside it; the supervisor deliberately waits when media workers are already active. Do not build or install retired Windows desktop packages.
