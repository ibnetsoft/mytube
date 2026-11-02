"""Subtitle scale shared with the web's 440px reference preview canvas."""


def subtitle_font_pixels(value, width):
    value = float(value)
    if 0.1 <= value <= 20:
        return width * min(22.0, max(13.0, value * 2.8)) / 440.0
    return value


def subtitle_outline_pixels(value, width):
    """Outer outline radius matching CSS text-stroke with stroke-before-fill.

    The editor stores full stroke width in 1920px canvas units. CSS centers
    that stroke on the glyph edge; painting the fill last hides its inner half.
    ASS and Pillow outline sizes specify the remaining outward radius.
    """
    return max(0.0, float(value)) * float(width) / 1920.0 / 2.0
