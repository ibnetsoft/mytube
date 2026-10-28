"""Prepare topic mouth patches without changing active AE jobs or topic assets."""
import json
from pathlib import Path
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'worker'))
import cowork_scene_assets as publisher
from prepared_mouth_layers import prepare_scene
from ae_mouth import digest

topic = sys.argv[1]
directory = ROOT / 'output' / ('prepared-topic-' + topic)
directory.mkdir(parents=True, exist_ok=True)
row, structure, _, _ = publisher._topic(topic)
(directory / 'snapshot.json').write_text(json.dumps(structure, ensure_ascii=False), encoding='utf-8')
prior = json.loads((directory / 'results.json').read_text(encoding='utf-8')) if (directory / 'results.json').exists() else []
review_failures = {r['scene']: r for r in prior if r.get('state') in ('needs_review', 'failed')}
results = []
for scene in structure.get('scenes', []):
    number = scene.get('scene_number')
    asset = scene.get('metadata', {}).get('cowork_image_asset', {})
    geometry = asset.get('speaker_geometry') or {}
    if number in review_failures:
        results.append(review_failures[number])
        (directory / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        continue  # Preserve failed visual QA; never regenerate it automatically.
    if geometry.get('state') != 'ready' or not any(s.get('status') == 'visible' for s in geometry.get('speakers', [])):
        results.append({'scene': number, 'state': 'excluded', 'reason': geometry.get('state', 'missing_geometry')})
    else:
        print('Preparing scene', number, flush=True)
        try:
            image = directory / f'scene-{number:03d}.png'
            if not image.exists() or digest(image) != geometry['source_sha256']:
                image.write_bytes(publisher._download_gcs_bytes(asset['gcs_bucket'], asset['gcs_path']))
            if digest(image) != geometry['source_sha256']:
                raise ValueError('Published source changed; coordinates are stale')
            results.append({'scene': number, **prepare_scene(image, geometry)})
        except Exception as exc:
            visual_failure = isinstance(exc, ValueError) and str(exc).startswith('Generated mouth layers need review:')
            results.append({'scene': number, 'state': 'needs_review' if visual_failure else 'failed', 'error': str(exc)[:500]})
            (directory / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
            print('Needs review:' if visual_failure else 'Stopped:', type(exc).__name__, str(exc)[:300], flush=True)
            if visual_failure:
                continue
            raise  # Never repeat failed/uncertain paid generation automatically.
    (directory / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print('Preparation complete', flush=True)
