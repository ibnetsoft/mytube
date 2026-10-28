from pathlib import Path
roots=[Path.cwd(),Path(Path('_dev/artifacts/project_completion_release_root.txt').read_text().strip())]
def replace(path,old,new):
    data=path.read_bytes();a,b=old.encode(),new.encode()
    if a not in data:a,b=a.replace(b'\n',b'\r\n'),b.replace(b'\n',b'\r\n')
    assert a in data,old[:80]
    path.write_bytes(data.replace(a,b,1))
for root in roots:
    p=root/'auth-web/app/std/page.tsx'
    replace(p,"import { restoreSavedSubtitleSnapshot }", "import { createSaveBeforeNavigationGuard } from '@/lib/stdSaveBeforeNavigation'\nimport { restoreSavedSubtitleSnapshot }")
    replace(p,'    const [currentNav, setCurrentNav] = useState<StdNavKey>', '''    const navigationConfigRef = useRef({ needsSave: () => false, save: async (): Promise<boolean> => true, onError: (_error: unknown) => {} })
    const guardedNavigation = useMemo(() => createSaveBeforeNavigationGuard({
        needsSave: () => navigationConfigRef.current.needsSave(),
        save: () => navigationConfigRef.current.save(),
        onError: error => navigationConfigRef.current.onError(error),
    }), [])
    const [currentNav, setCurrentNavRaw] = useState<StdNavKey>''')
    replace(p,"    const [isSubtitleSaved,", "    const setCurrentNav = (next: StdNavKey) => { void guardedNavigation(() => setCurrentNavRaw(next)) }\n    const [isSubtitleSaved,")
    replace(p,"const [subtitleSaveState, setSubtitleSaveState] = useState", "const [subtitleSaveState, setSubtitleSaveStateRaw] = useState")
    replace(p,"    const subtitleSaveRevisionRef = useRef(0)", "    const subtitleSaveStateRef = useRef(subtitleSaveState)\n    const setSubtitleSaveState = (next: typeof subtitleSaveState) => { subtitleSaveStateRef.current = next; setSubtitleSaveStateRaw(next) }\n    const subtitleSaveRevisionRef = useRef(0)")
    # Read pending status synchronously at click time, not from an older render.
    marker='    const openProject = async (projectId: string, overrideToken?: string, overrideImpEmail?: string, forceRefresh = false): Promise<SelectedProjectPayload | null> => {'
    replace(p,marker,'''    navigationConfigRef.current = {
        needsSave: () => Boolean(selectedProject?.project?.id && (subtitleTextSaveTimerRef.current || subtitleStyleSaveTimerRef.current || ['dirty', 'saving', 'error'].includes(subtitleSaveStateRef.current))),
        save: () => handleSaveSubtitles(false),
        onError: error => {
            const detail = error instanceof Error ? error.message : '변경사항을 저장하지 못했습니다.'
            setMessage(`저장에 실패해 현재 화면에 머물렀습니다. ${detail}`)
            setTtsNotice({ projectId: selectedProject?.project?.id || '', projectTitle: getProjectSyncedTitle(selectedProject) || '프로젝트', kind: 'subtitles', phase: 'error', detail: `저장에 실패해 이동하지 않았습니다. ${detail}` })
        },
    }
    const openProject = async (projectId: string, overrideToken?: string, overrideImpEmail?: string, forceRefresh = false): Promise<SelectedProjectPayload | null> => {
        let opened: SelectedProjectPayload | null = null
        await guardedNavigation(async () => { opened = await openProjectAfterSave(projectId, overrideToken, overrideImpEmail, forceRefresh) })
        return opened
    }
    const openProjectAfterSave = async (projectId: string, overrideToken?: string, overrideImpEmail?: string, forceRefresh = false): Promise<SelectedProjectPayload | null> => {''')
    replace(p,'    const signOut = async () => {','    const signOut = async () => { await guardedNavigation(signOutAfterSave) }\n    const signOutAfterSave = async () => {')
    # The dashboard buttons use full-page navigation rather than the internal tab setter.
    for _ in range(2):
        replace(p,"onClick={() => window.location.href = '/dashboard'}", "onClick={() => { void guardedNavigation(() => { window.location.assign('/dashboard') }) }}")
    # Capture ordinary links before router/default navigation, but leave new tabs and downloads alone.
    replace(p,"    const [isSubtitleSaved,", '''    useEffect(() => {
        const followLink = (event: MouseEvent) => {
            if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
            const anchor = (event.target as Element)?.closest?.('a[href]') as HTMLAnchorElement | null
            if (!anchor || anchor.hasAttribute('download') || (anchor.target && anchor.target !== '_self')) return
            const url = new URL(anchor.href, window.location.href)
            if (!['http:', 'https:'].includes(url.protocol) || url.href === window.location.href || (url.origin === window.location.origin && url.pathname === window.location.pathname && url.search === window.location.search)) return
            if (!navigationConfigRef.current.needsSave()) return
            event.preventDefault(); event.stopPropagation()
            void guardedNavigation(() => { window.location.assign(url.href) })
        }
        document.addEventListener('click', followLink, true)
        return () => document.removeEventListener('click', followLink, true)
    }, [guardedNavigation])
    const [isSubtitleSaved,''')
