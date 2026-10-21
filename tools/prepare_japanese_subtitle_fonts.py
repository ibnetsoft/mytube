"""Download pinned, complete Japanese Noto fonts; retain all glyphs for web/worker."""
from pathlib import Path
import hashlib
import io
import json
import urllib.request
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1] / 'auth-web/public/fonts'
REV = 'f8d157532fbfaeda587e826d4cd5b21a49186f7c'
FONTS = {
    'NotoSansJP-Regular': 'Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf',
    'NotoSansJP-Bold': 'Sans/OTF/Japanese/NotoSansCJKjp-Bold.otf',
    'NotoSerifJP-Bold': 'Serif/OTF/Japanese/NotoSerifCJKjp-Bold.otf',
}

def main():
    manifest = {}
    for family, source in FONTS.items():
        url = f'https://raw.githubusercontent.com/notofonts/noto-cjk/{REV}/{source}'
        data = urllib.request.urlopen(url, timeout=120).read()
        font = TTFont(io.BytesIO(data))
        assert len(font.getBestCmap()) > 40000
        font.flavor = 'woff'
        font.save(ROOT / f'{family}.woff')
        manifest[family] = {'source': url, 'sha256': hashlib.sha256(data).hexdigest(),
                            'glyphs': len(font.getBestCmap())}
        print(family, manifest[family]['glyphs'], flush=True)
    for folder in ('Sans', 'Serif'):
        url = f'https://raw.githubusercontent.com/notofonts/noto-cjk/{REV}/{folder}/LICENSE'
        (ROOT / f'Noto-{folder}-LICENSE.txt').write_bytes(urllib.request.urlopen(url).read())
    (ROOT / 'japanese-sources.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')

if __name__ == '__main__':
    main()
