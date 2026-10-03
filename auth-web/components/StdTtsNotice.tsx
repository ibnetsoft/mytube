import { AlertCircle, CheckCircle2, RefreshCw, X } from 'lucide-react'

export type TtsNotice = {
    projectId: string
    projectTitle: string
    phase: 'running' | 'success' | 'warning' | 'error'
    detail: string
}

const COPY = {
    ko: { running: '저장 및 TTS 처리 중', success: '저장 및 TTS 완료', warning: 'TTS 저장 확인 필요', error: '저장 및 TTS 실패', saving: '자막 변경 내용을 저장하고 있습니다.', preparing: '저장된 음성을 확인하고 필요한 구간을 준비하고 있습니다.', assembling: '모든 구간을 준비했습니다. 최종 음성을 합쳐 저장하고 있습니다.', saved: '최종 음성이 서버에 저장되었습니다.', unsaved: '음성의 서버 저장을 확인하지 못했습니다. 다시 시도해 주세요.', sync: '대본을 먼저 저장한 뒤 다시 시도해 주세요.', empty: '대본이 없습니다. 먼저 대본을 생성해 주세요.', navigation: 'AIR Studio 내부 메뉴로 이동해도 계속 진행됩니다. 완료될 때까지 새로고침하거나 이 탭을 닫지 마세요.', close: '확인', progress: (ready: number, total: number) => `음성 준비 중: ${ready}/${total}개`, counts: (reused: number, generated: number) => `기존 ${reused}개 재사용 · 새로 ${generated}개 생성` },
    th: { running: 'กำลังบันทึกและสร้างเสียง TTS', success: 'บันทึกและสร้างเสียง TTS แล้ว', warning: 'ต้องตรวจสอบการบันทึกเสียง', error: 'บันทึกหรือสร้างเสียง TTS ไม่สำเร็จ', saving: 'กำลังบันทึกการแก้ไขคำบรรยาย', preparing: 'กำลังตรวจสอบเสียงที่บันทึกไว้และเตรียมช่วงที่ยังไม่มีเสียง', assembling: 'เตรียมเสียงครบแล้ว กำลังรวมและบันทึกเสียงสุดท้าย', saved: 'บันทึกเสียงสุดท้ายบนเซิร์ฟเวอร์แล้ว', unsaved: 'ยังยืนยันการบันทึกเสียงบนเซิร์ฟเวอร์ไม่ได้ กรุณาลองอีกครั้ง', sync: 'กรุณาบันทึกบทก่อนแล้วลองอีกครั้ง', empty: 'ยังไม่มีบท กรุณาสร้างบทก่อน', navigation: 'เปลี่ยนเมนูภายใน AIR Studio ได้ งานจะทำต่อ อย่ารีเฟรชหรือปิดแท็บนี้จนกว่าจะเสร็จ', close: 'ตกลง', progress: (ready: number, total: number) => `กำลังเตรียมเสียง: ${ready}/${total} ช่วง`, counts: (reused: number, generated: number) => `ใช้เสียงเดิม ${reused} ช่วง · สร้างใหม่ ${generated} ช่วง` },
    en: { running: 'Saving and preparing TTS', success: 'Save and TTS complete', warning: 'TTS save needs attention', error: 'Save or TTS failed', saving: 'Saving subtitle changes.', preparing: 'Checking saved audio and preparing missing segments.', assembling: 'All segments are ready. Combining and saving the final audio.', saved: 'The final audio is saved on the server.', unsaved: 'The audio could not be confirmed as saved. Please retry.', sync: 'Save the script first, then retry.', empty: 'Create a script first.', navigation: 'You can use other AIR Studio menus. Keep this tab open and do not refresh until finished.', close: 'OK', progress: (ready: number, total: number) => `Preparing audio: ${ready}/${total}`, counts: (reused: number, generated: number) => `${reused} reused · ${generated} newly generated` },
    vi: { running: 'Đang lưu và tạo giọng TTS', success: 'Đã lưu và hoàn tất TTS', warning: 'Cần kiểm tra việc lưu TTS', error: 'Lưu hoặc tạo TTS thất bại', saving: 'Đang lưu chỉnh sửa phụ đề.', preparing: 'Đang kiểm tra âm thanh đã lưu và chuẩn bị các đoạn còn thiếu.', assembling: 'Đã chuẩn bị đủ các đoạn. Đang ghép và lưu âm thanh cuối.', saved: 'Âm thanh cuối đã được lưu trên máy chủ.', unsaved: 'Chưa xác nhận được âm thanh đã lưu. Vui lòng thử lại.', sync: 'Hãy lưu kịch bản trước rồi thử lại.', empty: 'Hãy tạo kịch bản trước.', navigation: 'Bạn có thể chuyển menu trong AIR Studio. Đừng tải lại hoặc đóng thẻ này trước khi hoàn tất.', close: 'Xác nhận', progress: (ready: number, total: number) => `Đang chuẩn bị âm thanh: ${ready}/${total}`, counts: (reused: number, generated: number) => `Dùng lại ${reused} đoạn · Tạo mới ${generated} đoạn` },
}

export const ttsNoticeCopy = (locale: string) => COPY[locale as keyof typeof COPY] || COPY.en

export default function StdTtsNotice({ notice, locale, onDismiss }: { notice: TtsNotice | null; locale: string; onDismiss: () => void }) {
    if (!notice) return null
    const copy = ttsNoticeCopy(locale)
    const running = notice.phase === 'running'
    const success = notice.phase === 'success'
    return (
        <section aria-label={copy[notice.phase]} className={`fixed bottom-4 right-4 z-[80] w-[min(420px,calc(100vw-32px))] max-h-[50vh] overflow-y-auto rounded-xl border p-4 shadow-2xl bg-[#17212d] ${success ? 'border-emerald-400/60' : running ? 'border-cyan-400/50' : 'border-amber-400/60'}`}>
            <div className="flex items-start gap-3">
                {running ? <RefreshCw aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-cyan-300" /> : success ? <CheckCircle2 aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-emerald-300" /> : <AlertCircle aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-amber-300" />}
                <div role={notice.phase === 'error' ? 'alert' : 'status'} aria-live={notice.phase === 'error' ? 'assertive' : 'polite'} aria-atomic="true" className="min-w-0 flex-1">
                    <h2 className="text-sm font-bold text-white">{copy[notice.phase]}</h2>
                    <p className="mt-1 truncate text-xs text-gray-300" title={notice.projectTitle}>{notice.projectTitle}</p>
                    <p className="mt-2 break-words text-xs leading-relaxed text-gray-100">{notice.detail}</p>
                    {running && <p className="mt-2 text-xs leading-relaxed text-cyan-200">{copy.navigation}</p>}
                </div>
                {!running && <button type="button" onClick={onDismiss} aria-label={copy.close} className="shrink-0 rounded p-1 text-gray-300 hover:bg-white/10 hover:text-white"><X size={18} aria-hidden="true" /></button>}
            </div>
            {!running && <button type="button" onClick={onDismiss} className="mt-3 w-full rounded-lg bg-white/10 px-3 py-2 text-sm font-semibold text-white hover:bg-white/20">{copy.close}</button>}
        </section>
    )
}
