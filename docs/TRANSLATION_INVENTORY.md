# TRANSLATION INVENTORY & LOCALIZATION DICTIONARY

## 1. Glossary (Common Terms)
Consistent terminology to be used across all screens.

| Korean | English | Thai | Vietnamese |
|---|---|---|---|
| 프로젝트 | Project | โปรเจกต์ | Dự án |
| 썸네일 | Thumbnail | ภาพปก | Ảnh thu nhỏ |
| 렌더링 | Render | เรนเดอร์ | Kết xuất |
| 대시보드 | Dashboard | แดชบอร์ด | Trang tổng quan |
| 토큰/크레딧 | Token/Credit | โทเค็น/เครดิต | Token/Tín dụng |
| 설정 | Settings | การตั้งค่า | Cài đặt |
| 저장 | Save | บันทึก | Lưu |
| 삭제 | Delete | ลบ | Xóa |
| 취소 | Cancel | ยกเลิก | Hủy |

## 2. Translation Inventory

| Translation Key | Korean | English | Thai | Vietnamese | Screen/Component | Source File | Priority |
|---|---|---|---|---|---|---|---|
| `common.loading` | 로딩 중... | Loading... | กำลังโหลด... | Đang tải... | Global | `translations.ts` | HIGH |
| `common.login` | 로그인 / 회원가입 | Login / Sign Up | เข้าสู่ระบบ / ลงทะเบียน | Đăng nhập / Đăng ký | Global | `translations.ts` | HIGH |
| `common.logout` | 로그아웃 | Sign Out | ออกจากระบบ | Đăng xuất | Global | `translations.ts` | HIGH |
| `nav.admin_panel` | 🛡️ 관리자 페이지 | 🛡️ Admin Panel | 🛡️ แผงควบคุมผู้ดูแล | 🛡️ Bảng điều khiển admin | Nav | `translations.ts` | LOW |
| `nav.back_to_dashboard` | ← 대시보드로 돌아가기 | ← Back to Dashboard | ← กลับไปยังแดชบอร์ด | ← Quay lại bảng điều khiển | Nav | `translations.ts` | HIGH |
| `auth.title` | AIR STUDIO | AIR STUDIO | AIR STUDIO | AIR STUDIO | Auth | `translations.ts` | HIGH |
| `auth.subtitle` | AIR STUDIO 로그인 | AIR STUDIO Login | เข้าสู่ระบบ AIR STUDIO | Đăng nhập AIR STUDIO | Auth | `translations.ts` | HIGH |
| `dashboard.greeting` | 안녕하세요, 크리에이터님! 👋 | Hello, Creator! 👋 | สวัสดีเหล่านักสร้างสรรค์! 👋 | Xin chào, Nhà sáng tạo! 👋 | Dashboard | `translations.ts` | HIGH |
| `dashboard.current_plan` | 현재 구독 중인 플랜 | Current Plan | แผนปัจจุบัน | Gói hiện tại | Dashboard | `translations.ts` | HIGH |
| `dashboard.license_key` | 내 라이선스 키 | License Key | รหัสใบอนุญาตของคุณ | Mã bản quyền của bạn | Dashboard | `translations.ts` | HIGH |
| `dashboard.copy_key` | 키 복사하기 | Copy Key | คัดลอกรหัส | Sao chép mã | Dashboard | `translations.ts` | HIGH |
| `dashboard.key_copied` | 라이선스 키가 복사되었습니다! | License key copied to clipboard! | คัดลอกรหัสใบอนุญาตแล้ว! | Đã sao chép mã bản quyền! | Dashboard | `translations.ts` | HIGH |
| `dashboard.download_title` | AIR STUDIO 다운로드 | Download AIR STUDIO | ดาวน์โหลด AIR STUDIO | Tải xuống AIR STUDIO | Dashboard | `translations.ts` | HIGH |
| `dashboard.download_desc` | 윈도우용 실행 파일을 다운로드하여 유튜브 영상 제작을 시작하세요. | Download the Windows executable and start creating YouTube videos. | ดาวน์โหลดไฟล์ติดตั้งสำหรับ Windows และเริ่มสร้างวิดีโอ YouTube | Tải xuống tệp thực thi cho Windows và bắt đầu tạo video YouTube. | Dashboard | `translations.ts` | HIGH |
| `dashboard.download_btn` | 설치 파일 다운로드 (Win) | Download Installer (Win) | ดาวน์โหลดตัวติดตั้ง (Win) | Tải bộ cài đặt (Win) | Dashboard | `translations.ts` | HIGH |
| `dashboard.guide_title` | 빠른 시작 가이드 | Quick Start Guide | คู่มือการเริ่มต้นอย่างรวดเร็ว | Hướng dẫn bắt đầu nhanh | Dashboard | `translations.ts` | MEDIUM |
| `dashboard.guide_1` | 좌측의 License Key를 복사합니다. | Copy the License Key on the left. | คัดลอกรหัสใบอนุญาตทางด้านซ้าย | Sao chép Mã bản quyền ở bên trái. | Dashboard | `translations.ts` | MEDIUM |
| `dashboard.guide_2` | 다운로드한 AIRStudio.exe를 실행합니다. | Run the downloaded AIRStudio.exe. | เรียกใช้ไฟล์ AIRStudio.exe ที่ดาวน์โหลดมา | Chạy tệp AIRStudio.exe đã tải xuống. | Dashboard | `translations.ts` | MEDIUM |
| `dashboard.guide_3` | 로그인 창에 복사한 키를 붙여넣으세요. | Paste the copied key into the login window. | วางรหัสที่คัดลอกลงในหน้าต่างเข้าสู่ระบบ | Dán mã đã sao chép vào cửa sổ đăng nhập. | Dashboard | `translations.ts` | MEDIUM |
| `dashboard.version` | 최신 버전 | Latest Version | เวอร์ชันล่าสุด | Phiên bản mới nhất | Dashboard | `translations.ts` | MEDIUM |
| `admin.api_management` | API 관리 | API Management | การจัดการ API | Quản lý API | Admin | `translations.ts` | LOW |
| `admin.user_name` | 사용자명 | User Name | ชื่อผู้ใช้ | Tên người dùng | Admin | `translations.ts` | LOW |
| `admin.start_date` | 시작일 | Start Date | วันที่เริ่มต้น | Ngày bắt đầu | Admin | `translations.ts` | LOW |
| `admin.update` | 업데이트 | Update | อัปเดต | Cập nhật | Admin | `translations.ts` | LOW |
| `admin.title` | 🛡️ 관리자 대시보드 | 🛡️ Admin Dashboard | 🛡️ แดชบอร์ดผู้ดูแลระบบ | 🛡️ Bảng điều khiển quản trị | Admin | `translations.ts` | LOW |
| `admin.total_users` | 총 사용자 | Total Users | ผู้ใช้ทั้งหมด | Tổng người dùng | Admin | `translations.ts` | LOW |
| `admin.new_users` | 이번 달 가입 | New This Month | ผู้ใช้ใหม่เดือนนี้ | Mới trong tháng này | Admin | `translations.ts` | LOW |
| `admin.user_management` | 회원 목록 관리 | User Management | การจัดการผู้ใช้ | Quản lý người dùng | Admin | `translations.ts` | LOW |
| `admin.search_email` | 이메일 검색... | Search email... | ค้นหาอีเมล... | Tìm kiếm email... | Admin | `translations.ts` | LOW |
| `admin.email_id` | 이메일 / ID | Email / ID | อีเมล / ID | Email / ID | Admin | `translations.ts` | LOW |
| `admin.join_date` | 가입일 | Joined | วันที่เข้าร่วม | Ngày tham gia | Admin | `translations.ts` | LOW |
| `admin.last_login` | 마지막 로그인 | Last Login | เข้าสู่ระบบล่าสุด | Lần đăng nhập cuối | Admin | `translations.ts` | LOW |
| `admin.status` | 상태 | Status | สถานะ | Trạng thái | Admin | `translations.ts` | LOW |
| `admin.manage` | 관리 | Manage | จัดการ | Quản lý | Admin | `translations.ts` | LOW |
| `admin.edit` | 수정 | Edit | แก้ไข | Sửa | Admin | `translations.ts` | LOW |
| `admin.ban` | 차단 | Ban | ระงับ | Chặn | Admin | `translations.ts` | LOW |
| `admin.no_data` | 조회된 사용자 데이터가 없습니다. | No user data found. | ไม่พบข้อมูลผู้ใช้ | Không tìm thấy dữ liệu người dùng. | Admin | `translations.ts` | LOW |
| `admin.membership` | 회원 등급 | Membership | ระดับสมาชิก | Membership | Admin | `translations.ts` | LOW |
| `admin.standard` | 일반 회원 | Standard | มาตรฐาน | Standard | Admin | `translations.ts` | LOW |
| `admin.independent` | 독립 회원 | Independent | โปร | Independent | Admin | `translations.ts` | LOW |
| `admin.toggle_role` | 등급 전환 | Toggle Role | เปลี่ยนระดับ | Toggle Role | Admin | `translations.ts` | LOW |
| `admin.download_lite` | Studio Lite 다운로드 | Download Studio Lite | ดาวน์โหลด Studio Lite | Download Studio Lite | Admin | `translations.ts` | LOW |
| `admin.download_pro` | Studio Pro 다운로드 | Download Studio Pro | ดาวน์โหลด Studio Pro | Download Studio Pro | Admin | `translations.ts` | LOW |
| `admin.publishing_queue` | 발행 검수 대기열 | Publishing Queue | คิวตรวจสอบการเผยแพร่ | Publishing Queue | Admin | `translations.ts` | LOW |
| `admin.video_title` | 영상 제목 | Video Title | ชื่อวิดีโอ | Video Title | Admin | `translations.ts` | LOW |
| `admin.request_date` | 업로드 요청일 | Requested Date | วันที่ร้องขอ | Requested Date | Admin | `translations.ts` | LOW |
| `admin.approve` | 승인 | Approve | อนุมัติ | Approve | Admin | `translations.ts` | LOW |
| `admin.reject` | 거절 | Reject | ปฏิเสธ | Reject | Admin | `translations.ts` | LOW |
| `admin.publish_to_youtube` | 유튜브 게시 | Publish to YT | เผยแพร่บน YouTube | Publish to YT | Admin | `translations.ts` | LOW |
| `admin.pending` | 대기 중 | Pending | รอดำเนินการ | Pending | Admin | `translations.ts` | LOW |
| `admin.approved` | 승인됨 | Approved | อนุมัติแล้ว | Approved | Admin | `translations.ts` | LOW |
| `admin.rejected` | 반려됨 | Rejected | ปฏิเสธแล้ว | Rejected | Admin | `translations.ts` | LOW |
| `admin.published` | 게시 완료 | Published | เผยแพร่แล้ว | Published | Admin | `translations.ts` | LOW |
| `admin.to_be_published` | 게시 중... | Publishing... | กำลังเผยแพร่... | Đang xuất bản... | Admin | `translations.ts` | LOW |
| `admin.no_requests` | 대기 중인 발행 요청이 없습니다. | No pending publishing requests. | ไม่มีคำขอเผยแพร่ที่รอดำเนินการ | No pending publishing requests. | Admin | `translations.ts` | LOW |
| `admin.view_video` | 영상 보기 | View Video | ดูวิดีโอ | View Video | Admin | `translations.ts` | LOW |
| `auth.full_name` | 이름 | Full Name | ชื่อ-นามสกุล | Full Name | Sign Up | `translations.ts` | HIGH |
| `auth.nationality` | 국적 | Nationality | สัญชาติ | Nationality | Sign Up | `translations.ts` | HIGH |
| `auth.contact` | 연락처 | Contact | ข้อมูลติดต่อ | Contact | Sign Up | `translations.ts` | HIGH |
| `auth.password` | 비밀번호 | Password | รหัสผ่าน | Password | Auth | `translations.ts` | HIGH |
| `auth.password_confirm` | 비밀번호 확인 | Confirm Password | ยืนันรหัสผ่าน | Confirm Password | Sign Up | `translations.ts` | HIGH |
| `auth.referrer` | 추천인코드 (선택) | Referrer Code (Optional) | รหัสผู้แนะนำ (ไม่บังคับ) | Referrer Code (Optional) | Sign Up | `translations.ts` | LOW |
| `auth.signup` | 회원가입 | Sign Up | สมัครสมาชิก | Sign Up | Auth | `translations.ts` | HIGH |
| `auth.signin` | 로그인 | Sign In | เข้าสู่ระบบ | Sign In | Auth | `translations.ts` | HIGH |
| `auth.already_have_account` | 이미 계정이 있으신가요? 로그인 | Already have an account? Sign In | มีบัญชีอยู่แล้ว? เข้าสู่ระบบ | Already have an account? Sign In | Auth | `translations.ts` | HIGH |
| `auth.dont_have_account` | 계정이 없으신가요? 회원가입 | Don't have an account? Sign Up | ยังไม่มีบัญชี? สมัครสมาชิก | Don't have an account? Sign Up | Auth | `translations.ts` | HIGH |
| `auth.error.password_mismatch` | 비밀번호 확인이 일치하지 않습니다. | Password confirmation does not match. | รหัสผ่านยืนยันไม่ตรงกัน | Xác nhận mật khẩu không khớp. | Sign Up | `AuthForm.tsx` | HIGH |
| `auth.error.missing_info` | 모든 필수 정보를 입력해주세요. | Please fill in all required information. | กรุณากรอกข้อมูลที่จำเป็นทั้งหมด | Vui lòng điền tất cả các thông tin bắt buộc. | Sign Up | `AuthForm.tsx` | HIGH |
| `auth.success.signup_email` | 회원가입 확인 메일이 발송되었습니다. 이메일을 확인해주세요! | A confirmation email has been sent. Please check your inbox! | ส่งอีเมลยืนยันการสมัครแล้ว กรุณาตรวจสอบอีเมลของคุณ! | Một email xác nhận đã được gửi. Vui lòng kiểm tra hộp thư đến của bạn! | Sign Up | `AuthForm.tsx` | HIGH |
| `auth.social.google` | Google로 로그인 | Sign in with Google | เข้าสู่ระบบด้วย Google | Đăng nhập bằng Google | Auth | `AuthForm.tsx` | HIGH |
| `auth.or` | 또는 | OR | หรือ | HOẶC | Auth | `AuthForm.tsx` | MEDIUM |
| `auth.label.email` | 이메일 | Email Address | อีเมล | Địa chỉ Email | Auth | `AuthForm.tsx` | HIGH |
| `auth.placeholder.email` | 이메일 주소 | Your email address | อีเมลของคุณ | Địa chỉ email của bạn | Auth | `AuthForm.tsx` | MEDIUM |
| `auth.label.available_lang` | 제작 가능 언어 | Available Languages for Production | ภาษาที่สามารถผลิตได้ | Ngôn ngữ hỗ trợ sản xuất | Sign Up | `AuthForm.tsx` | HIGH |
| `dashboard.prompt.recharge` | 충전할 토큰 수를 입력하세요. | Enter the number of tokens to recharge. | กรุณาระบุจำนวนโทเค็นที่ต้องการเติม | Nhập số lượng token cần nạp. | Dashboard | `DashboardContent.tsx` | MEDIUM |
| `dashboard.alert.success` | 성공적으로 적용되었습니다. | Successfully applied. | อัปเดตสำเร็จ | Áp dụng thành công. | Dashboard | `DashboardContent.tsx` | MEDIUM |
| `dashboard.table.prod_lang` | 제작 언어 | Production Language | ภาษาในการผลิต | Ngôn ngữ sản xuất | Dashboard | `DashboardContent.tsx` | LOW |
| `modal.update.title` | 새로운 업데이트 발견! | New Update Found! | พบอัปเดตใหม่! | Đã tìm thấy bản cập nhật mới! | Global | `base.html` | HIGH |
| `modal.update.body` | 최신 버전이 출시되었습니다. 안정적인 작업을 위해 업데이트를 진행해주세요. | The latest version has been released. Please update for stable operation. | มีเวอร์ชันล่าสุด กรุณาอัปเดตเพื่อการทำงานที่เสถียร | Phiên bản mới nhất đã được phát hành. Vui lòng cập nhật để hoạt động ổn định. | Global | `base.html` | HIGH |
| `modal.update.loading` | 다운로드 중... | Downloading... | กำลังดาวน์โหลด... | Đang tải xuống... | Global | `base.html` | HIGH |
| `project.btn.fetch_topic` | 오늘의 주제 가져오기 | Fetch Today's Topic | ดึงหัวข้อของวันนี้ | Lấy chủ đề của ngày hôm nay | Project | `projects.html` | MEDIUM |
| `project.badge.qa_warning` | QA 경고 확인 필요 | QA Warning Check Required | ต้องตรวจสอบคำเตือน QA | Cần kiểm tra cảnh báo QA | Project | `projects.html` | LOW |
| `project.status.music_plan` | 음악기획 | Music Plan | วางแผนดนตรี | Kế hoạch âm nhạc | Project | `projects.html` | LOW |
| `project.status.cover` | 커버 | Cover | หน้าปก | Ảnh bìa | Project | `projects.html` | LOW |
| `project.status.track` | 트랙 | Track | แทร็ก | Bản nhạc | Project | `projects.html` | LOW |
| `settings.qa_check` | 업로드 전 QA 검사 | QA Check Before Upload | ตรวจสอบ QA ก่อนอัปโหลด | Kiểm tra QA trước khi tải lên | Settings | `settings.html` | MEDIUM |
| `template.ai_analysis` | 두 이미지를 분석해 최적의 화풍+캐릭터 지침을 생성합니다. | Analyzes two images to create optimal art style and character guidelines. | วิเคราะห์สองรูปภาพเพื่อสร้างแนวทางสไตล์ศิลปะและตัวละครที่เหมาะสมที่สุด | Phân tích hai hình ảnh để tạo hướng dẫn phong cách và nhân vật tối ưu nhất. | Template | `template.html` | MEDIUM |
