import { stdUiText } from '@/lib/stdUiText'

export type SpeakerWorkInfo = {
    count: number
    workerCompleted?: number
    completed: number
    confirmed: number
    failed?: number
    pending?: number
    speakerProgress?: { total: number; confirmed: number }
}

export default function StdSpeakerWorkInfo({ data, speakerProgress = data.speakerProgress, locale = 'ko' }: {
    data: SpeakerWorkInfo
    speakerProgress?: SpeakerWorkInfo['speakerProgress']
    locale?: string
}) {
    const activeLocale = locale === 'en' || locale === 'vi' || locale === 'th' ? locale : 'ko'
    const ui = (text: string, values: Record<string, string | number>) => stdUiText(activeLocale, text, values)
    const workerCompleted = data.workerCompleted
    const pending = data.pending ?? Math.max(0, data.count - data.completed - (data.failed || 0))
    const copy = {
        ko: { video: `대사 대상 씬 중 AIR 처리 영상 ${workerCompleted ?? 0}/${data.count}개`, position: `화자 위치 결과 ${data.completed}/${data.count}씬 · 결과 없음 ${pending}씬 · 확인 필요 ${data.failed || 0}씬 · 직접 확정 ${data.confirmed}씬` },
        en: { video: `AIR-processed videos in dialogue scenes: ${workerCompleted ?? 0}/${data.count}`, position: `Speaker positions: ${data.completed}/${data.count} scenes · No result: ${pending} · Needs review: ${data.failed || 0} · Manually confirmed: ${data.confirmed}` },
        th: { video: `วิดีโอที่ AIR ประมวลผลในฉากบทสนทนา ${workerCompleted ?? 0}/${data.count}`, position: `ตำแหน่งผู้พูด ${data.completed}/${data.count} ฉาก · ไม่มีผล ${pending} · ต้องตรวจสอบ ${data.failed || 0} · ยืนยันเอง ${data.confirmed}` },
        vi: { video: `Video đã xử lý AIR trong cảnh hội thoại: ${workerCompleted ?? 0}/${data.count}`, position: `Vị trí người nói: ${data.completed}/${data.count} cảnh · Chưa có kết quả: ${pending} · Cần kiểm tra: ${data.failed || 0} · Tự xác nhận: ${data.confirmed}` },
    }[activeLocale]
    return <div className="text-xs leading-5 text-cyan-200" role="status">
        {workerCompleted !== undefined && <p className="font-semibold text-purple-200">{copy.video}</p>}
        <p>{copy.position}</p>
        {speakerProgress && <p className="text-yellow-200">{ui('대사 화자 지정 {confirmed}/{total}개 자막',
            {confirmed: speakerProgress.confirmed, total: speakerProgress.total})}</p>}
    </div>
}
