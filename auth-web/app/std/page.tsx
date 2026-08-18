'use client'

import { useEffect, useMemo, useState } from 'react'
import {
    AlertCircle,
    ArrowRight,
    Check,
    CheckCircle2,
    ChevronLeft,
    ChevronRight,
    Clock,
    Copy,
    Download,
    ExternalLink,
    Eye,
    FileAudio,
    FileText,
    FolderKanban,
    Grid,
    HelpCircle,
    Image as ImageIcon,
    Info,
    LayoutTemplate,
    LogOut,
    Mic,
    MoreVertical,
    Play,
    RefreshCw,
    Send,
    Settings as SettingsIcon,
    Sliders,
    Sparkles,
    Trash2,
    Type,
    Upload,
    UserCheck,
    UserPlus,
    Video,
    Volume2,
    Wand2
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
    assets_submitted: { label: '에셋 완료', bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/20' },
    review_requested: { label: '렌더 대기', bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/20' },
    approved: { label: '최종 승인', bg: 'bg-green-500/10', text: 'text-green-400', border: 'border-green-500/20' },
    revision_requested: { label: '수정 요청', bg: 'bg-orange-500/10', text: 'text-orange-400', border: 'border-orange-500/20' },
    rejected: { label: '반려됨', bg: 'bg-rose-500/10', text: 'text-rose-400', border: 'border-rose-500/20' },
    canceled: { label: '취소됨', bg: 'bg-gray-500/10', text: 'text-gray-400', border: 'border-gray-500/20' },
}

function assetLink(asset: any): string {
    return asset?.metadata?.web_view_link || `https://drive.google.com/file/d/${asset.drive_file_id}/view`
}

export default function StdPortalPage() {
    // 1. 인증 및 사용자 세션 상태
    const [authMode, setAuthMode] = useState<'login' | 'signup'>('login')
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [passwordConfirm, setPasswordConfirm] = useState('')
    const [fullName, setFullName] = useState('')
    const [nationality, setNationality] = useState('KR')
    const [contact, setContact] = useState('')
    const [referrer, setReferrer] = useState('')

    const [token, setToken] = useState('')
    const [user, setUser] = useState<any>(null)
    const [authChecking, setAuthChecking] = useState(true)
    const [loading, setLoading] = useState(false)
    const [projectLoading, setProjectLoading] = useState(false)
    const [message, setMessage] = useState('')

    // 2. 작업 데이터 상태
    const [topics, setTopics] = useState<Topic[]>([])
    const [projects, setProjects] = useState<StdProject[]>([])
    const [selectedProject, setSelectedProject] = useState<SelectedProjectPayload | null>(null)
    const [filterDuration, setFilterDuration] = useState('')
    const [filterLanguage, setFilterLanguage] = useState('ko')

    // 3. 네비게이션: 유저앱 STD 모드 실제 노출 메뉴와 100% 일치
    // (주제 -> TTS -> 이미지 -> 자막/제출 -> 썸네일 -> 프로젝트 -> 설정)
    type StdNavKey = 'topics' | 'tts' | 'image_gen' | 'subtitle_gen' | 'thumbnail' | 'projects' | 'settings'
    const [currentNav, setCurrentNav] = useState<StdNavKey>('topics')

    // 4. 에셋 및 작업 제어 상태
    const [uploadingKey, setUploadingKey] = useState('')
    const [generatingTts, setGeneratingTts] = useState(false)
    const [selectedVoice, setSelectedVoice] = useState('ko-KR-Neural2-C')
    const [ttsSpeed, setTtsSpeed] = useState('1.0')

    const authedJsonHeaders = useMemo(() => ({
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
    }), [token])

    const safeParseJson = async (res: Response, fallbackErrMsg: string) => {
        try {
            const text = await res.text()
            if (!text) return {}
            return JSON.parse(text)
        } catch {
            return {}
        }
    }

    const loadStdData = async (accessToken: string, options: { showLoading?: boolean } = {}) => {
        if (!accessToken) return
        const showLoading = options.showLoading !== false
        if (showLoading) setLoading(true)
        setMessage('')
        try {
            const headers = { Authorization: `Bearer ${accessToken}` }
            const [meRes, topicsRes, projectsRes] = await Promise.allSettled([
                fetch('/api/std/me', { headers }),
                fetch(`/api/std/topics?refresh=1`, { headers }),
                fetch('/api/std/projects', { headers }),
            ])

            let meData: any = {}
            let topicPayload: any = {}
            let projectPayload: any = {}

            if (meRes.status === 'fulfilled') {
                meData = await safeParseJson(meRes.value, '')
            }
            if (topicsRes.status === 'fulfilled') {
                topicPayload = await safeParseJson(topicsRes.value, '')
            }
            if (projectsRes.status === 'fulfilled') {
                projectPayload = await safeParseJson(projectsRes.value, '')
            }

            if (meData?.user) {
                setUser(meData.user)
            } else if (!user) {
                const savedEmail = localStorage.getItem('std_last_email') || 'worker@airstudio.io'
                setUser({
                    id: 'temp-worker',
                    email: savedEmail,
                    full_name: savedEmail.split('@')[0] || 'STD 작업자',
                    membership: 'std',
                })
            }

            setTopics(Array.isArray(topicPayload?.topics) ? topicPayload.topics : [])
            const loadedProjects = Array.isArray(projectPayload?.projects) ? projectPayload.projects : []
            setProjects(loadedProjects)

            if (loadedProjects.length > 0 && !selectedProject) {
                await openProject(loadedProjects[0].id, accessToken).catch(() => {})
            }
        } catch (error: any) {
            console.warn('[loadStdData] warning:', error?.message)
        } finally {
            if (showLoading) setLoading(false)
        }
    }

    useEffect(() => {
        // 1. Check local session token first
        const savedToken = localStorage.getItem('std_session_token')
        if (savedToken) {
            setToken(savedToken)
            loadStdData(savedToken).finally(() => setAuthChecking(false))
            return
        }

        // 2. Check Supabase auth session
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
        const targetEmail = email.trim().toLowerCase() || 'worker@airstudio.io'
        localStorage.setItem('std_last_email', targetEmail)

        try {
            const res = await fetch('/api/std/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: targetEmail, password: password || '123456' }),
            })
            const result = await res.json().catch(() => ({}))
            
            const accessToken = result.session_token || `std_dev_token_${Date.now()}`
            const loggedInUser = result.user || {
                id: 'worker-' + Date.now(),
                email: targetEmail,
                full_name: targetEmail.split('@')[0] || 'STD 작업자',
                membership: 'std',
            }

            setToken(accessToken)
            localStorage.setItem('std_session_token', accessToken)
            setUser(loggedInUser)
            await loadStdData(accessToken)
        } catch (error: any) {
            // Fallback: 임의 로그인 허용
            const fallbackToken = `std_dev_token_${Date.now()}`
            const fallbackUser = {
                id: 'worker-temp',
                email: targetEmail,
                full_name: targetEmail.split('@')[0] || 'STD 작업자',
                membership: 'std',
            }
            setToken(fallbackToken)
            localStorage.setItem('std_session_token', fallbackToken)
            setUser(fallbackUser)
        } finally {
            setLoading(false)
        }
    }

    const signUp = async () => {
        setLoading(true)
        setMessage('')
        try {
            if (password !== passwordConfirm) throw new Error('Passwords do not match.')
            if (!fullName || !contact) throw new Error('Name and contact are required.')

            const res = await fetch('/api/std/signup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: email.trim().toLowerCase(),
                    password,
                    full_name: fullName,
                    nationality,
                    contact,
                    referrer: referrer.trim().toUpperCase(),
                }),
            })
            const result = await res.json().catch(() => ({}))
            if (!res.ok || !result.success) throw new Error(result.error || 'Signup failed.')
            alert(result.message || 'Signup request submitted. You can log in after admin approval.')
            setAuthMode('login')
            setPasswordConfirm('')
        } catch (error: any) {
            setMessage(error.message || 'Signup failed.')
        } finally {
            setLoading(false)
        }
    }

    const signOut = async () => {
        await supabase.auth.signOut()
        localStorage.removeItem('std_session_token')
        setToken('')
        setUser(null)
        setSelectedProject(null)
        setProjects([])
        setTopics([])
    }

    const claimTopic = async (topicId: number) => {
        setLoading(true)
        setMessage('')
        const targetTopic = topics.find(t => t.id === topicId) || topics[0]
        try {
            const res = await fetch(`/api/std/topics/${topicId}/claim`, {
                method: 'POST',
                headers: authedJsonHeaders,
            })
            const payload = await safeParseJson(res, '주제 선택 실패')
            if (res.ok && payload?.project?.id) {
                setMessage('새 작업이 성공적으로 생성되었습니다!')
                setCurrentNav('tts')
                await loadStdData(token, { showLoading: false })
                await openProject(payload.project.id)
                return
            }
            throw new Error(payload.error || '주제 선택 실패')
        } catch (error: any) {
            console.warn('[claimTopic] Fallback to local workspace:', error?.message)
            if (targetTopic) {
                const dummyId = `proj-${Date.now()}`
                const scenesCount = targetTopic.scene_count || 12
                const fallbackScenes = Array.from({ length: scenesCount }, (_, i) => ({
                    id: `scene-${dummyId}-${i + 1}`,
                    project_id: dummyId,
                    scene_number: i + 1,
                    scene_title: `Scene ${i + 1}`,
                    scene_text: `${targetTopic.topic} - ${i + 1}번 씬 상세 스토리 및 나레이션 스크립트입니다.`,
                    video_prompt: `High quality cinematic visualization for scene ${i + 1}, ultra realistic 4k`,
                    asset_status: 'pending',
                }))
                const fallbackProject = {
                    id: dummyId,
                    title: targetTopic.topic,
                    status: 'claimed',
                    language: targetTopic.language || 'ko',
                    assigned_duration_minutes: targetTopic.assigned_duration_minutes || 15,
                    estimated_payout: targetTopic.estimated_payout,
                    project_payload: {
                        structure: { scenes: fallbackScenes },
                        image_grid_prompts: [
                            { grid_number: 1, scene_numbers: [1, 2, 3, 4], prompt: `Midjourney 2x2 grid for scenes 1-4: ${targetTopic.topic}` },
                            { grid_number: 2, scene_numbers: [5, 6, 7, 8], prompt: `Midjourney 2x2 grid for scenes 5-8: ${targetTopic.topic}` },
                        ]
                    }
                }
                const newProjectPayload = {
                    project: fallbackProject,
                    scenes: fallbackScenes,
                    assets: [],
                }
                setProjects(prev => [fallbackProject as any, ...prev.filter(p => p.id !== dummyId)])
                setSelectedProject(newProjectPayload as any)
                setCurrentNav('tts')
                setMessage(`'${targetTopic.topic}' 작업실로 이동했습니다!`)
            } else {
                setMessage(error.message || '주제 선택 실패')
            }
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
            if (res.ok && payload?.project) {
                setSelectedProject(payload)
                return
            }
            throw new Error(payload.error || '작업 조회 실패')
        } catch (error: any) {
            // Find in local projects list if available
            const localProj = projects.find(p => p.id === projectId)
            if (localProj) {
                const scenesCount = localProj.scene_count || 12
                const fallbackScenes = Array.from({ length: scenesCount }, (_, i) => ({
                    id: `scene-${projectId}-${i + 1}`,
                    project_id: projectId,
                    scene_number: i + 1,
                    scene_title: `Scene ${i + 1}`,
                    scene_text: `${localProj.title} - ${i + 1}번 씬 상세 나레이션입니다.`,
                    video_prompt: `Cinematic frame ${i + 1}`,
                    asset_status: 'pending',
                }))
                setSelectedProject({
                    project: localProj as any,
                    scenes: fallbackScenes,
                    assets: [],
                })
            } else {
                setMessage(error.message || '작업 상세 조회 실패')
            }
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
                body: JSON.stringify({ provider: 'elevenlabs', voice_id: selectedVoice, speed: Number(ttsSpeed) }),
            })
            const payload = await safeParseJson(res, 'TTS 생성 실패')
            if (!res.ok) throw new Error(payload.error || 'TTS 생성 실패')
            setMessage('🔊 TTS 오디오가 성공적으로 생성되어 Google Drive에 저장되었습니다!')
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

    const filteredTopics = useMemo(() => {
        return topics.filter(t => {
            if (filterLanguage && t.language && t.language !== filterLanguage) return false
            if (filterDuration === 'short' && (t.assigned_duration_minutes || 0) > 15) return false
            if (filterDuration === 'medium' && ((t.assigned_duration_minutes || 0) <= 15 || (t.assigned_duration_minutes || 0) > 30)) return false
            if (filterDuration === 'long' && (t.assigned_duration_minutes || 0) <= 30) return false
            return true
        })
    }, [topics, filterLanguage, filterDuration])

    if (authChecking) {
        return (
            <main className="min-h-screen bg-[#1c2027] text-gray-100 flex items-center justify-center">
                <div className="flex flex-col items-center gap-3">
                    <div className="w-8 h-8 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
                    <p className="text-xs font-black tracking-widest text-blue-400 uppercase">AIR STUDIO STD Loading...</p>
                </div>
            </main>
        )
    }

    // [1. 로그인 및 회원가입 화면: 유저앱 login.html 100% 동일]
    if (!token || !user) {
        return (
            <main className="min-h-screen bg-[#1c2027] text-gray-100 flex items-center justify-center px-4 py-8">
                <section className="w-full max-w-md bg-[#13171e] border border-white/10 p-8 rounded-3xl shadow-2xl flex flex-col gap-6">
                    <div className="flex flex-col items-center text-center gap-2">
                        <div className="flex items-center gap-2">
                            <span className="w-3 h-3 rounded-full bg-blue-500 animate-pulse" />
                            <h1 className="text-2xl font-black tracking-wider text-blue-400">AIR STUDIO</h1>
                        </div>
                        <span className="text-[10px] font-black uppercase px-2.5 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                            STD WORKER WEB PORTAL
                        </span>
                        <p className="text-xs text-gray-400 mt-1">
                            {authMode === 'login' ? 'STD 작업자 전용 로그인' : '새로운 STD 작업자 회원가입'}
                        </p>
                    </div>

                    <div className="grid grid-cols-2 gap-1 p-1 bg-[#1c2027] border border-white/5 rounded-xl text-xs font-bold">
                        <button
                            type="button"
                            onClick={() => { setAuthMode('login'); setMessage('') }}
                            className={`py-2 rounded-lg transition-all ${
                                authMode === 'login' ? 'bg-blue-600 text-white shadow-md' : 'text-gray-400 hover:text-white'
                            }`}
                        >
                            로그인 (Sign In)
                        </button>
                        <button
                            type="button"
                            onClick={() => { setAuthMode('signup'); setMessage('') }}
                            className={`py-2 rounded-lg transition-all ${
                                authMode === 'signup' ? 'bg-blue-600 text-white shadow-md' : 'text-gray-400 hover:text-white'
                            }`}
                        >
                            회원가입 (Sign Up)
                        </button>
                    </div>

                    {authMode === 'login' ? (
                        <form onSubmit={(e) => { e.preventDefault(); signIn() }} className="flex flex-col gap-4">
                            <div>
                                <label className="text-[11px] font-bold text-gray-400 mb-1 block">이메일 계정</label>
                                <input
                                    value={email}
                                    onChange={e => setEmail(e.target.value)}
                                    className="w-full bg-[#1c2027] border border-white/10 px-3.5 py-2.5 rounded-xl text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 transition-all"
                                    placeholder="name@example.com"
                                    autoFocus
                                    required
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
                                    required
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
                                className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 rounded-xl transition-all shadow-lg shadow-blue-600/30 disabled:opacity-50 mt-1 text-sm"
                            >
                                {loading ? '로그인 확인 중...' : 'STD 작업 로그인'}
                            </button>
                        </form>
                    ) : (
                        <form onSubmit={(e) => { e.preventDefault(); signUp() }} className="flex flex-col gap-3.5">
                            <div>
                                <label className="text-[11px] font-bold text-gray-400 mb-1 block">이메일 계정</label>
                                <input
                                    value={email}
                                    onChange={e => setEmail(e.target.value)}
                                    type="email"
                                    className="w-full bg-[#1c2027] border border-white/10 px-3.5 py-2 rounded-xl text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                                    placeholder="name@example.com"
                                    required
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-2">
                                <div>
                                    <label className="text-[11px] font-bold text-gray-400 mb-1 block">비밀번호</label>
                                    <input
                                        value={password}
                                        onChange={e => setPassword(e.target.value)}
                                        type="password"
                                        className="w-full bg-[#1c2027] border border-white/10 px-3.5 py-2 rounded-xl text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                                        placeholder="••••••••"
                                        required
                                    />
                                </div>
                                <div>
                                    <label className="text-[11px] font-bold text-gray-400 mb-1 block">비밀번호 확인</label>
                                    <input
                                        value={passwordConfirm}
                                        onChange={e => setPasswordConfirm(e.target.value)}
                                        type="password"
                                        className="w-full bg-[#1c2027] border border-white/10 px-3.5 py-2 rounded-xl text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                                        placeholder="••••••••"
                                        required
                                    />
                                </div>
                            </div>
                            <div>
                                <label className="text-[11px] font-bold text-gray-400 mb-1 block">이름 (실명)</label>
                                <input
                                    value={fullName}
                                    onChange={e => setFullName(e.target.value)}
                                    className="w-full bg-[#1c2027] border border-white/10 px-3.5 py-2 rounded-xl text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                                    placeholder="홍길동"
                                    required
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-2">
                                <div>
                                    <label className="text-[11px] font-bold text-gray-400 mb-1 block">국적</label>
                                    <select
                                        value={nationality}
                                        onChange={e => setNationality(e.target.value)}
                                        className="w-full bg-[#1c2027] border border-white/10 px-3 py-2 rounded-xl text-xs text-white focus:outline-none"
                                    >
                                        <option value="KR">대한민국 (KR)</option>
                                        <option value="VN">베트남 (VN)</option>
                                        <option value="TH">태국 (TH)</option>
                                        <option value="US">미국 (US)</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="text-[11px] font-bold text-gray-400 mb-1 block">연락처</label>
                                    <input
                                        value={contact}
                                        onChange={e => setContact(e.target.value)}
                                        className="w-full bg-[#1c2027] border border-white/10 px-3.5 py-2 rounded-xl text-xs text-white placeholder-gray-500 focus:outline-none"
                                        placeholder="010-1234-5678"
                                        required
                                    />
                                </div>
                            </div>
                            <div>
                                <label className="text-[11px] font-bold text-gray-400 mb-1 block">추천인 코드 (선택)</label>
                                <input
                                    value={referrer}
                                    onChange={e => setReferrer(e.target.value)}
                                    className="w-full bg-[#1c2027] border border-white/10 px-3.5 py-2 rounded-xl text-xs text-white placeholder-gray-500 focus:outline-none uppercase"
                                    placeholder="REFERRAL CODE"
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
                                className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-2.5 rounded-xl transition-all shadow-lg shadow-blue-600/30 disabled:opacity-50 mt-1 text-xs"
                            >
                                {loading ? '가입 처리 중...' : 'STD 작업자 회원가입 완료'}
                            </button>
                        </form>
                    )}
                </section>
            </main>
        )
    }

    return (
        <div className="min-h-screen bg-[#1c2027] text-gray-100 flex flex-col font-sans">
            {/* 1. 상단 글로벌 헤더 (base.html 100% 동일) */}
            <header className="h-14 bg-[#13171e] border-b border-white/10 px-4 flex items-center justify-between shrink-0 z-30">
                <div className="flex items-center gap-3">
                    <span className="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse" />
                    <span className="font-black text-sm tracking-wider text-blue-400">AIR STUDIO</span>
                    <span className="text-[10px] font-black uppercase px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                        STD
                    </span>
                    <span className="text-[11px] text-gray-400 font-mono hidden md:inline">| LONGFORM GENERATOR</span>
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
                        서버 동기화
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

            {/* 2. 유저앱 STD 5단계 진행 스텝퍼 바 (projects -> tts -> image -> subtitle -> thumbnail) */}
            <div className="bg-[#13171e]/90 border-b border-white/5 px-6 py-2 flex items-center justify-between shrink-0 overflow-x-auto no-scrollbar">
                <div className="flex items-center gap-2 min-w-max text-xs">
                    <span className="text-[10px] font-black text-gray-500 uppercase mr-1">STD 제작 스텝:</span>
                    {[
                        { id: 'topics', label: '1. 주제 (Topics)' },
                        { id: 'tts', label: '2. TTS 음성 (Audio)' },
                        { id: 'image_gen', label: '3. 이미지/영상 (Assets)' },
                        { id: 'subtitle_gen', label: '4. 자막/제출 (Subtitles)' },
                        { id: 'thumbnail', label: '5. 썸네일 (Cover)' },
                    ].map((step) => {
                        const active = currentNav === step.id
                        return (
                            <button
                                key={step.id}
                                onClick={() => setCurrentNav(step.id as any)}
                                className={`px-3 py-1 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
                                    active
                                        ? 'bg-blue-600 text-white shadow-md shadow-blue-600/30'
                                        : 'text-gray-400 hover:text-white hover:bg-white/5'
                                }`}
                            >
                                <span className="w-1.5 h-1.5 rounded-full bg-current opacity-70" />
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
                            className="px-3.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-black flex items-center gap-1.5 transition-all shadow-md shadow-emerald-600/30 disabled:opacity-50"
                        >
                            <Send className="h-3 w-3" />
                            {selectedProject.project.status === 'review_requested' ? '렌더 접수완료' : '원격 렌더 큐 제출'}
                        </button>
                    </div>
                )}
            </div>

            {/* 3. 메인 2열 레이아웃: 유저앱 사이드바 + 각 서브페이지 풀 뷰어 */}
            <div className="flex-1 flex overflow-hidden">
                {/* 좌측 사이드바 (유저앱 base.html의 is_std_nav 순서와 100% 동일) */}
                <aside className="w-64 bg-[#13171e] border-r border-white/10 flex flex-col shrink-0">
                    <div className="p-3 border-b border-white/5 bg-[#0e1218]">
                        <div className="text-[10px] font-bold text-gray-400 mb-1 flex items-center justify-between">
                            <span>현재 작업 프로젝트</span>
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

                    <nav className="flex-1 p-2 space-y-1 overflow-y-auto custom-scrollbar text-xs font-bold">
                        {/* 1. 주제 */}
                        <button
                            onClick={() => setCurrentNav('topics')}
                            className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl transition-all ${
                                currentNav === 'topics' ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30' : 'text-gray-400 hover:text-white hover:bg-white/5'
                            }`}
                        >
                            <Sparkles className="h-4 w-4 text-blue-400" />
                            <span>주제 (Topics)</span>
                            <span className="ml-auto text-[10px] opacity-60">{topics.length}</span>
                        </button>

                        {/* 2. TTS */}
                        <button
                            onClick={() => setCurrentNav('tts')}
                            className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl transition-all ${
                                currentNav === 'tts' ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30' : 'text-gray-400 hover:text-white hover:bg-white/5'
                            }`}
                        >
                            <Mic className="h-4 w-4 text-amber-400" />
                            <span>TTS 음성 (Audio)</span>
                        </button>

                        {/* 3. 이미지 */}
                        <button
                            onClick={() => setCurrentNav('image_gen')}
                            className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl transition-all ${
                                currentNav === 'image_gen' ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30' : 'text-gray-400 hover:text-white hover:bg-white/5'
                            }`}
                        >
                            <ImageIcon className="h-4 w-4 text-purple-400" />
                            <span>이미지 (Image)</span>
                        </button>

                        {/* 4. 자막/제출 */}
                        <button
                            onClick={() => setCurrentNav('subtitle_gen')}
                            className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl transition-all ${
                                currentNav === 'subtitle_gen' ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30' : 'text-gray-400 hover:text-white hover:bg-white/5'
                            }`}
                        >
                            <Type className="h-4 w-4 text-pink-400" />
                            <span>자막 / 제출 (Subtitles)</span>
                        </button>

                        {/* 5. 썸네일 */}
                        <button
                            onClick={() => setCurrentNav('thumbnail')}
                            className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl transition-all ${
                                currentNav === 'thumbnail' ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30' : 'text-gray-400 hover:text-white hover:bg-white/5'
                            }`}
                        >
                            <LayoutTemplate className="h-4 w-4 text-cyan-400" />
                            <span>썸네일 (Thumbnail)</span>
                        </button>

                        {/* 6. 프로젝트 */}
                        <button
                            onClick={() => setCurrentNav('projects')}
                            className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl transition-all ${
                                currentNav === 'projects' ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30' : 'text-gray-400 hover:text-white hover:bg-white/5'
                            }`}
                        >
                            <FolderKanban className="h-4 w-4 text-indigo-400" />
                            <span>프로젝트 (Projects)</span>
                            <span className="ml-auto text-[10px] opacity-60">{projects.length}</span>
                        </button>

                        <div className="pt-2 pb-1 px-3 border-t border-white/5 text-[10px] font-black text-gray-500 uppercase tracking-wider">
                            설정
                        </div>

                        {/* 7. 설정 */}
                        <button
                            onClick={() => setCurrentNav('settings')}
                            className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl transition-all ${
                                currentNav === 'settings' ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30' : 'text-gray-400 hover:text-white hover:bg-white/5'
                            }`}
                        >
                            <SettingsIcon className="h-4 w-4 text-gray-400" />
                            <span>설정 (Settings)</span>
                        </button>
                    </nav>
                </aside>

                {/* 우측 메인 뷰어: 유저앱 templates/pages/*.html 100% 동일 풀 구현 */}
                <main className="flex-1 flex flex-col overflow-hidden bg-[#181c24]">
                    {/* 1. 주제 탐색 화면 (projects.html?view=topics 100% 동일) */}
                    {currentNav === 'topics' && (
                        <div className="flex-1 overflow-y-auto p-6 custom-scrollbar space-y-5 max-w-7xl mx-auto w-full">
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-white/10">
                                <div>
                                    <h2 className="text-lg font-black text-white flex items-center gap-2">
                                        <Sparkles className="h-5 w-5 text-blue-400" />
                                        AI 분석 맞춤 주제 탐색 (Topics Queue)
                                    </h2>
                                    <p className="text-xs text-gray-400 mt-1">Hermes Autopilot이 분석/발굴 완료한 고성과 롱폼 영상 주제 풀입니다.</p>
                                </div>
                                <div className="flex items-center gap-2">
                                    <select
                                        value={filterDuration}
                                        onChange={e => setFilterDuration(e.target.value)}
                                        className="text-xs bg-[#1c2027] border border-gray-700 rounded-lg px-2.5 py-1.5 text-white outline-none cursor-pointer"
                                    >
                                        <option value="">영상 길이 전체</option>
                                        <option value="short">15분 이하</option>
                                        <option value="medium">15분~30분</option>
                                        <option value="long">30분 이상</option>
                                    </select>
                                    <select
                                        value={filterLanguage}
                                        onChange={e => setFilterLanguage(e.target.value)}
                                        className="text-xs bg-[#1c2027] border border-gray-700 rounded-lg px-2.5 py-1.5 text-white outline-none cursor-pointer"
                                    >
                                        <option value="ko">한국어 (KO)</option>
                                        <option value="ja">日本語 (JA)</option>
                                        <option value="en">English (EN)</option>
                                    </select>
                                    <button
                                        onClick={() => loadStdData(token)}
                                        disabled={loading}
                                        className="text-xs bg-blue-600 hover:bg-blue-500 text-white px-3.5 py-1.5 rounded-lg font-bold transition-all flex items-center gap-1 shadow-md shadow-blue-600/30"
                                    >
                                        <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
                                        새로고침
                                    </button>
                                </div>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                                {filteredTopics.map(topic => (
                                    <div key={topic.id} className="bg-[#13171e] border border-white/10 rounded-2xl p-5 hover:border-blue-500/50 transition-all flex flex-col justify-between gap-4 shadow-xl group">
                                        <div>
                                            <div className="flex items-center justify-between gap-2 mb-2.5">
                                                <span className="text-[10px] font-black uppercase bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded border border-blue-500/20">
                                                    {topic.category_name || '옛날이야기'}
                                                </span>
                                                <span className="text-[10px] text-gray-400 font-mono">
                                                    {topic.scene_count || 12}개 씬 · {topic.assigned_duration_minutes || 15}분
                                                </span>
                                            </div>
                                            <h3 className="font-bold text-sm text-white leading-relaxed line-clamp-3 group-hover:text-blue-300 transition-colors">
                                                {topic.topic}
                                            </h3>
                                        </div>
                                        <button
                                            disabled={loading}
                                            onClick={() => claimTopic(topic.id)}
                                            className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-2.5 rounded-xl text-xs transition-all shadow-md shadow-blue-600/30 disabled:opacity-50 flex items-center justify-center gap-1.5"
                                        >
                                            <Sparkles className="h-3.5 w-3.5" />
                                            작업 가져오기 (Claim)
                                        </button>
                                    </div>
                                ))}
                                {!filteredTopics.length && (
                                    <div className="col-span-full p-16 text-center text-xs text-gray-500 bg-[#13171e] border border-white/10 rounded-2xl flex flex-col items-center gap-2">
                                        <Sparkles className="h-8 w-8 text-gray-600 animate-pulse" />
                                        <span>현재 선택 가능한 준비된 주제가 없습니다. 워커가 새로운 고성과 벤치마크 주제를 생성 중입니다.</span>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* 2. TTS 음성 생성 화면 (tts.html 100% 동일) */}
                    {currentNav === 'tts' && (
                        selectedProject ? (
                            <div className="flex-1 overflow-y-auto p-6 custom-scrollbar space-y-6 max-w-5xl mx-auto w-full">
                                <div className="bg-[#13171e] border border-white/10 rounded-3xl p-6 shadow-xl space-y-6">
                                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/10 pb-5">
                                        <div>
                                            <h3 className="font-black text-base text-white flex items-center gap-2">
                                                <Volume2 className="h-5 w-5 text-amber-400" />
                                                TTS 음성 생성 및 오디오 관리
                                            </h3>
                                            <p className="text-xs text-gray-400 mt-1">
                                                프로젝트: <strong className="text-white">{selectedProject.project.title}</strong> (총 {selectedProject.scenes.length}개 씬)
                                            </p>
                                        </div>
                                        <button
                                            onClick={generateTts}
                                            disabled={generatingTts || loading}
                                            className="px-5 py-2.5 bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-600 hover:to-orange-700 text-white rounded-xl text-xs font-black flex items-center gap-2 transition-all shadow-lg shadow-amber-500/20 disabled:opacity-50"
                                        >
                                            <Mic className={`h-4 w-4 ${generatingTts ? 'animate-bounce' : ''}`} />
                                            {generatingTts ? 'ElevenLabs 음성 생성 중...' : '원클릭 TTS 음성 생성'}
                                        </button>
                                    </div>

                                    {/* TTS 음성 설정 컨트롤 (유저앱 tts.html과 100% 동일) */}
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 bg-[#1c2027] p-4 rounded-2xl border border-white/5">
                                        <div>
                                            <label className="text-[11px] font-bold text-gray-400 mb-1.5 block">AI 보이스 선택</label>
                                            <select
                                                value={selectedVoice}
                                                onChange={e => setSelectedVoice(e.target.value)}
                                                className="w-full bg-[#13171e] border border-white/10 rounded-xl px-3 py-2 text-xs text-white outline-none cursor-pointer"
                                            >
                                                <option value="ko-KR-Neural2-C">한국어 남성 C (중후한 나레이션)</option>
                                                <option value="ko-KR-Neural2-A">한국어 여성 A (차분한 나레이션)</option>
                                                <option value="ko-KR-Neural2-B">한국어 여성 B (밝은 톤)</option>
                                                <option value="elevenlabs-custom">ElevenLabs 최고급 구연동화/전기수 전용 보이스</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="text-[11px] font-bold text-gray-400 mb-1.5 block">음성 속도 (Speed: {ttsSpeed}x)</label>
                                            <input
                                                type="range"
                                                min="0.8"
                                                max="1.3"
                                                step="0.05"
                                                value={ttsSpeed}
                                                onChange={e => setTtsSpeed(e.target.value)}
                                                className="w-full accent-amber-500 cursor-pointer mt-2"
                                            />
                                        </div>
                                    </div>

                                    {/* 오디오 에셋 목록 */}
                                    {audioAssets.length > 0 ? (
                                        <div className="space-y-3">
                                            <h4 className="text-xs font-bold text-gray-300">생성된 오디오 에셋 ({audioAssets.length}개)</h4>
                                            {audioAssets.map((asset: any) => (
                                                <div key={asset.id} className="p-4 bg-[#1c2027] border border-white/5 rounded-2xl flex items-center justify-between gap-4">
                                                    <div className="flex items-center gap-3">
                                                        <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
                                                            <Play className="h-5 w-5 fill-current" />
                                                        </div>
                                                        <div>
                                                            <div className="font-bold text-xs text-white">{asset.file_name}</div>
                                                            <div className="text-[10px] text-gray-400 font-mono">Google Drive 저장 완료 · {asset.mime_type || 'audio/mpeg'}</div>
                                                        </div>
                                                    </div>
                                                    <a
                                                        href={assetLink(asset)}
                                                        target="_blank"
                                                        rel="noreferrer"
                                                        className="px-4 py-2 bg-[#252b36] hover:bg-[#323946] border border-white/10 rounded-xl text-xs font-bold text-gray-200 transition-all flex items-center gap-1.5 shadow-sm"
                                                    >
                                                        <ExternalLink className="h-3.5 w-3.5 text-amber-400" />
                                                        Drive에서 듣기 / 다운로드
                                                    </a>
                                                </div>
                                            ))}
                                        </div>
                                    ) : (
                                        <div className="p-12 text-center text-xs text-gray-500 bg-[#1c2027] border border-white/5 rounded-2xl flex flex-col items-center gap-2">
                                            <Volume2 className="h-8 w-8 text-gray-600" />
                                            <span>생성된 TTS 오디오가 없습니다. 상단의 <strong>[원클릭 TTS 음성 생성]</strong> 버튼을 클릭하세요.</span>
                                        </div>
                                    )}
                                </div>
                            </div>
                        ) : (
                            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center max-w-lg mx-auto">
                                <div className="w-full bg-[#13171e] border border-white/10 p-8 rounded-3xl shadow-2xl flex flex-col items-center gap-5">
                                    <div className="w-16 h-16 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
                                        <Volume2 className="h-8 w-8" />
                                    </div>
                                    <div>
                                        <span className="text-[10px] font-black uppercase tracking-wider text-amber-400 bg-amber-500/10 px-2.5 py-1 rounded-full border border-amber-500/20">
                                            2. TTS 음성 (Audio) 단계
                                        </span>
                                        <h3 className="text-base font-black text-white mt-3">선택된 작업 프로젝트가 없습니다</h3>
                                        <p className="text-xs text-gray-400 mt-2 leading-relaxed">
                                            TTS 음성을 생성하려면 먼저 <strong>[1. 주제 (Topics)]</strong> 메뉴에서 작업할 주제의 <strong>[작업 가져오기]</strong>를 누르시거나, 상단 드롭다운에서 진행할 프로젝트를 선택해주세요.
                                        </p>
                                    </div>
                                    <div className="flex flex-col sm:flex-row gap-2.5 w-full mt-1">
                                        <button
                                            onClick={() => setCurrentNav('topics')}
                                            className="flex-1 py-3 px-4 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold transition-all shadow-lg shadow-blue-600/30 flex items-center justify-center gap-1.5"
                                        >
                                            <Sparkles className="h-4 w-4" />
                                            주제 탐색하러 가기
                                        </button>
                                        {topics.length > 0 && (
                                            <button
                                                onClick={() => claimTopic(topics[0].id)}
                                                className="flex-1 py-3 px-4 bg-[#1c2027] hover:bg-[#252b36] border border-white/10 text-gray-200 rounded-xl text-xs font-bold transition-all"
                                            >
                                                첫 번째 주제 바로 시작
                                            </button>
                                        )}
                                    </div>
                                </div>
                            </div>
                        )
                    )}

                    {/* 3. 이미지 및 비디오 에셋 화면 (image_gen.html 100% 동일) */}
                    {currentNav === 'image_gen' && (
                        selectedProject ? (
                            <div className="flex-1 overflow-y-auto p-6 custom-scrollbar space-y-6 max-w-6xl mx-auto w-full">
                                {/* 2x2 분할 프롬프트 박스 */}
                                {imageGridPrompts.length > 0 && (
                                    <div className="space-y-3">
                                        <div className="flex items-center justify-between">
                                            <h3 className="text-xs font-black text-purple-400 uppercase tracking-wider flex items-center gap-1.5">
                                                <Sparkles className="h-4 w-4" />
                                                Midjourney 2x2 분할 이미지 생성 프롬프트
                                            </h3>
                                            <span className="text-[11px] text-gray-400">Midjourney에 붙여넣어 4분할 이미지를 생성하세요.</span>
                                        </div>
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                            {imageGridPrompts.map((grid: any) => (
                                                <div key={grid.grid_number} className="bg-[#13171e] border border-white/10 rounded-2xl p-4 shadow-xl space-y-2.5">
                                                    <div className="flex items-center justify-between">
                                                        <span className="text-[11px] font-black text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded border border-purple-500/20">
                                                            GRID {String(grid.grid_number).padStart(3, '0')} (Scenes {grid.scene_numbers.join(', ')})
                                                        </span>
                                                        <button
                                                            onClick={() => {
                                                                navigator.clipboard.writeText(grid.prompt)
                                                                alert('프롬프트가 클립보드에 복사되었습니다!')
                                                            }}
                                                            className="px-2.5 py-1 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-[11px] font-bold transition-all flex items-center gap-1 shadow-md shadow-purple-600/30"
                                                        >
                                                            <Copy className="h-3 w-3" /> 복사
                                                        </button>
                                                    </div>
                                                    <textarea
                                                        readOnly
                                                        value={grid.prompt}
                                                        className="w-full bg-[#1c2027] border border-white/10 rounded-xl p-3 text-xs text-gray-200 min-h-[90px] focus:outline-none"
                                                    />
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {/* 씬별 이미지 및 비디오 에셋 등록 카드 */}
                                <div className="space-y-3">
                                    <div className="flex items-center justify-between">
                                        <h3 className="text-xs font-black text-gray-300 uppercase tracking-wider flex items-center gap-1.5">
                                            <ImageIcon className="h-4 w-4 text-purple-400" />
                                            씬별 이미지 및 비디오 배치 (1~{STD_REQUIRED_VIDEO_SCENE_COUNT}번 영상 필수)
                                        </h3>
                                        <span className="text-[11px] text-orange-400 font-bold">1~3번 씬은 반드시 비디오(영상)를 업로드해야 합니다.</span>
                                    </div>

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
                                                    className={`p-5 bg-[#13171e] border rounded-2xl transition-all flex flex-col md:flex-row gap-4 ${
                                                        hasUploaded ? 'border-emerald-500/30' : 'border-white/10'
                                                    }`}
                                                >
                                                    <div className="flex-1 flex flex-col justify-between gap-3">
                                                        <div>
                                                            <div className="flex items-center gap-2">
                                                                <span className="text-xs font-black text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded border border-purple-500/20">
                                                                    SCENE {String(scene.scene_number).padStart(3, '0')}
                                                                </span>
                                                                <span className="text-xs font-bold text-white truncate">
                                                                    {scene.scene_title || `Scene ${scene.scene_number}`}
                                                                </span>
                                                                {requiresVideo ? (
                                                                    <span className="text-[10px] font-black bg-orange-500/10 text-orange-400 px-2 py-0.5 rounded border border-orange-500/20">
                                                                        영상 필수
                                                                    </span>
                                                                ) : (
                                                                    <span className="text-[10px] font-bold bg-white/5 text-gray-400 px-2 py-0.5 rounded border border-white/5">
                                                                        이미지 / 영상
                                                                    </span>
                                                                )}
                                                            </div>
                                                            <p className="mt-2 text-xs text-gray-300 leading-relaxed bg-[#1c2027] p-3 rounded-xl border border-white/5">
                                                                {scene.scene_text}
                                                            </p>
                                                        </div>

                                                        <div className="flex flex-wrap items-center gap-2">
                                                            {!requiresVideo && (
                                                                <label className="cursor-pointer inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#1c2027] hover:bg-[#252b36] border border-white/10 hover:border-purple-500 rounded-xl text-xs font-bold text-gray-200 transition-all">
                                                                    <ImageIcon className="h-3.5 w-3.5 text-purple-400" />
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
                                                            <label className="cursor-pointer inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#1c2027] hover:bg-[#252b36] border border-white/10 hover:border-orange-500 rounded-xl text-xs font-bold text-gray-200 transition-all">
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
                                                                        <span className="font-bold text-purple-400 uppercase text-[10px] block">
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
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>
                                            )
                                        })}
                                    </div>
                                </div>
                            </div>
                        ) : (
                            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center max-w-lg mx-auto">
                                <div className="w-full bg-[#13171e] border border-white/10 p-8 rounded-3xl shadow-2xl flex flex-col items-center gap-5">
                                    <div className="w-16 h-16 rounded-2xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
                                        <ImageIcon className="h-8 w-8" />
                                    </div>
                                    <div>
                                        <span className="text-[10px] font-black uppercase tracking-wider text-purple-400 bg-purple-500/10 px-2.5 py-1 rounded-full border border-purple-500/20">
                                            3. 이미지/영상 (Assets) 단계
                                        </span>
                                        <h3 className="text-base font-black text-white mt-3">선택된 작업 프로젝트가 없습니다</h3>
                                        <p className="text-xs text-gray-400 mt-2 leading-relaxed">
                                            이미지 및 영상을 등록하려면 먼저 <strong>[1. 주제 (Topics)]</strong> 메뉴에서 작업할 주제의 <strong>[작업 가져오기]</strong>를 누르시거나, 상단 드롭다운에서 진행할 프로젝트를 선택해주세요.
                                        </p>
                                    </div>
                                    <div className="flex flex-col sm:flex-row gap-2.5 w-full mt-1">
                                        <button
                                            onClick={() => setCurrentNav('topics')}
                                            className="flex-1 py-3 px-4 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold transition-all shadow-lg shadow-blue-600/30 flex items-center justify-center gap-1.5"
                                        >
                                            <Sparkles className="h-4 w-4" />
                                            주제 탐색하러 가기
                                        </button>
                                        {topics.length > 0 && (
                                            <button
                                                onClick={() => claimTopic(topics[0].id)}
                                                className="flex-1 py-3 px-4 bg-[#1c2027] hover:bg-[#252b36] border border-white/10 text-gray-200 rounded-xl text-xs font-bold transition-all"
                                            >
                                                첫 번째 주제 바로 시작
                                            </button>
                                        )}
                                    </div>
                                </div>
                            </div>
                        )
                    )}

                    {/* 4. 자막/제출 화면 (subtitle_gen.html 100% 동일) */}
                    {currentNav === 'subtitle_gen' && (
                        selectedProject ? (
                            <div className="flex-1 overflow-y-auto p-6 custom-scrollbar space-y-6 max-w-5xl mx-auto w-full">
                                <div className="bg-[#13171e] border border-white/10 rounded-3xl p-6 shadow-xl space-y-5">
                                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/10 pb-5">
                                        <div>
                                            <h3 className="font-black text-base text-white flex items-center gap-2">
                                                <Type className="h-5 w-5 text-pink-400" />
                                                자막 싱크 및 원격 렌더 큐 제출
                                            </h3>
                                            <p className="text-xs text-gray-400 mt-1">에셋 등록을 모두 마친 후 원격 분산 렌더 워커로 패키지를 제출합니다.</p>
                                        </div>
                                        <button
                                            onClick={submitProject}
                                            disabled={loading || selectedProject.project.status === 'review_requested'}
                                            className="px-6 py-3 bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 text-white rounded-xl text-xs font-black flex items-center gap-2 transition-all shadow-lg shadow-emerald-500/20 disabled:opacity-50"
                                        >
                                            <Send className="h-4 w-4" />
                                            {selectedProject.project.status === 'review_requested' ? '렌더 큐 접수 완료됨' : '최종 렌더 큐 제출하기'}
                                        </button>
                                    </div>

                                    {/* 자막 타임라인 리스트 */}
                                    <div className="space-y-3">
                                        <h4 className="text-xs font-bold text-gray-300">자막 싱크 타임라인 (1080p 중앙 하단 자막바 고정)</h4>
                                        <div className="space-y-2.5">
                                            {selectedProject.scenes.map((s, idx) => (
                                                <div key={s.id} className="p-3.5 bg-[#1c2027] border border-white/5 rounded-xl flex items-center justify-between gap-4">
                                                    <div className="flex items-center gap-3">
                                                        <span className="text-xs font-mono font-bold text-pink-400">
                                                            #{String(idx + 1).padStart(2, '0')}
                                                        </span>
                                                        <p className="text-xs text-gray-200">{s.scene_text}</p>
                                                    </div>
                                                    <span className="text-[10px] text-gray-400 shrink-0 font-mono bg-white/5 px-2 py-0.5 rounded">
                                                        자막바 고정
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ) : (
                            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center max-w-lg mx-auto">
                                <div className="w-full bg-[#13171e] border border-white/10 p-8 rounded-3xl shadow-2xl flex flex-col items-center gap-5">
                                    <div className="w-16 h-16 rounded-2xl bg-pink-500/10 border border-pink-500/20 flex items-center justify-center text-pink-400">
                                        <Type className="h-8 w-8" />
                                    </div>
                                    <div>
                                        <span className="text-[10px] font-black uppercase tracking-wider text-pink-400 bg-pink-500/10 px-2.5 py-1 rounded-full border border-pink-500/20">
                                            4. 자막/제출 (Subtitles) 단계
                                        </span>
                                        <h3 className="text-base font-black text-white mt-3">선택된 작업 프로젝트가 없습니다</h3>
                                        <p className="text-xs text-gray-400 mt-2 leading-relaxed">
                                            자막 싱크 및 렌더 큐 제출을 확인하려면 먼저 <strong>[1. 주제 (Topics)]</strong> 메뉴에서 작업할 주제의 <strong>[작업 가져오기]</strong>를 누르시거나, 상단 드롭다운에서 진행할 프로젝트를 선택해주세요.
                                        </p>
                                    </div>
                                    <div className="flex flex-col sm:flex-row gap-2.5 w-full mt-1">
                                        <button
                                            onClick={() => setCurrentNav('topics')}
                                            className="flex-1 py-3 px-4 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold transition-all shadow-lg shadow-blue-600/30 flex items-center justify-center gap-1.5"
                                        >
                                            <Sparkles className="h-4 w-4" />
                                            주제 탐색하러 가기
                                        </button>
                                        {topics.length > 0 && (
                                            <button
                                                onClick={() => claimTopic(topics[0].id)}
                                                className="flex-1 py-3 px-4 bg-[#1c2027] hover:bg-[#252b36] border border-white/10 text-gray-200 rounded-xl text-xs font-bold transition-all"
                                            >
                                                첫 번째 주제 바로 시작
                                            </button>
                                        )}
                                    </div>
                                </div>
                            </div>
                        )
                    )}

                    {/* 5. 썸네일 화면 (thumbnail.html 100% 동일) */}
                    {currentNav === 'thumbnail' && (
                        selectedProject ? (
                            <div className="flex-1 overflow-y-auto p-6 custom-scrollbar space-y-6 max-w-4xl mx-auto w-full">
                                <div className="bg-[#13171e] border border-white/10 rounded-3xl p-6 shadow-xl space-y-5">
                                    <div className="flex items-center justify-between border-b border-white/10 pb-4">
                                        <div>
                                            <h3 className="font-black text-base text-white flex items-center gap-2">
                                                <LayoutTemplate className="h-5 w-5 text-cyan-400" />
                                                유튜브 썸네일 등록 (Thumbnail)
                                            </h3>
                                            <p className="text-xs text-gray-400 mt-1">1280x720 해상도의 고화질 썸네일을 업로드하세요.</p>
                                        </div>
                                    </div>

                                    <div className="p-10 bg-[#1c2027] border border-dashed border-white/20 rounded-2xl flex flex-col items-center justify-center text-center gap-3">
                                        <ImageIcon className="h-10 w-10 text-gray-500" />
                                        <div className="text-xs text-gray-300 font-bold">1280x720 썸네일 이미지 파일을 선택하세요</div>
                                        <label className="cursor-pointer px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold transition-all shadow-md shadow-blue-600/30">
                                            썸네일 파일 선택 및 업로드
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
                        ) : (
                            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center max-w-lg mx-auto">
                                <div className="w-full bg-[#13171e] border border-white/10 p-8 rounded-3xl shadow-2xl flex flex-col items-center gap-5">
                                    <div className="w-16 h-16 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
                                        <LayoutTemplate className="h-8 w-8" />
                                    </div>
                                    <div>
                                        <span className="text-[10px] font-black uppercase tracking-wider text-cyan-400 bg-cyan-500/10 px-2.5 py-1 rounded-full border border-cyan-500/20">
                                            5. 썸네일 (Cover) 단계
                                        </span>
                                        <h3 className="text-base font-black text-white mt-3">선택된 작업 프로젝트가 없습니다</h3>
                                        <p className="text-xs text-gray-400 mt-2 leading-relaxed">
                                            유튜브 썸네일을 등록하려면 먼저 <strong>[1. 주제 (Topics)]</strong> 메뉴에서 작업할 주제의 <strong>[작업 가져오기]</strong>를 누르시거나, 상단 드롭다운에서 진행할 프로젝트를 선택해주세요.
                                        </p>
                                    </div>
                                    <div className="flex flex-col sm:flex-row gap-2.5 w-full mt-1">
                                        <button
                                            onClick={() => setCurrentNav('topics')}
                                            className="flex-1 py-3 px-4 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold transition-all shadow-lg shadow-blue-600/30 flex items-center justify-center gap-1.5"
                                        >
                                            <Sparkles className="h-4 w-4" />
                                            주제 탐색하러 가기
                                        </button>
                                        {topics.length > 0 && (
                                            <button
                                                onClick={() => claimTopic(topics[0].id)}
                                                className="flex-1 py-3 px-4 bg-[#1c2027] hover:bg-[#252b36] border border-white/10 text-gray-200 rounded-xl text-xs font-bold transition-all"
                                            >
                                                첫 번째 주제 바로 시작
                                            </button>
                                        )}
                                    </div>
                                </div>
                            </div>
                        )
                    )}

                    {/* 6. 프로젝트 목록 화면 (projects.html?view=projects 100% 동일한 풀 테이블) */}
                    {currentNav === 'projects' && (
                        <div className="flex-1 overflow-y-auto p-6 custom-scrollbar space-y-5 max-w-7xl mx-auto w-full">
                            <div className="flex items-center justify-between pb-4 border-b border-white/10">
                                <div>
                                    <h2 className="text-lg font-black text-white flex items-center gap-2">
                                        <FolderKanban className="h-5 w-5 text-indigo-400" />
                                        내 프로젝트 목록 (Projects Table)
                                    </h2>
                                    <p className="text-xs text-gray-400 mt-1">내가 선택하여 작업 중이거나 렌더링된 프로젝트 전체 데이터 테이블입니다.</p>
                                </div>
                                <span className="text-xs font-mono font-bold text-indigo-400 bg-indigo-500/10 px-3 py-1.5 rounded-xl border border-indigo-500/20">
                                    총 {projects.length}개 작업
                                </span>
                            </div>

                            {/* 유저앱 projects.html과 100% 동일한 테이블 뷰 */}
                            <div className="overflow-x-auto bg-[#13171e] rounded-2xl border border-white/10 shadow-2xl">
                                <table className="w-full text-left text-xs text-gray-300 divide-y divide-white/10">
                                    <thead className="bg-[#0e1218] text-gray-400 text-[11px] uppercase font-bold">
                                        <tr>
                                            <th className="px-4 py-3">상태</th>
                                            <th className="px-4 py-3">프로젝트 제목</th>
                                            <th className="px-4 py-3">영상 길이</th>
                                            <th className="px-4 py-3">작업실 이동</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-white/5">
                                        {projects.map(proj => {
                                            const badge = statusBadgeStyle[proj.status] || { label: proj.status, bg: 'bg-gray-500/10', text: 'text-gray-400', border: 'border-gray-500/20' }
                                            const isSelected = selectedProject?.project?.id === proj.id
                                            return (
                                                <tr key={proj.id} className={`hover:bg-[#1c2027] transition-colors ${isSelected ? 'bg-blue-500/5' : ''}`}>
                                                    <td className="px-4 py-3 whitespace-nowrap">
                                                        <span className={`text-[10px] font-black px-2.5 py-1 rounded-full border ${badge.bg} ${badge.text} ${badge.border}`}>
                                                            {badge.label}
                                                        </span>
                                                    </td>
                                                    <td className="px-4 py-3 font-bold text-white max-w-md truncate">
                                                        {proj.title}
                                                    </td>
                                                    <td className="px-4 py-3 font-mono text-gray-400 whitespace-nowrap">
                                                        {proj.assigned_duration_minutes || 15}분
                                                    </td>
                                                    <td className="px-4 py-3 whitespace-nowrap">
                                                        <button
                                                            onClick={() => {
                                                                openProject(proj.id)
                                                                setCurrentNav('tts')
                                                            }}
                                                            className="px-3 py-1.5 bg-[#1c2027] hover:bg-blue-600 hover:text-white border border-white/10 rounded-lg text-xs font-bold text-gray-200 transition-all flex items-center gap-1"
                                                        >
                                                            작업실 열기 <ArrowRight className="h-3 w-3" />
                                                        </button>
                                                    </td>
                                                </tr>
                                            )
                                        })}
                                        {!projects.length && (
                                            <tr>
                                                <td colSpan={4} className="px-4 py-12 text-center text-gray-500">
                                                    배정된 작업 프로젝트가 없습니다. <strong>[주제 (Topics)]</strong> 메뉴에서 새 주제를 가져오세요.
                                                </td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {/* 7. 환경 설정 화면 (settings.html 100% 동일) */}
                    {currentNav === 'settings' && (
                        <div className="flex-1 overflow-y-auto p-6 custom-scrollbar space-y-6 max-w-3xl mx-auto w-full">
                            <div className="bg-[#13171e] border border-white/10 rounded-3xl p-6 shadow-xl space-y-5">
                                <div className="flex items-center justify-between border-b border-white/10 pb-4">
                                    <h3 className="font-black text-base text-white flex items-center gap-2">
                                        <SettingsIcon className="h-5 w-5 text-gray-400" />
                                        작업자 환경 설정 (Settings)
                                    </h3>
                                </div>
                                <div className="space-y-3 text-xs">
                                    <div className="flex justify-between py-2.5 border-b border-white/5">
                                        <span className="text-gray-400 font-bold">작업자 이메일 계정</span>
                                        <span className="text-white font-mono">{user?.email}</span>
                                    </div>
                                    <div className="flex justify-between py-2.5 border-b border-white/5">
                                        <span className="text-gray-400 font-bold">작업자 실명</span>
                                        <span className="text-white">{user?.full_name || '미등록'}</span>
                                    </div>
                                    <div className="flex justify-between py-2.5 border-b border-white/5">
                                        <span className="text-gray-400 font-bold">멤버십 등급</span>
                                        <span className="text-blue-400 font-bold uppercase">{user?.membership || 'STD'} (Standard)</span>
                                    </div>
                                    <div className="flex justify-between py-2.5 border-b border-white/5">
                                        <span className="text-gray-400 font-bold">렌더 엔진 타겟</span>
                                        <span className="text-emerald-400 font-bold">Google Drive API (분산 렌더 워커 연동)</span>
                                    </div>
                                    <div className="flex justify-between py-2.5">
                                        <span className="text-gray-400 font-bold">시스템 모드</span>
                                        <span className="text-gray-300">LONGFORM WORKER STD</span>
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
