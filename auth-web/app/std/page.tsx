'use client'

import { useEffect, useMemo, useState } from 'react'
import {
    CheckCircle2,
    Clock,
    FileText,
    FolderKanban,
    Grid,
    HelpCircle,
    Image as ImageIcon,
    Layers,
    LogOut,
    Mic,
    Play,
    RefreshCw,
    Sparkles,
    Upload,
    Video
} from 'lucide-react'
import { supabase } from '@/lib/supabaseClient'
import { isStdRequiredVideoScene, STD_REQUIRED_VIDEO_SCENE_COUNT } from '@/lib/stdPolicy'

type Topic = {
    id: number
    topic: string
    category_name: string
    language: string
    assigned_duration_minutes: number | null
    estimated_payout: number | null
    scene_count: number
    created_at?: string
}

type StdProject = {
    id: string
    title: string
    status: string
    language: string
    assigned_duration_minutes: number | null
    estimated_payout: number | null
    drive_folder_id?: string | null
    progress_payload?: any
    created_at?: string
}

type SelectedProjectPayload = {
    project: StdProject & { project_payload?: any; review_notes?: string | null; reviewed_at?: string | null }
    scenes: any[]
    assets: any[]
}

const statusBadgeStyle: Record<string, { label: string; bg: string; text: string; border: string }> = {
    claimed: { label: '주제 선택됨', bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/20' },
    in_progress: { label: '작업 진행중', bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/20' },
    assets_submitted: { label: '에셋 제출완료', bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/20' },
    review_requested: { label: '렌더 큐 대기', bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/20' },
    approved: { label: '최종 승인', bg: 'bg-green-500/10', text: 'text-green-400', border: 'border-green-500/20' },
    revision_requested: { label: '수정 요청', bg: 'bg-orange-500/10', text: 'text-orange-400', border: 'border-orange-500/20' },
    rejected: { label: '반려됨', bg: 'bg-rose-500/10', text: 'text-rose-400', border: 'border-rose-500/20' },
    canceled: { label: '취소됨', bg: 'bg-gray-500/10', text: 'text-gray-400', border: 'border-gray-500/20' },
}

function assetLink(asset: any): string {
    return asset?.metadata?.web_view_link || `https://drive.google.com/file/d/${asset.drive_file_id}/view`
}

function imageGridPromptsFor(project: StdProject & { project_payload?: any }): any[] {
    const payload = project?.project_payload || {}
    const structure = payload.structure || {}
    const grids = Array.isArray(payload.image_grid_prompts)
        ? payload.image_grid_prompts
        : Array.isArray(structure.image_grid_prompts)
            ? structure.image_grid_prompts
            : []
    return grids
        .map((grid: any, index: number) => ({
            grid_number: grid?.grid_number || index + 1,
            scene_numbers: Array.isArray(grid?.scene_numbers) ? grid.scene_numbers : [],
            prompt: String(grid?.prompt || grid?.grid_prompt || '').trim(),
        }))
        .filter((grid: any) => grid.prompt && grid.scene_numbers.length === 4)
}

export default function StdPortalPage() {
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [token, setToken] = useState('')
    const [user, setUser] = useState<any>(null)
    const [topics, setTopics] = useState<Topic[]>([])
    const [projects, setProjects] = useState<StdProject[]>([])
    const [selectedProject, setSelectedProject] = useState<SelectedProjectPayload | null>(null)
    const [authChecking, setAuthChecking] = useState(true)
    const [loading, setLoading] = useState(false)
    const [projectLoading, setProjectLoading] = useState(false)
    const [uploadingKey, setUploadingKey] = useState('')
    const [generatingTts, setGeneratingTts] = useState(false)
    const [message, setMessage] = useState('')
    const [activeTab, setActiveTab] = useState<'scenes' | 'script' | 'grids' | 'tts'>('scenes')
    const [sidebarView, setSidebarView] = useState<'projects' | 'topics'>('projects')

    const authedJsonHeaders = useMemo(() => ({
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
    }), [token])

    const safeParseJson = async (res: Response, fallbackErrMsg: string) => {
        const text = await res.text()
        try {
            return JSON.parse(text)
        } catch {
            if (res.status === 401) throw new Error('로그인 세션이 만료되었습니다. 다시 로그인해주세요.')
            if (res.status === 403) throw new Error('STD 작업자 권한 승인 대기 중인 계정입니다. 관리자 승인을 기다려주세요.')
            throw new Error(fallbackErrMsg || `서버 에러 (${res.status})`)
        }
    }

    const loadStdData = async (accessToken: string, options: { showLoading?: boolean } = {}) => {
        const showLoading = options.showLoading !== false
        if (showLoading) setLoading(true)
        setMessage('')
        try {
            const headers = { Authorization: `Bearer ${accessToken}` }
            const [meRes, topicsRes, projectsRes] = await Promise.all([
                fetch('/api/std/me', { headers }),
                fetch('/api/std/topics', { headers }),
                fetch('/api/std/projects', { headers }),
            ])

            const me = await safeParseJson(meRes, 'STD 계정 프로필 조회 실패')
            const topicPayload = await safeParseJson(topicsRes, '주제 목록 조회 실패')
            const projectPayload = await safeParseJson(projectsRes, '작업 목록 조회 실패')

            if (!meRes.ok) throw new Error(me.error || 'STD 계정 확인 실패')
            setUser(me.user)
            setTopics(topicPayload.topics || [])
            const loadedProjects = projectPayload.projects || []
            setProjects(loadedProjects)

            // 만약 선택된 프로젝트가 없는데 작업 목록이 있다면 첫번째 자동 선택
            if (loadedProjects.length > 0 && !selectedProject) {
                await openProject(loadedProjects[0].id, accessToken)
            }
        } catch (error: any) {
            setMessage(error.message || '데이터를 불러오지 못했습니다.')
        } finally {
            if (showLoading) setLoading(false)
        }
    }

    useEffect(() => {
        supabase.auth.getSession()
            .then(async ({ data }) => {
                const accessToken = data.session?.access_token
                if (accessToken) {
                    setToken(accessToken)
                    await loadStdData(accessToken)
                }
            })
            .catch(() => {})
            .finally(() => setAuthChecking(false))
    }, [])

    const signIn = async () => {
        setLoading(true)
        setMessage('')
        try {
            const { data, error } = await supabase.auth.signInWithPassword({ email, password })
            if (error) throw error
            const accessToken = data.session?.access_token
            if (!accessToken) throw new Error('세션을 생성하지 못했습니다.')
            setToken(accessToken)
            await loadStdData(accessToken)
        } catch (error: any) {
            setMessage(error.message || '로그인 실패')
        } finally {
            setLoading(false)
        }
    }

    const signOut = async () => {
        await supabase.auth.signOut()
        setToken('')
        setUser(null)
        setSelectedProject(null)
        setProjects([])
        setTopics([])
    }

    const claimTopic = async (topicId: number) => {
        setLoading(true)
        setMessage('')
        try {
            const res = await fetch(`/api/std/topics/${topicId}/claim`, {
                method: 'POST',
                headers: authedJsonHeaders,
            })
            const payload = await safeParseJson(res, '주제 선택 실패')
            if (!res.ok) throw new Error(payload.error || '주제 선택 실패')
            setMessage('새 작업이 성공적으로 생성되었습니다!')
            setSidebarView('projects')
            await loadStdData(token)
        } catch (error: any) {
            setMessage(error.message || '주제 선택 실패')
        } finally {
            setLoading(false)
        }
    }

    const openProject = async (projectId: string, overrideToken?: string) => {
        setProjectLoading(true)
        setMessage('')
        try {
            const res = await fetch(`/api/std/projects/${projectId}`, {
                headers: { Authorization: `Bearer ${overrideToken || token}` },
            })
            const payload = await safeParseJson(res, '작업 조회 실패')
            if (!res.ok) throw new Error(payload.error || '작업 조회 실패')
            setSelectedProject(payload)
        } catch (error: any) {
            setMessage(error.message || '작업 상세 조회 실패')
        } finally {
            setProjectLoading(false)
        }
    }

    const reloadSelectedProject = async (options: { refreshLists?: boolean } = {}) => {
        if (!selectedProject?.project?.id) return
        await openProject(selectedProject.project.id)
        if (options.refreshLists) await loadStdData(token, { showLoading: false })
    }

    const uploadAsset = async (scene: any, assetType: 'image' | 'video', file: File | null) => {
        if (!file || !selectedProject) return
        const key = `${scene.scene_number}-${assetType}`
        setUploadingKey(key)
        setMessage('')
        try {
            const initRes = await fetch(`/api/std/projects/${selectedProject.project.id}/assets/init`, {
                method: 'POST',
                headers: authedJsonHeaders,
                body: JSON.stringify({
                    scene_number: scene.scene_number,
                    asset_type: assetType,
                    file_name: file.name,
                    mime_type: file.type || (assetType === 'image' ? 'image/png' : 'video/mp4'),
                    file_size: file.size,
                }),
            })
            const initPayload = await safeParseJson(initRes, 'Drive 업로드 준비 실패')
            if (!initRes.ok) throw new Error(initPayload.error || 'Drive 업로드 준비 실패')

            const uploadRes = await fetch(initPayload.upload_url, {
                method: 'PUT',
                headers: { 'Content-Type': file.type || initPayload.mime_type || 'application/octet-stream' },
                body: file,
            })
            const uploaded = await uploadRes.json().catch(() => ({}))
            if (!uploadRes.ok || !uploaded.id) {
                throw new Error(uploaded.error?.message || 'Google Drive 업로드 실패')
            }

            const completeRes = await fetch(`/api/std/projects/${selectedProject.project.id}/assets/complete`, {
                method: 'POST',
                headers: authedJsonHeaders,
                body: JSON.stringify({
                    scene_number: scene.scene_number,
                    asset_type: assetType,
                    drive_file_id: uploaded.id,
                    target_folder_id: initPayload.target_folder_id,
                    file_name: file.name,
                    mime_type: file.type,
                    file_size: file.size,
                }),
            })
            const completePayload = await safeParseJson(completeRes, '업로드 등록 실패')
            if (!completeRes.ok) throw new Error(completePayload.error || '업로드 등록 실패')

            setMessage(`Scene ${scene.scene_number} ${assetType === 'image' ? '이미지' : '영상'} 등록 완료!`)
            await reloadSelectedProject()
        } catch (error: any) {
            setMessage(error.message || '업로드 실패')
        } finally {
            setUploadingKey('')
        }
    }

    const submitProject = async () => {
        if (!selectedProject) return
        if (!confirm('에셋 검증 및 렌더 큐 제출을 진행하시겠습니까? 제출 후 원격 렌더링이 시작됩니다.')) return
        setLoading(true)
        setMessage('')
        try {
            const res = await fetch(`/api/std/projects/${selectedProject.project.id}/submit`, {
                method: 'POST',
                headers: authedJsonHeaders,
            })
            const payload = await safeParseJson(res, '제출 실패')
            if (!res.ok) {
                const missing = payload.missing_scene_numbers?.length
                    ? ` (누락 씬: ${payload.missing_scene_numbers.join(', ')}번)`
                    : ''
                throw new Error((payload.error || '제출 실패') + missing)
            }
            setMessage('✅ 원격 렌더 큐에 성공적으로 등록되었습니다!')
            await reloadSelectedProject({ refreshLists: true })
        } catch (error: any) {
            setMessage(error.message || '제출 실패')
        } finally {
            setLoading(false)
        }
    }

    const generateTts = async () => {
        if (!selectedProject) return
        setGeneratingTts(true)
        setMessage('')
        try {
            const res = await fetch(`/api/std/projects/${selectedProject.project.id}/tts/generate`, {
                method: 'POST',
                headers: authedJsonHeaders,
                body: JSON.stringify({ provider: 'elevenlabs' }),
            })
            const payload = await safeParseJson(res, 'TTS 생성 실패')
            if (!res.ok) throw new Error(payload.error || 'TTS 생성 실패')
            setMessage('🔊 TTS 오디오가 생성되어 Drive에 저장되었습니다!')
            await reloadSelectedProject()
        } catch (error: any) {
            setMessage(error.message || 'TTS 생성 실패')
        } finally {
            setGeneratingTts(false)
        }
    }

    const assetsByScene = useMemo(() => {
        const map = new Map<string, any[]>()
        for (const asset of selectedProject?.assets || []) {
            const key = String(asset.scene_number || '')
            map.set(key, [...(map.get(key) || []), asset])
        }
        return map
    }, [selectedProject])

    const audioAssets = useMemo(() => (
        (selectedProject?.assets || []).filter((asset: any) => asset.asset_type === 'audio' && ['uploaded', 'assigned'].includes(asset.status))
    ), [selectedProject])

    const imageGridPrompts = useMemo(
        () => selectedProject ? imageGridPromptsFor(selectedProject.project) : [],
        [selectedProject]
    )

    // 로딩 화면
    if (authChecking) {
        return (
            <main className="min-h-screen bg-[#1c2027] text-gray-100 flex items-center justify-center">
                <div className="flex flex-col items-center gap-3">
                    <div className="w-8 h-8 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
                    <p className="text-xs font-bold tracking-widest text-blue-400 uppercase">AIR STUDIO Loading...</p>
                </div>
            </main>
        )
    }

    // 로그인 화면 (유저앱 시그니처 다크 테마 완벽 일치)
    if (!token) {
        return (
            <main className="min-h-screen bg-[#1c2027] text-gray-100 flex items-center justify-center px-4">
                <section className="w-full max-w-md bg-[#13171e] border border-white/10 p-8 rounded-2xl shadow-2xl flex flex-col gap-6">
                    <div className="flex flex-col items-center text-center gap-2">
                        <div className="flex items-center gap-2">
                            <span className="w-3 h-3 rounded-full bg-blue-500 animate-pulse" />
                            <h1 className="text-2xl font-black tracking-wider text-blue-400">AIR STUDIO</h1>
                        </div>
                        <span className="text-[10px] font-black uppercase px-2.5 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                            STD WORKER WEB PORTAL
                        </span>
                        <p className="text-xs text-gray-400 mt-1">
                            설치형 유저앱과 100% 동일한 STD 전용 웹 작업 환경입니다.
                        </p>
                    </div>

                    <form onSubmit={(e) => { e.preventDefault(); signIn() }} className="flex flex-col gap-4">
                        <div>
                            <label className="text-[11px] font-bold text-gray-400 mb-1 block">이메일 계정</label>
                            <input
                                value={email}
                                onChange={e => setEmail(e.target.value)}
                                className="w-full bg-[#1c2027] border border-white/10 px-3.5 py-2.5 rounded-xl text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 transition-all"
                                placeholder="name@example.com"
                                autoFocus
                            />
                        </div>
                        <div>
                            <label className="text-[11px] font-bold text-gray-400 mb-1 block">비밀번호</label>
                            <input
                                value={password}
                                onChange={e => setPassword(e.target.value)}
                                type="password"
                                className="w-full bg-[#1c2027] border border-white/10 px-3.5 py-2.5 rounded-xl text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 transition-all"
                                placeholder="••••••••"
                            />
                        </div>

                        {message && (
                            <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-xs text-red-400 leading-relaxed">
                                {message}
                            </div>
                        )}

                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 rounded-xl transition-all shadow-lg shadow-blue-600/30 disabled:opacity-50 mt-2 text-sm"
                        >
                            {loading ? '로그인 확인 중...' : 'STD 작업 포털 로그인'}
                        </button>
                    </form>

                    <div className="text-center text-[11px] text-gray-500 border-t border-white/5 pt-4">
                        계정이 없으신가요? <a href="/" className="text-blue-400 hover:underline font-bold">메인 화면에서 회원가입</a>
                    </div>
                </section>
            </main>
        )
    }

    // 메인 작업 화면 (설치형 유저앱 1:1 완벽 일치 구조)
    return (
        <div className="min-h-screen bg-[#1c2027] text-gray-100 flex flex-col font-sans">
            {/* 상단 통합 헤더 */}
            <header className="h-14 bg-[#13171e] border-b border-white/10 px-4 flex items-center justify-between shrink-0 z-30">
                <div className="flex items-center gap-3">
                    <span className="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse" />
                    <span className="font-black text-sm tracking-wider text-blue-400">AIR STUDIO</span>
                    <span className="text-[10px] font-black uppercase px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                        STD MODE
                    </span>
                </div>

                <div className="flex items-center gap-3">
                    {message && (
                        <span className="text-xs px-3 py-1 bg-blue-500/10 border border-blue-500/20 text-blue-300 rounded-lg animate-fade-in truncate max-w-md">
                            {message}
                        </span>
                    )}
                    <button
                        onClick={() => loadStdData(token)}
                        disabled={loading}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#1c2027] hover:bg-[#252b36] border border-white/10 rounded-lg text-xs font-bold text-gray-300 transition-all"
                    >
                        <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
                        새로고침
                    </button>
                    <div className="h-4 w-px bg-white/10" />
                    <div className="text-right hidden sm:block">
                        <div className="text-xs font-bold text-white">{user?.full_name || 'STD 작업자'}</div>
                        <div className="text-[10px] text-gray-400 truncate max-w-[150px]">{user?.email}</div>
                    </div>
                    <button
                        onClick={signOut}
                        className="p-2 hover:bg-red-500/10 text-gray-400 hover:text-red-400 rounded-lg transition-all"
                        title="로그아웃"
                    >
                        <LogOut className="h-4 w-4" />
                    </button>
                </div>
            </header>

            {/* 메인 2열 레이아웃 (사이드바 + 워크스페이스) */}
            <div className="flex-1 flex overflow-hidden">
                {/* 좌측 사이드바 (유저앱 사이드바 1:1 완벽 일치) */}
                <aside className="w-80 bg-[#13171e] border-r border-white/10 flex flex-col shrink-0">
                    {/* 상단 탭 전환: [내 작업 목록] vs [새 주제 탐색] */}
                    <div className="p-3 border-b border-white/10 grid grid-cols-2 gap-1.5 bg-[#0e1218]">
                        <button
                            onClick={() => setSidebarView('projects')}
                            className={`py-2 px-3 rounded-lg text-xs font-bold flex items-center justify-center gap-1.5 transition-all ${
                                sidebarView === 'projects'
                                    ? 'bg-blue-600 text-white shadow-md shadow-blue-600/30'
                                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                            }`}
                        >
                            <FolderKanban className="h-3.5 w-3.5" />
                            내 작업 ({projects.length})
                        </button>
                        <button
                            onClick={() => setSidebarView('topics')}
                            className={`py-2 px-3 rounded-lg text-xs font-bold flex items-center justify-center gap-1.5 transition-all ${
                                sidebarView === 'topics'
                                    ? 'bg-blue-600 text-white shadow-md shadow-blue-600/30'
                                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                            }`}
                        >
                            <Sparkles className="h-3.5 w-3.5" />
                            주제 선택 ({topics.length})
                        </button>
                    </div>

                    {/* 사이드바 목록 스크롤 영역 */}
                    <div className="flex-1 overflow-y-auto p-3 space-y-2.5 custom-scrollbar">
                        {sidebarView === 'projects' ? (
                            projects.length > 0 ? (
                                projects.map(proj => {
                                    const isSelected = selectedProject?.project?.id === proj.id
                                    const badge = statusBadgeStyle[proj.status] || { label: proj.status, bg: 'bg-gray-500/10', text: 'text-gray-400', border: 'border-gray-500/20' }
                                    return (
                                        <button
                                            key={proj.id}
                                            disabled={projectLoading}
                                            onClick={() => openProject(proj.id)}
                                            className={`w-full text-left p-3.5 rounded-xl border transition-all flex flex-col gap-2 ${
                                                isSelected
                                                    ? 'bg-blue-500/10 border-blue-500/50 shadow-lg shadow-blue-500/10'
                                                    : 'bg-[#1c2027] border-white/5 hover:border-white/20'
                                            }`}
                                        >
                                            <div className="font-bold text-xs text-white line-clamp-2 leading-relaxed">
                                                {proj.title}
                                            </div>
                                            <div className="flex items-center justify-between text-[10px]">
                                                <span className={`px-2 py-0.5 rounded-md font-bold border ${badge.bg} ${badge.text} ${badge.border}`}>
                                                    {badge.label}
                                                </span>
                                                <span className="text-gray-400 flex items-center gap-1">
                                                    <Clock className="h-3 w-3" />
                                                    {proj.assigned_duration_minutes || 10}분
                                                </span>
                                            </div>
                                        </button>
                                    )
                                })
                            ) : (
                                <div className="p-8 text-center text-xs text-gray-500 flex flex-col items-center gap-2">
                                    <FolderKanban className="h-8 w-8 text-gray-600" />
                                    <span>진행 중인 작업이 없습니다.</span>
                                    <button
                                        onClick={() => setSidebarView('topics')}
                                        className="mt-2 text-blue-400 font-bold hover:underline"
                                    >
                                        새 주제 선택하러 가기 ➔
                                    </button>
                                </div>
                            )
                        ) : (
                            topics.length > 0 ? (
                                topics.map(topic => (
                                    <div
                                        key={topic.id}
                                        className="p-3.5 bg-[#1c2027] border border-white/5 rounded-xl hover:border-white/20 transition-all flex flex-col gap-2.5"
                                    >
                                        <div className="font-bold text-xs text-white leading-relaxed">
                                            {topic.topic}
                                        </div>
                                        <div className="flex items-center gap-2 text-[10px] text-gray-400">
                                            <span className="bg-white/5 px-2 py-0.5 rounded border border-white/5 text-gray-300">
                                                {topic.category_name || '일반'}
                                            </span>
                                            <span>· {topic.scene_count} 씬</span>
                                            <span>· {topic.assigned_duration_minutes || 10}분</span>
                                        </div>
                                        <button
                                            disabled={loading}
                                            onClick={() => claimTopic(topic.id)}
                                            className="w-full mt-1 bg-blue-600/80 hover:bg-blue-600 text-white py-1.5 rounded-lg text-xs font-bold transition-all shadow-md shadow-blue-600/20 disabled:opacity-50"
                                        >
                                            작업 가져오기 (Claim)
                                        </button>
                                    </div>
                                ))
                            ) : (
                                <div className="p-8 text-center text-xs text-gray-500 flex flex-col items-center gap-2">
                                    <HelpCircle className="h-8 w-8 text-gray-600" />
                                    <span>선택 가능한 준비된 주제가 없습니다.</span>
                                    <span className="text-[10px] text-gray-600">워커(Hermes)가 주제를 발굴 중입니다.</span>
                                </div>
                            )
                        )}
                    </div>
                </aside>

                {/* 우측 메인 작업 영역 */}
                <main className="flex-1 flex flex-col overflow-hidden bg-[#181c24]">
                    {!selectedProject ? (
                        <div className="flex-1 flex flex-col items-center justify-center text-center p-8">
                            <div className="w-16 h-16 rounded-2xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400 mb-4 shadow-xl">
                                <Layers className="h-8 w-8" />
                            </div>
                            <h2 className="text-base font-bold text-white">작업을 선택해주세요</h2>
                            <p className="text-xs text-gray-400 mt-1 max-w-sm">
                                좌측 사이드바에서 진행할 프로젝트를 선택하거나, 새로운 주제를 가져와 작업을 시작하세요.
                            </p>
                        </div>
                    ) : (
                        <>
                            {/* 프로젝트 상단 헤더 & 컨트롤 바 */}
                            <div className="p-4 bg-[#13171e] border-b border-white/10 flex flex-col md:flex-row md:items-center md:justify-between gap-4 shrink-0">
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                        <h2 className="text-base font-black text-white truncate">
                                            {selectedProject.project.title}
                                        </h2>
                                        {statusBadgeStyle[selectedProject.project.status] && (
                                            <span className={`text-[10px] font-black px-2.5 py-0.5 rounded-full border shrink-0 ${statusBadgeStyle[selectedProject.project.status].bg} ${statusBadgeStyle[selectedProject.project.status].text} ${statusBadgeStyle[selectedProject.project.status].border}`}>
                                                {statusBadgeStyle[selectedProject.project.status].label}
                                            </span>
                                        )}
                                    </div>
                                    <div className="text-[11px] text-gray-400 mt-1 flex items-center gap-3">
                                        <span>총 {selectedProject.scenes.length}개 씬</span>
                                        <span>· 배정 시간: {selectedProject.project.assigned_duration_minutes || 10}분</span>
                                        <span>· 언어: {selectedProject.project.language || 'ko'}</span>
                                    </div>
                                </div>

                                <div className="flex items-center gap-2.5 shrink-0">
                                    <button
                                        onClick={generateTts}
                                        disabled={generatingTts || loading || selectedProject.project.status === 'review_requested'}
                                        className="px-3.5 py-2 bg-[#1c2027] hover:bg-[#252b36] border border-white/10 rounded-xl text-xs font-bold text-white flex items-center gap-2 transition-all shadow-md disabled:opacity-50"
                                    >
                                        <Mic className={`h-4 w-4 text-blue-400 ${generatingTts ? 'animate-bounce' : ''}`} />
                                        {generatingTts ? 'TTS 생성 중...' : 'TTS 음성 생성'}
                                    </button>

                                    <button
                                        onClick={submitProject}
                                        disabled={loading || selectedProject.project.status === 'review_requested'}
                                        className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-black flex items-center gap-2 transition-all shadow-lg shadow-emerald-600/30 disabled:opacity-50"
                                    >
                                        <CheckCircle2 className="h-4 w-4" />
                                        {selectedProject.project.status === 'review_requested' ? '렌더 큐 접수됨' : '원격 렌더 큐 제출'}
                                    </button>
                                </div>
                            </div>

                            {/* 검수 메모 경고창 */}
                            {selectedProject.project.review_notes && (
                                <div className="px-4 py-2.5 bg-orange-500/10 border-b border-orange-500/20 flex items-start gap-2.5 text-xs text-orange-300">
                                    <span className="font-bold shrink-0">⚠️ 관리자 검수 피드백:</span>
                                    <span className="whitespace-pre-wrap">{selectedProject.project.review_notes}</span>
                                </div>
                            )}

                            {/* 작업 탭 바 */}
                            <div className="px-4 border-b border-white/10 bg-[#13171e] flex gap-4 text-xs font-bold shrink-0">
                                <button
                                    onClick={() => setActiveTab('scenes')}
                                    className={`py-3 flex items-center gap-1.5 border-b-2 transition-all ${
                                        activeTab === 'scenes'
                                            ? 'border-blue-500 text-blue-400'
                                            : 'border-transparent text-gray-400 hover:text-white'
                                    }`}
                                >
                                    <Layers className="h-3.5 w-3.5" />
                                    🎬 씬 에셋 작업 ({selectedProject.scenes.length})
                                </button>
                                <button
                                    onClick={() => setActiveTab('script')}
                                    className={`py-3 flex items-center gap-1.5 border-b-2 transition-all ${
                                        activeTab === 'script'
                                            ? 'border-blue-500 text-blue-400'
                                            : 'border-transparent text-gray-400 hover:text-white'
                                    }`}
                                >
                                    <FileText className="h-3.5 w-3.5" />
                                    📝 대본 본문
                                </button>
                                <button
                                    onClick={() => setActiveTab('grids')}
                                    className={`py-3 flex items-center gap-1.5 border-b-2 transition-all ${
                                        activeTab === 'grids'
                                            ? 'border-blue-500 text-blue-400'
                                            : 'border-transparent text-gray-400 hover:text-white'
                                    }`}
                                >
                                    <Grid className="h-3.5 w-3.5" />
                                    🎨 2x2 이미지 프롬프트 ({imageGridPrompts.length})
                                </button>
                                <button
                                    onClick={() => setActiveTab('tts')}
                                    className={`py-3 flex items-center gap-1.5 border-b-2 transition-all ${
                                        activeTab === 'tts'
                                            ? 'border-blue-500 text-blue-400'
                                            : 'border-transparent text-gray-400 hover:text-white'
                                    }`}
                                >
                                    <Mic className="h-3.5 w-3.5" />
                                    🔊 TTS 오디오 ({audioAssets.length})
                                </button>
                            </div>

                            {/* 탭 본문 영역 (스크롤 가능) */}
                            <div className="flex-1 overflow-y-auto p-5 custom-scrollbar">
                                {/* 1. 씬 에셋 작업 탭 */}
                                {activeTab === 'scenes' && (
                                    <div className="space-y-4 max-w-5xl mx-auto">
                                        <div className="p-3.5 bg-blue-500/10 border border-blue-500/20 rounded-xl text-xs text-blue-300 flex items-center justify-between">
                                            <span>📌 <strong>1~{STD_REQUIRED_VIDEO_SCENE_COUNT}번 씬</strong>은 반드시 <strong>영상(MP4/WebM)</strong> 파일로 업로드하셔야 제출이 가능합니다.</span>
                                            <span className="text-[11px] text-gray-400">나머지 씬: 이미지 또는 영상</span>
                                        </div>

                                        <div className="grid grid-cols-1 gap-4">
                                            {selectedProject.scenes.map((scene: any) => {
                                                const sceneAssets = assetsByScene.get(String(scene.scene_number)) || []
                                                const isImageUploading = uploadingKey === `${scene.scene_number}-image`
                                                const isVideoUploading = uploadingKey === `${scene.scene_number}-video`
                                                const requiresVideo = isStdRequiredVideoScene(scene.scene_number)
                                                const hasUploaded = sceneAssets.length > 0

                                                return (
                                                    <div
                                                        key={scene.id}
                                                        className={`p-4 bg-[#13171e] border rounded-2xl transition-all flex flex-col md:flex-row gap-4 ${
                                                            hasUploaded
                                                                ? 'border-emerald-500/30 bg-[#13171e]'
                                                                : 'border-white/10'
                                                        }`}
                                                    >
                                                        {/* 좌측: 씬 정보 & 나레이션 */}
                                                        <div className="flex-1 flex flex-col justify-between gap-3">
                                                            <div>
                                                                <div className="flex items-center gap-2">
                                                                    <span className="text-xs font-black text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded-md border border-blue-500/20">
                                                                        SCENE {String(scene.scene_number).padStart(3, '0')}
                                                                    </span>
                                                                    <span className="text-xs font-bold text-white truncate">
                                                                        {scene.scene_title || `Scene ${scene.scene_number}`}
                                                                    </span>
                                                                    {requiresVideo && (
                                                                        <span className="text-[10px] font-black bg-orange-500/10 text-orange-400 px-2 py-0.5 rounded border border-orange-500/20">
                                                                            영상 필수
                                                                        </span>
                                                                    )}
                                                                </div>
                                                                <p className="mt-2.5 text-xs text-gray-300 leading-relaxed bg-[#1c2027] p-3 rounded-xl border border-white/5">
                                                                    {scene.scene_text}
                                                                </p>
                                                            </div>

                                                            {/* 업로드 버튼 그룹 */}
                                                            <div className="flex flex-wrap items-center gap-2 pt-2">
                                                                {!requiresVideo && (
                                                                    <label className="cursor-pointer inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#1c2027] hover:bg-[#252b36] border border-white/10 hover:border-blue-500 rounded-lg text-xs font-bold text-gray-200 transition-all">
                                                                        <ImageIcon className="h-3.5 w-3.5 text-blue-400" />
                                                                        {isImageUploading ? '이미지 업로드 중...' : '이미지 등록'}
                                                                        <input
                                                                            disabled={Boolean(uploadingKey)}
                                                                            type="file"
                                                                            accept="image/*"
                                                                            className="hidden"
                                                                            onChange={e => uploadAsset(scene, 'image', e.target.files?.[0] || null)}
                                                                        />
                                                                    </label>
                                                                )}
                                                                <label className="cursor-pointer inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#1c2027] hover:bg-[#252b36] border border-white/10 hover:border-blue-500 rounded-lg text-xs font-bold text-gray-200 transition-all">
                                                                    <Video className="h-3.5 w-3.5 text-orange-400" />
                                                                    {isVideoUploading ? '영상 업로드 중...' : '비디오 등록'}
                                                                    <input
                                                                        disabled={Boolean(uploadingKey)}
                                                                        type="file"
                                                                        accept="video/*"
                                                                        className="hidden"
                                                                        onChange={e => uploadAsset(scene, 'video', e.target.files?.[0] || null)}
                                                                    />
                                                                </label>
                                                            </div>
                                                        </div>

                                                        {/* 우측: 등록된 에셋 프리뷰 카드 */}
                                                        <div className="w-full md:w-56 shrink-0 bg-[#0e1218] border border-white/5 rounded-xl p-3 flex flex-col justify-center items-center text-center min-h-[140px]">
                                                            {sceneAssets.length > 0 ? (
                                                                <div className="w-full space-y-2">
                                                                    <div className="text-[10px] font-bold text-emerald-400 flex items-center justify-center gap-1">
                                                                        <CheckCircle2 className="h-3.5 w-3.5" />
                                                                        에셋 등록 완료
                                                                    </div>
                                                                    {sceneAssets.map((asset: any) => (
                                                                        <a
                                                                            key={asset.id}
                                                                            href={assetLink(asset)}
                                                                            target="_blank"
                                                                            rel="noreferrer"
                                                                            className="block p-2 bg-[#1c2027] hover:bg-[#252b36] border border-white/10 rounded-lg text-[11px] text-gray-300 truncate text-left transition-all"
                                                                        >
                                                                            <span className="font-bold text-blue-400 uppercase text-[10px] block">
                                                                                [{asset.asset_type}]
                                                                            </span>
                                                                            {asset.file_name}
                                                                        </a>
                                                                    ))}
                                                                </div>
                                                            ) : (
                                                                <div className="text-gray-500 text-xs flex flex-col items-center gap-1">
                                                                    <Upload className="h-5 w-5 text-gray-600 mb-1" />
                                                                    <span>미등록 상태</span>
                                                                    <span className="text-[10px] text-gray-600">파일을 업로드하세요</span>
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>
                                                )
                                            })}
                                        </div>
                                    </div>
                                )}

                                {/* 2. 대본 본문 탭 */}
                                {activeTab === 'script' && (
                                    <div className="max-w-4xl mx-auto bg-[#13171e] border border-white/10 rounded-2xl p-6 shadow-xl">
                                        <div className="flex items-center justify-between border-b border-white/10 pb-4 mb-4">
                                            <h3 className="font-bold text-sm text-white flex items-center gap-2">
                                                <FileText className="h-4 w-4 text-blue-400" />
                                                전체 대본 본문
                                            </h3>
                                        </div>
                                        <pre className="whitespace-pre-wrap font-sans text-xs text-gray-300 leading-relaxed bg-[#1c2027] p-5 rounded-xl border border-white/5 max-h-[600px] overflow-y-auto">
                                            {selectedProject.project.project_payload?.script || selectedProject.scenes.map((s: any) => s.scene_text).join('\n\n') || '대본 내용이 없습니다.'}
                                        </pre>
                                    </div>
                                )}

                                {/* 3. 2x2 이미지 프롬프트 탭 */}
                                {activeTab === 'grids' && (
                                    <div className="max-w-4xl mx-auto space-y-4">
                                        <div className="p-3.5 bg-blue-500/10 border border-blue-500/20 rounded-xl text-xs text-blue-300">
                                            💡 Midjourney 또는 AI 이미지 툴에 바로 복사하여 2x2 분할 이미지를 생성할 수 있는 통합 프롬프트입니다.
                                        </div>
                                        {imageGridPrompts.length > 0 ? (
                                            imageGridPrompts.map((grid: any) => (
                                                <div key={grid.grid_number} className="bg-[#13171e] border border-white/10 rounded-2xl p-5 shadow-xl space-y-3">
                                                    <div className="flex items-center justify-between">
                                                        <span className="text-xs font-black text-blue-400 bg-blue-500/10 px-2.5 py-1 rounded-lg border border-blue-500/20">
                                                            GRID {String(grid.grid_number).padStart(3, '0')} (Scenes {grid.scene_numbers.join(', ')})
                                                        </span>
                                                        <button
                                                            onClick={() => {
                                                                navigator.clipboard.writeText(grid.prompt)
                                                                alert('프롬프트가 클립보드에 복사되었습니다!')
                                                            }}
                                                            className="px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-bold transition-all shadow-md shadow-blue-600/30"
                                                        >
                                                            프롬프트 복사
                                                        </button>
                                                    </div>
                                                    <textarea
                                                        readOnly
                                                        value={grid.prompt}
                                                        className="w-full bg-[#1c2027] border border-white/10 rounded-xl p-3.5 text-xs text-gray-200 min-h-[140px] focus:outline-none"
                                                    />
                                                </div>
                                            ))
                                        ) : (
                                            <div className="p-8 text-center text-xs text-gray-500 bg-[#13171e] border border-white/10 rounded-2xl">
                                                생성된 2x2 이미지 프롬프트가 없습니다.
                                            </div>
                                        )}
                                    </div>
                                )}

                                {/* 4. TTS 오디오 탭 */}
                                {activeTab === 'tts' && (
                                    <div className="max-w-4xl mx-auto bg-[#13171e] border border-white/10 rounded-2xl p-6 shadow-xl space-y-4">
                                        <div className="flex items-center justify-between border-b border-white/10 pb-4">
                                            <h3 className="font-bold text-sm text-white flex items-center gap-2">
                                                <Mic className="h-4 w-4 text-blue-400" />
                                                TTS 음성 파일 관리
                                            </h3>
                                        </div>

                                        {audioAssets.length > 0 ? (
                                            <div className="space-y-3">
                                                {audioAssets.map((asset: any) => (
                                                    <div key={asset.id} className="p-4 bg-[#1c2027] border border-white/5 rounded-xl flex items-center justify-between">
                                                        <div className="flex items-center gap-3">
                                                            <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
                                                                <Play className="h-5 w-5 fill-current" />
                                                            </div>
                                                            <div>
                                                                <div className="font-bold text-xs text-white">{asset.file_name}</div>
                                                                <div className="text-[10px] text-gray-400">{asset.mime_type || 'audio/mpeg'}</div>
                                                            </div>
                                                        </div>
                                                        <a
                                                            href={assetLink(asset)}
                                                            target="_blank"
                                                            rel="noreferrer"
                                                            className="px-3.5 py-1.5 bg-[#252b36] hover:bg-[#323946] border border-white/10 rounded-lg text-xs font-bold text-gray-200 transition-all"
                                                        >
                                                            Drive에서 듣기 / 다운로드
                                                        </a>
                                                    </div>
                                                ))}
                                            </div>
                                        ) : (
                                            <div className="p-8 text-center text-xs text-gray-500 bg-[#1c2027] border border-white/5 rounded-xl">
                                                아직 생성된 TTS 음성 파일이 없습니다. 상단의 <strong>[TTS 음성 생성]</strong> 버튼을 눌러주세요.
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        </>
                    )}
                </main>
            </div>
        </div>
    )
}
