export type StdFeedbackAction = 'subtitle_save' | 'tts' | 'submit'
type FeedbackLocale = 'en' | 'th' | 'vi'

const feedback = {
    subtitle_save: {
        en: 'Could not save the subtitles. Please try again.',
        th: 'บันทึกคำบรรยายไม่สำเร็จ โปรดลองอีกครั้ง',
        vi: 'Không thể lưu phụ đề. Vui lòng thử lại.',
    },
    tts: {
        en: 'Could not generate and save the audio. Please try again.',
        th: 'สร้างและบันทึกเสียงไม่สำเร็จ โปรดลองอีกครั้ง',
        vi: 'Không thể tạo và lưu âm thanh. Vui lòng thử lại.',
    },
    submit: {
        en: 'Could not submit the project. Please try again.',
        th: 'ส่งโปรเจกต์ไม่สำเร็จ โปรดลองอีกครั้ง',
        vi: 'Không thể gửi dự án. Vui lòng thử lại.',
    },
    auth: {
        en: 'Your session has expired or you do not have access. Please sign in again.',
        th: 'เซสชันหมดอายุหรือคุณไม่มีสิทธิ์เข้าถึง โปรดเข้าสู่ระบบอีกครั้ง',
        vi: 'Phiên đăng nhập đã hết hạn hoặc bạn không có quyền truy cập. Vui lòng đăng nhập lại.',
    },
    project_missing: {
        en: 'The project could not be found. Please reopen it from the project list.',
        th: 'ไม่พบโปรเจกต์ โปรดเปิดโปรเจกต์อีกครั้งจากรายการโปรเจกต์',
        vi: 'Không tìm thấy dự án. Vui lòng mở lại từ danh sách dự án.',
    },
    project_closed: {
        en: 'This project is closed or cannot be edited.',
        th: 'โปรเจกต์นี้ปิดแล้วหรือไม่สามารถแก้ไขได้',
        vi: 'Dự án này đã đóng hoặc không thể chỉnh sửa.',
    },
    conflict: {
        en: 'The project changed while saving. Please reload it and try again.',
        th: 'โปรเจกต์มีการเปลี่ยนแปลงระหว่างบันทึก โปรดโหลดโปรเจกต์ใหม่แล้วลองอีกครั้ง',
        vi: 'Dự án đã thay đổi trong khi lưu. Vui lòng tải lại dự án rồi thử lại.',
    },
    network: {
        en: 'Could not connect to the server. Check your connection and try again.',
        th: 'เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ โปรดตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง',
        vi: 'Không thể kết nối với máy chủ. Vui lòng kiểm tra kết nối rồi thử lại.',
    },
    timeout: {
        en: 'The request timed out. Please try again shortly.',
        th: 'คำขอใช้เวลานานเกินกำหนด โปรดลองอีกครั้งในอีกสักครู่',
        vi: 'Yêu cầu đã hết thời gian chờ. Vui lòng thử lại sau ít phút.',
    },
    tts_timeout: {
        en: 'Audio generation timed out. Completed segments remain saved. Please try again shortly.',
        th: 'การสร้างเสียงใช้เวลานานเกินกำหนด ส่วนที่เสร็จแล้วได้บันทึกไว้ โปรดลองอีกครั้งในอีกสักครู่',
        vi: 'Quá trình tạo âm thanh đã hết thời gian chờ. Các đoạn đã hoàn tất vẫn được lưu. Vui lòng thử lại sau ít phút.',
    },
    script_changed: {
        en: 'The script has changed. Generate the audio again before submitting for rendering.',
        th: 'สคริปต์มีการเปลี่ยนแปลง โปรดสร้างเสียงใหม่ก่อนส่งไปเรนเดอร์',
        vi: 'Kịch bản đã thay đổi. Vui lòng tạo lại âm thanh trước khi gửi để kết xuất.',
    },
    no_scenes: {
        en: 'This project has no scenes to render.',
        th: 'โปรเจกต์นี้ไม่มีฉากสำหรับเรนเดอร์',
        vi: 'Dự án này chưa có cảnh để kết xuất.',
    },
    missing_assets: {
        en: 'Some scenes are missing the required images or videos. Please upload them before submitting.',
        th: 'บางฉากยังไม่มีภาพหรือวิดีโอที่จำเป็น โปรดอัปโหลดให้ครบก่อนส่งโปรเจกต์',
        vi: 'Một số cảnh còn thiếu hình ảnh hoặc video cần thiết. Vui lòng tải lên đầy đủ trước khi gửi.',
    },
    storage: {
        en: 'A saved media file could not be read. Please check the image, video, or audio and try again.',
        th: 'อ่านไฟล์สื่อที่บันทึกไว้ไม่สำเร็จ โปรดตรวจสอบภาพ วิดีโอ หรือเสียง แล้วลองอีกครั้ง',
        vi: 'Không thể đọc tệp phương tiện đã lưu. Vui lòng kiểm tra hình ảnh, video hoặc âm thanh rồi thử lại.',
    },
    gcs_setup: {
        en: 'GCS storage is not ready. Please ask the administrator to check the storage configuration.',
        th: 'พื้นที่จัดเก็บ GCS ยังไม่พร้อม โปรดแจ้งผู้ดูแลระบบให้ตรวจสอบการตั้งค่าพื้นที่จัดเก็บ',
        vi: 'Bộ nhớ GCS chưa sẵn sàng. Vui lòng nhờ quản trị viên kiểm tra cấu hình lưu trữ.',
    },
    tts_required: {
        en: 'Generate and save the TTS audio before submitting for rendering.',
        th: 'โปรดสร้างและบันทึกเสียง TTS ก่อนส่งไปเรนเดอร์',
        vi: 'Vui lòng tạo và lưu âm thanh TTS trước khi gửi để kết xuất.',
    },
    thumbnail_required: {
        en: 'Save the final thumbnail before submitting for rendering.',
        th: 'โปรดบันทึกภาพปกฉบับสมบูรณ์ก่อนส่งไปเรนเดอร์',
        vi: 'Vui lòng lưu ảnh thu nhỏ hoàn chỉnh trước khi gửi để kết xuất.',
    },
    thumbnail_layers: {
        en: 'Save the thumbnail background and text layers first.',
        th: 'โปรดบันทึกพื้นหลังและเลเยอร์ข้อความของภาพปกก่อน',
        vi: 'Vui lòng lưu nền và các lớp văn bản của ảnh thu nhỏ trước.',
    },
    empty_text: {
        en: 'There is no text to generate audio from. Please save the script or subtitles first.',
        th: 'ไม่มีข้อความสำหรับสร้างเสียง โปรดบันทึกสคริปต์หรือคำบรรยายก่อน',
        vi: 'Chưa có văn bản để tạo âm thanh. Vui lòng lưu kịch bản hoặc phụ đề trước.',
    },
    google_quota: {
        en: 'The Google voice API request limit was reached. This is separate from ElevenLabs credits. Please check the Google Cloud TTS quota.',
        th: 'ถึงขีดจำกัดคำขอของ Google voice API แล้ว ขีดจำกัดนี้แยกจากเครดิต ElevenLabs โปรดตรวจสอบโควตา TTS ใน Google Cloud',
        vi: 'Đã đạt giới hạn yêu cầu của API giọng nói Google. Giới hạn này độc lập với tín dụng ElevenLabs. Vui lòng kiểm tra hạn mức TTS trên Google Cloud.',
    },
    eleven_quota: {
        en: 'The ElevenLabs API usage limit was reached. Check the account and per-key limit for the API key registered in AIR Studio.',
        th: 'ถึงขีดจำกัดการใช้งาน ElevenLabs API แล้ว โปรดตรวจสอบบัญชีและขีดจำกัดของคีย์ API ที่ลงทะเบียนใน AIR Studio',
        vi: 'Đã đạt giới hạn sử dụng API ElevenLabs. Vui lòng kiểm tra tài khoản và giới hạn riêng của khóa API đã đăng ký trong AIR Studio.',
    },
    quota: {
        en: 'The voice provider usage limit was reached. Please check the provider account and API limits.',
        th: 'ถึงขีดจำกัดการใช้งานของผู้ให้บริการเสียงแล้ว โปรดตรวจสอบบัญชีและขีดจำกัด API ของผู้ให้บริการ',
        vi: 'Đã đạt giới hạn sử dụng của nhà cung cấp giọng nói. Vui lòng kiểm tra tài khoản và giới hạn API của nhà cung cấp.',
    },
    google_billing: {
        en: 'Google Cloud billing prevented audio generation. Please check the billing status of the configured project.',
        th: 'สร้างเสียงไม่ได้เนื่องจากการตั้งค่าการเรียกเก็บเงิน Google Cloud โปรดตรวจสอบสถานะการเรียกเก็บเงินของโปรเจกต์ที่ตั้งค่าไว้',
        vi: 'Không thể tạo âm thanh do cài đặt thanh toán Google Cloud. Vui lòng kiểm tra trạng thái thanh toán của dự án đã cấu hình.',
    },
    google_setup: {
        en: 'Please ask the administrator to check the Google Cloud project, server credentials, and Text-to-Speech API access.',
        th: 'โปรดแจ้งผู้ดูแลระบบให้ตรวจสอบโปรเจกต์ Google Cloud ข้อมูลรับรองของเซิร์ฟเวอร์ และสิทธิ์ใช้งาน Text-to-Speech API',
        vi: 'Vui lòng nhờ quản trị viên kiểm tra dự án Google Cloud, thông tin xác thực máy chủ và quyền truy cập API Text-to-Speech.',
    },
    eleven_setup: {
        en: 'Please check the ElevenLabs API key and its permissions in AIR Studio.',
        th: 'โปรดตรวจสอบคีย์ ElevenLabs API และสิทธิ์การใช้งานใน AIR Studio',
        vi: 'Vui lòng kiểm tra khóa API ElevenLabs và quyền truy cập của khóa trong AIR Studio.',
    },
    google_request: {
        en: 'Google rejected this audio request. Please check the segment text and voice settings.',
        th: 'Google ปฏิเสธคำขอสร้างเสียงนี้ โปรดตรวจสอบข้อความและการตั้งค่าเสียงของส่วนนี้',
        vi: 'Google đã từ chối yêu cầu tạo âm thanh này. Vui lòng kiểm tra văn bản và cài đặt giọng nói của đoạn này.',
    },
    google_error: {
        en: 'Google could not complete the audio request. Please try again shortly.',
        th: 'Google ไม่สามารถดำเนินการคำขอสร้างเสียงให้เสร็จสิ้นได้ โปรดลองอีกครั้งในอีกสักครู่',
        vi: 'Google không thể hoàn tất yêu cầu tạo âm thanh. Vui lòng thử lại sau ít phút.',
    },
    tts_pending: {
        en: 'Audio generation is already in progress or its saved result needs confirmation. Please try again shortly.',
        th: 'กำลังสร้างเสียงอยู่หรือยังต้องตรวจสอบผลการบันทึก โปรดลองอีกครั้งในอีกสักครู่',
        vi: 'Âm thanh đang được tạo hoặc cần xác nhận kết quả đã lưu. Vui lòng thử lại sau ít phút.',
    },
    project_load: {
        en: 'Could not load the project. Please reopen it and try again.',
        th: 'โหลดโปรเจกต์ไม่สำเร็จ โปรดเปิดโปรเจกต์ใหม่แล้วลองอีกครั้ง',
        vi: 'Không thể tải dự án. Vui lòng mở lại dự án rồi thử lại.',
    },
} satisfies Record<string, Record<FeedbackLocale, string>>

function errorText(error: unknown): string {
    if (typeof error === 'string') return error.trim()
    if (error instanceof Error) return error.message.trim()
    if (error && typeof error === 'object') {
        const value = error as { message?: unknown; error?: unknown }
        if (typeof value.message === 'string') return value.message.trim()
        if (typeof value.error === 'string') return value.error.trim()
    }
    return ''
}

/** Never append untranslated server/provider text to a localized user notification. */
export function localizeStdActionError(error: unknown, locale: string, action: StdFeedbackAction): string {
    const raw = errorText(error)
    const language = String(locale || '').toLowerCase().split(/[-_]/)[0]
    if (language !== 'en' && language !== 'th' && language !== 'vi') {
        return raw || ({ subtitle_save: '자막을 저장하지 못했습니다. 다시 시도해 주세요.', tts: '음성을 생성하고 저장하지 못했습니다. 다시 시도해 주세요.', submit: '프로젝트를 제출하지 못했습니다. 다시 시도해 주세요.' }[action])
    }
    const lower = raw.toLowerCase()
    const google = /google|gemini|voice studio|aiplatform|texttospeech|text-to-speech api/.test(lower)
    const eleven = /elevenlabs/.test(lower)
    let key: keyof typeof feedback = action

    if (/project changed while saving|저장 중.*변경|저장.*충돌/.test(lower)) key = 'conflict'
    else if (/project not found|프로젝트.*찾을 수 없|프로젝트가 없습니다/.test(lower)) key = 'project_missing'
    else if (/project is (closed|not editable)|프로젝트.*(종료|편집할 수 없)/.test(lower)) key = 'project_closed'
    else if (/대본이 변경|script.*changed|script_changed_requires_audio_regeneration/.test(lower)) key = 'script_changed'
    else if (/project has no scenes|렌더.*씬.*없/.test(lower)) key = 'no_scenes'
    else if (/required uploaded assets|needs an image for the selected comic motion/.test(lower)) key = 'missing_assets'
    else if (/편집 배경과 문구 레이어/.test(lower)) key = 'thumbnail_layers'
    else if (/thumbnail is required|최종 썸네일.*저장/.test(lower)) key = 'thumbnail_required'
    else if (/tts audio is required|렌더용 오디오 파일.*없/.test(lower)) key = 'tts_required'
    else if (/tts text is empty|tts multi-voice text has no segments/.test(lower)) key = 'empty_text'
    else if (/gcs.*not configured|gcs config upload failed|gcs 저장 정보.*없/.test(lower)) key = 'gcs_setup'
    else if (/읽을 수 없|불러오지 못|missing from render storage|could not be read|failed to prepare stored assets/.test(lower) && /파일|이미지|영상|오디오|음성|gcs|storage|assets|media/.test(lower)) key = 'storage'
    else if (/진행 중이거나 저장 확인|중복 생성 방지|already.*(generat|progress)/.test(lower)) key = 'tts_pending'
    else if (/프로젝트 정보.*불러오지 못|failed to load project/.test(lower)) key = 'project_load'
    else if (google && /billing|payment|결제 설정|결제 상태/.test(lower)) key = 'google_billing'
    else if (/quota|resource_exhausted|429|요청 한도|사용 한도|insufficient credits|credits remaining|크레딧이 부족/.test(lower)) key = google ? 'google_quota' : eleven ? 'eleven_quota' : 'quota'
    else if ((google || eleven) && /not configured|먼저 설정|401|unauthorized|unauthenticated|permission|forbidden|403|api.?key|인증|사용 권한|설정.*확인|사용 가능한 키가 없|현재 elevenlabs 키로 사용할 수 없/.test(lower)) key = google ? 'google_setup' : 'eleven_setup'
    else if (/function_invocation_timeout|gateway timeout|504|timeout|timed out|deadline_exceeded|시간.*초과|시간.*만료/.test(lower)) key = action === 'tts' ? 'tts_timeout' : 'timeout'
    else if (google && /거부|invalid.argument|bad.request|safety|prohibited|content.policy/.test(lower)) key = 'google_request'
    else if (google) key = 'google_error'
    else if (/unauthorized|forbidden|not authenticated|authentication required|jwt expired|session.*expired|로그인|인증.*필요/.test(lower)) key = 'auth'
    else if (/failed to fetch|fetch failed|network|load failed|econn|offline|네트워크|연결.*실패/.test(lower)) key = 'network'

    let message = feedback[key][language]
    const subtitle = raw.match(/(?:자막\s*(\d+)\s*번|subtitle\s*#?\s*(\d+))/i)
    const scene = raw.match(/(?:생성 이미지|생성 영상|이미지|영상)\s*(\d+)\s*번|scene\s*#?\s*(\d+)/i)
    if (subtitle) {
        const number = subtitle[1] || subtitle[2]
        message = `${({ en: 'Subtitle', th: 'คำบรรยาย', vi: 'Phụ đề' }[language])} ${number}: ${message}`
    } else if (scene) {
        const number = scene[1] || scene[2]
        message = `${({ en: 'Scene', th: 'ฉาก', vi: 'Cảnh' }[language])} ${number}: ${message}`
    }
    const credits = key === 'eleven_quota' && raw.match(/you have\s+([\d,]+)\s+credits?\s+remaining,\s+while\s+([\d,]+)\s+credits?\s+are required/i)
    if (credits) message += ({
        en: ` The API reports ${credits[1]} credits remaining; this request requires ${credits[2]}.`,
        th: ` API รายงานว่าเหลือ ${credits[1]} เครดิต แต่คำขอนี้ต้องใช้ ${credits[2]} เครดิต`,
        vi: ` API báo còn ${credits[1]} tín dụng; yêu cầu này cần ${credits[2]} tín dụng.`,
    }[language])
    return message
}
