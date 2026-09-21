"""Prepare shared browser/worker assets (development dependency: fonttools[woff]).

Keep glyph outlines intact. Three supplied WOFFs contain a blank space glyph
but omit U+0020 from their cmap, causing system-font fallback even for spaces.
"""
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen

ROOT = Path(__file__).resolve().parents[1] / 'auth-web/public/fonts'


def main():
    for source, output in (
        ('NanumSquareExtraBold.woff2', 'NanumSquareExtraBold.ttf'),
        ('GmarketSansBold.woff', 'GmarketSansBold.otf'),
        ('JalnanOTF00.woff', 'Jalnan.otf'),
        ('BinggraeMelona-Bold.woff', 'BinggraeMelona-Bold.otf'),
    ):
        font = TTFont(ROOT / source)
        if 32 not in font.getBestCmap():
            glyph = font.getGlyphOrder()[1]
            pen = BoundsPen(font.getGlyphSet())
            font.getGlyphSet()[glyph].draw(pen)
            assert pen.bounds is None and font['hmtx'][glyph][0] > 0
            for table in font['cmap'].tables:
                if table.isUnicode():
                    table.cmap[32] = glyph
        font.flavor = None
        font.save(ROOT / output)


if __name__ == '__main__':
    main()
