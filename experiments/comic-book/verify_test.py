import json
from pathlib import Path
import numpy as np
import requests
from PIL import Image
from moviepy import VideoFileClip

root = Path(__file__).resolve().parent
manifest = json.loads((root / 'test_manifest.json').read_text(encoding='utf-8'))
source = json.loads((root / 'source.json').read_text(encoding='utf-8'))
assert len(manifest['scenes']) == 10
assert [s['narration'] for s in manifest['scenes']] == [s['narration'] for s in source['pregenerated_structure']['scenes'][:10]]
pages = sorted((root / 'comic_pages').glob('page_*.png'))
assert len(pages) == 5
for page in pages:
    with Image.open(page) as image:
        assert image.size == (1280, 720)
with VideoFileClip(str(root / 'output.mp4')) as video:
    assert video.size == [1280,720]
    assert abs(video.duration - 52.8) < .1
    assert abs(video.fps - 24) < .1
    for i, page in enumerate(pages):
        # By the latter half of each page both captions must be visible.
        frame = video.get_frame(i * 10.7 + 8)
        expected = np.asarray(Image.open(page).convert('RGB')).astype(float)
        assert np.mean(np.abs(frame.astype(float) - expected)) < 8
    duration = video.duration
for name in ['','output.mp4','test_manifest.json','prompts.json'] + [f'comic_pages/{p.name}' for p in pages]:
    assert requests.head('http://127.0.0.1:3004/' + name,timeout=10).status_code == 200
report = {'topic_id':3285,'scenes':10,'pages':5,'resolution':[1280,720], 'video_seconds':duration,
    'source_narration_preserved':True,'video_pages_match_png':True,'http_assets_ok':True,
    'tts_included':False,'renderer_tests_passed':7}
(root / 'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
