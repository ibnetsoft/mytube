"""Review saved 3386 effect composites and planes without face comparison."""
import json, sys, time, traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'worker')]
from codex_content_runner import CodexStagedContentRunner
from worker.script_topic_delivery import write

OUT = ROOT / 'output/codex-local-console/d57947df4af3479b85185c7ca0610a60/actual-production'
REVIEWS = OUT / 'layer-reviews'
REVIEWS.mkdir(exist_ok=True)
STATUS = OUT / 'final-review-status.json'
manifest = json.loads((OUT / 'manifest.json').read_text(encoding='utf-8'))
specs = {s['scene_number']: s for s in manifest['scene_specs']}

def review(number):
    target = REVIEWS / f'scene-{number:03d}.json'
    if target.exists():
        return
    image = OUT / 'images' / f'scene-{number:03d}.png'
    receipt = json.loads((OUT / 'images' / f'scene-{number:03d}-planes.json').read_text(encoding='utf-8'))
    paths = [str(image)] + [str(OUT / 'images' / f'scene-{number:03d}-{role}.png') for role in receipt['files']]
    result = CodexStagedContentRunner()._stage('review-3386-layers', f'scene-{number:03d}',
        {'_local_image_paths': paths, 'scene_spec': specs[number]},
        'Inspect the attached actual composite and independent planes for scene direction, narrative action, placement, compositing artifacts, transparency and usable separation. Do not compare faces or claim facial identity approval. Return JSON verdict pass or needs_review, evidence array of observed facts and issues array. Be candid and identify major story contradictions.')
    if result.get('verdict') not in ('pass', 'needs_review') or not result.get('evidence'):
        raise ValueError(f'scene {number}: incomplete visual review')
    write(target, result)

try:
    write(STATUS, {'status':'running', 'updated_at':time.time()})
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(review, range(19, 51)))
    write(STATUS, {'status':'completed', 'count':32, 'updated_at':time.time()})
except Exception as exc:
    write(STATUS, {'status':'failed', 'error':str(exc), 'traceback':traceback.format_exc(), 'updated_at':time.time()})
