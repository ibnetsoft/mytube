import os

file_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\main.py'
with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

updates = {
    396: '    """Script Planning Page"""\n',
    405: '    """Script Generation Page"""\n',
    414: '    """Image Generation Page"""\n',
    423: '    """Video Generation Page"""\n',
    432: '    """TTS Generation Page"""\n',
    441: '    """Video Render Page"""\n',
    445: '        "title": "Video Render"\n'
}

# Note: lines list is 0-indexed, but my updates keys are 0-indexed (line_num - 1)
# Wait, previous attempt used 1-based keys and subtracted 1.
# Let's map directly to 0-based index.
# Previous file view:
# 397:     """?€蹂?湲고쉷 ?섏씠吏€""" -> Zero-index: 396
# 406:     """?€蹂??앹꽦 ?섏씠吏€""" -> Zero-index: 405
# 415:     """?대?吏€ ?앹꽦 ?섏씠吏€""" -> Zero-index: 414
# 424:     """?숈쁺???앹꽦 ?섏씠吏€""" -> Zero-index: 423
# 433:     """TTS ?앹꽦 ?섏씠吏€""" -> Zero-index: 432
# 442:     """?곸긽 ?뚮뜑留??섏씠吏€""" -> Zero-index: 441
# 446:         "title": "?곸긽 ?뚮뜑留? -> Zero-index: 445

for idx, content in updates.items():
    if idx < len(lines):
        lines[idx] = content

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Fixed lines in main.py')
