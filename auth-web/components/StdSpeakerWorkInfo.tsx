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
    return <div className="text-xs leading-5 text-cyan-200" role="status">
        {workerCompleted !== undefined && <p className="font-semibold text-purple-200">{ui('AIR작업 완료 {completed}/{total}씬 · 미완료 {pending}씬',
            {completed: workerCompleted, total: data.count, pending: Math.max(0, data.count-workerCompleted)})}</p>}
        <p>{ui('위치 준비 {completed}/{total}씬 · 추가 확인 {failed}씬 · 남은 분석 {pending}씬 · 직접 확정 {confirmed}씬',
            {completed: data.completed, total: data.count, failed: data.failed || 0, pending, confirmed: data.confirmed})}</p>
        {speakerProgress && <p className="text-yellow-200">{ui('대사 화자 지정 {confirmed}/{total}개 자막',
            {confirmed: speakerProgress.confirmed, total: speakerProgress.total})}</p>}
    </div>
}
