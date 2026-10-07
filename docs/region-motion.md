# Web region motion

The subtitle-page character panel opens **영역 동작 지정 · AE**. Select an image scene, draw a rectangle or a polygon, select a pivot, and choose horizontal/vertical oscillation, rotation, or scale. Set amplitude, seconds per cycle, number of cycles, and starting subtitle. The restricted command parser fills those same fields; it does not execute natural language as script.

**설정 저장** saves an immutable plan. **AE 영상 만들기** queues native AE rendering. **AE 결과 보기** resolves an authenticated private playback URL. **확인한 영상을 씬에 적용** registers the reviewed output as the scene video. Pending/unreviewed renders never replace scene media. Deleting all regions and saving clears the latest plan. Source and timing changes require a new render.

Motion is a rigid selected cutout around a pivot, not a joint rig. The worker repairs the exposed background with local OpenCV inpainting; complex backgrounds can need a smaller amplitude or a more precise polygon. The browser previews the movement path with gray exposed regions; inspect the rendered video before applying. Existing videos/lip-sync are not automatically composited with these still-image cutouts.

## Windows backend

Run a separate source checkout. Do not build or modify retired installers. Reuse the existing backend Python interpreter and credentials via `AIR_WORKER_ENV_FILE`, and give this worker its own `AIRWORKER_HOME`. `opencv-python-headless==4.10.0.84`, Pillow, NumPy and the existing AE backend dependencies are required. An isolated `--target` directory for OpenCV avoids changing other workers' dependencies; prepend it to this process's `PYTHONPATH`.

```powershell
$env:AIR_WORKER_ENV_FILE = 'C:/path/to/existing-worker/.env'
$env:AIRWORKER_HOME = Join-Path $env:LOCALAPPDATA 'AIRStudio/RegionMotionWorker'
$env:PYTHONPATH = Join-Path $env:AIRWORKER_HOME 'python'
& $workerPython -u worker/ae_region_motion_worker.py
```

The worker claims `std_project_assets` records with `metadata.kind=region_motion_plan`. Claims use `updated_at` compare-and-swap and a per-claim lease; a heartbeat keeps an active render from being reclaimed. Failed jobs do not block other scenes. Re-rendering creates a new plan; obsolete plans cannot be applied. The native AE instance is isolated (`AfterFX -m` through the existing AE runner).

Local/API tests:

```sh
node auth-web/tests/std-region-motion.cjs
node auth-web/tests/std-region-motion-api.cjs
python -m pytest tests/test_ae_region_motion.py -q
```

On the Windows AE host, this synthetic smoke test creates a 4-second native AE clip and checks that the rendered arm moves left and right. It does not modify any project or database:

```powershell
& $workerPython worker/ae_region_motion_smoke.py output/region-motion-smoke
```

## Reusable precise layers

Before a new render, use **외곽선 분리·배경 복원**. The worker follows image edges inside the selected polygon with GrabCut, or preserves the polygon exactly when selected. Review every transparent foreground, repaired background and composite. The brush editor can erase alpha or restore source pixels. Save the corrected foreground and prepare again; **레이어 확정하고 재사용** approves the package. Image/geometry/supplement changes invalidate reuse; animation, anchor and subtitle timing changes do not.

Mark occluded/cropped parts explicitly. Such regions cannot be prepared without a completed full-canvas transparent PNG. Alternatively fix the scene image on the image page and redraw. A corrected full-canvas background can replace the automatic local inpainting. Automatic repair is an estimate, not reconstruction of unseen anatomy. Upload PNG/JPEG/WebP background or transparent PNG foreground, at original canvas dimensions or the package dimensions (longest side at most 1920), maximum 4 MB. Preview PNGs can be downloaded for external editing.

Packages and supplements are private `std_project_assets` records (`region_layer_package` / `region_layer_upload`) with immutable GCS objects. The same region-motion worker handles preparation and uses verified saved PNG bytes on later renders. No database schema change or new image model dependency is required.

Validation: `node --test auth-web/tests/std-region-layers-api.cjs` and `python -m pytest tests/test_ae_region_layers.py -q`. Native saved-layer rendering: `python worker/ae_region_motion_smoke.py output/region-layer-smoke --layers`.
