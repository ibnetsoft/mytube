import sys
import os

i18n_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\services\i18n.py'

NEW_KEYS = {
    'intro_settings_title': {
        'ko': '🎥 인트로 설정 (Loop Mode)',
        'en': '🎥 Intro Settings (Loop Mode)',
        'vi': '🎥 Thiết lập Intro (Loop Mode)'
    },
    'placeholder_video_search': {
        'ko': '검색어 (예: winter night)',
        'en': 'Keywords (e.g. winter night)',
        'vi': 'Từ khóa (Vd: đêm đông)'
    },
    'btn_auto': {
        'ko': '🤖 자동',
        'en': '🤖 Auto',
        'vi': '🤖 Tự động'
    },
    'btn_video_upload': {
        'ko': '📤 영상 업로드',
        'en': '📤 Upload Video',
        'vi': '📤 Tải video lên'
    },
    'status_uploading': {
        'ko': '업로드 중...',
        'en': 'Uploading...',
        'vi': 'Đang tải lên...'
    },
    'video_results_title': {
        'ko': '🎬 동영상 결과',
        'en': '🎬 Video Results',
        'vi': '🎬 Kết quả video'
    },
    'vgen_complete_title': {
        'ko': '🎉 동영상 설정이 완료되었습니다!',
        'en': '🎉 Video settings completed!',
        'vi': '🎉 Thiết lập video hoàn tất!'
    },
    'btn_go_tts': {
        'ko': '🔊 음성(TTS) 생성하러 가기',
        'en': '🔊 Go to TTS (Voice)',
        'vi': '🔊 Đi đến tạo giọng nói (TTS)'
    },
    'status_search_results': {
        'ko': '{count}개의 영상을 찾았습니다.',
        'en': 'Found {count} videos.',
        'vi': 'Tìm thấy {count} video.'
    },
    'status_no_results': {
        'ko': '검색 결과가 없습니다.',
        'en': 'No results found.',
        'vi': 'Không tìm thấy kết quả.'
    },
    'vgen_complete_desc': {
        'ko': '배경 동영상은 자동으로 반복 재생됩니다.',
        'en': 'Background video will loop automatically.',
        'vi': 'Video nền sẽ được phát lặp lại tự động.'
    },
    'status_loading_video': {
        'ko': '저장된 영상 불러옴',
        'en': 'Loaded saved video',
        'vi': 'Đã tải video đã lưu'
    },
    'char_consistency_title': {
        'ko': '👤 주인공/캐릭터 일관성 유지 (Reference)',
        'en': '👤 Character Consistency (Reference)',
        'vi': '👤 Duy trì tính nhất quán nhân vật (Tham chiếu)'
    },
    'ethnicity_title': {
        'ko': '🌍 주인공/등장인물 인종 (Ethnicity) 설정',
        'en': '🌍 Character Ethnicity Settings',
        'vi': '🌍 Thiết lập sắc tộc nhân vật'
    },
    'ethnicity_desc': {
        'ko': '전 세계 8대 주요 그룹 중 하나를 선택하세요. (생성되는 이미지 프롬프트에 자동 반영됩니다)',
        'en': 'Select one of the 8 major world groups. (Auto-applied to prompts)',
        'vi': 'Chọn một trong 8 nhóm chính trên thế giới. (Sẽ tự động áp dụng)'
    },
    'ethnicity_1': {
        'ko': '1. 동북아시아 계열 (East Asian)',
        'en': '1. East Asian',
        'vi': '1. Đông Bắc Á (East Asian)'
    },
    'ethnicity_2': {
        'ko': '2. 동남아시아 및 태평양 계열 (Southeast Asian & Pacific Islander)',
        'en': '2. Southeast Asian & Pacific Islander',
        'vi': '2. Đông Nam Á & Thái Bình Dương'
    },
    'ethnicity_3': {
        'ko': '3. 남부 아시아 계열 (South Asian)',
        'en': '3. South Asian',
        'vi': '3. Nam Á (South Asian)'
    },
    'ethnicity_4': {
        'ko': '4. 유럽 및 코카서스 계열 (European / Caucasian)',
        'en': '4. European / Caucasian',
        'vi': '4. Châu Âu / Da trắng'
    },
    'ethnicity_5': {
        'ko': '5. 중동 및 북아프리카 계열 (Middle Eastern & North African)',
        'en': '5. Middle Eastern & North African',
        'vi': '5. Trung Đông & Bắc Phi'
    },
    'ethnicity_6': {
        'ko': '6. 아프리카 사하라 이남 계열 (Sub-Saharan African)',
        'en': '6. Sub-Saharan African',
        'vi': '6. Châu Phi hạ Sahara'
    },
    'ethnicity_7': {
        'ko': '7. 라틴 아메리카 혼혈 계열 (Hispanic / Latino - Mestizo)',
        'en': '7. Hispanic / Latino - Mestizo',
        'vi': '7. Mỹ Latinh lai'
    },
    'ethnicity_8': {
        'ko': '8. 원주민 및 오세아니아 계열 (Indigenous / Indigenous Australian)',
        'en': '8. Indigenous / Indigenous Australian',
        'vi': '8. Bản địa / Châu Đại Dương'
    },
    'char_analysis_result_title': {
        'ko': '캐릭터 분석 결과 및 관리',
        'en': 'Character Analysis Result & Management',
        'vi': 'Kết quả phân tích & Quản lý nhân vật'
    },
    'btn_add_char_manual': {
        'ko': '➕ 직접 추가',
        'en': '➕ Add Manually',
        'vi': '➕ Thêm thủ công'
    },
    'btn_reset_all': {
        'ko': '🗑️ 전체 초기화',
        'en': '🗑️ Reset All',
        'vi': '🗑️ Khôi phục tất cả'
    },
    'char_edit_helper': {
        'ko': '* 이름을 클릭하여 수정할 수 있습니다. 수동으로 편집한 내용은 반드시 [서버에 저장]을 눌러야 오토파일럿에 반영됩니다.',
        'en': '* Click name to edit. Manually edited content must be [Saved to Server] for Autopilot.',
        'vi': '* Nhấp vào tên để sửa. Phải nhấn [Lưu lên máy chủ] để áp dụng vào Autopilot.'
    },
    'motion_gen_title': {
        'ko': '🎬 Motion 자동생성',
        'en': '🎬 Auto Motion Generation',
        'vi': '🎬 Tự động tạo Motion'
    },
    'motion_gen_desc': {
        'ko': '각 씬의 내용을 분석하여 영상 모션 프롬프트를 AI가 자동 생성합니다. (기존 Motion이 있는 씬은 덮어씁니다.)',
        'en': 'AI analyzes scenes to auto-generate motion prompts. (Overwrites existing)',
        'vi': 'AI tự động tạo chuyển động dựa trên nội dung cảnh. (Ghi đè Motion cũ)'
    },
    'motion_gen_range': {
        'ko': '생성할 씬 범위',
        'en': 'Scene Range',
        'vi': 'Phạm vi cảnh'
    },
    'motion_gen_from': {
        'ko': '씬 1 ~',
        'en': 'Scene 1 ~',
        'vi': 'Cảnh 1 ~'
    },
    'motion_gen_to': {
        'ko': '씬까지',
        'en': 'until Scene',
        'vi': 'đến cảnh'
    },
    'btn_start_gen': {
        'ko': '✨ 생성 시작',
        'en': '✨ Start Generating',
        'vi': '✨ Bắt đầu tạo'
    },
    'btn_blog_post': {
        'ko': '📝 블로그 게시',
        'en': '📝 Blog Post',
        'vi': '📝 Đăng bài Blog'
    },
    'blog_panel_title': {
        'ko': '📝 블로그 게시 (대본 + 이미지)',
        'en': '📝 Blog Post (Script + Images)',
        'vi': '📝 Đăng Blog (Kịch bản + Ảnh)'
    },
    'blog_post_title_label': {
        'ko': '포스팅 제목',
        'en': 'Post Title',
        'vi': 'Tiêu đề bài viết'
    },
    'blog_post_title_placeholder': {
        'ko': '제목을 입력하세요 (비우면 자동 추출)',
        'en': 'Enter title (leave empty for auto extraction)',
        'vi': 'Nhập tiêu đề (Để trống để tự trích xuất)'
    },
    'blog_scene_count': {
        'ko': '{count}개 장면',
        'en': '{count} Scenes',
        'vi': '{count} cảnh'
    },
    'blog_image_count': {
        'ko': '{count}개 이미지 포함',
        'en': 'Includes {count} images',
        'vi': 'bao gồm {count} ảnh'
    },
    'blog_platform_label': {
        'ko': '게시 플랫폼',
        'en': 'Platorm',
        'vi': 'Nền tảng'
    },
    'blog_platform_wp': {
        'ko': '워드프레스',
        'en': 'WordPress',
        'vi': 'WordPress'
    },
    'blog_platform_blogger': {
        'ko': '구글 블로그',
        'en': 'Google Blog',
        'vi': 'Google Blog'
    },
    'blog_captured_images_title': {
        'ko': '🖼 포착된 이미지 (무료)',
        'en': '🖼 Captured Images (Free)',
        'vi': '🖼 Ảnh đã bắt được (Miễn phí)'
    },
    'blog_captured_helper': {
        'ko': 'Google ImageFX에서 이미지를 생성하면 Flow Bridge 확장프로그램이 자동 포착합니다. 클릭하면 블로그 삽입 목록에 추가됩니다.',
        'en': 'Flow Bridge extension captures images generated on Google ImageFX automatically. Click to add to blog.',
        'vi': 'Flow Bridge sẽ tự động bắt ảnh trên Google ImageFX. Nhấp để thêm vào blog.'
    },
    'blog_refresh_btn': {
        'ko': '새로고침',
        'en': 'Refresh',
        'vi': 'Làm mới'
    },
    'blog_open_imagefx': {
        'ko': 'ImageFX 열기',
        'en': 'Open ImageFX',
        'vi': 'Mở ImageFX'
    },
    'blog_no_captured': {
        'ko': '"새로고침"을 눌러 포착된 이미지를 불러오세요',
        'en': 'Click "Refresh" to load captured images',
        'vi': 'Nhấn "Làm mới" để hiện ảnh đã bắt'
    },
    'blog_selected_images_label': {
        'ko': '삽입할 이미지 ({count}개)',
        'en': 'Images to insert ({count})',
        'vi': 'Ảnh sẽ chèn ({count} ảnh)'
    },
    'blog_clear_selected': {
        'ko': '모두 제거',
        'en': 'Clear All',
        'vi': 'Xóa tất cả'
    },
    'btn_post_to_blog': {
        'ko': '🚀 블로그에 게시하기',
        'en': '🚀 Post to Blog',
        'vi': '🚀 Đăng bài lên Blog'
    },
    'btn_preview_blog': {
        'ko': '미리보기',
        'en': 'Preview',
        'vi': 'Xem trước'
    },
    'thumb_styling_tip_title': {
        'ko': 'Styling Tip',
        'en': 'Styling Tip',
        'vi': 'Mẹo tạo kiểu'
    },
    'thumb_styling_tip_desc': {
        'ko': '바이럴 스타일을 위해 <b>외곽선(Stroke)</b>을 굵게 하고 <b>Gmarket Sans</b> 폰트를 사용해 보세요.',
        'en': 'Use bold <b>Stroke</b> and <b>Gmarket Sans</b> font for viral style.',
        'vi': 'Dùng font <b>Gmarket Sans</b> và <b>viền (Stroke)</b> dày cho phong cách viral.'
    },
    'btn_save_style': {
        'ko': '🎨 스타일 저장',
        'en': '🎨 Save Style',
        'vi': '🎨 Lưu kiểu'
    },
    'btn_load_style': {
        'ko': '📂 스타일 불러오기',
        'en': '📂 Load Style',
        'vi': '📂 Tải kiểu'
    },
    'btn_clear_style': {
        'ko': '🗑️',
        'en': '🗑️',
        'vi': '🗑️'
    },
    'thumb_tip_title': {
        'ko': '💡 팁',
        'en': '💡 Tips',
        'vi': '💡 Mẹo'
    },
    'thumb_tip_1': {
        'ko': '• 텍스트는 3-5단어가 최적',
        'en': '• 3-5 words text is optimal',
        'vi': '• Văn bản tối ưu từ 3-5 từ'
    },
    'thumb_tip_2': {
        'ko': '• 대비가 강한 색상 사용',
        'en': '• Use high contrast colors',
        'vi': '• Dùng màu sắc tương phản mạnh'
    },
    'thumb_tip_3': {
        'ko': '• 얼굴이 있으면 클릭률 UP',
        'en': '• Faces increase CTR',
        'vi': '• Có khuôn mặt tăng tỷ lệ click'
    },
    'label_font': {
        'ko': '서체',
        'en': 'Font',
        'vi': 'Phông chữ'
    },
    'label_size_percent': {
        'ko': '크기',
        'en': 'Size',
        'vi': 'Kích thước'
    },
    'label_line_spacing': {
        'ko': '줄간격',
        'en': 'Spacing',
        'vi': 'Giãn dòng'
    },
    'label_color': {
        'ko': '색상',
        'en': 'Color',
        'vi': 'Màu sắc'
    },
    'label_text_color': {
        'ko': '글자',
        'en': 'Text',
        'vi': 'Chữ'
    },
    'label_stroke_color': {
        'ko': '테두리',
        'en': 'Stroke',
        'vi': 'Viền'
    },
    'label_stroke_width': {
        'ko': '테두리두께',
        'en': 'Stroke W',
        'vi': 'Độ dày viền'
    },
    'label_bg_strip': {
        'ko': '배경띠',
        'en': 'BG Strip',
        'vi': 'Dải nền'
    },
    'label_bg_color': {
        'ko': '배경색',
        'en': 'BG Color',
        'vi': 'Màu nền'
    },
    'label_opacity': {
        'ko': '투명도',
        'en': 'Opacity',
        'vi': 'Độ trong suốt'
    },
    'label_aspect_ratio': {
        'ko': '화면비',
        'en': 'Ratio',
        'vi': 'Tỷ lệ khung hình'
    },
    'ratio_16_9': {
        'ko': '가로 16:9',
        'en': 'Wide 16:9',
        'vi': 'Ngang 16:9'
    },
    'ratio_9_16': {
        'ko': '세로 9:16',
        'en': 'Vertical 9:16',
        'vi': 'Dọc 9:16'
    },
    'btn_reset_reload': {
        'ko': '🔄 초기화 및 최신 데이터 로드',
        'en': '🔄 Reset & Reload',
        'vi': '🔄 Khôi phục & Tải lại'
    },
    'btn_ai_sync': {
        'ko': 'AI 이미지 싱크 맞추기',
        'en': 'AI Image Sync',
        'vi': 'Khớp ảnh AI'
    },
    'btn_split_2lines': {
        'ko': '✂️ 자막 2줄 분할',
        'en': '✂️ Split to 2 lines',
        'vi': '✂️ Chia phụ đề 2 dòng'
    },
    'btn_save_setting': {
        'ko': '💾 세팅저장',
        'en': '💾 Save Settings',
        'vi': '💾 Lưu cài đặt'
    },
    'btn_save': {
        'ko': '저장',
        'en': 'Save',
        'vi': 'Lưu'
    },
    'btn_render_video': {
        'ko': '영상 렌더링',
        'en': 'Render Video',
        'vi': 'Render Video'
    },
    'subtitle_list_title': {
        'ko': '자막 리스트 (DEBUG MODE)',
        'en': 'Subtitle List (DEBUG)',
        'vi': 'Danh sách phụ đề (DEBUG)'
    },
    'btn_regen_all': {
        'ko': '전체 AI 재생성',
        'en': 'AI Regen All',
        'vi': 'Tái tạo AI toàn bộ'
    },
    'btn_add': {
        'ko': '+ 추가',
        'en': '+ Add',
        'vi': '+ Thêm'
    },
    'btn_delete_selected': {
        'ko': '☑ 선택삭제',
        'en': '☑ Delete Selected',
        'vi': '☑ Xóa mục đã chọn'
    },
    'delete_bar_selected': {
        'ko': '{count}개 선택됨',
        'en': '{count} selected',
        'vi': 'Đã chọn {count} mục'
    },
    'btn_select_all_rows': {
        'ko': '전체선택',
        'en': 'Select All',
        'vi': 'Chọn tất cả'
    },
    'btn_delete_rows': {
        'ko': '🗑 선택 삭제',
        'en': '🗑 Delete',
        'vi': '🗑 Xóa'
    },
    'tab_edit_subtitle': {
        'ko': '자막 편집',
        'en': 'Edit Subtitle',
        'vi': 'Sửa phụ đề'
    },
    'tab_bgm_sfx': {
        'ko': '🎵 BGM/SFX 설정',
        'en': '🎵 BGM/SFX Settings',
        'vi': '🎵 Cài đặt BGM/SFX'
    },
    'edit_selected_title': {
        'ko': '현재 선택된 자막 편집',
        'en': 'Edit Selected Subtitle',
        'vi': 'Sửa phụ đề đang chọn'
    },
    'label_current_image': {
        'ko': '현재 이미지: {img}',
        'en': 'Current Image: {img}',
        'vi': 'Ảnh hiện tại: {img}'
    },
    'label_start_time': {
        'ko': '시작',
        'en': 'Start',
        'vi': 'Bắt đầu'
    },
    'label_end_time': {
        'ko': '종료',
        'en': 'End',
        'vi': 'Kết thúc'
    },
    'placeholder_select_subtitle': {
        'ko': '리스트에서 자막을 선택하세요.',
        'en': 'Select a subtitle from the list.',
        'vi': 'Chọn phụ đề từ danh sách.'
    },
    'preview_no_subtitle': {
        'ko': '자막을 선택하면 미리보기가 표시됩니다',
        'en': 'Select a subtitle to preview',
        'vi': 'Chọn phụ đề để xem trước'
    },
    'status_preview_rendering': {
        'ko': '🔄 렌더링 중...',
        'en': '🔄 Rendering...',
        'vi': '🔄 Đang render...'
    },
    'label_bgm_volume': {
        'ko': '볼륨',
        'en': 'Volume',
        'vi': 'Âm lượng'
    },
    'bgm_no_file': {
        'ko': '설정된 BGM 없음',
        'en': 'No BGM set',
        'vi': 'Chưa thiết lập BGM'
    },
    'btn_clear_bgm': {
        'ko': '✕ 제거',
        'en': '✕ Clear',
        'vi': '✕ Gỡ bỏ'
    },
    'bgm_tab_upload': {
        'ko': '📂 파일 업로드',
        'en': '📂 Upload',
        'vi': '📂 Tải lên'
    },
    'bgm_tab_url': {
        'ko': '🔗 URL 입력',
        'en': '🔗 URL',
        'vi': '🔗 URL'
    },
    'bgm_tab_generated': {
        'ko': '✨ 생성됨',
        'en': '✨ Gen',
        'vi': '✨ Đã tạo'
    },
    'bgm_upload_label': {
        'ko': '📂 BGM 파일 선택 (mp3, wav, m4a)',
        'en': '📂 Select BGM (mp3, wav, m4a)',
        'vi': '📂 Chọn tệp BGM (mp3, wav, m4a)'
    },
    'bgm_url_placeholder': {
        'ko': 'https://... (MP3 URL)',
        'en': 'https://... (MP3 URL)',
        'vi': 'https://... (URL MP3)'
    },
    'btn_apply_url': {
        'ko': '적용',
        'en': 'Apply',
        'vi': 'Áp dụng'
    },
    'btn_load_generated': {
        'ko': '🔄 audio_gen에서 생성한 BGM 불러오기',
        'en': '🔄 Load Generated BGM',
        'vi': '🔄 Tải BGM đã tạo'
    },
    'label_sfx': {
        'ko': '🔊 SFX (효과음)',
        'en': '🔊 SFX',
        'vi': '🔊 SFX'
    },
    'label_use': {
        'ko': '사용',
        'en': 'Use',
        'vi': 'Dùng'
    },
    'sfx_upload_button': {
        'ko': '📂 SFX 파일 선택',
        'en': '📂 Select SFX',
        'vi': '📂 Chọn tệp SFX'
    },
    'sfx_no_file': {
        'ko': '설정된 SFX 없음',
        'en': 'No SFX set',
        'vi': 'Chưa thiết lập SFX'
    },
    'bgm_tip': {
        'ko': '💡 BGM은 <strong>영상 렌더링</strong> 시 자동으로 포함됩니다. 영상 길이에 맞게 BGM이 루프/페이드 처리됩니다.',
        'en': '💡 BGM included during <strong>Render</strong>. Auto loop/fade applied.',
        'vi': '💡 BGM tự động chèn khi <strong>Render</strong>. Tự động lặp/fade.'
    },
    'title_rendered_video': {
        'ko': '🎬 렌더링된 영상',
        'en': '🎬 Rendered Video',
        'vi': '🎬 Video đã render'
    },
    'btn_close': {
        'ko': '✕ 닫기',
        'en': '✕ Close',
        'vi': '✕ Đóng'
    }
}

# Add Webtoon and other missing keys to VI if not present
VI_EXTRAS = {
    'btn_save_to_server': 'Lưu lên máy chủ',
    'btn_add_char_manual': 'Thêm thủ công',
    'status_generating': 'Đang tạo...',
}

def patch():
    with open(i18n_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Prepare dictionary structure
    import ast
    
    # We will use a safe way to inject or update the PLATFORM_TRANSLATIONS dict
    # But since it's a large file, let's use string manipulation carefully.
    
    lines = content.split('\n')
    
    # Find start of PLATFORM_TRANSLATIONS
    start_idx = -1
    for i, line in enumerate(lines):
        if 'PLATFORM_TRANSLATIONS = {' in line:
            start_idx = i
            break
            
    if start_idx == -1:
        print("Could not find PLATFORM_TRANSLATIONS")
        return

    # 2. Extract components
    # We want to insert/update keys in ko, en, and vi.
    
    for lang in ['ko', 'en', 'vi']:
        marker = f"    '{lang}': {{"
        lang_start = -1
        for i, line in enumerate(lines):
            if marker in line:
                lang_start = i
                break
        
        if lang_start != -1:
            # Lang exists, insert new keys at the top of the lang block
            insert_pos = lang_start + 1
            added_lines = []
            for key, vals in NEW_KEYS.items():
                val = vals[lang].replace("'", "\\'")
                added_lines.append(f"        '{key}': '{val}',")
            
            # Special extras for VI
            if lang == 'vi':
                for key, val in VI_EXTRAS.items():
                    added_lines.append(f"        '{key}': '{val}',")
            
            lines[insert_pos:insert_pos] = added_lines
        else:
            # Lang doesn't exist (like 'vi' if root level missing), add at the end of dict
            # Find the closing brace of PLATFORM_TRANSLATIONS
            # This is tricky because of nested braces.
            # Let's find the last '    },' or similar.
            
            # If 'vi' is missing, let's actually create it before the final '}'
            # Find the very last '    },' before the end of the dict
            last_lang_end = -1
            for i in range(len(lines)-1, start_idx, -1):
                if lines[i].strip() == '    },' or lines[i].strip() == '    }':
                    last_lang_end = i
                    break
            
            if last_lang_end != -1:
                new_lang_block = [f"    '{lang}': {{"]
                for key, vals in NEW_KEYS.items():
                    val = vals[lang].replace("'", "\\'")
                    new_lang_block.append(f"        '{key}': '{val}',")
                if lang == 'vi':
                    for key, val in VI_EXTRAS.items():
                        new_lang_block.append(f"        '{key}': '{val}',")
                new_lang_block.append("    },")
                lines.insert(last_lang_end + 1, "\n".join(new_lang_block))

    # 3. Clean up misplaced Vietnamese keys in 'pt' or at end
    # (Actually the insertion above might make it redundant or messy, so let's just write the whole thing)
    
    # Write back
    with open(i18n_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print("Patch applied successfully.")

if __name__ == '__main__':
    patch()
