with open('services/i18n.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Let's replace translations at specified lines
lines[382-1] = "        'btn_split_2lines': '1줄로 분할',\n"

# For English at 3132 and 3308
lines[3132-1] = "        'btn_split_2lines': 'Split to 1 line',\n"
lines[3308-1] = "        'btn_split_2lines': 'Split to 1 line',\n"

# confirm_split_all for English at 3335
lines[3335-1] = "        'confirm_split_all': 'Do you want to split all subtitles into 1 line?\\nLong subtitles will be divided, and time will be redistributed evenly.',\n"

# For Vietnamese at 5019 and 5284
lines[5019-1] = "        'btn_split_2lines': 'Chia phụ đề 1 dòng',\n"
lines[5284-1] = "        'btn_split_2lines': 'Chia 1 dòng',\n"

# confirm_split_all for Vietnamese at 5057 and 5311
lines[5057-1] = "        'confirm_split_all': 'Bạn có muốn chia tất cả phụ đề thành 1 dòng không?\\n(Chỉ những câu dài mới được chia)',\n"
lines[5311-1] = "        'confirm_split_all': 'Bạn có muốn chia tất cả phụ đề thành 1 dòng không?\\nPhụ đề dài sẽ được chia thành nhiều phụ đề ngắn và thời gian sẽ được phân bổ lại đều.',\n"

with open('services/i18n.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Split i18n translations successfully updated!")
