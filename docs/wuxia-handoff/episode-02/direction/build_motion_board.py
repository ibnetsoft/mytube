"""Standalone editable-layer browser preview of the authored AE specification."""
import json,shutil
from pathlib import Path
P=Path(__file__).resolve().parent.parent
D=P/'direction'
repo=P.parents[2]
fonts=P/'fonts';fonts.mkdir(exist_ok=True)
for source in [repo/'static/fonts/NotoSansKR-Bold.ttf',repo/'auth-web/public/fonts/DoHyeon-Regular.ttf',repo/'auth-web/public/fonts/BlackHanSans-Regular.ttf']:
 shutil.copy2(source,fonts/source.name)
cfg=json.loads((D/'ae-scene-package.json').read_text(encoding='utf-8'))
body=(D/'motion-board-template.html').read_text(encoding='utf-8')
(D/'motion-preview.html').write_text(body.replace('/*__MANIFEST__*/',json.dumps(cfg,ensure_ascii=False).replace('</','<\\/')),encoding='utf-8')
