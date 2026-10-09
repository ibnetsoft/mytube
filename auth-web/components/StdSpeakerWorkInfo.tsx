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
    const th = locale === 'th'
    const workerCompleted = data.workerCompleted
    const pending = data.pending ?? Math.max(0, data.count - data.completed - (data.failed || 0))
    return <div className="text-xs leading-5 text-cyan-200" role="status">
        {workerCompleted !== undefined && <p className="font-semibold text-purple-200">{th
            ? `งาน AIR เสร็จแล้ว ${workerCompleted}/${data.count} ฉาก · ยังไม่เสร็จ ${Math.max(0, data.count - workerCompleted)} ฉาก`
            : `AIR작업 완료 ${workerCompleted}/${data.count}씬 · 미완료 ${Math.max(0, data.count - workerCompleted)}씬`}</p>}
        <p>{th
            ? `ตำแหน่งพร้อม ${data.completed}/${data.count} ฉาก · ต้องตรวจสอบเพิ่ม ${data.failed || 0} ฉาก · รอวิเคราะห์ ${pending} ฉาก · ยืนยันเอง ${data.confirmed} ฉาก`
            : `위치 준비 ${data.completed}/${data.count}씬 · 추가 확인 ${data.failed || 0}씬 · 남은 분석 ${pending}씬 · 직접 확정 ${data.confirmed}씬`}</p>
        {speakerProgress && <p className="text-yellow-200">{th
            ? `กำหนดผู้พูดแล้ว ${speakerProgress.confirmed}/${speakerProgress.total} คำบรรยาย`
            : `대사 화자 지정 ${speakerProgress.confirmed}/${speakerProgress.total}개 자막`}</p>}
    </div>
}
