from pathlib import Path
for root in [Path.cwd(),Path(Path('_dev/artifacts/project_completion_release_root.txt').read_text().strip())]:
    path=root/'auth-web/app/std/page.tsx'
    data=path.read_bytes()
    def change(old,new):
        global data
        a,b=old.encode(),new.encode()
        if a not in data:a,b=a.replace(b'\n',b'\r\n'),b.replace(b'\n',b'\r\n')
        assert a in data,old[:60]
        data=data.replace(a,b,1)
    change('    const navigationConfigRef = useRef(', '    const [subtitleNavigationBusy, setSubtitleNavigationBusy] = useState(false)\n    const navigationConfigRef = useRef(')
    change('        onError: error => navigationConfigRef.current.onError(error),', '        onError: error => navigationConfigRef.current.onError(error),\n        onBusy: setSubtitleNavigationBusy,')
    change('            <StdTtsNotice notice={ttsNotice}', '''            {subtitleNavigationBusy && <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60" role="status" aria-live="polite" aria-busy="true">
                <div className="rounded-xl border border-white/20 bg-[#1c2027] p-6 text-sm text-white">{ui('변경사항을 저장한 뒤 이동합니다. 잠시 기다려 주세요.')}</div>
            </div>}
            <StdTtsNotice notice={ttsNotice}''')
    path.write_bytes(data)
