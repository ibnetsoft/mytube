import { AlertCircle, CheckCircle2, RefreshCw, X } from 'lucide-react'

export type TtsNotice = {
    kind?: 'tts' | 'subtitles'
    projectId: string
    projectTitle: string
    phase: 'running' | 'success' | 'warning' | 'error'
    detail: string
}

const COPY = {
    ko: {
        playbackFailed: '미리듣기 파일을 불러오지 못했습니다. 프로젝트를 다시 열면 저장된 음성을 다시 불러옵니다. TTS를 다시 생성할 필요는 없습니다.', timingSaveFailed: '음성은 저장됐지만 자막 타이밍 변경 사항을 저장하지 못했습니다. 자막 저장 버튼으로 다시 저장해 주세요.',
        subtitleTitles: { running: '자막 저장 중', success: '자막 저장 완료', warning: '자막 저장 확인 필요', error: '자막 저장 실패' },
        subtitleSaving: '자막 변경 내용을 저장하고 있습니다.',
        subtitleSaved: '자막 변경 내용이 서버에 저장되었습니다.',
        subtitleFailed: '자막 변경 내용을 저장하지 못했습니다. 다시 시도해 주세요.',
        subtitleSaveErrorTitle: '자막 저장 실패',
        finalSaveFailedTitle: '최종 저장 실패',
        ttsFailedTitle: '음성 생성 실패',
        voiceSettingsSaved: '성우 설정이 저장되었습니다.',
        voiceAssignmentRequired: (needed: number, ready: number) => `성우를 지정해야 하는 자막 ${needed}개 중 ${ready}개가 준비되었습니다. 모든 자막의 성우를 지정해 주세요.`,
        saveStatus: { saving: '저장 중…', dirty: '저장되지 않은 변경 사항', saved: '저장됨', error: '저장 실패' },
        project: '프로젝트',
        dialogueVoiceRequired: '대사 성우를 내레이션 성우와 다르게 일괄 적용한 뒤 최종 TTS를 생성해 주세요. 상단 툴바의 [대사 성우] 버튼에서 선택할 수 있습니다.',
        presetNameRequired: '프리셋 이름을 입력해 주세요.',
        presetSaved: (name: string) => `'${name}' 자막 프리셋이 저장되었습니다.`,
        subtitleSaveLabel: '자막 저장',
        subtitleSaveHint: 'TTS를 생성하지 않고 수정 내용을 저장합니다.',
        saveTtsLabel: '자막 저장 및 TTS 생성',
        running: '저장 및 TTS 처리 중', success: '저장 및 TTS 완료', warning: 'TTS 확인 필요', error: '저장 및 TTS 실패', saving: '자막 변경 내용을 저장하고 있습니다.', preparing: '저장된 음성을 확인하고 필요한 구간을 준비하고 있습니다.', assembling: '모든 구간을 준비했습니다. 최종 음성을 합쳐 저장하고 있습니다.', saved: '최종 음성이 서버에 저장되었습니다.', unsaved: '음성의 서버 저장을 확인하지 못했습니다. 다시 시도해 주세요.', sync: '대본을 먼저 저장한 뒤 다시 시도해 주세요.', empty: '대본이 없습니다. 먼저 대본을 생성해 주세요.', navigation: 'AIR Studio 내부 메뉴로 이동해도 계속 진행됩니다. 완료될 때까지 새로고침하거나 이 탭을 닫지 마세요.', close: '확인', progress: (ready: number, total: number) => `음성 준비 중: ${ready}/${total}개`, counts: (reused: number, generated: number) => `기존 ${reused}개 재사용 · 새로 ${generated}개 생성` },
    th: {
        playbackFailed: 'โหลดเสียงตัวอย่างไม่ได้ เปิดโปรเจกต์นี้ใหม่เพื่อโหลดเสียงที่บันทึกไว้ ไม่ต้องสร้างเสียง TTS ใหม่', timingSaveFailed: 'บันทึกเสียงแล้ว แต่บันทึกการเปลี่ยนแปลงเวลาคำบรรยายไม่ได้ กรุณาลองอีกครั้งด้วยปุ่มบันทึกคำบรรยาย',
        subtitleTitles: { running: 'กำลังบันทึกคำบรรยาย', success: 'บันทึกคำบรรยายแล้ว', warning: 'ต้องตรวจสอบการบันทึกคำบรรยาย', error: 'บันทึกคำบรรยายไม่สำเร็จ' },
        subtitleSaving: 'กำลังบันทึกการแก้ไขคำบรรยาย',
        subtitleSaved: 'บันทึกการแก้ไขคำบรรยายบนเซิร์ฟเวอร์แล้ว',
        subtitleFailed: 'บันทึกการแก้ไขคำบรรยายไม่สำเร็จ กรุณาลองอีกครั้ง',
        subtitleSaveErrorTitle: 'บันทึกคำบรรยายไม่สำเร็จ',
        finalSaveFailedTitle: 'บันทึกขั้นสุดท้ายไม่สำเร็จ',
        ttsFailedTitle: 'สร้างเสียงไม่สำเร็จ',
        voiceSettingsSaved: 'บันทึกการตั้งค่าเสียงแล้ว',
        voiceAssignmentRequired: (needed: number, ready: number) => `กำหนดเสียงแล้ว ${ready} จาก ${needed} ช่วงคำบรรยายที่ต้องกำหนดเสียง กรุณากำหนดเสียงให้ครบทุกช่วง`,
        saveStatus: { saving: 'กำลังบันทึก…', dirty: 'มีการแก้ไขที่ยังไม่ได้บันทึก', saved: 'บันทึกแล้ว', error: 'บันทึกไม่สำเร็จ' },
        project: 'โปรเจกต์',
        dialogueVoiceRequired: 'กรุณากำหนดเสียงบทสนทนาทั้งหมดให้ต่างจากเสียงบรรยายก่อนสร้างเสียง TTS สุดท้าย เลือกได้จากปุ่ม [เสียงบทสนทนา] บนแถบเครื่องมือด้านบน',
        presetNameRequired: 'กรุณาระบุชื่อพรีเซ็ต',
        presetSaved: (name: string) => `บันทึกพรีเซ็ตคำบรรยาย '${name}' แล้ว`,
        subtitleSaveLabel: 'บันทึกคำบรรยาย',
        subtitleSaveHint: 'บันทึกการแก้ไขโดยไม่สร้างเสียง TTS',
        saveTtsLabel: 'บันทึกคำบรรยายและสร้างเสียง TTS',
        running: 'กำลังบันทึกและสร้างเสียง TTS', success: 'บันทึกและสร้างเสียง TTS แล้ว', warning: 'มีรายการเสียงที่ต้องตรวจสอบ', error: 'บันทึกหรือสร้างเสียง TTS ไม่สำเร็จ', saving: 'กำลังบันทึกการแก้ไขคำบรรยาย', preparing: 'กำลังตรวจสอบเสียงที่บันทึกไว้และเตรียมช่วงที่ยังไม่มีเสียง', assembling: 'เตรียมเสียงครบแล้ว กำลังรวมและบันทึกเสียงสุดท้าย', saved: 'บันทึกเสียงสุดท้ายบนเซิร์ฟเวอร์แล้ว', unsaved: 'ยังยืนยันการบันทึกเสียงบนเซิร์ฟเวอร์ไม่ได้ กรุณาลองอีกครั้ง', sync: 'กรุณาบันทึกบทก่อนแล้วลองอีกครั้ง', empty: 'ยังไม่มีบท กรุณาสร้างบทก่อน', navigation: 'เปลี่ยนเมนูภายใน AIR Studio ได้ งานจะทำต่อ อย่ารีเฟรชหรือปิดแท็บนี้จนกว่าจะเสร็จ', close: 'ตกลง', progress: (ready: number, total: number) => `กำลังเตรียมเสียง: ${ready}/${total} ช่วง`, counts: (reused: number, generated: number) => `ใช้เสียงเดิม ${reused} ช่วง · สร้างใหม่ ${generated} ช่วง` },
    en: {
        playbackFailed: 'The preview could not be loaded. Reopen this project to load the saved audio. You do not need to generate TTS again.', timingSaveFailed: 'The audio is saved, but subtitle timing changes could not be saved. Retry with the subtitle Save button.',
        subtitleTitles: { running: 'Saving subtitles', success: 'Subtitles saved', warning: 'Subtitle save needs attention', error: 'Subtitle save failed' },
        subtitleSaving: 'Saving subtitle changes.',
        subtitleSaved: 'Subtitle changes have been saved on the server.',
        subtitleFailed: 'Subtitle changes could not be saved. Please try again.',
        subtitleSaveErrorTitle: 'Subtitle save failed',
        finalSaveFailedTitle: 'Final save failed',
        ttsFailedTitle: 'Audio generation failed',
        voiceSettingsSaved: 'Voice settings have been saved.',
        voiceAssignmentRequired: (needed: number, ready: number) => `Voices are assigned to ${ready} of ${needed} subtitle segments that need them. Assign a voice to every segment.`,
        saveStatus: { saving: 'Saving…', dirty: 'Unsaved changes', saved: 'Saved', error: 'Save failed' },
        project: 'Project',
        dialogueVoiceRequired: 'Apply a voice other than the narrator to all dialogue before generating the final TTS audio. Use the [Dialogue voice] button in the top toolbar.',
        presetNameRequired: 'Enter a preset name.',
        presetSaved: (name: string) => `Subtitle preset '${name}' has been saved.`,
        subtitleSaveLabel: 'Save subtitles',
        subtitleSaveHint: 'Save changes without generating TTS audio.',
        saveTtsLabel: 'Save subtitles and generate TTS',
        running: 'Saving and preparing TTS', success: 'Save and TTS complete', warning: 'TTS needs attention', error: 'Save or TTS failed', saving: 'Saving subtitle changes.', preparing: 'Checking saved audio and preparing missing segments.', assembling: 'All segments are ready. Combining and saving the final audio.', saved: 'The final audio is saved on the server.', unsaved: 'The audio could not be confirmed as saved. Please retry.', sync: 'Save the script first, then retry.', empty: 'Create a script first.', navigation: 'You can use other AIR Studio menus. Keep this tab open and do not refresh until finished.', close: 'OK', progress: (ready: number, total: number) => `Preparing audio: ${ready}/${total}`, counts: (reused: number, generated: number) => `${reused} reused · ${generated} newly generated` },
    vi: {
        playbackFailed: 'Không tải được bản nghe thử. Mở lại dự án để tải âm thanh đã lưu. Không cần tạo lại TTS.', timingSaveFailed: 'Âm thanh đã được lưu nhưng chưa lưu được thay đổi thời gian phụ đề. Hãy thử lại bằng nút Lưu phụ đề.',
        subtitleTitles: { running: 'Đang lưu phụ đề', success: 'Đã lưu phụ đề', warning: 'Cần kiểm tra việc lưu phụ đề', error: 'Lưu phụ đề thất bại' },
        subtitleSaving: 'Đang lưu chỉnh sửa phụ đề.',
        subtitleSaved: 'Các chỉnh sửa phụ đề đã được lưu trên máy chủ.',
        subtitleFailed: 'Không thể lưu các chỉnh sửa phụ đề. Vui lòng thử lại.',
        subtitleSaveErrorTitle: 'Lưu phụ đề thất bại',
        finalSaveFailedTitle: 'Lưu lần cuối thất bại',
        ttsFailedTitle: 'Tạo âm thanh thất bại',
        voiceSettingsSaved: 'Đã lưu cài đặt giọng đọc.',
        voiceAssignmentRequired: (needed: number, ready: number) => `Đã gán giọng đọc cho ${ready}/${needed} đoạn phụ đề cần giọng đọc. Vui lòng gán giọng đọc cho tất cả các đoạn.`,
        saveStatus: { saving: 'Đang lưu…', dirty: 'Có thay đổi chưa lưu', saved: 'Đã lưu', error: 'Lưu thất bại' },
        project: 'Dự án',
        dialogueVoiceRequired: 'Hãy áp dụng giọng đọc khác với giọng người dẫn chuyện cho toàn bộ lời thoại trước khi tạo âm thanh TTS cuối cùng. Bạn có thể chọn bằng nút [Giọng lời thoại] trên thanh công cụ phía trên.',
        presetNameRequired: 'Vui lòng nhập tên cài đặt sẵn.',
        presetSaved: (name: string) => `Đã lưu cài đặt sẵn phụ đề '${name}'.`,
        subtitleSaveLabel: 'Lưu phụ đề',
        subtitleSaveHint: 'Lưu thay đổi mà không tạo âm thanh TTS.',
        saveTtsLabel: 'Lưu phụ đề và tạo TTS',
        running: 'Đang lưu và tạo giọng TTS', success: 'Đã lưu và hoàn tất TTS', warning: 'Cần kiểm tra TTS', error: 'Lưu hoặc tạo TTS thất bại', saving: 'Đang lưu chỉnh sửa phụ đề.', preparing: 'Đang kiểm tra âm thanh đã lưu và chuẩn bị các đoạn còn thiếu.', assembling: 'Đã chuẩn bị đủ các đoạn. Đang ghép và lưu âm thanh cuối.', saved: 'Âm thanh cuối đã được lưu trên máy chủ.', unsaved: 'Chưa xác nhận được âm thanh đã lưu. Vui lòng thử lại.', sync: 'Hãy lưu kịch bản trước rồi thử lại.', empty: 'Hãy tạo kịch bản trước.', navigation: 'Bạn có thể chuyển menu trong AIR Studio. Đừng tải lại hoặc đóng thẻ này trước khi hoàn tất.', close: 'Xác nhận', progress: (ready: number, total: number) => `Đang chuẩn bị âm thanh: ${ready}/${total}`, counts: (reused: number, generated: number) => `Dùng lại ${reused} đoạn · Tạo mới ${generated} đoạn` },
}

export const ttsNoticeCopy = (locale: string) => COPY[locale as keyof typeof COPY] || COPY.en

export default function StdTtsNotice({ notice, locale, onDismiss }: { notice: TtsNotice | null; locale: string; onDismiss: () => void }) {
    if (!notice) return null
    const copy = ttsNoticeCopy(locale)
    const title = notice.kind === 'subtitles' ? copy.subtitleTitles[notice.phase] : copy[notice.phase]
    const running = notice.phase === 'running'
    const success = notice.phase === 'success'
    return (
        <section aria-label={title} className={`fixed bottom-4 right-4 z-[80] w-[min(420px,calc(100vw-32px))] max-h-[50vh] overflow-y-auto rounded-xl border p-4 shadow-2xl bg-[#17212d] ${success ? 'border-emerald-400/60' : running ? 'border-cyan-400/50' : 'border-amber-400/60'}`}>
            <div className="flex items-start gap-3">
                {running ? <RefreshCw aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-cyan-300" /> : success ? <CheckCircle2 aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-emerald-300" /> : <AlertCircle aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-amber-300" />}
                <div role={notice.phase === 'error' ? 'alert' : 'status'} aria-live={notice.phase === 'error' ? 'assertive' : 'polite'} aria-atomic="true" className="min-w-0 flex-1">
                    <h2 className="text-sm font-bold text-white">{title}</h2>
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
