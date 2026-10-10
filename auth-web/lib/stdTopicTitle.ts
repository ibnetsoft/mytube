import type { SupportedLocale } from './i18n'

const preparedJapaneseTitles: Record<string, Record<SupportedLocale, string>> = {
    '封をほどく朝': {
        ko: '봉투를 푸는 아침',
        en: 'The Morning the Letter Was Opened',
        vi: 'Buổi sáng mở lá thư',
        th: 'เช้าวันเปิดจดหมาย',
    },
    '木曽路、藍の灯｜店を守るため、女がたどった記録': {
        ko: '기소 길, 쪽빛 등불｜가게를 지키기 위해 한 여인이 걸어온 기록',
        en: 'Kiso Road, Indigo Light｜A Woman’s Journey to Protect Her Shop',
        vi: 'Đường Kiso, ngọn đèn chàm｜Hành trình người phụ nữ bảo vệ cửa hàng',
        th: 'เส้นทางคิโสะ แสงคราม｜บันทึกเส้นทางของหญิงผู้ปกป้องร้าน',
    },
    '追い出した友が、向かいの宿にいた｜信州宿場の人情噺': {
        ko: '쫓아낸 친구가 맞은편 여관에 있었다｜신슈 역참마을의 인정 이야기',
        en: 'The Friend I Drove Away Was at the Inn Across the Road｜A Tale of Humanity from a Shinshu Post Town',
        vi: 'Người bạn bị đuổi đi lại ở quán trọ đối diện｜Câu chuyện nghĩa tình tại trạm nghỉ Shinshu',
        th: 'เพื่อนที่ถูกไล่ออกไปกลับอยู่โรงเตี๊ยมฝั่งตรงข้าม｜เรื่องราวน้ำใจแห่งเมืองพักม้าชินชู',
    },
}

const text = (...values: unknown[]) => values.map(value => String(value || '').trim()).find(Boolean) || ''
const preparedTitleKey = (value: string) => value.replace(/\s+/g, '').replaceAll('|', '｜')

export function topicSourceTitle(topic: any): string {
    return text(topic?.generated_title, topic?.source_title, topic?.topic)
}

export function localizedTopicTitle(topic: any, locale: SupportedLocale): string {
    const source = topicSourceTitle(topic)
    const translations = topic?.title_translations
        || topic?.progress_payload?.title_translations
        || topic?.pregenerated_structure?.title_translations
        || topic?.publish_metadata?.title_translations
        || {}
    const localized = text(
        topic?.[`topic_${locale}`],
        topic?.[`title_${locale}`],
        translations?.[locale],
        preparedJapaneseTitles[preparedTitleKey(source)]?.[locale],
    )
    return localized && localized !== source ? localized : ''
}
