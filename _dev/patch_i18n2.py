import re

with open("services/i18n.py", "r", encoding="utf-8") as f:
    code = f.read()

ko_extra = """
        'th_desc': '설명',
        'th_publish': '발행',
        'th_upload': '업로드',
        'btn_landscape_mode': '풍경 모드',
"""

en_extra = """
        'th_desc': 'Desc',
        'th_publish': 'Publish',
        'th_upload': 'Upload',
        'btn_landscape_mode': 'Landscape Mode',
"""

vi_extra = """
        'th_desc': 'Mô tả',
        'th_publish': 'Xuất bản',
        'th_upload': 'Tải lên',
        'btn_landscape_mode': 'Cách thức phong cảnh',
"""

def inject_extra(code, lang, extra):
    pattern = rf"('{lang}':\s*{{)"
    return re.sub(pattern, r"\1\n" + extra, code, count=1)

code = inject_extra(code, 'ko', ko_extra)
code = inject_extra(code, 'en', en_extra)
code = inject_extra(code, 'vi', vi_extra)

with open("services/i18n.py", "w", encoding="utf-8") as f:
    f.write(code)

print("i18n.py updated successfully again!")
