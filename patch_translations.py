
import os

file_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\main.py'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

insertion_index = -1
for i, line in enumerate(lines):
    if 'templates = Jinja2Templates' in line:
        insertion_index = i + 1
        break

if insertion_index != -1:
    print(f"Inserting translations at line {insertion_index + 1}")
    
    translations_code = [
        '\n',
        '# [PATCH] Translations for Templates\n',
        'TRANSLATIONS = {\n',
        '    "ko": {\n',
        '        "trend_title": "트렌드 키워드",\n',
        '        "trend_refresh": "새로고침",\n',
        '        "trend_period_now": "지금",\n',
        '        "trend_period_week": "이번 주",\n',
        '        "trend_period_month": "이번 달",\n',
        '        "trend_age_all": "전체",\n',
        '        "trend_age_10s": "10대",\n',
        '        "trend_age_20s": "20대",\n',
        '        "trend_age_30s": "30대",\n',
        '        "trend_age_40s": "40대",\n',
        '        "trend_age_50s": "50대",\n',
        '        "trend_placeholder": "데이터를 불러오는 중...",\n',
        '        "trend_load_btn": "데이터 로드",\n',
        '        "search_placeholder": "검색어 입력",\n',
        '        "search_sort_relevance": "관련순",\n',
        '        "search_sort_views": "조회수순",\n',
        '        "search_sort_date": "날짜순",\n',
        '        "search_sort_rating": "평점순",\n',
        '        "search_period_all": "전체",\n',
        '        "search_period_week": "이번 주",\n',
        '        "search_period_month": "이번 달",\n',
        '        "search_period_year": "올해",\n',
        '        "search_lang_all": "모든 언어",\n',
        '        "search_btn": "검색",\n',
        '        "recommended_topics": "추천 주제",\n',
        '        "status_loading": "로딩 중...",\n',
        '        "search_results": "검색 결과",\n',
        '        "btn_sort_viral": "바이럴순",\n',
        '        "btn_sort_views": "조회수순",\n',
        '        "btn_save_archive": "보관함 저장",\n',
        '        "btn_analyze_batch": "일괄 분석",\n',
        '        "th_thumb": "썸네일",\n',
        '        "th_channel": "채널",\n',
        '        "th_title": "제목",\n',
        '        "th_upload": "업로드",\n',
        '        "th_subs": "구독자",\n',
        '        "th_views": "조회수",\n',
        '        "th_contribution": "기여도",\n',
        '        "th_performance": "성과",\n',
        '        "th_likes": "좋아요",\n',
        '        "th_actions": "작업",\n',
        '        "empty_title": "검색 결과가 없습니다",\n',
        '        "empty_desc": "다른 키워드로 검색해보세요",\n',
        '        "loading_analysis": "분석 중...",\n',
        '        "loading_desc": "잠시만 기다려주세요"\n',
        '    }\n',
        '}\n',
        '\n',
        'def t(key, lang="ko"):\n',
        '    # Fallback to Korean if lang not found\n',
        '    return TRANSLATIONS.get(lang, TRANSLATIONS["ko"]).get(key, key)\n',
        '\n',
        'templates.env.globals["t"] = t\n',
        '\n'
    ]
    
    lines[insertion_index:insertion_index] = translations_code
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print("Translations patched.")
else:
    print("Could not find insertion point.")
