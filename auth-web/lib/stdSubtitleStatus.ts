import type { SupportedLocale } from './i18n'
import { stdUiText } from './stdUiText'

type Copy = Record<'en' | 'vi' | 'th', string>
const copy: Record<string, Copy> = {
  '자막 미리듣기 준비 중... ({current}/{total})': { en: 'Preparing subtitle preview… ({current}/{total})', vi: 'Đang chuẩn bị nghe thử phụ đề… ({current}/{total})', th: 'กำลังเตรียมฟังตัวอย่างคำบรรยาย… ({current}/{total})' },
  '저장된 최종 TTS로 자막 미리듣기 재생 중...': { en: 'Playing subtitle preview using saved final TTS…', vi: 'Đang nghe thử phụ đề bằng giọng đọc TTS đã lưu…', th: 'กำลังฟังตัวอย่างคำบรรยายด้วยเสียง TTS ที่บันทึกไว้…' },
  '자막 미리듣기가 완료되었습니다.': { en: 'Subtitle preview complete.', vi: 'Đã nghe thử phụ đề xong.', th: 'ฟังตัวอย่างคำบรรยายเสร็จแล้ว' },
  '자막 번역을 준비하거나 진행하고 있습니다.': { en: 'Preparing or translating subtitles…', vi: 'Đang chuẩn bị hoặc dịch phụ đề…', th: 'กำลังเตรียมหรือแปลคำบรรยาย…' },
  '자막 {count}개를 블록 그대로 {language}로 번역했습니다.': { en: 'Translated {count} subtitle blocks into {language}.', vi: 'Đã dịch {count} khối phụ đề sang {language}.', th: 'แปลคำบรรยาย {count} บล็อกเป็น{language}แล้ว' },
  '저장된 {language} 자막 번역을 불러왔습니다.': { en: 'Loaded saved {language} subtitle translations.', vi: 'Đã tải bản dịch phụ đề {language} đã lưu.', th: 'โหลดคำแปลคำบรรยาย{language}ที่บันทึกไว้แล้ว' },
  '자막 목록이 변경됐습니다. 합칠 자막을 다시 선택해 주세요.': { en: 'The subtitle list changed. Select the lines to merge again.', vi: 'Danh sách phụ đề đã thay đổi. Hãy chọn lại các dòng cần ghép.', th: 'รายการคำบรรยายเปลี่ยนไป โปรดเลือกบรรทัดที่จะรวมอีกครั้ง' },
  '분리할 수 있는 자막 내용이 없습니다.': { en: 'There is no subtitle text to split.', vi: 'Không có nội dung phụ đề để tách.', th: 'ไม่มีข้อความคำบรรยายที่จะแยก' },
  '자막 내용의 중간에 커서를 놓고 다시 분리해 주세요.': { en: 'Place the cursor within the subtitle text and try splitting again.', vi: 'Đặt con trỏ vào giữa nội dung phụ đề và thử tách lại.', th: 'วางเคอร์เซอร์ภายในข้อความคำบรรยายแล้วลองแยกอีกครั้ง' },
  '씬 {scene}의 자막 {count}개를 하나로 합쳤습니다.': { en: 'Merged {count} subtitles in scene {scene}.', vi: 'Đã ghép {count} phụ đề trong cảnh {scene}.', th: 'รวมคำบรรยาย {count} รายการในฉาก {scene} แล้ว' },
  '씬 {scene}의 자막을 2개로 분리했습니다.': { en: 'Split the subtitle in scene {scene} into two.', vi: 'Đã tách phụ đề trong cảnh {scene} thành hai phần.', th: 'แยกคำบรรยายในฉาก {scene} เป็นสองส่วนแล้ว' },
  '선택한 자막 {count}개의 성우를 {voice}(으)로 변경했습니다.': { en: 'Changed the voice of {count} selected subtitles to {voice}.', vi: 'Đã đổi giọng của {count} phụ đề đã chọn thành {voice}.', th: 'เปลี่ยนเสียงคำบรรยายที่เลือก {count} รายการเป็น {voice} แล้ว' },
  '줄별 TTS 길이로 보정했습니다. 저장된 전체 음성에 맞춘 정밀 싱크는 아닙니다.': { en: 'Adjusted using each line’s TTS duration. This is not precise alignment to the full saved audio.', vi: 'Đã điều chỉnh theo thời lượng TTS từng dòng. Đây không phải đồng bộ chính xác với toàn bộ âm thanh đã lưu.', th: 'ปรับตามความยาว TTS ของแต่ละบรรทัดแล้ว แต่ยังไม่ใช่การซิงก์อย่างละเอียดกับเสียงที่บันทึกทั้งไฟล์' },
  '배경음 적용을 해제했습니다.': { en: 'Background music removed.', vi: 'Đã bỏ nhạc nền.', th: 'นำเพลงพื้นหลังออกแล้ว' },
  '현재 자막 구간의 SFX 적용을 해제했습니다.': { en: 'Sound effect removed from this subtitle.', vi: 'Đã bỏ hiệu ứng âm thanh khỏi đoạn phụ đề này.', th: 'นำเอฟเฟกต์เสียงออกจากช่วงคำบรรยายนี้แล้ว' },
  '배경음 파일을 불러오지 못했습니다. 다시 업로드해 주세요.': { en: 'Could not load the background audio. Please upload it again.', vi: 'Không thể tải âm thanh nền. Vui lòng tải lên lại.', th: 'โหลดเสียงพื้นหลังไม่สำเร็จ โปรดอัปโหลดอีกครั้ง' },
  '선택한 씬에 변경할 나레이션 자막이 없습니다.': { en: 'There are no narration subtitles to change in the selected scenes.', vi: 'Các cảnh đã chọn không có phụ đề lời dẫn để thay đổi.', th: 'ฉากที่เลือกไม่มีคำบรรยายเสียงเล่าที่จะแก้ไข' },
  '씬 효과 저장 중...': { en: 'Saving scene effects…', vi: 'Đang lưu hiệu ứng cảnh…', th: 'กำลังบันทึกเอฟเฟกต์ฉาก…' },
  '씬 {count}개 효과를 저장했습니다.': { en: 'Saved effects for {count} scenes.', vi: 'Đã lưu hiệu ứng cho {count} cảnh.', th: 'บันทึกเอฟเฟกต์สำหรับ {count} ฉากแล้ว' },
  '씬 효과 저장에 실패했습니다. 다시 선택해 주세요.': { en: 'Could not save scene effects. Please select them again.', vi: 'Không thể lưu hiệu ứng cảnh. Vui lòng chọn lại.', th: 'บันทึกเอฟเฟกต์ฉากไม่สำเร็จ โปรดเลือกอีกครั้ง' },
}
const patterns: Array<[RegExp, string, string[]]> = [
  [/^자막 미리듣기 준비 중\.\.\. \((\d+)\/(\d+)\)$/, '자막 미리듣기 준비 중... ({current}/{total})', ['current','total']],
  [/^씬 (\d+)의 자막 (\d+)개를 하나로 합쳤습니다\.$/, '씬 {scene}의 자막 {count}개를 하나로 합쳤습니다.', ['scene','count']],
  [/^씬 (\d+)의 자막을 2개로 분리했습니다\.$/, '씬 {scene}의 자막을 2개로 분리했습니다.', ['scene']],
  [/^선택한 자막 (\d+)개의 성우를 (.+)\(으\)로 변경했습니다\.$/, '선택한 자막 {count}개의 성우를 {voice}(으)로 변경했습니다.', ['count','voice']],
  [/^씬 (\d+)개 효과를 저장했습니다\.$/, '씬 {count}개 효과를 저장했습니다.', ['count']],
  [/^자막 (\d+)개를 블록 그대로 (.+)로 번역했습니다\.$/, '자막 {count}개를 블록 그대로 {language}로 번역했습니다.', ['count','language']],
  [/^저장된 (.+) 자막 번역을 불러왔습니다\.$/, '저장된 {language} 자막 번역을 불러왔습니다.', ['language']],
]
const languageNames: Record<string, Copy> = {
  '한국어': { en:'Korean', vi:'tiếng Hàn', th:'ภาษาเกาหลี' }, '영어': { en:'English', vi:'tiếng Anh', th:'ภาษาอังกฤษ' },
  '베트남어': { en:'Vietnamese', vi:'tiếng Việt', th:'ภาษาเวียดนาม' }, '태국어': { en:'Thai', vi:'tiếng Thái', th:'ภาษาไทย' },
}
export function localizeSubtitleStatus(message: string, locale: SupportedLocale): string {
  if (locale === 'ko' || !message) return message
  let key = message
  const values: Record<string, string> = {}
  for (const [regex, template, names] of patterns) {
    const match = message.match(regex)
    if (match) { key = template; names.forEach((name, i) => { values[name] = name === 'language' ? languageNames[match[i+1]]?.[locale] || match[i+1] : match[i+1] }); break }
  }
  const result = (copy[key]?.[locale] || stdUiText(locale, key, values))
    .replace(/\{(\w+)\}/g, (_, name) => values[name] ?? `{${name}}`)
  // Provider errors can be arbitrary. Keep their original detail in the status
  // element's title while showing a readable, truthful fallback in the UI.
  if (result === message && (/[가-힣]/.test(result) || (locale !== 'en' && /error|failed|unable|could not|timed out/i.test(message)))) {
    const failed = /실패|오류|못했|없습니다|않았습니다|중단|❌|error|failed|unable|could not|timed out/i.test(message)
    const pending = /중\.\.\.|중…|진행 중|준비 중/.test(message)
    const fallback = failed
      ? { en: 'The operation needs attention. Hover for details.', vi: 'Thao tác cần được kiểm tra. Di chuột để xem chi tiết.', th: 'การดำเนินการต้องได้รับการตรวจสอบ วางเมาส์เพื่อดูรายละเอียด' }
      : pending
        ? { en: 'Operation in progress. Hover for details.', vi: 'Đang xử lý. Di chuột để xem chi tiết.', th: 'กำลังดำเนินการ วางเมาส์เพื่อดูรายละเอียด' }
        : { en: 'Operation status updated. Hover for details.', vi: 'Đã cập nhật trạng thái. Di chuột để xem chi tiết.', th: 'อัปเดตสถานะแล้ว วางเมาส์เพื่อดูรายละเอียด' }
    return fallback[locale]
  }
  return result
}
