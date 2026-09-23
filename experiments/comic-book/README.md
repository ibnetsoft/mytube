# Comic book rendering experiments (v1–v13)

Archived source for the local topic 3285 experiments. These scripts are prototypes,
not production entry points. The latest composition is `render_book_v13.py` with
`editorial_v13.py`: 26 portrait pages / 13 spreads, 130 seconds, individual panel
motion, speaker-facing short tails, silent thought bubbles, selective 88% opacity,
3D page curl and four rotating page sounds stretched to 115% duration.

## Reproduce using existing local media

From the repository root, copy these `.py` and `.cjs` files into
`output/comic-test-3285/` (back up any newer local scripts first). Run there so the
scripts retain their original repository-relative imports:

```powershell
.\venv\Scripts\python.exe output/comic-test-3285/render_book_v13.py
```

Required local inputs (intentionally not in Git):
- `images/scene_01.png` through `scene_10.png`
- `v2/events.json` and the narration/dialogue WAV files referenced by event IDs
- `v4/foreground.png`
- `page-turn-audio/page-turn-01.mp3` through `page-turn-04.mp3`
- Earlier preparation scripts additionally need `source.json`.

The repository font and installed Python environment are also required. Rendering
v13 reuses existing images and audio; it does not request AI generation. Outputs
remain in the ignored `output` directory. Historical v4–v7 scripts require an
existing transparent foreground image supplied as `foreground-source.png`.

## Production versus prototype

The shared renderer has the page mesh, bounded speech-bubble pop animation and
cycling recorded page sounds. The web canvas has the matching pop animation.
GCS-backed file assets skip the legacy storage lookup.

The v13 face coordinates are manually annotated for these sample images and
transformed with each crop/motion. They are not automatic face recognition.
Editorial layouts, speaker targeting, thought styling, opacity, portrait book
framing and 15% sound stretching remain prototype composition logic; archiving
this code does not deploy those features to the editor or rebuild AIRWorker.

Raw media, generated videos, database exports, migration backups, credentials and
machine-local caches are not tracked here. Existing local files are preserved.
