
import sys

target_file = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\services\i18n.py'

encodings = ['utf-8', 'cp949', 'euc-kr']
content = None
chosen_enc = None

for enc in encodings:
    try:
        with open(target_file, 'r', encoding=enc) as f:
            content = f.read()
            chosen_enc = enc
            print(f"Successfully read with {enc}")
            break
    except Exception:
        continue

if content:
    new_content = content.replace("숏폼 템플릿", "템플릿")
    
    # Also fix the previous failed attempt if it replaced with weird chars
    # We saw " ø" in my thought, but let's just make sure "숏폼 템플릿" -> "템플릿" is done.
    
    with open(target_file, 'w', encoding=chosen_enc) as f:
        f.write(new_content)
    print(f"Replacement successful using {chosen_enc}")
else:
    print("Failed to read file with any encoding")
