import type { SupportedLocale } from './i18n'

export interface VoiceDialogCopy {
    dialogueTitle: string
    narrationTitle: string
    chooseTitle: string
    currentVoice: string
    close: string
    speaker: string
    speakerRequired: string
    speakerNameUnavailable: string
    male: string
    female: string
    neutral: string
    genderUnknown: string
    speakerNote: string
    applyAll: (count: number) => string
    providers: string
    google: string
    elevenlabs: string
    search: string
    searchPlaceholder: string
    genderFilter: string
    all: string
    googleDescription: string
    elevenlabsDescription: string
    loading: string
    preview: string
    selected: string
    select: string
    noResults: string
    previewFailed: string
    sampleFailed: string
    noSample: string
    googleSampleNote: string
    direction: string
    directionPlaceholder: string
    mismatch: (speaker: string, voice: string) => string
    allowMismatch: string
    selection: string
    chooseVoice: string
    cancel: string
    confirm: string
    saving: string
    saveFailed: string
    narrationOnly: string
    characterScope: string
    lineScope: string
    targetScope: string
    sceneScope: string
    selectedScenesTitle: (count: number) => string
    selectedBlocksTitle: (count: number) => string
    sceneTitle: (scene: number | string) => string
    play: string
    pause: string
    seek: string
    volume: string
    dialogueScope: string
}

const COPY: Record<SupportedLocale, VoiceDialogCopy> = {
    ko: {
        dialogueTitle: '인물 음성',
        narrationTitle: '내레이션 성우 선택',
        chooseTitle: '성우 선택',
        currentVoice: '현재 성우',
        close: '닫기',
        speaker: '화자',
        speakerRequired: '화자 확인 필요',
        speakerNameUnavailable: '선택한 자막의 인물 (이름 번역 없음)',
        male: '남성',
        female: '여성',
        neutral: '중성',
        genderUnknown: '성별 미지정',
        speakerNote: '화자 정보는 편집용이며 음성 합성·영상 자막에 포함되지 않습니다.',
        applyAll: count => `이 인물의 모든 대사 ${count}개에 적용`,
        providers: '성우 제공사',
        google: 'Google 성우',
        elevenlabs: 'ElevenLabs 성우',
        search: '성우 검색',
        searchPlaceholder: '성우 이름, 설명 검색',
        genderFilter: '성별 필터',
        all: '전체',
        googleDescription: 'Google 음성',
        elevenlabsDescription: 'ElevenLabs 음성',
        loading: '불러오는 중…',
        preview: '미리듣기',
        selected: '선택됨',
        select: '선택',
        noResults: '검색 결과가 없습니다.',
        previewFailed: '미리듣기를 재생하지 못했습니다. 다시 시도해 주세요.',
        sampleFailed: '샘플을 불러오지 못했습니다. 다시 시도해 주세요.',
        noSample: '제공된 미리듣기 샘플이 없습니다.',
        googleSampleNote: 'Google 샘플은 미리듣기를 누를 때만 요청하며, 최초 생성 시 사용료가 발생할 수 있습니다.',
        direction: '말투·감정',
        directionPlaceholder: '예: 담담하고 따뜻하게',
        mismatch: (speaker, voice) => `${speaker}의 성별과 선택한 성우 ${voice}의 성별이 다릅니다.`,
        allowMismatch: '의도적으로 다른 성별의 성우를 사용합니다',
        selection: '선택',
        chooseVoice: '성우를 선택해 주세요',
        cancel: '취소',
        confirm: '선택 완료',
        saving: '저장 중…',
        saveFailed: '성우 저장에 실패했습니다. 다시 시도해 주세요.',
        narrationOnly: '내레이션에만 적용합니다.',
        characterScope: '인물별 성우를 선택합니다. 전체 적용을 해제하면 이 자막만 변경합니다.',
        lineScope: '이 자막 한 줄에만 적용합니다. 다른 자막의 성우는 유지됩니다.',
        targetScope: '선택한 대상의 성우를 변경합니다.',
        sceneScope: '선택한 씬의 내레이션 자막만 변경합니다. 화자가 지정된 대사와 확인이 필요한 노란색 자막은 유지됩니다.',
        selectedScenesTitle: count => `선택한 씬 ${count}개 내레이션 성우`,
        selectedBlocksTitle: count => `선택한 자막 ${count}개 대사 성우`,
        sceneTitle: scene => `씬 ${scene} 내레이션 성우 선택`,
        play: '재생',
        pause: '일시 정지',
        seek: '재생 위치',
        volume: '음량',
        dialogueScope: '대사 자막에만 적용합니다.',
    },
    en: {
        dialogueTitle: 'Character voice',
        narrationTitle: 'Choose a narration voice',
        chooseTitle: 'Choose a voice',
        currentVoice: 'Current voice',
        close: 'Close',
        speaker: 'Speaker',
        speakerRequired: 'Speaker confirmation required',
        speakerNameUnavailable: 'Character in the selected subtitle (name translation unavailable)',
        male: 'Male',
        female: 'Female',
        neutral: 'Neutral',
        genderUnknown: 'Gender unspecified',
        speakerNote: 'Speaker information is for editing only and is not included in synthesized speech or video subtitles.',
        applyAll: count => `Apply to all ${count} dialogue lines for this character`,
        providers: 'Voice providers',
        google: 'Google voices',
        elevenlabs: 'ElevenLabs voices',
        search: 'Search voices',
        searchPlaceholder: 'Search voice names and descriptions',
        genderFilter: 'Gender filter',
        all: 'All',
        googleDescription: 'Google voice',
        elevenlabsDescription: 'ElevenLabs voice',
        loading: 'Loading…',
        preview: 'Preview',
        selected: 'Selected',
        select: 'Select',
        noResults: 'No results found.',
        previewFailed: 'Unable to play the preview. Please try again.',
        sampleFailed: 'Unable to load the sample. Please try again.',
        noSample: 'No preview sample is available.',
        googleSampleNote: 'Google samples are requested only when you press Preview. The first generation may incur a charge.',
        direction: 'Tone and emotion',
        directionPlaceholder: 'For example: calm and warm',
        mismatch: (speaker, voice) => `The gender of ${speaker} differs from the selected voice, ${voice}.`,
        allowMismatch: 'I intend to use a voice of a different gender',
        selection: 'Selection',
        chooseVoice: 'Please choose a voice',
        cancel: 'Cancel',
        confirm: 'Confirm selection',
        saving: 'Saving…',
        saveFailed: 'Unable to save the voice. Please try again.',
        narrationOnly: 'Applies to narration only.',
        characterScope: 'Choose a voice for this character. Uncheck the option to apply it to all lines to change only this subtitle.',
        lineScope: 'Applies only to this subtitle line. Voices for other subtitles remain unchanged.',
        targetScope: 'Changes the voice for the selected items.',
        sceneScope: 'Changes only narration subtitles in the selected scene. Dialogue with an assigned speaker and yellow subtitles requiring review remain unchanged.',
        selectedScenesTitle: count => `Narration voice for ${count} selected ${count === 1 ? 'scene' : 'scenes'}`,
        selectedBlocksTitle: count => `Dialogue voice for ${count} selected ${count === 1 ? 'subtitle' : 'subtitles'}`,
        sceneTitle: scene => `Choose a narration voice for scene ${scene}`,
        play: 'Play',
        pause: 'Pause',
        seek: 'Playback position',
        volume: 'Volume',
        dialogueScope: 'Applies to dialogue subtitles only.',
    },
    vi: {
        dialogueTitle: 'Giọng nhân vật',
        narrationTitle: 'Chọn giọng thuyết minh',
        chooseTitle: 'Chọn giọng đọc',
        currentVoice: 'Giọng hiện tại',
        close: 'Đóng',
        speaker: 'Người nói',
        speakerRequired: 'Cần xác nhận người nói',
        speakerNameUnavailable: 'Nhân vật trong phụ đề đã chọn (chưa có bản dịch tên)',
        male: 'Nam',
        female: 'Nữ',
        neutral: 'Trung tính',
        genderUnknown: 'Chưa xác định giới tính',
        speakerNote: 'Thông tin người nói chỉ dùng để biên tập, không được đưa vào giọng nói tổng hợp hoặc phụ đề video.',
        applyAll: count => `Áp dụng cho tất cả ${count} câu thoại của nhân vật này`,
        providers: 'Nhà cung cấp giọng đọc',
        google: 'Giọng Google',
        elevenlabs: 'Giọng ElevenLabs',
        search: 'Tìm giọng đọc',
        searchPlaceholder: 'Tìm theo tên hoặc mô tả giọng đọc',
        genderFilter: 'Lọc theo giới tính',
        all: 'Tất cả',
        googleDescription: 'Giọng đọc Google',
        elevenlabsDescription: 'Giọng đọc ElevenLabs',
        loading: 'Đang tải…',
        preview: 'Nghe thử',
        selected: 'Đã chọn',
        select: 'Chọn',
        noResults: 'Không tìm thấy kết quả.',
        previewFailed: 'Không thể phát bản nghe thử. Vui lòng thử lại.',
        sampleFailed: 'Không thể tải mẫu giọng. Vui lòng thử lại.',
        noSample: 'Không có mẫu giọng để nghe thử.',
        googleSampleNote: 'Mẫu giọng Google chỉ được yêu cầu khi bạn nhấn Nghe thử. Lần tạo đầu tiên có thể phát sinh phí.',
        direction: 'Giọng điệu và cảm xúc',
        directionPlaceholder: 'Ví dụ: điềm tĩnh và ấm áp',
        mismatch: (speaker, voice) => `Giới tính của ${speaker} khác với giọng đọc đã chọn, ${voice}.`,
        allowMismatch: 'Tôi chủ ý sử dụng giọng đọc có giới tính khác',
        selection: 'Đã chọn',
        chooseVoice: 'Vui lòng chọn giọng đọc',
        cancel: 'Hủy',
        confirm: 'Xác nhận lựa chọn',
        saving: 'Đang lưu…',
        saveFailed: 'Không thể lưu giọng đọc. Vui lòng thử lại.',
        narrationOnly: 'Chỉ áp dụng cho phần thuyết minh.',
        characterScope: 'Chọn giọng đọc cho nhân vật này. Bỏ chọn áp dụng cho tất cả câu thoại để chỉ thay đổi phụ đề này.',
        lineScope: 'Chỉ áp dụng cho dòng phụ đề này. Giọng đọc của các phụ đề khác được giữ nguyên.',
        targetScope: 'Thay đổi giọng đọc cho các mục đã chọn.',
        sceneScope: 'Chỉ thay đổi phụ đề thuyết minh trong cảnh đã chọn. Giữ nguyên câu thoại đã có người nói và phụ đề màu vàng cần kiểm tra.',
        selectedScenesTitle: count => `Giọng thuyết minh cho ${count} cảnh đã chọn`,
        selectedBlocksTitle: count => `Giọng thoại cho ${count} phụ đề đã chọn`,
        sceneTitle: scene => `Chọn giọng thuyết minh cho cảnh ${scene}`,
        play: 'Phát',
        pause: 'Tạm dừng',
        seek: 'Vị trí phát',
        volume: 'Âm lượng',
        dialogueScope: 'Chỉ áp dụng cho phụ đề hội thoại.',
    },
    th: {
        dialogueTitle: 'เสียงตัวละคร',
        narrationTitle: 'เลือกเสียงบรรยาย',
        chooseTitle: 'เลือกเสียง',
        currentVoice: 'เสียงปัจจุบัน',
        close: 'ปิด',
        speaker: 'ผู้พูด',
        speakerRequired: 'ต้องยืนยันผู้พูดก่อน',
        speakerNameUnavailable: 'ตัวละครในคำบรรยายที่เลือก (ยังไม่มีคำแปลชื่อ)',
        male: 'ชาย',
        female: 'หญิง',
        neutral: 'เป็นกลาง',
        genderUnknown: 'ไม่ระบุเพศ',
        speakerNote: 'ข้อมูลผู้พูดใช้สำหรับการตัดต่อเท่านั้น ไม่รวมอยู่ในเสียงสังเคราะห์หรือคำบรรยายวิดีโอ',
        applyAll: count => `ใช้เสียงนี้กับบทพูดทั้ง ${count} ประโยคของตัวละครนี้`,
        providers: 'ผู้ให้บริการเสียง',
        google: 'เสียงจากกูเกิล',
        elevenlabs: 'เสียงจากอีเลฟเวนแล็บส์',
        search: 'ค้นหาเสียง',
        searchPlaceholder: 'ค้นหาชื่อเสียงหรือคำอธิบาย',
        genderFilter: 'ตัวกรองเพศ',
        all: 'ทั้งหมด',
        googleDescription: 'เสียงจากกูเกิล',
        elevenlabsDescription: 'เสียงจากอีเลฟเวนแล็บส์',
        loading: 'กำลังโหลด…',
        preview: 'ฟังตัวอย่าง',
        selected: 'เลือกแล้ว',
        select: 'เลือก',
        noResults: 'ไม่พบผลการค้นหา',
        previewFailed: 'ไม่สามารถเล่นเสียงตัวอย่างได้ โปรดลองอีกครั้ง',
        sampleFailed: 'ไม่สามารถโหลดเสียงตัวอย่างได้ โปรดลองอีกครั้ง',
        noSample: 'ไม่มีเสียงตัวอย่างให้ฟัง',
        googleSampleNote: 'ระบบจะขอเสียงตัวอย่างจากกูเกิลเมื่อกดฟังตัวอย่างเท่านั้น การสร้างครั้งแรกอาจมีค่าใช้จ่าย',
        direction: 'น้ำเสียงและอารมณ์',
        directionPlaceholder: 'เช่น สงบและอบอุ่น',
        mismatch: (speaker, voice) => `เพศของตัวละคร ${speaker} ไม่ตรงกับเสียงที่เลือก ${voice}`,
        allowMismatch: 'ยืนยันว่าเลือกเสียงต่างเพศโดยตั้งใจ',
        selection: 'เสียงที่เลือก',
        chooseVoice: 'โปรดเลือกเสียง',
        cancel: 'ยกเลิก',
        confirm: 'ยืนยันการเลือก',
        saving: 'กำลังบันทึก…',
        saveFailed: 'ไม่สามารถบันทึกเสียงที่เลือกได้ โปรดลองอีกครั้ง',
        narrationOnly: 'ใช้กับเสียงบรรยายเท่านั้น',
        characterScope: 'เลือกเสียงให้ตัวละครนี้ หากต้องการเปลี่ยนเฉพาะคำบรรยายบรรทัดนี้ ให้ยกเลิกการเลือกใช้กับทุกประโยค',
        lineScope: 'ใช้กับคำบรรยายบรรทัดนี้เท่านั้น เสียงของคำบรรยายอื่นจะยังคงเดิม',
        targetScope: 'เปลี่ยนเสียงสำหรับรายการที่เลือก',
        sceneScope: 'เปลี่ยนเฉพาะคำบรรยายในส่วนของผู้บรรยายในฉากที่เลือก บทพูดที่ระบุผู้พูดแล้วและคำบรรยายสีเหลืองที่ต้องตรวจสอบจะยังคงเดิม',
        selectedScenesTitle: count => `เสียงบรรยายสำหรับ ${count} ฉากที่เลือก`,
        selectedBlocksTitle: count => `เสียงบทพูดสำหรับคำบรรยาย ${count} รายการที่เลือก`,
        sceneTitle: scene => `เลือกเสียงบรรยายสำหรับฉากที่ ${scene}`,
        play: 'เล่น',
        pause: 'หยุดชั่วคราว',
        seek: 'ตำแหน่งการเล่น',
        volume: 'ระดับเสียง',
        dialogueScope: 'ใช้กับคำบรรยายบทพูดเท่านั้น',
    },
}

export function voiceDialogCopy(locale: SupportedLocale): VoiceDialogCopy {
    return COPY[locale]
}

/** Use an existing localized label without changing the speaker's stored identity. */
export function voiceDialogSpeakerName(speaker: { name: string; label: string } | null | undefined, locale: SupportedLocale): string {
    if (!speaker) return ''
    const prefix = `${speaker.name} (`
    if (speaker.label.startsWith(prefix) && speaker.label.endsWith(')')) return speaker.label.slice(prefix.length, -1)
    const name = speaker.name.trim()
    const native = locale === 'th' ? /^[\u0e00-\u0e7f\s\p{N}\p{P}]+$/u.test(name)
        : locale === 'ko' ? /^[가-힣ㄱ-ㅎㅏ-ㅣ\s\p{N}\p{P}]+$/u.test(name)
        : /^[\p{Script=Latin}\p{M}\s\p{N}\p{P}]+$/u.test(name)
    return native ? name : COPY[locale].speakerNameUnavailable
}
