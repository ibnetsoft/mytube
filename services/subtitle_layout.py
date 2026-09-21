"""Subtitle scale shared with the web's 440px reference preview canvas."""


def subtitle_font_pixels(value, width):
    value = float(value)
    if 0.1 <= value <= 20:
        return width * min(22.0, max(13.0, value * 2.8)) / 440.0
    return value
