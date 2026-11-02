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


def wrap_subtitle_lines(text, measure, max_width):
    """Wrap display text by measured width without modifying the stored caption.

    Prefer sentence/phrase boundaries, keep punctuation with its preceding text,
    and rebalance a one-character last line whenever both lines can fit.
    """
    import unicodedata

    result = []
    forbidden_start = set('、。，．！？!?.,:;：；)]}）］｝」』】〉》’”ぁぃぅぇぉっゃゅょァィゥェォッャュョー')
    forbidden_end = set('([{（［｛「『【〈《‘“')
    particles = set('はがをにへとものでやかのねよ은는이가을를에도의와과')
    for paragraph in str(text or '').replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        remaining = paragraph.strip()
        if not remaining:
            continue
        while measure(remaining) > max_width and len(remaining) > 1:
            candidates = []
            for i in range(1, len(remaining)):
                left, right = remaining[:i].rstrip(), remaining[i:].lstrip()
                if not left or not right or measure(left) > max_width:
                    continue
                if right[0] in forbidden_start or left[-1] in forbidden_end or unicodedata.combining(right[0]):
                    continue
                # A word boundary / punctuation / grammatical particle is a
                # useful phrase boundary; size still dominates distant splits.
                boundary = 3 if left[-1] in '。！？!?、，,.；;：:' else 2 if remaining[i-1].isspace() or remaining[i].isspace() else 1 if left[-1] in particles else 0
                orphan = len(right.strip()) == 1
                score = round((measure(left) / max_width + boundary * 0.10 - (4 if orphan else 0)) * 1000)
                candidates.append((score, i, left, right))
            if not candidates:
                # A glyph wider than the canvas must be handled by the caller.
                result.append(remaining[0])
                remaining = remaining[1:]
                continue
            _, _, left, remaining = max(candidates)
            result.append(left)
        if remaining:
            result.append(remaining)
    return result or ['']
