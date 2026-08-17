'use client'

import { useEffect, useMemo, useState } from 'react'
import {
    CheckCircle2,
    Clock,
    Copy,
    Download,
    ExternalLink,
    FileText,
    FolderKanban,
    Grid,
    HelpCircle,
    Image as ImageIcon,
    Layers,
    LayoutTemplate,
    LogOut,
    Mic,
    Play,
    RefreshCw,
    Settings as SettingsIcon,
    Sliders,
    Sparkles,
    Type,
    Upload,
    Video,
    Volume2
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

    // 유저앱 전체 메뉴 및 스텝퍼 일치 상태
    const [currentNav, setCurrentNav] = useState<'topics' | 'projects' | 'plan' | 'tts' | 'image' | 'subtitle' | 'thumbnail' | 'settings'>('topics')

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
            setCurrentNav('plan')
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

    const uploadAsset = async (scene: any, assetType: 'image' | 'video' | 'thumbnail', file: File | null) => {
        if (!file || !selectedProject) return
        const key = `${scene?.scene_number || 'thumb'}-${assetType}`
        setUploadingKey(key)
        setMessage('')
        try {
            const initRes = await fetch(`/api/std/projects/${selectedProject.project.id}/assets/init`, {
                method: 'POST',
                headers: authedJsonHeaders,
                body: JSON.stringify({
                    scene_number: scene?.scene_number || 1,
                    asset_type: assetType,
                    file_name: file.name,
                    mime_type: file.type || (assetType === 'image' || assetType === 'thumbnail' ? 'image/png' : 'video/mp4'),
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
                    scene_number: scene?.scene_number || 1,
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

            setMessage(`에셋(${file.name}) 등록 완료!`)
            await reloadSelectedProject()
        } catch (error: any) {
            setMessage(error.message || '업로드 실패')
        } finally {
            setUploadingKey('')
        }
    }

    const submitProject = async () => {
        if (!selectedProject) return
        if (!confirm('에셋 검증 및 원격 렌더 큐 제출을 진행하시겠습니까?')) return
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
            setMessage('🔊 TTS 오디오가 생성되어 Google Drive에 저장되었습니다!')
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

    const imageGridPrompts = useMemo(() => {
        const payload = selectedProject?.project?.project_payload || {}
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
    }, [selectedProject])

    if (authChecking) {
        return (
            <main className="min-h-screen bg-[#1c2027] text-gray-100 flex items-center justify-center">
                <div className="flex flex-col items-center gap-3">
                    <div className="w-8 h-8 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
                    <p className="text-xs font-black tracking-widest text-blue-400 uppercase">AIR STUDIO Loading...</p>
                </div>
            </main>
        )
    }

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
                            설치형 유저앱과 100% 동일한 기능 및 엔드포인트를 제공하는 웹 포털입니다.
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
                </section>
            </main>
        )
    }

    return (
        <div className="min-h-screen bg-[#1c2027] text-gray-100 flex flex-col font-sans">
            {/* 1. 상단 글로벌 헤더 */}
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
                        동기화
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

            {/* 2. 유저앱 100% 동일 11단계 스텝퍼 네비게이션 바 */}
            <div className="bg-[#13171e]/90 border-b border-white/5 px-6 py-2 flex items-center justify-between shrink-0 overflow-x-auto no-scrollbar">
                <div className="flex items-center gap-1 min-w-max text-xs">
                    <span className="text-[10px] font-black text-gray-500 uppercase mr-2">진행 단계:</span>
                    {[
                        { id: 'topics', label: '1. 주제 (Topics)' },
                        { id: 'plan', label: '2. 기획안 (Plan)' },
                        { id: 'tts', label: '3. TTS 음성 (Audio)' },
                        { id: 'image', label: '4. 이미지/영상 (Assets)' },
                        { id: 'subtitle', label: '5. 자막 (Subtitle)' },
                        { id: 'thumbnail', label: '6. 썸네일 (Cover)' },
                    ].map((step, idx) => {
                        const active = currentNav === step.id
                        return (
                            <button
                                key={step.id}
                                onClick={() => setCurrentNav(step.id as any)}
                                className={`px-3 py-1.5 rounded-lg font-bold flex items-center gap-1.5 transition-all ${
                                    active
                                        ? 'bg-blue-600 text-white shadow-md shadow-blue-600/30'
                                        : 'text-gray-400 hover:text-white hover:bg-white/5'
                                }`}
                            >
                                <span>{step.label}</span>
                            </button>
                        )
                    })}
                </div>

                {selectedProject && (
                    <div className="flex items-center gap-2 shrink-0 ml-4">
                        <button
                            onClick={submitProject}
                            disabled={loading || selectedProject.project.status === 'review_requested'}
                            className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-black flex items-center gap-1.5 transition-all shadow-md shadow-emerald-600/30 disabled:opacity-50"
                        >
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            {selectedProject.project.status === 'review_requested' ? '렌더 접수완료' : '원격 렌더 큐 제출'}
                        </button>
                    </div>
                )}
            </div>

            {/* 3. 메인 2열 레이아웃: 유저앱 사이드바 + 전용 뷰어 */}
            <div className="flex-1 flex overflow-hidden">
                {/* 좌측 사이드바 (유저앱 메뉴 1:1 완벽 일치) */}
                <aside className="w-64 bg-[#13171e] border-r border-white/10 flex flex-col shrink-0">
                    {/* 활성 프로젝트 선택 셀렉트 */}
                    <div className="p-3 border-b border-white/5 bg-[#0e1218]">
                        <div className="text-[10px] font-bold text-gray-400 mb-1 flex items-center justify-between">
                            <span>현재 프로젝트</span>
                            <span className="text-blue-400 font-mono">{projects.length}개</span>
                        </div>
                        <select
                            value={selectedProject?.project?.id || ''}
                            onChange={(e) => {
                                if (e.target.value) openProject(e.target.value)
                            }}
                            className="w-full bg-[#1c2027] border border-white/10 rounded-lg p-2 text-xs text-white cursor-pointer focus:outline-none focus:border-blue-500"
                        >
                            <option value="">프로젝트 선택...</option>
                            {projects.map(p => (
                                <option key={p.id} value={p.id}>
                                    {p.title}
                                </option>
                            ))}
                        </select>
                    </div>

                    {/* 유저앱 네비게이션 메뉴 리스트 */}
                    <nav className="flex-1 p-2 space-y-1 overflow-y-auto custom-scrollbar text-xs font-bold">
                        <button
                            onClick={() => setCurrentNav('topics')}
                            className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl transition-all ${
                                currentNav === 'topics' ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30' : 'text-gray-400 hover:text-white hover:bg-white/5'
                            }`}
                        >
                            <Sparkles className="h-4 w-4" />
                            <span>주제 (Topics)</span>
                            <span className="ml-auto text-[10px] opacity-60">{topics.length}</span>
                        </button>

                        <button
                            onClick={() => setCurrentNav('projects')}
                            className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl transition-all ${
                                currentNav === 'projects' ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30' : 'text-gray-400 hover:text-white hover:bg-white/5'
                            }`}
                        >
                            <FolderKanban className="h-4 w-4" />
                            <span>프로젝트 (Projects)</span>
                            <span className="ml-auto text-[10px] opacity-60">{projects.length}</span>
                        </button>

                        <div className="pt-2 pb-1 px-3 text-[10px] font-black text-gray-500 uppercase tracking-wider">
                            제작 워크플로우
                        </div>

                        <button
                            onClick={() => setCurrentNav('plan')}
                            className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl transition-all ${
                                currentNav === 'plan' ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30' : 'text-gray-400 hover:text-white hover:bg-white/5'
                            }`}
                        >
                            <FileText className="h-4 w-4" />
                            <span>대본 기획안 (Plan)</span>
                        </button>

                        <button
                            onClick={() => setCurrentNav('tts')}
                            className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl transition-all ${
                                currentNav === 'tts' ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30' : 'text-gray-400 hover:text-white hover:bg-white/5'
                            }`}
                        >
                            <Mic className="h-4 w-4" />
                            <span>TTS 음성 (Audio)</span>
                        </button>

                        <button
                            onClick={() => setCurrentNav('image')}
                            className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl transition-all ${
                                currentNav === 'image' ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30' : 'text-gray-400 hover:text-white hover:bg-white/5'
                            }`}
                        >
                            <ImageIcon className="h-4 w-4" />
                            <span>이미지/영상 (Assets)</span>
                        </button>

                        <button
                            onClick={() => setCurrentNav('subtitle')}
                            className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl transition-all ${
                                currentNav === 'subtitle' ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30' : 'text-gray-400 hover:text-white hover:bg-white/5'
                            }`}
                        >
                            <Type className="h-4 w-4" />
                            <span>자막 (Subtitles)</span>
                        </button>

                        <button
                            onClick={() => setCurrentNav('thumbnail')}
                            className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl transition-all ${
                                currentNav === 'thumbnail' ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30' : 'text-gray-400 hover:text-white hover:bg-white/5'
                            }`}
                        >
                            <LayoutTemplate className="h-4 w-4" />
                            <span>썸네일 (Thumbnail)</span>
                        </button>

                        <div className="pt-2 pb-1 px-3 text-[10px] font-black text-gray-500 uppercase tracking-wider">
                            시스템 설정
                        </div>

                        <button
                            onClick={() => setCurrentNav('settings')}
                            className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl transition-all ${
                                currentNav === 'settings' ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30' : 'text-gray-400 hover:text-white hover:bg-white/5'
                            }`}
                        >
                            <SettingsIcon className="h-4 w-4" />
                            <span>환경 설정 (Settings)</span>
                        </button>
                    </nav>
                </aside>

                {/* 우측 화면 (선택된 메뉴에 따른 1:1 완벽 일치 화면) */}
                <main className="flex-1 flex flex-col overflow-hidden bg-[#181c24]">
                    {/* 메뉴 1: 주제 (Topics) */}
                    {currentNav === 'topics' && (
                        <div className="flex-1 overflow-y-auto p-6 custom-scrollbar space-y-4 max-w-6xl mx-auto w-full">
                            <div className="flex items-center justify-between pb-3 border-b border-white/10">
                                <div>
                                    <h2 className="text-lg font-black text-white flex items-center gap-2">
                                        <Sparkles className="h-5 w-5 text-blue-400" />
                                        선택 가능한 주제 (Topics Queue)
                                    </h2>
                                    <p className="text-xs text-gray-400 mt-1">워커(Hermes)가 실시간으로 발굴 및 기획 완료한 롱폼 영상 주제 풀입니다.</p>
                                </div>
                                <span className="text-xs font-bold text-blue-400 bg-blue-500/10 px-3 py-1.5 rounded-xl border border-blue-500/20">
                                    총 {topics.length}개 준비됨
                                </span>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                {topics.map(topic => (
                                    <div key={topic.id} className="bg-[#13171e] border border-white/10 rounded-2xl p-5 hover:border-blue-500/50 transition-all flex flex-col justify-between gap-4 shadow-xl">
                                        <div>
                                            <div className="flex items-center justify-between gap-2 mb-2">
                                                <span className="text-[10px] font-black uppercase bg-white/5 px-2 py-0.5 rounded border border-white/5 text-gray-300">
                                                    {topic.category_name || '일반'}
                                                </span>
                                                <span className="text-[10px] text-gray-400">
                                                    {topic.scene_count}개 씬 · {topic.assigned_duration_minutes || 10}분
                                                </span>
                                            </div>
                                            <h3 className="font-bold text-sm text-white leading-relaxed line-clamp-3">
                                                {topic.topic}
                                            </h3>
                                        </div>
                                        <button
                                            disabled={loading}
                                            onClick={() => claimTopic(topic.id)}
                                            className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-2 rounded-xl text-xs transition-all shadow-md shadow-blue-600/30 disabled:opacity-50"
                                        >
                                            이 주제로 작업 시작 (Claim)
                                        </button>
                                    </div>
                                ))}
                                {!topics.length && (
                                    <div className="col-span-full p-12 text-center text-xs text-gray-500 bg-[#13171e] border border-white/10 rounded-2xl">
                                        현재 선택 가능한 준비된 주제가 없습니다. 워커가 새로운 고성과 벤치마크 주제를 생성 중입니다.
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* 메뉴 2: 프로젝트 (Projects) */}
                    {currentNav === 'projects' && (
                        <div className="flex-1 overflow-y-auto p-6 custom-scrollbar space-y-4 max-w-6xl mx-auto w-full">
                            <div className="flex items-center justify-between pb-3 border-b border-white/10">
                                <div>
                                    <h2 className="text-lg font-black text-white flex items-center gap-2">
                                        <FolderKanban className="h-5 w-5 text-blue-400" />
                                        내 작업 목록 (Projects)
                                    </h2>
                                    <p className="text-xs text-gray-400 mt-1">내가 선택하여 현재 제작 및 렌더링 진행 중인 프로젝트 리스트입니다.</p>
                                </div>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {projects.map(proj => {
                                    const isSelected = selectedProject?.project?.id === proj.id
                                    const badge = statusBadgeStyle[proj.status] || { label: proj.status, bg: 'bg-gray-500/10', text: 'text-gray-400', border: 'border-gray-500/20' }
                                    return (
                                        <div
                                            key={proj.id}
                                            className={`p-5 rounded-2xl border transition-all flex flex-col justify-between gap-4 bg-[#13171e] ${
                                                isSelected ? 'border-blue-500 shadow-xl shadow-blue-500/10' : 'border-white/10'
                                            }`}
                                        >
                                            <div>
                                                <div className="flex items-center justify-between mb-2">
                                                    <span className={`text-[10px] font-black px-2.5 py-0.5 rounded-full border ${badge.bg} ${badge.text} ${badge.border}`}>
                                                        {badge.label}
                                                    </span>
                                                    <span className="text-[10px] text-gray-400">
                                                        {proj.assigned_duration_minutes || 10}분 영상
                                                    </span>
                                                </div>
                                                <h3 className="font-bold text-sm text-white leading-relaxed line-clamp-2">
                                                    {proj.title}
                                                </h3>
                                            </div>
                                            <div className="flex items-center gap-2">
                                                <button
                                                    onClick={() => {
                                                        openProject(proj.id)
                                                        setCurrentNav('plan')
                                                    }}
                                                    className="flex-1 bg-[#1c2027] hover:bg-blue-600 hover:text-white border border-white/10 rounded-xl py-2 text-xs font-bold text-gray-300 transition-all"
                                                >
                                                    작업실 열기
                                                </button>
                                            </div>
                                        </div>
                                    )
                                })}
                            </div>
                        </div>
                    )}

                    {/* 메뉴 3: 대본 기획안 (Plan) */}
                    {currentNav === 'plan' && selectedProject && (
                        <div className="flex-1 overflow-y-auto p-6 custom-scrollbar space-y-6 max-w-5xl mx-auto w-full">
                            <div className="bg-[#13171e] border border-white/10 rounded-2xl p-6 shadow-xl space-y-4">
                                <div className="flex items-center justify-between border-b border-white/10 pb-4">
                                    <div>
                                        <h3 className="font-black text-base text-white">{selectedProject.project.title}</h3>
                                        <p className="text-xs text-gray-400 mt-1">총 {selectedProject.scenes.length}개 씬 구성 대본 기획안</p>
                                    </div>
                                    <button
                                        onClick={() => setCurrentNav('tts')}
                                        className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold transition-all shadow-md shadow-blue-600/30"
                                    >
                                        다음: TTS 생성으로 이동 ➔
                                    </button>
                                </div>

                                <div className="space-y-4">
                                    <h4 className="text-xs font-bold text-gray-300">씬별 나레이션 대본</h4>
                                    <div className="space-y-3">
                                        {selectedProject.scenes.map(s => (
                                            <div key={s.id} className="p-4 bg-[#1c2027] border border-white/5 rounded-xl space-y-2">
                                                <div className="flex items-center justify-between">
                                                    <span className="text-[11px] font-black text-blue-400">
                                                        SCENE {String(s.scene_number).padStart(3, '0')} · {s.scene_title}
                                                    </span>
                                                </div>
                                                <p className="text-xs text-gray-200 leading-relaxed whitespace-pre-wrap">{s.scene_text}</p>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* 메뉴 4: TTS 음성 (Audio) */}
                    {currentNav === 'tts' && selectedProject && (
                        <div className="flex-1 overflow-y-auto p-6 custom-scrollbar space-y-6 max-w-4xl mx-auto w-full">
                            <div className="bg-[#13171e] border border-white/10 rounded-2xl p-6 shadow-xl space-y-5">
                                <div className="flex items-center justify-between border-b border-white/10 pb-4">
                                    <div>
                                        <h3 className="font-black text-base text-white flex items-center gap-2">
                                            <Volume2 className="h-5 w-5 text-blue-400" />
                                            TTS 음성 생성 및 오디오 관리
                                        </h3>
                                        <p className="text-xs text-gray-400 mt-1">ElevenLabs 고품질 AI 음성으로 전체 대본 나레이션을 생성합니다.</p>
                                    </div>
                                    <button
                                        onClick={generateTts}
                                        disabled={generatingTts || loading}
                                        className="px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold flex items-center gap-2 transition-all shadow-lg shadow-blue-600/30 disabled:opacity-50"
                                    >
                                        <Mic className={`h-4 w-4 ${generatingTts ? 'animate-bounce' : ''}`} />
                                        {generatingTts ? 'TTS 음성 생성 중...' : '원클릭 TTS 음성 생성'}
                                    </button>
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
                                                    className="px-3.5 py-1.5 bg-[#252b36] hover:bg-[#323946] border border-white/10 rounded-lg text-xs font-bold text-gray-200 transition-all flex items-center gap-1.5"
                                                >
                                                    <ExternalLink className="h-3.5 w-3.5" />
                                                    Drive에서 듣기 / 확인
                                                </a>
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="p-12 text-center text-xs text-gray-500 bg-[#1c2027] border border-white/5 rounded-xl flex flex-col items-center gap-2">
                                        <Volume2 className="h-8 w-8 text-gray-600" />
                                        <span>생성된 TTS 오디오가 없습니다. 상단의 <strong>[원클릭 TTS 음성 생성]</strong>을 클릭하세요.</span>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* 메뉴 5: 이미지/영상 에셋 (Assets) */}
                    {currentNav === 'image' && selectedProject && (
                        <div className="flex-1 overflow-y-auto p-6 custom-scrollbar space-y-6 max-w-6xl mx-auto w-full">
                            {/* 2x2 분할 프롬프트 박스 */}
                            {imageGridPrompts.length > 0 && (
                                <div className="space-y-3">
                                    <h3 className="text-xs font-black text-gray-400 uppercase tracking-wider">Midjourney 2x2 분할 이미지 생성 프롬프트</h3>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        {imageGridPrompts.map(grid => (
                                            <div key={grid.grid_number} className="bg-[#13171e] border border-white/10 rounded-2xl p-4 shadow-xl space-y-2.5">
                                                <div className="flex items-center justify-between">
                                                    <span className="text-[11px] font-black text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded border border-blue-500/20">
                                                        GRID {String(grid.grid_number).padStart(3, '0')} (Scenes {grid.scene_numbers.join(', ')})
                                                    </span>
                                                    <button
                                                        onClick={() => {
                                                            navigator.clipboard.writeText(grid.prompt)
                                                            alert('프롬프트가 클립보드에 복사되었습니다!')
                                                        }}
                                                        className="px-2.5 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-[11px] font-bold transition-all flex items-center gap-1 shadow-md shadow-blue-600/30"
                                                    >
                                                        <Copy className="h-3 w-3" /> 복사
                                                    </button>
                                                </div>
                                                <textarea
                                                    readOnly
                                                    value={grid.prompt}
                                                    className="w-full bg-[#1c2027] border border-white/10 rounded-xl p-3 text-xs text-gray-200 min-h-[100px] focus:outline-none"
                                                />
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* 씬별 에셋 업로드 카드 */}
                            <div className="space-y-3">
                                <h3 className="text-xs font-black text-gray-400 uppercase tracking-wider">씬별 이미지 및 영상 파일 배치</h3>
                                <div className="space-y-4">
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
                                                    hasUploaded ? 'border-emerald-500/30' : 'border-white/10'
                                                }`}
                                            >
                                                <div className="flex-1 flex flex-col justify-between gap-3">
                                                    <div>
                                                        <div className="flex items-center gap-2">
                                                            <span className="text-xs font-black text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded border border-blue-500/20">
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
                                                        <p className="mt-2 text-xs text-gray-300 leading-relaxed bg-[#1c2027] p-3 rounded-xl border border-white/5">
                                                            {scene.scene_text}
                                                        </p>
                                                    </div>

                                                    <div className="flex flex-wrap items-center gap-2">
                                                        {!requiresVideo && (
                                                            <label className="cursor-pointer inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#1c2027] hover:bg-[#252b36] border border-white/10 hover:border-blue-500 rounded-lg text-xs font-bold text-gray-200 transition-all">
                                                                <ImageIcon className="h-3.5 w-3.5 text-blue-400" />
                                                                {isImageUploading ? '업로드 중...' : '이미지 등록'}
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
                                                            {isVideoUploading ? '업로드 중...' : '비디오 등록'}
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

                                                <div className="w-full md:w-56 shrink-0 bg-[#0e1218] border border-white/5 rounded-xl p-3 flex flex-col justify-center items-center text-center min-h-[120px]">
                                                    {sceneAssets.length > 0 ? (
                                                        <div className="w-full space-y-2">
                                                            <div className="text-[10px] font-bold text-emerald-400 flex items-center justify-center gap-1">
                                                                <CheckCircle2 className="h-3.5 w-3.5" />
                                                                등록 완료
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
                                                            <span>미등록</span>
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        )
                                    })}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* 메뉴 6: 자막 (Subtitles) */}
                    {currentNav === 'subtitle' && selectedProject && (
                        <div className="flex-1 overflow-y-auto p-6 custom-scrollbar space-y-6 max-w-5xl mx-auto w-full">
                            <div className="bg-[#13171e] border border-white/10 rounded-2xl p-6 shadow-xl space-y-4">
                                <div className="flex items-center justify-between border-b border-white/10 pb-4">
                                    <h3 className="font-black text-base text-white flex items-center gap-2">
                                        <Type className="h-5 w-5 text-blue-400" />
                                        자막 싱크 및 타임라인 뷰어
                                    </h3>
                                    <span className="text-xs text-gray-400">자막 스타일: 1080p 중앙 하단 자막바 고정</span>
                                </div>

                                <div className="space-y-3">
                                    {selectedProject.scenes.map((s, idx) => (
                                        <div key={s.id} className="p-3.5 bg-[#1c2027] border border-white/5 rounded-xl flex items-center justify-between gap-4">
                                            <div className="flex items-center gap-3">
                                                <span className="text-xs font-mono font-bold text-blue-400">
                                                    #{idx + 1}
                                                </span>
                                                <p className="text-xs text-gray-200">{s.scene_text}</p>
                                            </div>
                                            <span className="text-[10px] text-gray-400 shrink-0 font-mono">
                                                자동 동기화
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* 메뉴 7: 썸네일 (Thumbnail) */}
                    {currentNav === 'thumbnail' && selectedProject && (
                        <div className="flex-1 overflow-y-auto p-6 custom-scrollbar space-y-6 max-w-4xl mx-auto w-full">
                            <div className="bg-[#13171e] border border-white/10 rounded-2xl p-6 shadow-xl space-y-4">
                                <div className="flex items-center justify-between border-b border-white/10 pb-4">
                                    <h3 className="font-black text-base text-white flex items-center gap-2">
                                        <LayoutTemplate className="h-5 w-5 text-blue-400" />
                                        유튜브 업로드용 썸네일 등록
                                    </h3>
                                </div>
                                <div className="p-8 bg-[#1c2027] border border-dashed border-white/20 rounded-2xl flex flex-col items-center justify-center text-center gap-3">
                                    <ImageIcon className="h-10 w-10 text-gray-500" />
                                    <div className="text-xs text-gray-300 font-bold">1280x720 썸네일 이미지를 업로드하세요</div>
                                    <label className="cursor-pointer px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold transition-all shadow-md shadow-blue-600/30">
                                        썸네일 파일 선택
                                        <input
                                            type="file"
                                            accept="image/*"
                                            className="hidden"
                                            onChange={e => uploadAsset(null, 'thumbnail', e.target.files?.[0] || null)}
                                        />
                                    </label>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* 메뉴 8: 환경 설정 (Settings) */}
                    {currentNav === 'settings' && (
                        <div className="flex-1 overflow-y-auto p-6 custom-scrollbar space-y-6 max-w-3xl mx-auto w-full">
                            <div className="bg-[#13171e] border border-white/10 rounded-2xl p-6 shadow-xl space-y-4">
                                <div className="flex items-center justify-between border-b border-white/10 pb-4">
                                    <h3 className="font-black text-base text-white flex items-center gap-2">
                                        <SettingsIcon className="h-5 w-5 text-blue-400" />
                                        작업자 계정 및 환경 설정
                                    </h3>
                                </div>
                                <div className="space-y-3 text-xs">
                                    <div className="flex justify-between py-2 border-b border-white/5">
                                        <span className="text-gray-400">작업자 계정</span>
                                        <span className="text-white font-mono">{user?.email}</span>
                                    </div>
                                    <div className="flex justify-between py-2 border-b border-white/5">
                                        <span className="text-gray-400">작업자 등급</span>
                                        <span className="text-blue-400 font-bold uppercase">{user?.membership || 'STD'}</span>
                                    </div>
                                    <div className="flex justify-between py-2 border-b border-white/5">
                                        <span className="text-gray-400">선호 언어</span>
                                        <span className="text-white">한국어 (KO)</span>
                                    </div>
                                    <div className="flex justify-between py-2">
                                        <span className="text-gray-400">렌더 엔진</span>
                                        <span className="text-emerald-400 font-bold">AIR Remote Distributed Render Queue</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </main>
            </div>
        </div>
    )
}
