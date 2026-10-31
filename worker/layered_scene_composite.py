"""Compose independently generated scene planes into a single preview image."""
from pathlib import Path
from PIL import Image


def composite_scene(background: Path, layers: list[Path], output: Path) -> Path:
    """Combine full-canvas PNGs in back-to-front order without replacing originals."""
    background, output = Path(background), Path(output)
    if output.exists():
        raise FileExistsError(f'refusing to overwrite existing image: {output}')
    with Image.open(background) as source:
        source.load()
        if source.format != 'PNG':
            raise ValueError('background must be PNG')
        canvas = source.convert('RGBA')
    if canvas.getchannel('A').getextrema() != (255, 255):
        raise ValueError('background must cover the canvas')
    for path in map(Path, layers):
        with Image.open(path) as source:
            source.load()
            if source.format != 'PNG' or source.size != canvas.size:
                raise ValueError(f'layer must be a same-size PNG: {path}')
            if 'A' not in source.getbands() and 'transparency' not in source.info:
                raise ValueError(f'layer requires transparent alpha: {path}')
            layer = source.convert('RGBA')
        minimum, maximum = layer.getchannel('A').getextrema()
        if minimum == 255 or maximum == 0:
            raise ValueError(f'layer must have both transparency and visible content: {path}')
        canvas.alpha_composite(layer)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents replacement if another worker won the race.
    with output.open('xb') as target:
        canvas.convert('RGB').save(target, format='PNG')
    return output
