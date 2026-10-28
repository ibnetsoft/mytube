from pathlib import Path
for root in [Path.cwd(),Path(Path('_dev/artifacts/project_completion_release_root.txt').read_text().strip())]:
    path=root/'auth-web/app/std/page.tsx'
    data=path.read_bytes()
    start=data.index(b"        if (subtitleTextSaveTimerRef.current",data.index(b'    const openProjectAfterSave'))
    end=data.index(b'        setProjectLoading(true)',start)
    data=data[:start]+data[end:]
    def change(old,new):
        global data
        a,b=old.encode(),new.encode()
        if a not in data:a,b=a.replace(b'\n',b'\r\n'),b.replace(b'\n',b'\r\n')
        assert a in data,old[:60]
        data=data.replace(a,b,1)
    change('    const navigationConfigRef = useRef(','''    const navigationBusyPanelRef = useRef<HTMLDivElement | null>(null)
    useEffect(() => {
        if (!subtitleNavigationBusy) return
        const previous = document.activeElement as HTMLElement | null
        navigationBusyPanelRef.current?.focus()
        return () => { if (previous?.isConnected) previous.focus() }
    }, [subtitleNavigationBusy])
    const navigationConfigRef = useRef(''')
    change('role="status" aria-live="polite" aria-busy="true">\n                <div className="rounded-xl', 'role="dialog" aria-modal="true" aria-label={ui(\'변경사항 저장 중\')} aria-busy="true" tabIndex={-1} ref={navigationBusyPanelRef} onKeyDown={event => { if (event.key === \'Tab\') event.preventDefault() }}>\n                <div role="status" aria-live="polite" className="rounded-xl')
    path.write_bytes(data)
