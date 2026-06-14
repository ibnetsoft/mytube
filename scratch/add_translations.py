import re

filepath = 'services/i18n.py'

new_keys = {
    'ko': {
        'daily_assigned_topic': "오늘의 배정 주제",
        'ai_recommended': "AI 추천",
        'daily_assigned_topic_desc': "대표님이 배정하신 오늘의 유튜브 비디오 제작 주제를 가져옵니다.",
        'btn_get_daily_topic': "오늘의 주제 가져오기",
        'toast_fetching_topic': "오늘의 주제를 조회하는 중...",
        'toast_project_created': "새 프로젝트가 성공적으로 생성되었습니다!",
        'toast_no_assigned_topics': "배정된 대기 중인 주제가 없습니다.",
        'toast_fetch_topic_failed': "주제 가져오기 실패: ",
        'label_text': "글자",
        'label_stroke': "테두리",
        'label_bg': "배경",
        'placeholder_mp3_url': "(MP3 URL 입력)"
    },
    'en': {
        'daily_assigned_topic': "Today's Assigned Topic",
        'ai_recommended': "AI Recommendation",
        'daily_assigned_topic_desc': "Gets today's YouTube video production topic assigned by the representative.",
        'btn_get_daily_topic': "Get Today's Topic",
        'toast_fetching_topic': "Retrieving today's topic...",
        'toast_project_created': "New project successfully created!",
        'toast_no_assigned_topics': "No assigned topics waiting.",
        'toast_fetch_topic_failed': "Failed to get topic: ",
        'label_text': "Text",
        'label_stroke': "Stroke",
        'label_bg': "BG",
        'placeholder_mp3_url': "(Enter MP3 URL)"
    },
    'vi': {
        'daily_assigned_topic': "Chủ đề phân bổ hôm nay",
        'ai_recommended': "AI khuyên dùng",
        'daily_assigned_topic_desc': "Lấy chủ đề sản xuất video YouTube hôm nay do đại diện phân bổ.",
        'btn_get_daily_topic': "Lấy chủ đề hôm nay",
        'toast_fetching_topic': "Đang truy vấn chủ đề hôm nay...",
        'toast_project_created': "Dự án mới đã được tạo thành công!",
        'toast_no_assigned_topics': "Không có chủ đề chờ phân bổ.",
        'toast_fetch_topic_failed': "Lấy chủ đề thất bại: ",
        'label_text': "Chữ",
        'label_stroke': "Viền",
        'label_bg': "Nền",
        'placeholder_mp3_url': "(Nhập URL MP3)"
    }
}

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Insert for 'ko'
# Let's find "'ko': {" and insert right after it
ko_match = re.search(r"\'ko\'\s*:\s*\{", content)
if ko_match:
    idx = ko_match.end()
    ko_insert = ""
    for k, v in new_keys['ko'].items():
        ko_insert += f"\n        '{k}': '{v}',"
    content = content[:idx] + ko_insert + content[idx:]

# Insert for 'en'
en_match = re.search(r"\'en\'\s*:\s*\{", content)
if en_match:
    idx = en_match.end()
    en_insert = ""
    for k, v in new_keys['en'].items():
        en_insert += f"\n        '{k}': '{v}',"
    content = content[:idx] + en_insert + content[idx:]

# Insert for 'vi'
vi_match = re.search(r"\'vi\'\s*:\s*\{", content)
if vi_match:
    idx = vi_match.end()
    vi_insert = ""
    for k, v in new_keys['vi'].items():
        vi_insert += f"\n        '{k}': '{v}',"
    content = content[:idx] + vi_insert + content[idx:]

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("Translations successfully injected!")
