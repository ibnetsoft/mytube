
path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\templates\pages\topic.html'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Insert at line 980 (index 980 because it's after 979)
# Actually line 980 in the view is empty.
# We want to replace lines 980-981 with the code.
start_idx = 980
end_idx = 981 # Replace one empty line

new_code = [
    "        console.error(e);\n",
    "        Utils.showToast(`오류 발생: ${e.message}`, 'error');\n",
    "    }\n",
    "    }\n"
]

lines[start_idx:end_idx] = new_code

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)
