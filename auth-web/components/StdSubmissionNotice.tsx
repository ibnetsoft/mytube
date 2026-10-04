import { AlertCircle, CheckCircle2, RefreshCw, X } from 'lucide-react'

export type SubmissionNotice = {
    projectId: string
    title: string
    detail: string
    phase: 'running' | 'success' | 'warning' | 'error'
}

const COPY = {
    ko: {
        running: '프로젝트 제출 중',
        success: '렌더 큐 등록 완료',
        warning: '제출 상태 확인 필요',
        error: '프로젝트 제출 실패',
        saving: '대본과 자막 변경 내용을 저장하고 있습니다.',
        preparing: '이미지·영상·음성을 확인하고 렌더 큐에 등록하고 있습니다.',
        submitConfirm: '프로젝트를 제출하고 렌더링을 시작하시겠습니까?',
        refreshFailed: '렌더 큐에 등록되었습니다. 목록을 갱신하지 못했으니 새로고침해 주세요.',
        timeout: '서버 응답을 기다리는 시간이 초과되었습니다. 제출이 처리되었을 수 있으니 프로젝트 목록에서 접수 상태를 확인한 뒤 다시 시도해 주세요.',
        scriptSaveFailed: '대본을 저장하지 못해 제출을 중단했습니다. 대본 저장 후 다시 시도해 주세요.',
        subtitleSaveFailed: '자막을 저장하지 못해 제출을 중단했습니다. 자막 저장 후 다시 시도해 주세요.',
        alreadySubmitted: '이 프로젝트는 이미 원격 렌더 큐에 등록되어 있습니다.',
        accepted: (version: number) => `렌더링 v${version}이(가) 원격 렌더 큐에 등록되었습니다.`,
        sharedSubmitted: '공동 작업 프로젝트가 이미 원격 렌더 큐에 등록되어 있습니다.',
        projectChanged: '편집 중인 프로젝트가 변경되어 제출을 중단했습니다. 제출할 프로젝트에서 다시 시도해 주세요.',
        navigation: '완료 알림이 나올 때까지 새로고침하거나 이 탭을 닫지 마세요.',
        project: '프로젝트',
        close: '알림 닫기',
        confirm: '확인',
    },
    th: {
        running: 'กำลังส่งโปรเจกต์',
        success: 'เพิ่มลงคิวเรนเดอร์แล้ว',
        warning: 'ต้องตรวจสอบสถานะการส่ง',
        error: 'ส่งโปรเจกต์ไม่สำเร็จ',
        saving: 'กำลังบันทึกการแก้ไขบทและคำบรรยาย',
        preparing: 'กำลังตรวจสอบภาพ วิดีโอ และเสียง แล้วเพิ่มโปรเจกต์ลงคิวเรนเดอร์',
        submitConfirm: 'ต้องการส่งโปรเจกต์และเริ่มเรนเดอร์หรือไม่?',
        refreshFailed: 'เพิ่มลงคิวเรนเดอร์แล้ว แต่ยังอัปเดตรายการไม่ได้ กรุณารีเฟรชหน้า',
        timeout: 'หมดเวลารอการตอบกลับจากเซิร์ฟเวอร์ โปรเจกต์อาจถูกส่งแล้ว กรุณาตรวจสอบสถานะในรายการโปรเจกต์ก่อนลองอีกครั้ง',
        scriptSaveFailed: 'หยุดการส่งเนื่องจากบันทึกบทไม่สำเร็จ กรุณาบันทึกบทแล้วลองอีกครั้ง',
        subtitleSaveFailed: 'หยุดการส่งเนื่องจากบันทึกคำบรรยายไม่สำเร็จ กรุณาบันทึกคำบรรยายแล้วลองอีกครั้ง',
        alreadySubmitted: 'โปรเจกต์นี้อยู่ในคิวเรนเดอร์แล้ว',
        accepted: (version: number) => `เพิ่มการเรนเดอร์ v${version} ลงคิวเรนเดอร์แล้ว`,
        sharedSubmitted: 'โปรเจกต์ที่ทำงานร่วมกันนี้อยู่ในคิวเรนเดอร์แล้ว',
        projectChanged: 'หยุดการส่งเนื่องจากมีการเปลี่ยนโปรเจกต์ที่กำลังแก้ไข กรุณาลองอีกครั้งจากโปรเจกต์ที่ต้องการส่ง',
        navigation: 'อย่ารีเฟรชหรือปิดแท็บนี้จนกว่าจะแสดงการแจ้งเตือนว่าเสร็จแล้ว',
        project: 'โปรเจกต์',
        close: 'ปิดการแจ้งเตือน',
        confirm: 'ตกลง',
    },
    en: {
        running: 'Submitting project',
        success: 'Added to render queue',
        warning: 'Check submission status',
        error: 'Project submission failed',
        saving: 'Saving script and subtitle changes.',
        preparing: 'Checking images, videos, and audio, then adding the project to the render queue.',
        submitConfirm: 'Submit this project and start rendering?',
        refreshFailed: 'The project is in the render queue, but the list could not be updated. Please refresh the page.',
        timeout: 'The server response timed out. The project may have been submitted. Check its status in the project list before retrying.',
        scriptSaveFailed: 'Submission stopped because the script could not be saved. Save the script, then retry.',
        subtitleSaveFailed: 'Submission stopped because subtitles could not be saved. Save the subtitles, then retry.',
        alreadySubmitted: 'This project is already in the render queue.',
        accepted: (version: number) => `Render v${version} has been added to the render queue.`,
        sharedSubmitted: 'This shared project is already in the render queue.',
        projectChanged: 'Submission stopped because the project being edited changed. Retry from the project you want to submit.',
        navigation: 'Keep this tab open and do not refresh until the completion notice appears.',
        project: 'Project',
        close: 'Close notice',
        confirm: 'OK',
    },
    vi: {
        running: 'Đang gửi dự án',
        success: 'Đã thêm vào hàng đợi kết xuất',
        warning: 'Cần kiểm tra trạng thái gửi',
        error: 'Gửi dự án thất bại',
        saving: 'Đang lưu chỉnh sửa kịch bản và phụ đề.',
        preparing: 'Đang kiểm tra hình ảnh, video và âm thanh rồi thêm dự án vào hàng đợi kết xuất.',
        submitConfirm: 'Bạn muốn gửi dự án và bắt đầu kết xuất?',
        refreshFailed: 'Dự án đã vào hàng đợi kết xuất nhưng chưa cập nhật được danh sách. Vui lòng tải lại trang.',
        timeout: 'Đã hết thời gian chờ phản hồi từ máy chủ. Dự án có thể đã được gửi. Hãy kiểm tra trạng thái trong danh sách dự án trước khi thử lại.',
        scriptSaveFailed: 'Đã dừng gửi vì không lưu được kịch bản. Hãy lưu kịch bản rồi thử lại.',
        subtitleSaveFailed: 'Đã dừng gửi vì không lưu được phụ đề. Hãy lưu phụ đề rồi thử lại.',
        alreadySubmitted: 'Dự án này đã có trong hàng đợi kết xuất.',
        accepted: (version: number) => `Bản kết xuất v${version} đã được thêm vào hàng đợi kết xuất.`,
        sharedSubmitted: 'Dự án cộng tác này đã có trong hàng đợi kết xuất.',
        projectChanged: 'Đã dừng gửi vì dự án đang chỉnh sửa đã thay đổi. Hãy thử lại từ dự án bạn muốn gửi.',
        navigation: 'Đừng tải lại hoặc đóng thẻ này cho đến khi thông báo hoàn tất xuất hiện.',
        project: 'Dự án',
        close: 'Đóng thông báo',
        confirm: 'Xác nhận',
    },
}

export const submissionNoticeCopy = (locale: string) => COPY[locale as keyof typeof COPY] || COPY.en

export default function StdSubmissionNotice({ notice, locale, onDismiss }: {
    notice: SubmissionNotice | null
    locale: string
    onDismiss: () => void
}) {
    if (!notice) return null
    const copy = submissionNoticeCopy(locale)
    const running = notice.phase === 'running'
    const success = notice.phase === 'success'
    const error = notice.phase === 'error'
    const iconClass = 'mt-0.5 h-5 w-5 shrink-0'
    const borderClass = success ? 'border-emerald-400/60'
        : running ? 'border-cyan-400/50'
            : error ? 'border-red-400/60' : 'border-amber-400/60'

    return (
        <section
            aria-label={copy[notice.phase]}
            className={`fixed right-4 top-4 z-[80] w-[min(420px,calc(100vw-32px))] max-h-[50vh] overflow-y-auto rounded-xl border bg-[#17212d] p-4 shadow-2xl ${borderClass}`}
        >
            <div className="flex items-start gap-3">
                {running ? (
                    <span className={`${iconClass} animate-spin motion-reduce:animate-none text-cyan-300`}>
                        <RefreshCw aria-hidden="true" className="h-5 w-5" />
                    </span>
                ) : success ? (
                    <CheckCircle2 aria-hidden="true" className={`${iconClass} text-emerald-300`} />
                ) : (
                    <AlertCircle aria-hidden="true" className={`${iconClass} ${error ? 'text-red-300' : 'text-amber-300'}`} />
                )}
                <div role={error ? 'alert' : 'status'} aria-live={error ? 'assertive' : 'polite'} aria-atomic="true" className="min-w-0 flex-1">
                    <h2 className="text-sm font-bold text-white">{copy[notice.phase]}</h2>
                    <p className="mt-1 truncate text-xs text-gray-300" title={notice.title}>{notice.title}</p>
                    <p className="mt-2 break-words text-xs leading-relaxed text-gray-100">{notice.detail}</p>
                    {running ? <p className="mt-2 text-xs leading-relaxed text-cyan-200">{copy.navigation}</p> : null}
                </div>
                {!running ? (
                    <button
                        type="button"
                        onClick={onDismiss}
                        aria-label={copy.close}
                        className="shrink-0 rounded p-1 text-gray-300 hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300"
                    >
                        <X size={18} aria-hidden="true" />
                    </button>
                ) : null}
            </div>
            {!running ? (
                <button
                    type="button"
                    onClick={onDismiss}
                    className="mt-3 w-full rounded-lg bg-white/10 px-3 py-2 text-sm font-semibold text-white hover:bg-white/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300"
                >
                    {copy.confirm}
                </button>
            ) : null}
        </section>
    )
}
