# Archived Artifacts

This folder keeps old generated files that used to live in the repository root.

Current layout:

- `debug/`: debug dumps, trace files, screenshots, and temporary logs
- `media/`: generated or temporary audio/video files
- `schemas/`: temporary API/schema JSON dumps
- `samples/`: sample images and audio files
- `test_output/`: generated files from manual rendering tests
- `test_webtoon/`: generated files from manual webtoon tests
- `databases/`: old root-level database placeholders
- `logs/`: old root-level server/test logs

Runtime output should continue to go to `output/`, `data/`, `logs/`, `assets/`, and `uploads/`.
Those folders are intentionally ignored by Git.
