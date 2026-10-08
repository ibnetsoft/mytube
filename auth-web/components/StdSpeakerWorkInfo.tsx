export type SpeakerWorkInfo = {
    count: number
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
    return <div className="space-y-1 text-xs text-cyan-200" role="status">
        <p className="mt-1">{th
            ? `ตำแหน่งพร้อมสำหรับ AIR STUDIO ${data.completed}/${data.count} ฉาก · ยืนยันเอง ${data.confirmed} ฉาก`
            : `AIR STUDIO 위치 준비 ${data.completed}/${data.count}씬 · 직접 확정 ${data.confirmed}씬`}</p>
        <p>{th
            ? `ต้องตรวจสอบเพิ่ม ${data.failed || 0} ฉาก · รอวิเคราะห์ ${data.pending ?? Math.max(0, data.count - data.completed)} ฉาก`
            : `추가 확인 ${data.failed || 0}씬 · 남은 분석 ${data.pending ?? Math.max(0, data.count - data.completed)}씬`}</p>
        {data.completed > 0 && <p>{th
            ? 'บันทึกตำแหน่งของฉากที่เสร็จแล้ว พร้อมใช้งานใน AIR STUDIO'
            : '완료된 씬의 위치는 저장되어 AIR STUDIO 작업에 사용할 수 있습니다.'}</p>}
        {speakerProgress && <p className="text-yellow-200">{th
            ? `กำหนดผู้พูดแล้ว ${speakerProgress.confirmed}/${speakerProgress.total} คำบรรยาย`
            : `대사 화자 지정 ${speakerProgress.confirmed}/${speakerProgress.total}개 자막`}</p>}
    </div>
}
