import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'

export const dynamic = 'force-dynamic'

const DEFAULT_TERMS: Record<string, string> = {
    ko: `[AIR STUDIO 서비스 이용약관]

제1조 (목적)
본 약관은 AIR STUDIO(이하 "회사")가 제공하는 영상 제작 작업 및 플랫폼 서비스의 이용 조건 및 절차, 권리와 의무에 관한 사항을 규정함을 목적으로 합니다.

제2조 (회원의 의무)
1. 회원은 서비스 이용과 관련하여 관계 법령, 본 약관의 규정, 이용안내 및 주의사항을 준수하여야 합니다.
2. 회원은 부여받은 계정 및 비밀번호를 직접 관리하여야 하며, 제3자에게 양도하거나 대여할 수 없습니다.
3. 생성된 모든 콘텐츠 및 작업물은 회사의 자산 기준 및 검수 가이드라인을 준수해야 하며, 부정한 방법으로 작업을 조작하거나 어뷰징 행위를 하여서는 안 됩니다.

제3조 (서비스 제공 및 중단)
회사는 업무상 또는 기술상 특별한 지장이 없는 한 연중무휴, 1일 24시간 서비스를 제공합니다. 단, 시스템 정기점검 및 업그레이드 등 필요 시 서비스가 일시 중단될 수 있습니다.`,
    en: `[AIR STUDIO Terms of Service]

Article 1 (Purpose)
These Terms govern the conditions, procedures, rights, and obligations for using video production and platform services provided by AIR STUDIO ("Company").

Article 2 (Member Obligations)
1. Members must comply with relevant laws, regulations, and guidelines.
2. Accounts are non-transferable and must be managed securely.
3. All created content must follow quality guidelines without manipulation or abuse.`,
    vi: `[Điều khoản dịch vụ AIR STUDIO]

Điều 1 (Mục đích)
Các điều khoản này quy định việc sử dụng dịch vụ sản xuất video và nền tảng do AIR STUDIO cung cấp.

Điều 2 (Nghĩa vụ của thành viên)
1. Tuân thủ quy định và hướng dẫn của nền tảng.
2. Bảo mật tài khoản cá nhân, không chia sẻ cho bên thứ ba.
3. Tạo nội dung chất lượng theo đúng tiêu chuẩn kiểm duyệt.`,
    th: `[ข้อกำหนดการให้บริการ AIR STUDIO]

ข้อ 1 (วัตถุประสงค์)
ข้อกำหนดนี้ควบคุมการใช้งานบริการสร้างวิดีโอและแพลตฟอร์มของ AIR STUDIO

ข้อ 2 (หน้าที่ของสมาชิก)
1. ปฏิบัติตามกฎหมายและแนวทางของแพลตฟอร์ม
2. รักษาความปลอดภัยของบัญชี ไม่ส่งต่อให้บุคคลอื่น
3. ส่งมอบผลงานที่มีคุณภาพตามมาตรฐานการตรวจสอบ`
}

const DEFAULT_PRIVACY: Record<string, string> = {
    ko: `[개인정보 수집 및 이용 동의]

1. 수집하는 개인정보 항목
- 필수항목: 이름, 이메일 주소, 연락처, 국적, 비밀번호
- 작업 및 정산 항목: 추천인 코드, USDT 정산 지갑 주소, 작업 내역

2. 개인정보의 수집 및 이용 목적
- 회원 가입 의사 확인, 본인 식별 및 회원제 서비스 제공
- 작업 승인, 콘텐츠 배정, 수당 정산 및 세무 처리
- 부정 이용 방지 및 서비스 운영 관련 공지 전달

3. 개인정보의 보유 및 이용 기간
- 회원 탈퇴 시 또는 법령에 따른 보존 의무 기간까지 안전하게 보관 후 파기됩니다.`,
    en: `[Privacy Policy & Data Collection]

1. Collected Information: Name, Email, Contact number, Country, Password, USDT Wallet address.
2. Purpose of Collection: User authentication, project assignment, payout settlements, security audits.
3. Retention Period: Retained during active membership and deleted upon account termination according to regulations.`,
    vi: `[Chính sách bảo mật & Thu thập dữ liệu]

1. Thông tin thu thập: Họ tên, Email, Số liên hệ, Quốc gia, Mật khẩu, Ví USDT.
2. Mục đích: Xác thực tài khoản, phân công dự án, thanh toán thù lao.
3. Thời gian lưu trữ: Lưu trữ trong suốt thời gian hoạt động tài khoản.`,
    th: `[นโยบายความเป็นส่วนตัวและการเก็บข้อมูล]

1. ข้อมูลที่เก็บรวบรวม: ชื่อ, อีเมล, เบอร์ติดต่อ, ประเทศ, รหัสผ่าน, ที่อยู่กระเป๋า USDT
2. วัตถุประสงค์: การยืนยันตัวตน, การมอบหมายงาน, การจ่ายผลตอบแทน
3. ระยะเวลาการเก็บรักษา: ตลอดระยะเวลาที่ใช้งานบัญชี`
}

export async function GET() {
    try {
        const { data } = await supabaseAdmin
            .from('global_settings')
            .select('key, value')
            .in('key', [
                'terms_ko', 'terms_en', 'terms_vi', 'terms_th',
                'privacy_ko', 'privacy_en', 'privacy_vi', 'privacy_th'
            ])

        const settings: Record<string, string> = {}
        for (const row of data || []) {
            if (row?.key && String(row.value || '').trim()) {
                settings[row.key] = String(row.value)
            }
        }

        return NextResponse.json({
            success: true,
            terms: {
                ko: settings.terms_ko || DEFAULT_TERMS.ko,
                en: settings.terms_en || DEFAULT_TERMS.en,
                vi: settings.terms_vi || DEFAULT_TERMS.vi,
                th: settings.terms_th || DEFAULT_TERMS.th,
            },
            privacy: {
                ko: settings.privacy_ko || DEFAULT_PRIVACY.ko,
                en: settings.privacy_en || DEFAULT_PRIVACY.en,
                vi: settings.privacy_vi || DEFAULT_PRIVACY.vi,
                th: settings.privacy_th || DEFAULT_PRIVACY.th,
            }
        })
    } catch (err: any) {
        return NextResponse.json({
            success: true,
            terms: DEFAULT_TERMS,
            privacy: DEFAULT_PRIVACY,
        })
    }
}
