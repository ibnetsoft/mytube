# Manga scene layer generation

An exported CoWork scene manifest supports independent asset generation for seven AE manga templates: triple reaction, body qi, ink impact, wall impact, glasses reflection, kinetic title, and backlit hand. The exporter downloads the already approved character portraits beside the manifest and includes their hashes. The scene plan must identify each character or hand role with `ae_effect_plan.character_role_keys`; an ambiguous or missing identity stops generation before an image tool call.

The existing grid generation and `crop` step still supplies `scene-NNN.png` base images for every scene. Run that step with the same manifest and images directory before `publish`; `generate-layers` only creates the additional template layers.

Apply the `20260926134000_atomic_topic_scene_asset_publish.sql` migration before
`publish`. It merges only the approved asset fields under a topic row lock and
rejects a stale scene plan or asset snapshot; scene PNGs, derived PNGs and PSDs
use content-addressed GCS object paths.

```powershell
python worker/cowork_scene_assets.py export --topic-id 3197 --out output/topic-3197/manifest.json
python worker/cowork_scene_assets.py generate-layers --manifest output/topic-3197/manifest.json --images-dir output/topic-3197/images
python worker/cowork_scene_assets.py prepare-layers --manifest output/topic-3197/manifest.json --images-dir output/topic-3197/images
python worker/cowork_scene_assets.py approve-layers --manifest output/topic-3197/manifest.json --images-dir output/topic-3197/images --reviewer artist --note "Checked identity, alpha edges and composition"
python worker/cowork_scene_assets.py publish --manifest output/topic-3197/manifest.json --images-dir output/topic-3197/images
```

`generate-layers` asks the Codex built-in image generator for one background and one independent transparent PNG per required role. It attaches the matching portrait to character and hand requests. The broken wall uses the newly generated intact wall as its geometry reference. The glasses reflection is a separate scene plate that AE masks into both lenses. Training emphasis requires a separate training prop; the Korean title is editable AE text. The backlit hand uses a verified character portrait and AE adds rays at the planned light origin. Each cutout is validated for genuine alpha and placed in a template slot. A flattened scene is never used as a cutout. Invalid alpha, missing identity mapping, tool unavailability, safety refusal, or an interrupted call stops with `needs_review`; the generator does not silently change the prompt or retry. Existing role files are retained. A new generation plan or failed call requires a new revision directory or manually supplied valid PNGs.

The generated PNGs are not automatically approved. `prepare-layers` builds the PSD and preview, then a person checks identity, anatomy, the two wall states, lens contents, prop placement, and cutout edges before `approve-layers` records the PSD/input hashes. `publish` requires that approval. The image model can still produce the wrong face or anatomy despite receiving the reference, so the visual check is mandatory.
