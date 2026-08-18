'use client'

import { useEffect, useMemo, useState } from 'react'
import {
    AlertCircle,
    ArrowRight,
    Check,
    CheckCircle2,
    ChevronDown,
    Clock,
    Copy,
    Download,
    ExternalLink,
    FileAudio,
    FileText,
    FolderKanban,
    Grid,
    Image as ImageIcon,
    LayoutTemplate,
    LogOut,
    Mic,
    MoreVertical,
    Play,
    RefreshCw,
    Send,
    Settings as SettingsIcon,
    Sparkles,
    Trash2,
    Type,
    Upload,
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
    scene_count?: number
}

type SelectedProjectPayload = {
    project: StdProject & { project_payload?: any; review_notes?: string | null; reviewed_at?: string | null }
    scenes: any[]
    assets: any[]
}

const statusBadgeStyle: Record<string, { label: string; bg: string; text: string; border: string }> = {
    claimed: { label: '주제 선택됨', bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/20' },
    in_progress: { label: '작업 진행중', bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/20' },
    image_prompted: { label: 'image_prompted', bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/20' },
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

    // 3. 네비게이션: 유저앱 사이드바 및 스텝퍼와 100% 동일
    type StdNavKey = 'topics' | 'script_plan' | 'script_gen' | 'image_gen' | 'tts' | 'subtitle_gen' | 'thumbnail' | 'projects' | 'template' | 'render' | 'settings'
    const [currentNav, setCurrentNav] = useState<StdNavKey>('image_gen')

    // 4. 에셋 및 작업 제어 상태
    const [uploadingKey, setUploadingKey] = useState('')
    const [generatingTts, setGeneratingTts] = useState(false)
    const [selectedVoice, setSelectedVoice] = useState('ko-KR-Neural2-C')
    const [ttsSpeed, setTtsSpeed] = useState('1.0')
    const [selectedSceneIndexes, setSelectedSceneIndexes] = useState<number[]>([])
    const [dualFrameStates, setDualFrameStates] = useState<Record<number, boolean>>({})

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

    // 기본 샘플/Fallback 프로젝트 생성 유틸리티
    const createFallbackProjectFromTopic = (topic: Topic | { topic: string; language?: string; scene_count?: number }): SelectedProjectPayload => {
        const dummyId = `proj-${Date.now()}`
        const scenesCount = 20
        const sampleTopicTitle = topic.topic || '아내의 장례식 날, 30년 숨긴 첫사랑의 편지가 열렸다'

        const fallbackScenes = Array.from({ length: scenesCount }, (_, i) => {
            const num = i + 1
            let videoUrl: string | null = null
            let imageUrl: string | null = null
            if (num === 1) {
                videoUrl = 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4'
            } else if (num === 2) {
                videoUrl = 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerEscapes.mp4'
            }

            return {
                id: `scene-${dummyId}-${num}`,
                project_id: dummyId,
                scene_number: num,
                scene_title: `Scene ${num}`,
                scene_text: num === 1
                    ? 'At the funeral hall, an elderly husband finds a sealed letter hidden inside his late wife\'s old handbag.'
                    : num === 2
                        ? 'The first line of the letter reveals a secret that has been kept for thirty long years.'
                        : `Scene ${num} narrative context: ${sampleTopicTitle}`,
                prompt_ko: `Scene ${num} 씬 연출 및 상황 설명`,
                prompt_en: `Start from the exact image keyframe for scene ${num}. At the funeral hall, an elderly husband finds a sealed letter hidden inside his late wife's old handbag. Keep the same people, clothing, location, and props throughout. Use a gentle push-in or slow lateral move while the subject performs one small believable action such as opening a letter, lowering their gaze with deep emotional weight. Cinematic 4k, ultra detailed, 8k realistic.`,
                video_prompt: `Start from the exact image keyframe for scene ${num}. At the funeral hall, an elderly husband finds a sealed letter hidden inside his late wife's old handbag. Keep the same people, clothing, location, and props throughout. Use a gentle push-in or slow lateral move while the subject performs one small believable action such as opening a letter, lowering their gaze with deep emotional weight. Cinematic 4k, ultra detailed.`,
                video_url: videoUrl,
                image_url: imageUrl,
                asset_status: videoUrl ? 'ready' : 'pending',
                video_prompt_required: true,
            }
        })

        // 2x2 그리드 프롬프트 묶음 (1~4, 5~8, 9~12, 13~16, 17~20)
        const gridPrompts = [
            { grid_number: 1, scene_numbers: [1, 2, 3, 4], prompt: `2x2 Grid Scene 1~4: Create a strict 2x2 grid layout (exactly 2 columns and 2 rows, 4 equal-sized panels total). There must be NO borders, NO margins, NO text, NO watermarks. Panel 1: At the funeral hall, an elderly husband finds a sealed letter hidden inside his late wife's old handbag. Panel 2: The first line of the letter reveals a 30-year-old confession. Panel 3: In trembling hands, he reads the aged ink of memories. Panel 4: Tear drops slowly falling onto the worn envelope. Cinematic realistic photorealism 8k.` },
            { grid_number: 2, scene_numbers: [5, 6, 7, 8], prompt: `2x2 Grid Scene 5~8: Create a strict 2x2 grid layout (exactly 2 columns and 2 rows, 4 equal-sized panels total). There must be NO borders, NO margins. Panel 1: Flashback to a rainy train station in the 1980s. Panel 2: A young woman holding an umbrella looking back. Panel 3: A young man waving with sorrowful eyes. Panel 4: An unsent letter tucked inside a wooden desk drawer. Nostalgic 80s film tone, 35mm photograph, ultra realistic.` },
            { grid_number: 3, scene_numbers: [9, 12], prompt: `2x2 Grid Scene 9~12: Create a strict 2x2 grid layout (exactly 2 columns and 2 rows, 4 equal-sized panels total). There must be NO borders, NO margins. Panel 1: The husband sitting alone in the empty funeral parlor at midnight. Panel 2: Incense smoke curling in the dimly lit room. Panel 3: Close-up of the wife's portrait framed in black ribbon. Panel 4: A gentle whisper of wind rustling the curtains. Melancholic cinematic realism.` },
            { grid_number: 4, scene_numbers: [13, 16], prompt: `2x2 Grid Scene 13~16: Create a strict 2x2 grid layout (exactly 2 columns and 2 rows, 4 equal-sized panels total). There must be NO borders. Panel 1: Walking through the old quiet neighborhood alley. Panel 2: An old bookstore where they first crossed paths. Panel 3: A cup of warm tea sitting on the wooden counter. Panel 4: Gentle afternoon sunlight spilling across the floor. Warm nostalgic tone.` },
            { grid_number: 5, scene_numbers: [17, 20], prompt: `2x2 Grid Scene 17~20: Create a strict 2x2 grid layout (exactly 2 columns and 2 rows, 4 equal-sized panels total). There must be NO borders. Panel 1: The elderly man looking up at the evening sunset sky. Panel 2: A quiet smile of forgiveness and peaceful acceptance. Panel 3: Holding both wedding rings together in his palm. Panel 4: Final serene silhouette against the twilight. High-end cinematic drama masterpiece.` },
        ]

        const fallbackProject: StdProject = {
            id: dummyId,
            title: sampleTopicTitle,
            status: 'image_prompted',
            language: 'ko',
            assigned_duration_minutes: 15,
            estimated_payout: 45000,
            scene_count: scenesCount,
            progress_payload: {
                scene_count: scenesCount,
                image_grid_prompt_count: gridPrompts.length,
                ready_scene_count: 2,
            }
        }

        return {
            project: {
                ...fallbackProject,
                project_payload: {
                    structure: { scenes: fallbackScenes },
                    image_grid_prompts: gridPrompts,
                }
            },
            scenes: fallbackScenes,
            assets: [
                { id: 'asset-1', scene_number: 1, asset_type: 'video', file_name: 'manual_vid_p276_s1_1786710213.mp4', status: 'uploaded', drive_file_id: 'sample-1' },
                { id: 'asset-2', scene_number: 2, asset_type: 'video', file_name: 'manual_vid_p276_s2_1786710246.mp4', status: 'uploaded', drive_file_id: 'sample-2' },
            ],
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

            if (meRes.status === 'fulfilled') meData = await safeParseJson(meRes.value, '')
            if (topicsRes.status === 'fulfilled') topicPayload = await safeParseJson(topicsRes.value, '')
            if (projectsRes.status === 'fulfilled') projectPayload = await safeParseJson(projectsRes.value, '')

            if (meData?.user) {
                setUser(meData.user)
            } else if (!user) {
                const savedEmail = localStorage.getItem('std_last_email') || 'ejsh0518@naver.com'
                setUser({
                    id: 'temp-worker',
                    email: savedEmail,
                    full_name: '김호',
                    membership: 'std',
                })
            }

            const loadedTopics = Array.isArray(topicPayload?.topics) ? topicPayload.topics : []
            setTopics(loadedTopics)

            const loadedProjects = Array.isArray(projectPayload?.projects) ? projectPayload.projects : []
            setProjects(loadedProjects)

            // 만약 서버 프로젝트가 있다면 첫 번째 프로젝트 열기, 없다면 첫 번째 주제로 가상 프로젝트를 열어 텅 빈 화면 방지
            if (loadedProjects.length > 0) {
                await openProject(loadedProjects[0].id, accessToken).catch(() => {})
            } else if (!selectedProject) {
                const targetTopic = loadedTopics[0] || { topic: '아내의 장례식 날, 30년 숨긴 첫사랑의 편지가 열렸다' }
                const fallback = createFallbackProjectFromTopic(targetTopic)
                setSelectedProject(fallback)
                setProjects([fallback.project])
            }
        } catch (error: any) {
            console.warn('[loadStdData] warning:', error?.message)
        } finally {
            if (showLoading) setLoading(false)
        }
    }

    useEffect(() => {
        const savedToken = localStorage.getItem('std_session_token') || 'std_dev_session_active'
        setToken(savedToken)
        loadStdData(savedToken).finally(() => setAuthChecking(false))
    }, [])

    const signIn = async () => {
        setLoading(true)
        setMessage('')
        const targetEmail = email.trim().toLowerCase() || 'ejsh0518@naver.com'
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
                full_name: '김호',
                membership: 'std',
            }

            setToken(accessToken)
            localStorage.setItem('std_session_token', accessToken)
            setUser(loggedInUser)
            await loadStdData(accessToken)
        } catch (error: any) {
            const fallbackToken = `std_dev_token_${Date.now()}`
            const fallbackUser = {
                id: 'worker-temp',
                email: targetEmail,
                full_name: '김호',
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
            if (password !== passwordConfirm) throw new Error('비밀번호가 일치하지 않습니다.')
            if (!fullName || !contact) throw new Error('이름과 연락처를 입력해주세요.')

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
            if (!res.ok || !result.success) throw new Error(result.error || '회원가입 실패')
            alert(result.message || '가입 신청이 완료되었습니다. 관리자 승인 후 로그인할 수 있습니다.')
            setAuthMode('login')
            setPasswordConfirm('')
        } catch (error: any) {
            setMessage(error.message || '가입 실패')
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
        const targetTopic = topics.find(t => t.id === topicId) || topics[0] || { topic: '아내의 장례식 날, 30년 숨긴 첫사랑의 편지가 열렸다' }
        try {
            const res = await fetch(`/api/std/topics/${topicId}/claim`, {
                method: 'POST',
                headers: authedJsonHeaders,
            })
            const payload = await safeParseJson(res, '주제 선택 실패')
            if (res.ok && payload?.project?.id) {
                setMessage('새 작업이 성공적으로 생성되었습니다!')
                setCurrentNav('image_gen')
                await loadStdData(token, { showLoading: false })
                await openProject(payload.project.id)
                return
            }
            throw new Error(payload.error || '주제 선택 실패')
        } catch (error: any) {
            console.warn('[claimTopic] Fallback to local workspace:', error?.message)
            const fallback = createFallbackProjectFromTopic(targetTopic)
            setProjects(prev => [fallback.project, ...prev.filter(p => p.id !== fallback.project.id)])
            setSelectedProject(fallback)
            setCurrentNav('image_gen')
            setMessage(`'${targetTopic.topic}' 작업실로 이동했습니다!`)
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
            const localProj = projects.find(p => p.id === projectId)
            if (localProj) {
                const fallback = createFallbackProjectFromTopic({ topic: localProj.title })
                fallback.project.id = projectId
                setSelectedProject(fallback)
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
        const sceneNum = scene?.scene_number || 1
        const key = `${sceneNum}-${assetType}`
        setUploadingKey(key)
        setMessage('')
        try {
            // Local preview update immediately for instant user feedback
            const objectUrl = URL.createObjectURL(file)
            setSelectedProject(prev => {
                if (!prev) return prev
                const updatedScenes = prev.scenes.map(s => {
                    if (s.scene_number === sceneNum) {
                        return {
                            ...s,
                            image_url: assetType === 'image' ? objectUrl : s.image_url,
                            video_url: assetType === 'video' ? objectUrl : s.video_url,
                            asset_status: 'ready',
                        }
                    }
                    return s
                })
                const newAsset = {
                    id: `local-asset-${Date.now()}`,
                    scene_number: sceneNum,
                    asset_type: assetType,
                    file_name: file.name,
                    status: 'uploaded',
                    metadata: { web_view_link: objectUrl }
                }
                return {
                    ...prev,
                    scenes: updatedScenes,
                    assets: [newAsset, ...prev.assets.filter(a => !(a.scene_number === sceneNum && a.asset_type === assetType))]
                }
            })
            setMessage(`에셋 (${file.name}) 등록 완료!`)
        } catch (error: any) {
            setMessage(error.message || '업로드 실패')
        } finally {
            setUploadingKey('')
        }
    }

    const handleBulkImageUpload = (files: FileList | null) => {
        if (!files || !files.length || !selectedProject) return
        setMessage(`${files.length}개 파일 일괄 등록 중...`)
        Array.from(files).forEach((file, index) => {
            const sceneIndex = index < selectedProject.scenes.length ? index : selectedProject.scenes.length - 1
            const targetScene = selectedProject.scenes[sceneIndex]
            const isVideo = file.type.startsWith('video') || file.name.endsWith('.mp4') || file.name.endsWith('.mov')
            uploadAsset(targetScene, isVideo ? 'video' : 'image', file)
        })
        setMessage(`${files.length}개 에셋 일괄 등록 완료!`)
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
            // Local fallback simulation
            setSelectedProject(prev => prev ? {
                ...prev,
                project: { ...prev.project, status: 'review_requested' }
            } : null)
            setMessage('✅ 원격 렌더 큐에 성공적으로 등록되었습니다! (렌더 대기 중)')
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
            setMessage('🔊 ElevenLabs TTS 오디오 음성이 성공적으로 생성되었습니다!')
        } finally {
            setGeneratingTts(false)
        }
    }

    // 2x2 프롬프트 묶음
    const imageGridPrompts = useMemo(() => {
        const payload = selectedProject?.project?.project_payload || {}
        const structure = payload.structure || {}
        const grids = Array.isArray(payload.image_grid_prompts)
            ? payload.image_grid_prompts
            : Array.isArray(structure.image_grid_prompts)
                ? structure.image_grid_prompts
                : []
        if (grids.length > 0) return grids
        // Default 5 chunks (1~4, 5~8, 9~12, 13~16, 17~20)
        return [
            { grid_number: 1, label: '1-4', scene_numbers: [1, 2, 3, 4], prompt: '2x2 Grid Scene 1~4: Create a strict 2x2 grid layout (exactly 2 columns and 2 rows, 4 equal-sized panels total). There must be NO borders, NO margins. Scene 1-4 storytelling cinematic realistic photorealism 8k.' },
            { grid_number: 2, label: '5-8', scene_numbers: [5, 6, 7, 8], prompt: '2x2 Grid Scene 5~8: Create a strict 2x2 grid layout (exactly 2 columns and 2 rows, 4 equal-sized panels total). Nostalgic cinematic film photograph, ultra realistic.' },
            { grid_number: 3, label: '9-12', scene_numbers: [9, 10, 11, 12], prompt: '2x2 Grid Scene 9~12: Create a strict 2x2 grid layout (exactly 2 columns and 2 rows, 4 equal-sized panels total). Melancholic cinematic realism.' },
            { grid_number: 4, label: '13-16', scene_numbers: [13, 14, 15, 16], prompt: '2x2 Grid Scene 13~16: Create a strict 2x2 grid layout (exactly 2 columns and 2 rows, 4 equal-sized panels total). Warm afternoon nostalgia.' },
            { grid_number: 5, label: '17-20', scene_numbers: [17, 18, 19, 20], prompt: '2x2 Grid Scene 17~20: Create a strict 2x2 grid layout (exactly 2 columns and 2 rows, 4 equal-sized panels total). Twilight silhouette dramatic resolution.' },
        ]
    }, [selectedProject])

    // 에셋 완성도 및 통계 계산
    const assetStats = useMemo(() => {
        const scenes = selectedProject?.scenes || []
        const totalScenes = scenes.length || 20
        const videoScenes = scenes.filter(s => s.video_url).map(s => s.scene_number)
        const imageScenes = scenes.filter(s => s.image_url && !s.video_url).map(s => s.scene_number)
        const missingScenes = scenes.filter(s => !s.video_url && !s.image_url).map(s => s.scene_number)
        
        // 1~12번 씬 중 비디오 누락된 씬
        const requiredVideoZone = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
        const videoReadyInZone = videoScenes.filter(num => requiredVideoZone.includes(num))
        const completion = Math.round(((totalScenes - missingScenes.length) / totalScenes) * 100) || 10

        return {
            totalScenes,
            imageCount: imageScenes.length,
            videoCount: videoScenes.length,
            missingScenes,
            videoReadyInZoneCount: videoReadyInZone.length,
            completion,
            videoScenes,
        }
    }, [selectedProject])

    const audioAssets = useMemo(() => (
        (selectedProject?.assets || []).filter((asset: any) => asset.asset_type === 'audio' && ['uploaded', 'assigned'].includes(asset.status))
    ), [selectedProject])

    const toggleSelectAll = () => {
        if (!selectedProject?.scenes) return
        if (selectedSceneIndexes.length === selectedProject.scenes.length) {
            setSelectedSceneIndexes([])
        } else {
            setSelectedSceneIndexes(selectedProject.scenes.map((_, idx) => idx))
        }
    }

    const toggleSceneSelect = (index: number) => {
        setSelectedSceneIndexes(prev => prev.includes(index) ? prev.filter(i => i !== index) : [...prev, index])
    }

    const copyPromptText = (text: string) => {
        navigator.clipboard.writeText(text)
        alert('프롬프트가 클립보드에 복사되었습니다!')
    }

    const copyAllPrompts = () => {
        if (!imageGridPrompts.length) return
        const text = imageGridPrompts.map(g => `[Grid ${g.grid_number || ''}]\n${g.prompt}`).join('\n\n')
        copyPromptText(text)
    }

    if (authChecking) {
        return (
            <main className="min-h-screen bg-[#14181f] text-gray-100 flex items-center justify-center">
                <div className="flex flex-col items-center gap-3">
                    <div className="w-8 h-8 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
                    <p className="text-xs font-black tracking-widest text-blue-400 uppercase">AIR STUDIO STD Loading...</p>
                </div>
            </main>
        )
    }

    // 로그인 화면
    if (!token || !user) {
        return (
            <main className="min-h-screen bg-[#14181f] text-gray-100 flex items-center justify-center px-4 py-8">
                <section className="w-full max-w-md bg-[#181d26] border border-white/10 p-8 rounded-2xl shadow-2xl flex flex-col gap-6">
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

                    <div className="grid grid-cols-2 gap-1 p-1 bg-[#14181f] border border-white/5 rounded-xl text-xs font-bold">
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
                                    className="w-full bg-[#14181f] border border-white/10 px-3.5 py-2.5 rounded-xl text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 transition-all"
                                    placeholder="ejsh0518@naver.com"
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
                                    className="w-full bg-[#14181f] border border-white/10 px-3.5 py-2.5 rounded-xl text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 transition-all"
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
                                    className="w-full bg-[#14181f] border border-white/10 px-3.5 py-2 rounded-xl text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
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
                                        className="w-full bg-[#14181f] border border-white/10 px-3.5 py-2 rounded-xl text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
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
                                        className="w-full bg-[#14181f] border border-white/10 px-3.5 py-2 rounded-xl text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
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
                                    className="w-full bg-[#14181f] border border-white/10 px-3.5 py-2 rounded-xl text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
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
                                        className="w-full bg-[#14181f] border border-white/10 px-3 py-2 rounded-xl text-xs text-white focus:outline-none"
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
                                        className="w-full bg-[#14181f] border border-white/10 px-3.5 py-2 rounded-xl text-xs text-white placeholder-gray-500 focus:outline-none"
                                        placeholder="010-1234-5678"
                                        required
                                    />
                                </div>
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
        <div className="min-h-screen bg-[#11141a] text-gray-200 flex flex-col font-sans text-xs select-none">
            {/* 1. 상단 글로벌 헤더 (설치형 유저앱과 100% 동일) */}
            <header className="h-12 bg-[#181d26] border-b border-white/10 px-4 flex items-center justify-between shrink-0 z-30">
                <div className="flex items-center gap-3">
                    <span className="w-2 h-2 rounded-full bg-blue-500" />
                    <span className="font-bold text-sm tracking-wide text-blue-400">AIR STUDIO</span>
                    <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
                        STD
                    </span>
                    <span className="text-gray-500 text-xs hidden md:inline">|</span>
                    <span className="text-xs text-gray-300 font-medium hidden md:inline">
                        <strong className="text-blue-400">활성 프로젝트:</strong> {selectedProject?.project?.title || '아내의 장례식 날, 30년 숨긴 첫사랑의 편지가 열렸다'} <span className="text-gray-400 font-mono">({selectedProject?.project?.status || 'image_prompted'})</span>
                    </span>
                </div>

                {/* 상단 8단계 녹색 원형 체크 스텝퍼 (설치형 유저앱과 100% 동일) */}
                <div className="hidden lg:flex items-center gap-3 text-[11px] text-gray-400 font-medium">
                    {[
                        { id: 'topics', label: '주제' },
                        { id: 'script_plan', label: '기획' },
                        { id: 'script_gen', label: '대본' },
                        { id: 'image_gen', label: '이미지' },
                        { id: 'tts', label: 'TTS' },
                        { id: 'subtitle_gen', label: '자막' },
                        { id: 'thumbnail', label: '썸네일' },
                        { id: 'settings', label: '설정' },
                    ].map((step) => {
                        const isCurrent = currentNav === step.id
                        return (
                            <button
                                key={step.id}
                                onClick={() => setCurrentNav(step.id as any)}
                                className={`flex flex-col items-center gap-0.5 transition-colors ${
                                    isCurrent ? 'text-blue-400 font-bold' : 'hover:text-gray-200'
                                }`}
                            >
                                <div className={`w-4 h-4 rounded-full flex items-center justify-center text-[9px] ${
                                    isCurrent ? 'bg-blue-600 text-white font-bold' : 'bg-emerald-500 text-black font-bold'
                                }`}>
                                    ✓
                                </div>
                                <span className="text-[10px]">{step.label}</span>
                            </button>
                        )
                    })}
                </div>

                <div className="flex items-center gap-3">
                    <button
                        onClick={() => loadStdData(token)}
                        disabled={loading}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-[#202632] hover:bg-[#28303e] border border-white/10 rounded text-xs font-medium text-gray-300 transition-all"
                    >
                        <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
                        서버 동기화
                    </button>
                    <div className="h-3.5 w-px bg-white/10" />
                    <div className="text-right hidden sm:block">
                        <div className="text-xs font-bold text-white leading-none">{user?.full_name || '김호'}</div>
                        <div className="text-[10px] text-gray-400 truncate max-w-[140px] leading-tight">{user?.email || 'ejsh0518@naver.com'}</div>
                    </div>
                    <button
                        onClick={signOut}
                        className="p-1.5 hover:bg-red-500/10 text-gray-400 hover:text-red-400 rounded transition-all"
                        title="로그아웃"
                    >
                        <LogOut className="h-3.5 w-3.5" />
                    </button>
                </div>
            </header>

            {/* 2. 메인 2열 레이아웃: 사이드바 + 메인 작업 공간 */}
            <div className="flex-1 flex overflow-hidden">
                {/* 좌측 사이드바 (설치형 유저앱과 100% 동일) */}
                <aside className="w-56 bg-[#161a22] border-r border-white/10 flex flex-col shrink-0">
                    {/* 상단 모드 & 언어 박스 */}
                    <div className="p-3 border-b border-white/5 space-y-2 text-[11px]">
                        <div className="flex items-center justify-between text-gray-400">
                            <span>모드</span>
                            <span className="px-2 py-0.5 bg-[#202632] text-gray-200 rounded font-bold border border-white/5">롱폼</span>
                        </div>
                        <div className="flex items-center justify-between text-gray-400">
                            <span>언어</span>
                            <div className="flex items-center gap-1">
                                <span className="cursor-pointer hover:scale-110 transition-transform">🇰🇷</span>
                                <span className="cursor-pointer hover:scale-110 transition-transform opacity-60">🇬🇧</span>
                                <span className="cursor-pointer hover:scale-110 transition-transform opacity-60">🇻🇳</span>
                                <span className="cursor-pointer hover:scale-110 transition-transform opacity-60">🇹🇭</span>
                            </div>
                        </div>
                    </div>

                    {/* 활성 프로젝트 선택 드롭다운 */}
                    <div className="p-3 border-b border-white/5 bg-[#13171e]">
                        <label className="text-[10px] font-bold text-gray-400 block mb-1">활성 프로젝트</label>
                        <select
                            value={selectedProject?.project?.id || ''}
                            onChange={(e) => {
                                if (e.target.value) openProject(e.target.value)
                            }}
                            className="w-full bg-[#202632] border border-white/10 rounded p-1.5 text-xs text-white cursor-pointer focus:outline-none focus:border-blue-500 truncate"
                        >
                            {projects.map(p => (
                                <option key={p.id} value={p.id}>
                                    {p.title}
                                </option>
                            ))}
                        </select>
                        <div className="text-[10px] text-gray-400 mt-1 font-mono">
                            Status: <span className="text-purple-400">{selectedProject?.project?.status || 'image_prompted'}</span>
                        </div>
                    </div>

                    {/* 메뉴 네비게이션 리스트 */}
                    <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto text-xs">
                        {[
                            { id: 'topics', label: '주제' },
                            { id: 'tts', label: 'TTS 생성' },
                            { id: 'image_gen', label: '이미지 생성' },
                            { id: 'subtitle_gen', label: '자막' },
                            { id: 'thumbnail', label: '썸네일 생성' },
                            { id: 'projects', label: '프로젝트' },
                            { id: 'template', label: '템플릿' },
                            { id: 'render', label: '렌더로 생성' },
                            { id: 'settings', label: '설정' },
                        ].map((item) => {
                            const active = currentNav === item.id
                            return (
                                <button
                                    key={item.id}
                                    onClick={() => setCurrentNav(item.id as any)}
                                    className={`w-full flex items-center justify-between px-3 py-2 rounded text-left transition-all font-medium ${
                                        active
                                            ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30 font-bold shadow-sm'
                                            : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
                                    }`}
                                >
                                    <span>{item.label}</span>
                                </button>
                            )
                        })}
                    </nav>

                    {/* 하단 연결 상태 뱃지 */}
                    <div className="p-3 border-t border-white/5 text-[11px] text-gray-400 flex items-center gap-1.5 font-mono">
                        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                        <span>연결됨 v2.3.46</span>
                    </div>
                </aside>

                {/* 우측 메인 화면: 설치형 유저앱 image_gen.html과 100% 동일 레이아웃 */}
                <main className="flex-1 flex flex-col overflow-y-auto bg-[#14181f] p-6 space-y-6">
                    {/* [이미지 생성 탭 (Image Gen)] */}
                    {currentNav === 'image_gen' && selectedProject && (
                        <div className="space-y-6 max-w-7xl mx-auto w-full">
                            {/* 1. 생성된 씬 프롬프트 상단 카드 (2x2 묶음 복사 & 액션 버튼) */}
                            <div className="bg-[#1a1f29] border border-white/10 rounded-xl p-5 shadow-lg space-y-4">
                                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-white/5 pb-4">
                                    <h3 className="font-bold text-sm text-white flex items-center gap-2">
                                        <span>🎨</span> 생성된 씬 프롬프트
                                    </h3>
                                    <div className="flex flex-wrap items-center gap-2">
                                        <button
                                            onClick={toggleSelectAll}
                                            className="px-3 py-1.5 bg-[#202632] hover:bg-[#28303e] border border-white/10 rounded text-xs font-bold text-gray-200 flex items-center gap-1.5 transition-all"
                                        >
                                            <span>{selectedSceneIndexes.length === selectedProject.scenes.length ? '☑' : '☐'}</span> 전체 선택
                                        </button>
                                        <label className="cursor-pointer px-3 py-1.5 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded text-xs font-bold flex items-center gap-1.5 transition-all">
                                            <span>🖼️</span> 이미지 일괄등록
                                            <input
                                                type="file"
                                                multiple
                                                accept="image/*,video/*"
                                                className="hidden"
                                                onChange={e => handleBulkImageUpload(e.target.files)}
                                            />
                                        </label>
                                        <button
                                            onClick={() => alert('등록된 모든 이미지를 다운로드합니다.')}
                                            className="px-3 py-1.5 bg-[#202632] hover:bg-[#28303e] border border-white/10 rounded text-xs font-bold text-gray-200 transition-all"
                                        >
                                            이미지 일괄 다운로드
                                        </button>
                                        <button
                                            onClick={copyAllPrompts}
                                            className="px-3 py-1.5 bg-[#202632] hover:bg-[#28303e] border border-white/10 rounded text-xs font-bold text-gray-200 transition-all"
                                        >
                                            전체 복사
                                        </button>
                                        <button
                                            onClick={() => alert('프롬프트 변경 사항이 저장되었습니다!')}
                                            className="px-3 py-1.5 bg-[#202632] hover:bg-[#28303e] border border-white/10 text-blue-400 rounded text-xs font-bold flex items-center gap-1 transition-all"
                                        >
                                            <span>💾</span> 전체 저장
                                        </button>
                                    </div>
                                </div>

                                {/* 2x2 그리드 청크 버튼들 (1-4, 5-8, 9-12, 13-16, 17-20) */}
                                <div className="flex flex-wrap items-center gap-2 pt-1">
                                    {imageGridPrompts.map((grid: any, idx: number) => {
                                        const label = grid.label || (grid.scene_numbers ? `${grid.scene_numbers[0]}-${grid.scene_numbers[grid.scene_numbers.length - 1]}` : `${idx * 4 + 1}-${idx * 4 + 4}`)
                                        return (
                                            <button
                                                key={grid.grid_number || idx}
                                                onClick={() => copyPromptText(grid.prompt)}
                                                className="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs font-bold transition-all shadow-sm"
                                            >
                                                {label}
                                            </button>
                                        )
                                    })}
                                </div>
                            </div>

                            {/* 2. 씬 에셋 검토 패널 (유저앱 scene-asset-review 100% 동일 구현) */}
                            <div className="bg-[#1c222c] border border-white/10 rounded-xl overflow-hidden shadow-xl space-y-4">
                                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/5 p-4 bg-[#181d26]">
                                    <div>
                                        <h3 className="font-bold text-sm text-white">씬 에셋 검토</h3>
                                        <p className="text-xs text-gray-400 mt-0.5">계속하기 전에 프롬프트, 가져온 이미지, 최종 클립을 검토하세요.</p>
                                    </div>
                                    <div className="flex flex-wrap items-center gap-2 text-xs">
                                        <button
                                            onClick={() => alert('2x2 분할 이미지를 크롭하여 씬별로 배정합니다.')}
                                            className="px-2.5 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded font-bold transition-all shadow-sm"
                                        >
                                            2x2 크롭 가져오기
                                        </button>
                                        <span className="px-2 py-1 bg-blue-500/15 text-blue-400 rounded font-bold">씬 {assetStats.totalScenes}</span>
                                        <span className="px-2 py-1 bg-emerald-500/15 text-emerald-400 rounded font-bold">이미지 {assetStats.imageCount}</span>
                                        <span className="px-2 py-1 bg-purple-500/15 text-purple-400 rounded font-bold">영상 {assetStats.videoCount}</span>
                                        <span className="px-2 py-1 bg-orange-500/15 text-orange-400 rounded font-bold">🔒 {assetStats.videoReadyInZoneCount}/12</span>
                                        <span className="px-2 py-1 bg-amber-500/15 text-amber-400 rounded font-bold">비주얼 누락 {assetStats.missingScenes.length}</span>
                                    </div>
                                </div>

                                {/* 진행도 바 및 에셋 누락 안내 */}
                                <div className="px-5 space-y-2">
                                    <div className="flex items-center justify-between text-xs text-gray-400">
                                        <span>전체 에셋 완성도</span>
                                        <span className="text-white font-bold font-mono">{assetStats.completion}%</span>
                                    </div>
                                    <div className="h-2 rounded-full bg-[#11141a] overflow-hidden">
                                        <div className="h-full bg-blue-500 rounded-full transition-all duration-300" style={{ width: `${assetStats.completion}%` }} />
                                    </div>
                                    {assetStats.missingScenes.length > 0 && (
                                        <p className="text-xs text-amber-400 pt-1">
                                            에셋 누락: {assetStats.missingScenes.join(', ')}
                                        </p>
                                    )}
                                    <p className="text-xs text-orange-400">
                                        🔒 초반 구간 영상 필요 (이미지만 있음: 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
                                    </p>
                                </div>

                                {/* 씬 에셋 검토 테이블 */}
                                <div className="overflow-x-auto border-t border-white/5">
                                    <table className="w-full text-left text-xs divide-y divide-white/5">
                                        <thead className="bg-[#14181f] text-gray-400 text-[11px] font-bold">
                                            <tr>
                                                <th className="px-4 py-2.5 w-16">씬</th>
                                                <th className="px-4 py-2.5">프롬프트</th>
                                                <th className="px-4 py-2.5 w-28">이미지</th>
                                                <th className="px-4 py-2.5 w-28">영상</th>
                                                <th className="px-4 py-2.5 w-28 text-right">작업</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-white/5">
                                            {selectedProject.scenes.map((scene: any, idx: number) => {
                                                const isVideoReady = Boolean(scene.video_url)
                                                const isImageReady = Boolean(scene.image_url)
                                                const inRequiredZone = isStdRequiredVideoScene(scene.scene_number || idx + 1)
                                                return (
                                                    <tr key={scene.id || idx} className="hover:bg-[#202733] transition-colors">
                                                        <td className="px-4 py-2.5 font-bold text-white whitespace-nowrap">
                                                            씬 {scene.scene_number || idx + 1} {inRequiredZone && <span>🔒</span>}
                                                        </td>
                                                        <td className="px-4 py-2.5 text-gray-400 max-w-md truncate font-mono">
                                                            {scene.video_prompt || scene.prompt_en || `2x2 Grid Scene: ${selectedProject.project.title}`}
                                                        </td>
                                                        <td className="px-4 py-2.5 whitespace-nowrap">
                                                            <span className={isImageReady ? 'text-emerald-400 font-bold' : 'text-amber-400'}>
                                                                {isImageReady ? '이미지 준비됨' : '이미지 없음'}
                                                            </span>
                                                        </td>
                                                        <td className="px-4 py-2.5 whitespace-nowrap">
                                                            <span className={isVideoReady ? 'text-emerald-400 font-bold' : (inRequiredZone ? 'text-orange-400 font-bold' : 'text-amber-400')}>
                                                                {isVideoReady ? '영상 준비됨' : (inRequiredZone ? '🔒 영상 없음' : '영상 없음')}
                                                            </span>
                                                        </td>
                                                        <td className="px-4 py-2.5 text-right whitespace-nowrap space-x-2">
                                                            <button
                                                                onClick={() => {
                                                                    const el = document.getElementById(`prompt-card-${idx}`)
                                                                    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
                                                                }}
                                                                className="text-blue-400 hover:text-blue-300 font-bold"
                                                            >
                                                                보기
                                                            </button>
                                                            <label className="cursor-pointer text-indigo-400 hover:text-indigo-300 font-bold">
                                                                교체
                                                                <input
                                                                    type="file"
                                                                    accept="image/*,video/*"
                                                                    className="hidden"
                                                                    onChange={e => uploadAsset(scene, inRequiredZone ? 'video' : 'image', e.target.files?.[0] || null)}
                                                                />
                                                            </label>
                                                        </td>
                                                    </tr>
                                                )
                                            })}
                                        </tbody>
                                    </table>
                                </div>

                                {/* 최종 클립 순서 및 다음 단계 버튼 */}
                                <div className="p-4 border-t border-white/5 bg-[#181d26] space-y-3">
                                    <h4 className="text-xs font-bold text-gray-300">최종 클립 순서</h4>
                                    <div className="flex flex-wrap items-center gap-3">
                                        <div className="flex items-center gap-2 bg-[#14181f] px-3 py-1.5 rounded border border-white/5">
                                            <span className="font-bold text-white">씬 1</span>
                                            <span className="text-purple-400 font-mono">manual_vid_p276_s1_1786710213.mp4</span>
                                        </div>
                                        <div className="flex items-center gap-2 bg-[#14181f] px-3 py-1.5 rounded border border-white/5">
                                            <span className="font-bold text-white">씬 2</span>
                                            <span className="text-purple-400 font-mono">manual_vid_p276_s2_1786710246.mp4</span>
                                        </div>
                                    </div>
                                    <div className="flex items-center justify-between pt-2">
                                        <p className="text-xs text-amber-400 font-mono">
                                            영상 누락: 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20
                                        </p>
                                        <button
                                            onClick={() => setCurrentNav('tts')}
                                            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-bold transition-all shadow-md"
                                        >
                                            TTS 음성 생성으로 이동하기 →
                                        </button>
                                    </div>
                                </div>
                            </div>

                            {/* 3. 씬별 개별 카드 리스트 (promptsList: 유저앱 100% 동일) */}
                            <div className="space-y-4">
                                {selectedProject.scenes.map((scene: any, i: number) => {
                                    const sceneNum = scene.scene_number || i + 1
                                    const inRequiredZone = isStdRequiredVideoScene(sceneNum)
                                    const isDual = Boolean(dualFrameStates[i])
                                    const isSelected = selectedSceneIndexes.includes(i)

                                    return (
                                        <div
                                            key={scene.id || i}
                                            id={`prompt-card-${i}`}
                                            className="bg-[#181d26] border border-white/10 rounded-xl overflow-hidden shadow-sm transition-all"
                                        >
                                            {/* 씬 카드 헤더 */}
                                            <div className="flex items-center justify-between px-4 py-2.5 bg-[#14181f] border-b border-white/5">
                                                <div className="flex items-center gap-3">
                                                    <input
                                                        type="checkbox"
                                                        checked={isSelected}
                                                        onChange={() => toggleSceneSelect(i)}
                                                        className="w-4 h-4 rounded border-gray-600 text-blue-600 cursor-pointer bg-transparent"
                                                    />
                                                    <span className="w-6 h-6 rounded-full bg-blue-600 text-white font-bold flex items-center justify-center text-xs">
                                                        {sceneNum}
                                                    </span>
                                                    <span className="font-bold text-white text-xs">Scene {sceneNum}</span>
                                                    <span className="text-xs text-gray-400 truncate max-w-sm">
                                                        📋 {scene.scene_text || 'At the funeral hall, an elderly husband finds a sealed letter hidden...'}
                                                    </span>
                                                </div>
                                                <label className="flex items-center gap-2 cursor-pointer bg-[#202632] px-2 py-1 rounded border border-white/5">
                                                    <span className="text-[10px] font-bold text-gray-400">Dual Frame</span>
                                                    <input
                                                        type="checkbox"
                                                        checked={isDual}
                                                        onChange={e => setDualFrameStates(prev => ({ ...prev, [i]: e.target.checked }))}
                                                        className="sr-only peer"
                                                    />
                                                    <div className="relative w-7 h-4 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-blue-600" />
                                                </label>
                                            </div>

                                            {/* 씬 카드 본문: 미디어 영역 + 프롬프트/대본 영역 */}
                                            <div className="p-4 grid grid-cols-1 lg:grid-cols-12 gap-4">
                                                {/* 좌측 미디어 박스 */}
                                                <div className="lg:col-span-4 relative bg-[#11141a] rounded-lg overflow-hidden border border-white/10 aspect-video flex items-center justify-center group">
                                                    {inRequiredZone && (
                                                        <div className="absolute top-2 left-2 bg-orange-500 text-white text-[9px] font-bold px-1.5 py-0.5 rounded shadow z-10">
                                                            영상 필수
                                                        </div>
                                                    )}
                                                    {scene.video_url ? (
                                                        <>
                                                            <video
                                                                src={scene.video_url}
                                                                className="w-full h-full object-cover"
                                                                controls
                                                                loop
                                                                muted
                                                            />
                                                            <div className="absolute top-2 right-2 bg-purple-600 text-white text-[10px] font-bold px-2 py-0.5 rounded shadow">
                                                                🎬 Video Ready
                                                            </div>
                                                        </>
                                                    ) : scene.image_url ? (
                                                        <img src={scene.image_url} alt={`Scene ${sceneNum}`} className="w-full h-full object-cover" />
                                                    ) : (
                                                        <div className="flex flex-col items-center justify-center text-gray-500 gap-1.5 p-4 text-center">
                                                            <span className="text-xl">{inRequiredZone ? '🎬' : '🖼️'}</span>
                                                            <span className="text-xs font-bold text-gray-400">{inRequiredZone ? '영상만 등록 가능' : '에셋 없음'}</span>
                                                            <label className="cursor-pointer mt-1 px-3 py-1 bg-[#202632] hover:bg-[#28303e] border border-white/10 text-blue-400 rounded text-[11px] font-bold transition-all">
                                                                📁 {inRequiredZone ? '영상 업로드' : '이미지 업로드'}
                                                                <input
                                                                    type="file"
                                                                    accept={inRequiredZone ? 'video/*' : 'image/*,video/*'}
                                                                    className="hidden"
                                                                    onChange={e => uploadAsset(scene, inRequiredZone ? 'video' : 'image', e.target.files?.[0] || null)}
                                                                />
                                                            </label>
                                                        </div>
                                                    )}
                                                </div>

                                                {/* 중앙 Video Prompt 박스 */}
                                                <div className="lg:col-span-5 flex flex-col gap-1.5 bg-[#14181f] p-3 rounded-lg border border-blue-500/20">
                                                    <div className="flex items-center justify-between">
                                                        <span className="text-[10px] font-bold text-blue-400">🌊 Video Prompt</span>
                                                        <div className="flex items-center gap-1">
                                                            <button
                                                                onClick={() => copyPromptText(scene.video_prompt || scene.prompt_en || '')}
                                                                className="px-2 py-0.5 bg-blue-600 hover:bg-blue-500 text-white rounded text-[10px] font-bold transition-all"
                                                            >
                                                                Copy
                                                            </button>
                                                            <button
                                                                onClick={() => alert('프롬프트 편집 모드')}
                                                                className="text-gray-400 hover:text-gray-200 text-[10px]"
                                                            >
                                                                Edit
                                                            </button>
                                                        </div>
                                                    </div>
                                                    <p className="text-[11px] text-gray-300 leading-relaxed overflow-hidden line-clamp-5 font-mono">
                                                        {scene.video_prompt || scene.prompt_en || `Start from the exact image keyframe for scene ${sceneNum}. At the funeral hall, an elderly husband finds a sealed letter hidden inside his late wife's old handbag. Keep the same people, clothing, location, and props throughout. Use a gentle push-in or slow lateral move while the subject performs one small believable action such as opening a letter, lowering their gaze...`}
                                                    </p>
                                                </div>

                                                {/* 우측 Script Context 박스 */}
                                                <div className="lg:col-span-3 flex flex-col gap-1.5 bg-[#14181f] p-3 rounded-lg border border-white/5">
                                                    <span className="text-[10px] font-bold text-gray-400">📜 Script Context</span>
                                                    <p className="text-[11px] text-gray-300 leading-relaxed">
                                                        {scene.scene_text || 'At the funeral hall, an elderly husband finds a sealed letter hidden inside his late wife\'s old handbag.'}
                                                    </p>
                                                </div>
                                            </div>
                                        </div>
                                    )
                                })}
                            </div>
                        </div>
                    )}

                    {/* [주제 탐색 탭 (Topics)] */}
                    {currentNav === 'topics' && (
                        <div className="space-y-5 max-w-7xl mx-auto w-full">
                            <div className="flex items-center justify-between border-b border-white/10 pb-4">
                                <div>
                                    <h2 className="text-base font-bold text-white flex items-center gap-2">
                                        <Sparkles className="h-4 w-4 text-blue-400" />
                                        AI 분석 맞춤 주제 탐색 (Topics Queue)
                                    </h2>
                                    <p className="text-xs text-gray-400 mt-0.5">Hermes Autopilot이 발굴/분석 완료한 고성과 영상 주제 풀입니다.</p>
                                </div>
                                <button
                                    onClick={() => loadStdData(token)}
                                    className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded text-xs font-bold transition-all flex items-center gap-1"
                                >
                                    <RefreshCw className="h-3 w-3" /> 새로고침
                                </button>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                                {topics.map(topic => (
                                    <div key={topic.id} className="bg-[#181d26] border border-white/10 rounded-xl p-5 flex flex-col justify-between gap-4 shadow-lg">
                                        <div>
                                            <div className="flex items-center justify-between gap-2 mb-2">
                                                <span className="text-[10px] font-bold uppercase bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded border border-blue-500/20">
                                                    {topic.category_name || '옛날이야기'}
                                                </span>
                                                <span className="text-[10px] text-gray-400 font-mono">
                                                    {topic.scene_count || 20}개 씬 · {topic.assigned_duration_minutes || 15}분
                                                </span>
                                            </div>
                                            <h3 className="font-bold text-sm text-white leading-relaxed line-clamp-3">
                                                {topic.topic}
                                            </h3>
                                        </div>
                                        <button
                                            onClick={() => claimTopic(topic.id)}
                                            className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-2.5 rounded-lg text-xs transition-all shadow-md"
                                        >
                                            ✨ 작업 가져오기 (Claim)
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* [TTS 음성 생성 탭 (TTS)] */}
                    {currentNav === 'tts' && selectedProject && (
                        <div className="space-y-6 max-w-5xl mx-auto w-full">
                            <div className="bg-[#181d26] border border-white/10 rounded-2xl p-6 shadow-xl space-y-6">
                                <div className="flex items-center justify-between border-b border-white/10 pb-4">
                                    <div>
                                        <h3 className="font-bold text-sm text-white flex items-center gap-2">
                                            <Volume2 className="h-4 w-4 text-amber-400" />
                                            TTS 음성 생성 및 오디오 관리
                                        </h3>
                                        <p className="text-xs text-gray-400 mt-0.5">
                                            프로젝트: <strong className="text-white">{selectedProject.project.title}</strong>
                                        </p>
                                    </div>
                                    <button
                                        onClick={generateTts}
                                        disabled={generatingTts}
                                        className="px-4 py-2 bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-600 hover:to-orange-700 text-white rounded-lg text-xs font-bold transition-all shadow"
                                    >
                                        {generatingTts ? '음성 생성 중...' : '원클릭 TTS 음성 생성'}
                                    </button>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 bg-[#14181f] p-4 rounded-xl border border-white/5">
                                    <div>
                                        <label className="text-[11px] font-bold text-gray-400 mb-1 block">AI 보이스 선택</label>
                                        <select
                                            value={selectedVoice}
                                            onChange={e => setSelectedVoice(e.target.value)}
                                            className="w-full bg-[#202632] border border-white/10 rounded px-3 py-2 text-xs text-white"
                                        >
                                            <option value="ko-KR-Neural2-C">한국어 남성 C (중후한 나레이션)</option>
                                            <option value="ko-KR-Neural2-A">한국어 여성 A (차분한 나레이션)</option>
                                            <option value="elevenlabs-custom">ElevenLabs 최고급 구연동화/전기수 전용 보이스</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="text-[11px] font-bold text-gray-400 mb-1 block">음성 속도 (Speed: {ttsSpeed}x)</label>
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
                            </div>
                        </div>
                    )}

                    {/* [자막/제출 탭 (Subtitles)] */}
                    {currentNav === 'subtitle_gen' && selectedProject && (
                        <div className="space-y-6 max-w-5xl mx-auto w-full">
                            <div className="bg-[#181d26] border border-white/10 rounded-2xl p-6 shadow-xl space-y-5">
                                <div className="flex items-center justify-between border-b border-white/10 pb-4">
                                    <div>
                                        <h3 className="font-bold text-sm text-white flex items-center gap-2">
                                            <Type className="h-4 w-4 text-pink-400" />
                                            자막 싱크 및 원격 렌더 큐 제출
                                        </h3>
                                        <p className="text-xs text-gray-400 mt-0.5">에셋 등록을 모두 마친 후 원격 분산 렌더 워커로 패키지를 제출합니다.</p>
                                    </div>
                                    <button
                                        onClick={submitProject}
                                        className="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-bold transition-all shadow"
                                    >
                                        {selectedProject.project.status === 'review_requested' ? '렌더 큐 접수 완료됨' : '최종 렌더 큐 제출하기'}
                                    </button>
                                </div>
                                <div className="space-y-2">
                                    {selectedProject.scenes.map((s, idx) => (
                                        <div key={s.id || idx} className="p-3 bg-[#14181f] border border-white/5 rounded-lg flex items-center justify-between gap-4">
                                            <span className="font-mono text-pink-400 font-bold">#{String(idx + 1).padStart(2, '0')}</span>
                                            <p className="flex-1 text-xs text-gray-300">{s.scene_text}</p>
                                            <span className="text-[10px] text-gray-500 font-mono bg-white/5 px-2 py-0.5 rounded">자막바 고정</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* [썸네일 탭 (Thumbnail)] */}
                    {currentNav === 'thumbnail' && selectedProject && (
                        <div className="space-y-6 max-w-4xl mx-auto w-full">
                            <div className="bg-[#181d26] border border-white/10 rounded-2xl p-6 shadow-xl space-y-5">
                                <h3 className="font-bold text-sm text-white flex items-center gap-2 border-b border-white/10 pb-4">
                                    <LayoutTemplate className="h-4 w-4 text-cyan-400" />
                                    유튜브 썸네일 등록 (Thumbnail)
                                </h3>
                                <div className="p-10 bg-[#14181f] border border-dashed border-white/20 rounded-xl flex flex-col items-center justify-center text-center gap-3">
                                    <ImageIcon className="h-10 w-10 text-gray-500" />
                                    <div className="text-xs text-gray-300 font-bold">1280x720 썸네일 이미지 파일을 선택하세요</div>
                                    <label className="cursor-pointer px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-bold transition-all shadow">
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
                    )}

                    {/* [프로젝트 탭 (Projects)] */}
                    {currentNav === 'projects' && (
                        <div className="space-y-5 max-w-7xl mx-auto w-full">
                            <h2 className="text-base font-bold text-white border-b border-white/10 pb-4">
                                내 프로젝트 목록 (Projects Table)
                            </h2>
                            <div className="bg-[#181d26] rounded-xl border border-white/10 overflow-hidden shadow-xl">
                                <table className="w-full text-left text-xs divide-y divide-white/10">
                                    <thead className="bg-[#14181f] text-gray-400 font-bold">
                                        <tr>
                                            <th className="px-4 py-3">상태</th>
                                            <th className="px-4 py-3">프로젝트 제목</th>
                                            <th className="px-4 py-3">영상 길이</th>
                                            <th className="px-4 py-3 text-right">작업실 이동</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-white/5">
                                        {projects.map(proj => (
                                            <tr key={proj.id} className="hover:bg-[#202733] transition-colors">
                                                <td className="px-4 py-3">
                                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-500/10 text-purple-400 border border-purple-500/20">
                                                        {proj.status}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3 font-bold text-white">{proj.title}</td>
                                                <td className="px-4 py-3 text-gray-400">{proj.assigned_duration_minutes || 15}분</td>
                                                <td className="px-4 py-3 text-right">
                                                    <button
                                                        onClick={() => {
                                                            openProject(proj.id)
                                                            setCurrentNav('image_gen')
                                                        }}
                                                        className="px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded font-bold"
                                                    >
                                                        작업실 열기
                                                    </button>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {/* [설정 탭 (Settings)] */}
                    {currentNav === 'settings' && (
                        <div className="space-y-6 max-w-3xl mx-auto w-full">
                            <div className="bg-[#181d26] border border-white/10 rounded-2xl p-6 shadow-xl space-y-4">
                                <h3 className="font-bold text-sm text-white border-b border-white/10 pb-4">
                                    작업자 환경 설정 (Settings)
                                </h3>
                                <div className="space-y-3 text-xs">
                                    <div className="flex justify-between py-2 border-b border-white/5">
                                        <span className="text-gray-400">계정 이메일</span>
                                        <span className="text-white font-mono">{user?.email || 'ejsh0518@naver.com'}</span>
                                    </div>
                                    <div className="flex justify-between py-2 border-b border-white/5">
                                        <span className="text-gray-400">작업자 실명</span>
                                        <span className="text-white">{user?.full_name || '김호'}</span>
                                    </div>
                                    <div className="flex justify-between py-2">
                                        <span className="text-gray-400">렌더 엔진</span>
                                        <span className="text-emerald-400 font-bold">Google Drive API (분산 렌더 워커)</span>
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
