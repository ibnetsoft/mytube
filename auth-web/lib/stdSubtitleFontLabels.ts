// Display names only: the saved font family and render font IDs remain unchanged.
const labels: Record<string, Record<string, string>> = {
  'NotoSansJP-Regular': { ko: 'Noto Sans JP · 일본어 고딕 보통', en: 'Noto Sans JP · Japanese sans serif regular', vi: 'Noto Sans JP · Sans serif Nhật thường', th: 'Noto Sans JP · แซนส์ญี่ปุ่น ปกติ' },
  'NotoSansJP-Bold': { ko: 'Noto Sans JP · 일본어 고딕 굵게', en: 'Noto Sans JP · Japanese sans serif bold', vi: 'Noto Sans JP · Sans serif Nhật đậm', th: 'Noto Sans JP · แซนส์ญี่ปุ่น ตัวหนา' },
  'NotoSerifJP-Bold': { ko: 'Noto Serif JP · 일본어 명조 굵게', en: 'Noto Serif JP · Japanese serif bold', vi: 'Noto Serif JP · Serif Nhật đậm', th: 'Noto Serif JP · เซอริฟญี่ปุ่น ตัวหนา' },
  'CookieRun-Regular': { ko: '쿠키런 보통 (CookieRun)', en: 'CookieRun Regular', vi: 'CookieRun thường', th: 'CookieRun ปกติ' },
  'GmarketSansBold': { ko: '지마켓 산스 굵게 (Gmarket Sans)', en: 'Gmarket Sans Bold', vi: 'Gmarket Sans đậm', th: 'Gmarket Sans ตัวหนา' },
  'TmonMonsori': { ko: '티몬 몬소리 (Tmon Monsori)', en: 'Tmon Monsori', vi: 'Tmon Monsori', th: 'Tmon Monsori' },
  'Jalnan': { ko: '잘난체 (Jalnan)', en: 'Jalnan', vi: 'Jalnan', th: 'Jalnan' },
  'Pretendard-Bold': { ko: '프리텐다드 굵게 (Pretendard)', en: 'Pretendard Bold', vi: 'Pretendard đậm', th: 'Pretendard ตัวหนา' },
  'NanumSquareExtraBold': { ko: '나눔스퀘어 아주 굵게', en: 'Nanum Square Extra Bold', vi: 'Nanum Square rất đậm', th: 'Nanum Square หนาพิเศษ' },
  'BinggraeMelona-Bold': { ko: '빙그레 메로나 굵게', en: 'Binggrae Melona Bold', vi: 'Binggrae Melona đậm', th: 'Binggrae Melona ตัวหนา' },
  'NetmarbleB': { ko: '넷마블 굵게', en: 'Netmarble Bold', vi: 'Netmarble đậm', th: 'Netmarble ตัวหนา' },
  'ChosunIlboMyungjo': { ko: '조선일보 명조', en: 'Chosun Ilbo Myeongjo', vi: 'Chosun Ilbo Myeongjo', th: 'Chosun Ilbo Myeongjo' },
  'MapoFlowerIsland': { ko: '마포꽃섬', en: 'Mapo Flower Island', vi: 'Mapo Flower Island', th: 'Mapo Flower Island' },
  'S-CoreDream-6Bold': { ko: '에스코어 드림 6 굵게', en: 'S-Core Dream 6 Bold', vi: 'S-Core Dream 6 đậm', th: 'S-Core Dream 6 ตัวหนา' },
  'Black Han Sans': { ko: '검은고딕 (Black Han Sans)', en: 'Black Han Sans', vi: 'Black Han Sans', th: 'Black Han Sans' },
  'Jua': { ko: '주아 (Jua)', en: 'Jua', vi: 'Jua', th: 'Jua' },
  'Do Hyeon': { ko: '도현 (Do Hyeon)', en: 'Do Hyeon', vi: 'Do Hyeon', th: 'Do Hyeon' },
  'NanumMyeongjo': { ko: '나눔명조', en: 'Nanum Myeongjo', vi: 'Nanum Myeongjo', th: 'Nanum Myeongjo' },
  'Malgun Gothic': { ko: '맑은 고딕 (Malgun Gothic · 렌더 폰트)', en: 'Malgun Gothic · render font', vi: 'Malgun Gothic · phông kết xuất', th: 'Malgun Gothic · แบบอักษรสำหรับเรนเดอร์' },
}

export function subtitleFontLabel(font: string, locale: string): string {
  return labels[font]?.[locale] || labels[font]?.en || font
}
