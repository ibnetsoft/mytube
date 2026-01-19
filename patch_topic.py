
path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\templates\pages\topic.html'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Indicated lines: 938-946 (0-indexed means 937-946)
start_idx = 937
end_idx = 946

new_code = [
    "                // [MODIFIED] Repository Notification\n",
    "                Utils.showToast('저장소에 분석 결과가 저장되었습니다.', 'info');\n",
    "                setTimeout(() => {\n",
    "                    if(confirm('저장소로 이동하여 결과를 확인하시겠습니까?')) {\n",
    "                        window.location.href = '/repository';\n",
    "                    }\n",
    "                }, 500);\n"
]

lines[start_idx:end_idx] = new_code

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)
