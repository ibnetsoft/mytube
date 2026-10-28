from pathlib import Path

roots = [Path.cwd(), Path('_dev/artifacts/project_completion_release_root.txt').read_text().strip()]
for root in map(Path, roots):
    path = root / 'auth-web/app/std/page.tsx'
    raw = path.read_bytes()
    newline = b'\r\n' if b'\r\n' in raw else b'\n'
    text = raw.decode().replace('\r\n', '\n')
    start = text.index('                        <h1 className="text-2xl font-black text-white mb-6">', text.index("{(['ko', 'en', 'vi', 'th'] as const).map(lang"))
    end = text.index('                        {/* 탭 전환', start)
    text = text[:start] + '''                        {authMode !== 'login' && <h1 className="text-2xl font-black text-white mb-6">
                            {t('auth_signup_title')}
                        </h1>}

''' + text[end:]
    text = text.replace('<div className="text-center pt-1">\n                                    <button', '<div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-2 pt-1 text-xs font-normal text-gray-400">\n                                    <button', 1)
    anchor = "                                        {t('auth_btn_forgot')}\n                                    </button>"
    assert text.count(anchor) == 1
    text = text.replace(anchor, anchor + '''
                                    <span aria-hidden="true">·</span>
                                    <a href="/terms" target="_blank" rel="noreferrer" className="text-xs text-gray-400 hover:text-blue-400 transition underline underline-offset-2">
                                        서비스 이용약관
                                    </a>
                                    <span aria-hidden="true">·</span>
                                    <a href="/privacy" target="_blank" rel="noreferrer" className="text-xs text-gray-400 hover:text-blue-400 transition underline underline-offset-2">
                                        개인정보처리방침
                                    </a>''', 1)
    path.write_bytes(text.replace('\n', newline.decode()).encode())
    path = root / 'auth-web/lib/i18n.ts'
    data = path.read_bytes()
    assert "auth_btn_forgot: '비밀번호를 잊으셨나요?'".encode() in data
    path.write_bytes(data.replace("auth_btn_forgot: '비밀번호를 잊으셨나요?'".encode(), "auth_btn_forgot: '비밀번호찾기'".encode(), 1))
