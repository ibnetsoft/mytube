import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import {
    AIR_STUDIO_PRIVACY_POLICY_EN,
    AIR_STUDIO_PRIVACY_POLICY_KO,
    AIR_STUDIO_TERMS_OF_SERVICE_EN,
    AIR_STUDIO_TERMS_OF_SERVICE_KO,
} from '@/lib/legalContent'

export const dynamic = 'force-dynamic'

const DEFAULT_TERMS: Record<string, string> = {
    ko: AIR_STUDIO_TERMS_OF_SERVICE_KO,
    en: AIR_STUDIO_TERMS_OF_SERVICE_EN,
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

function resolveTermsOfService(locale: 'ko' | 'en' | 'vi' | 'th', configured?: string) {
    const value = String(configured || '').trim()
    if (!value) return DEFAULT_TERMS[locale]
    if ((locale === 'ko' || locale === 'en') && !/Google|구글|YouTube|Drive/i.test(value)) {
        return DEFAULT_TERMS[locale]
    }
    return value
}

const DEFAULT_PRIVACY: Record<string, string> = {
    ko: AIR_STUDIO_PRIVACY_POLICY_KO,
    en: AIR_STUDIO_PRIVACY_POLICY_EN,
    vi: `[Chính sách bảo mật & Thu thập dữ liệu]

1. Thông tin thu thập: Họ tên, Email, Số liên hệ, Quốc gia, Mật khẩu, Ví USDT.
2. Mục đích: Xác thực tài khoản, phân công dự án, thanh toán thù lao.
3. Thời gian lưu trữ: Lưu trữ trong suốt thời gian hoạt động tài khoản.`,
    th: `[นโยบายความเป็นส่วนตัวและการเก็บข้อมูล]

1. ข้อมูลที่เก็บรวบรวม: ชื่อ, อีเมล, เบอร์ติดต่อ, ประเทศ, รหัสผ่าน, ที่อยู่กระเป๋า USDT
2. วัตถุประสงค์: การยืนยันตัวตน, การมอบหมายงาน, การจ่ายผลตอบแทน
3. ระยะเวลาการเก็บรักษา: ตลอดระยะเวลาที่ใช้งานบัญชี`
}

function resolvePrivacyPolicy(locale: 'ko' | 'en' | 'vi' | 'th', configured?: string) {
    const value = String(configured || '').trim()
    if (!value) return DEFAULT_PRIVACY[locale]
    if ((locale === 'ko' || locale === 'en') && !/Google|구글/i.test(value)) {
        return DEFAULT_PRIVACY[locale]
    }
    return value
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
                ko: resolveTermsOfService('ko', settings.terms_ko),
                en: resolveTermsOfService('en', settings.terms_en),
                vi: resolveTermsOfService('vi', settings.terms_vi),
                th: resolveTermsOfService('th', settings.terms_th),
            },
            privacy: {
                ko: resolvePrivacyPolicy('ko', settings.privacy_ko),
                en: resolvePrivacyPolicy('en', settings.privacy_en),
                vi: resolvePrivacyPolicy('vi', settings.privacy_vi),
                th: resolvePrivacyPolicy('th', settings.privacy_th),
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
