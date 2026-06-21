#!/usr/bin/env python3
"""Add missing translation keys for withdrawal and history features"""

import re

file_path = "services/i18n.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# New translations to add - Korean, English, Vietnamese
new_translations = {
    'label_work_history': {
        'ko': '작업 수당 내역 (History)',
        'en': 'Work History',
        'vi': 'Lịch sử công việc'
    },
    'label_work_date': {
        'ko': '작업일 (Date)',
        'en': 'Work Date',
        'vi': 'Ngày làm việc'
    },
    'label_project_name_col': {
        'ko': '프로젝트명',
        'en': 'Project Name',
        'vi': 'Tên dự án'
    },
    'label_video_duration': {
        'ko': '영상시간',
        'en': 'Video Duration',
        'vi': 'Thời lượng video'
    },
    'label_video_scenes': {
        'ko': '비디오 씬',
        'en': 'Video Scenes',
        'vi': 'Cảnh video'
    },
    'label_image_scenes': {
        'ko': '이미지 씬',
        'en': 'Image Scenes',
        'vi': 'Cảnh ảnh'
    },
    'label_estimated_payout': {
        'ko': '수당(USDT 예상)',
        'en': 'Estimated Payout (USDT)',
        'vi': 'Dự kiến thanh toán (USDT)'
    },
    'label_wallet_and_withdrawal': {
        'ko': '지갑 및 출금',
        'en': 'Wallet & Withdrawal',
        'vi': 'Ví & Rút tiền'
    },
    'label_my_wallet_address': {
        'ko': '내 앱 지갑 주소 (자동 생성)',
        'en': 'My App Wallet Address (Auto-generated)',
        'vi': 'Địa chỉ ví ứng dụng của tôi (Tự động tạo)'
    },
    'placeholder_wallet_generating': {
        'ko': '지갑 자동생성 중...',
        'en': 'Generating wallet...',
        'vi': 'Đang tạo ví...'
    },
    'btn_copy': {
        'ko': '복사',
        'en': 'Copy',
        'vi': 'Sao chép'
    },
    'msg_copied': {
        'ko': '복사되었습니다.',
        'en': 'Copied.',
        'vi': 'Đã sao chép.'
    },
    'hint_wallet_address': {
        'ko': '가입 시 최초 자동 생성된 고유',
        'en': 'Your unique wallet address auto-generated upon sign-up',
        'vi': 'Địa chỉ ví duy nhất của bạn được tạo tự động khi đăng ký'
    },
    'label_available_balance': {
        'ko': '현재 출금 가능 수당 (USDT 잔액)',
        'en': 'Available Withdrawal Amount (USDT Balance)',
        'vi': 'Số tiền có sẵn để rút (Số dư USDT)'
    },
    'label_withdrawal_request': {
        'ko': 'USDT 출금 신청 (외부 지갑으로 전송)',
        'en': 'USDT Withdrawal Request (Transfer to External Wallet)',
        'vi': 'Yêu cầu rút USDT (Chuyển đến ví bên ngoài)'
    },
    'label_destination_wallet': {
        'ko': '받을 지갑 주소',
        'en': 'Destination Wallet Address',
        'vi': 'Địa chỉ ví đích'
    },
    'label_auto_saved': {
        'ko': '자동 저장됨',
        'en': 'Auto-saved',
        'vi': 'Tự động lưu'
    },
    'btn_paste': {
        'ko': '붙여넣기',
        'en': 'Paste',
        'vi': 'Dán'
    },
    'label_withdrawal_amount': {
        'ko': '출금 수량 (USDT)',
        'en': 'Withdrawal Amount (USDT)',
        'vi': 'Số tiền rút (USDT)'
    },
    'label_minimum_withdrawal': {
        'ko': '최소 출금',
        'en': 'Minimum Withdrawal',
        'vi': 'Rút tối thiểu'
    },
    'btn_max': {
        'ko': '최대',
        'en': 'Max',
        'vi': 'Tối đa'
    },
    'btn_request_withdrawal': {
        'ko': '출금 신청',
        'en': 'Request Withdrawal',
        'vi': 'Yêu cầu rút tiền'
    },
    'label_transaction_history': {
        'ko': '트랜잭션 히스토리',
        'en': 'Transaction History',
        'vi': 'Lịch sử giao dịch'
    },
    'label_date': {
        'ko': '날짜',
        'en': 'Date',
        'vi': 'Ngày'
    },
    'label_withdrawal_address': {
        'ko': '출금 지갑 주소',
        'en': 'Withdrawal Address',
        'vi': 'Địa chỉ rút tiền'
    },
    'label_amount_usdt': {
        'ko': '금액 (USDT)',
        'en': 'Amount (USDT)',
        'vi': 'Số tiền (USDT)'
    },
    'label_status': {
        'ko': '상태',
        'en': 'Status',
        'vi': 'Trạng thái'
    },
    'msg_loading_data': {
        'ko': '데이터를 불러오는 중입니다...',
        'en': 'Loading data...',
        'vi': 'Đang tải dữ liệu...'
    },
    'msg_withdrawal_confirm': {
        'ko': '출금 신청을 진행하시겠습니까?',
        'en': 'Proceed with withdrawal request?',
        'vi': 'Tiến hành yêu cầu rút tiền?'
    },
    'msg_withdrawal_failed': {
        'ko': '출금 신청 실패',
        'en': 'Withdrawal request failed',
        'vi': 'Yêu cầu rút tiền thất bại'
    },
    'msg_withdrawal_success': {
        'ko': '출금 신청이 완료되었습니다.',
        'en': 'Withdrawal request completed.',
        'vi': 'Yêu cầu rút tiền đã hoàn tất.'
    },
    'err_invalid_amount': {
        'ko': '출금 수량을 올바르게 입력해주세요.',
        'en': 'Please enter a valid withdrawal amount.',
        'vi': 'Vui lòng nhập số tiền rút hợp lệ.'
    },
    'err_missing_address': {
        'ko': '출금 지갑 주소를 입력해주세요.',
        'en': 'Please enter withdrawal wallet address.',
        'vi': 'Vui lòng nhập địa chỉ ví rút tiền.'
    },
    'msg_clipboard_error': {
        'ko': '클립보드에서 주소를 읽지 못했습니다.',
        'en': 'Failed to read address from clipboard.',
        'vi': 'Không thể đọc địa chỉ từ clipboard.'
    },
    'msg_no_clipboard': {
        'ko': '이 브라우저에서는 붙여넣기를 지원하지 않습니다.',
        'en': 'This browser does not support paste operation.',
        'vi': 'Trình duyệt này không hỗ trợ thao tác dán.'
    },
    'status_pending': {
        'ko': '대기중',
        'en': 'Pending',
        'vi': 'Đang chờ'
    },
    'status_completed': {
        'ko': '완료',
        'en': 'Completed',
        'vi': 'Đã hoàn thành'
    }
}

# Find the position to insert new translations
# Look for the last Korean key before the 'en' section
ko_section_match = re.search(r"'ko': \{([\s\S]*?)\n    \},\n    'en':", content)
if not ko_section_match:
    print("Could not find Korean section")
    exit(1)

ko_end_pos = ko_section_match.end(1) - 4  # Go back to just before the closing brace

# Build the new Korean translations string
new_ko_trans = ""
for key, trans_dict in sorted(new_translations.items()):
    new_ko_trans += f"        '{key}': '{trans_dict['ko']}',\n"

# Find English section
en_section_match = re.search(r"'en': \{([\s\S]*?)\n    \},\n    'vi':", content)
if not en_section_match:
    print("Could not find English section")
    exit(1)

en_end_pos = en_section_match.end(1) - 4

# Build the new English translations string
new_en_trans = ""
for key, trans_dict in sorted(new_translations.items()):
    new_en_trans += f"        '{key}': '{trans_dict['en']}',\n"

# Find Vietnamese section
vi_section_match = re.search(r"'vi': \{([\s\S]*?)\n    \}\n\}", content)
if not vi_section_match:
    print("Could not find Vietnamese section")
    exit(1)

vi_end_pos = vi_section_match.end(1) - 4

# Build the new Vietnamese translations string
new_vi_trans = ""
for key, trans_dict in sorted(new_translations.items()):
    new_vi_trans += f"        '{key}': '{trans_dict['vi']}',\n"

# Add translations in reverse order to not mess up positions
content_parts = list(content)

# Insert Vietnamese translations
content = content[:vi_end_pos] + "\n" + new_vi_trans + content[vi_end_pos:]

# Recalculate positions after Vietnamese insertion
en_offset = len("\n" + new_vi_trans)
en_section_match = re.search(r"'en': \{([\s\S]*?)\n    \},\n    'vi':", content)
en_end_pos = en_section_match.end(1) - 4

# Insert English translations
content = content[:en_end_pos] + "\n" + new_en_trans + content[en_end_pos:]

# Recalculate positions after English insertion
ko_offset = len("\n" + new_en_trans)
ko_section_match = re.search(r"'ko': \{([\s\S]*?)\n    \},\n    'en':", content)
ko_end_pos = ko_section_match.end(1) - 4

# Insert Korean translations
content = content[:ko_end_pos] + "\n" + new_ko_trans + content[ko_end_pos:]

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Translation keys added successfully")
