import sys, json, re
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'worker')]
from dotenv import load_dotenv
for f in ['.env', '.env.local', 'auth-web/.env.local']:
    load_dotenv(ROOT / f)
from worker.script_worker_store import ScriptStore
from worker.ae_highlight_worker import _download_gcs_file, GcsRef
store = ScriptStore()
project = store.request('GET', 'std_projects', params={'select':'project_payload', 'id':'eq.e9233112-f0d7-4b35-91bf-2f892844eb30'})[0][0]
anchors = project['project_payload']['structure']['character_anchors']
characters = [anchors['main_character'], *anchors['supporting_characters']]
assert len(characters) == 5
results = []
for i, character in enumerate(characters):
    query = parse_qs(urlparse(character['image_url']).query)
    path = query['path'][0]
    assert re.fullmatch(r'topics/\d+/characters/[^/]+\.(png|jpe?g|webp|gif)', path)
    destination = ROOT / f'_dev/artifacts/image_repair_3373/thumbnail-verification-{i}.png'
    _download_gcs_file(GcsRef(query['bucket'][0], path), destination)
    with Image.open(destination) as image:
        image.load()
        results.append({'name':character['name'], 'size':image.size, 'valid':True})
(ROOT / '_dev/artifacts/image_repair_3373/thumbnail-verification.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf8')
print(json.dumps(results, ensure_ascii=False))
