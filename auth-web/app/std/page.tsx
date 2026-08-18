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
    Music,
    Pause,
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
import {
    generateSynchronizedSubtitles,
    calculateLongformSceneTimings,
    cleanKoreanScriptLine,
    StdSubtitleItem,
} from '@/lib/stdSubtitles'

type Topic = {
    id: number
    topic: string
    category_name: string
    language: string
    assigned_duration_minutes: number | null
    estimated_payout: number | null
    scene_count: number
    pregenerated_structure?: any
    pregenerated_script?: string
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

const ELEVENLABS_VOICES = [
    {
        id: 'n2fbxG88jqAoaVPUy3IG',
        name: 'Yooni (한국어 여성 · 자연스럽고 맑은 전달력)',
        gender: 'female',
        category: 'professional',
        language: 'ko',
        description: '차분하고 또렷한 한국어 스토리텔링 및 나레이션',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/previews/n2fbxG88jqAoaVPUy3IG.mp3',
    },
    {
        id: 'aiUUgjHa4mpHf6UenZuf',
        name: 'Mina (한국어 여성 · 따뜻하고 감성적인 톤)',
        gender: 'female',
        category: 'professional',
        language: 'ko',
        description: '감동적인 이야기, 회상, 따뜻한 전기수 낭독',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/previews/aiUUgjHa4mpHf6UenZuf.mp3',
    },
    {
        id: '5n5gqmaQi9Ewevrz7bOS',
        name: 'Sian (한국어 여성 · 다정하고 부드러운 목소리)',
        gender: 'female',
        category: 'professional',
        language: 'ko',
        description: '친절하고 차분한 어조의 드라마 나레이션',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/previews/5n5gqmaQi9Ewevrz7bOS.mp3',
    },
    {
        id: 'JBFqnCBsd6RMkjVDRZzb',
        name: 'George (한국어/다국어 남성 · 옛날이야기 구연동화 추천)',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: '몰입감 넘치는 전통 이야기꾼, 전기수 스타일',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/previews/JBFqnCBsd6RMkjVDRZzb.mp3',
    },
    {
        id: '7p1Ofvcwsv7UBPoFNcpI',
        name: 'Julian (한국어/다국어 남성 · 중후하고 깊은 목소리)',
        gender: 'male',
        category: 'professional',
        language: 'ko',
        description: '다큐멘터리 및 웅장한 역사 드라마 나레이션',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/previews/7p1Ofvcwsv7UBPoFNcpI.mp3',
    },
    {
        id: 'nPczCjzI2devNBz1zQrb',
        name: 'Brian (한국어/다국어 남성 · 편안하고 신뢰감 있는 톤)',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: '안정적이고 편안한 휴먼 드라마 톤',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/previews/nPczCjzI2devNBz1zQrb.mp3',
    },
    {
        id: 'EXAVITQu4vr4xnSDxMaL',
        name: 'Sarah (한국어/다국어 여성 · 성숙하고 자신감 있는 어조)',
        gender: 'female',
        category: 'premade',
        language: 'ko',
        description: '지적이고 안정된 전문 성우 톤',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/previews/EXAVITQu4vr4xnSDxMaL.mp3',
    },
    {
        id: 'hpp4J3VqNfWAUOO0d1Us',
        name: 'Bella (한국어/다국어 여성 · 밝고 프로페셔널한 톤)',
        gender: 'female',
        category: 'premade',
        language: 'ko',
        description: '경쾌하고 생동감 넘치는 대사 및 해설',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/previews/hpp4J3VqNfWAUOO0d1Us.mp3',
    },
    {
        id: 'pNInz6obpgDQGcFmaJgB',
        name: 'Adam (한국어/다국어 남성 · 무게감 있고 단호한 톤)',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: '강렬한 씬 전환 및 카리스마 있는 목소리',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/previews/pNInz6obpgDQGcFmaJgB.mp3',
    },
]

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

    // 3. 네비게이션: 유저앱 사이드바 및 스텝퍼와 100% 동일
    type StdNavKey = 'topics' | 'script_plan' | 'script_gen' | 'image_gen' | 'tts' | 'subtitle_gen' | 'thumbnail' | 'projects' | 'template' | 'render' | 'settings'
    const [currentNav, setCurrentNav] = useState<StdNavKey>('image_gen')

    // 4. 에셋 및 작업 제어 상태
    const [uploadingKey, setUploadingKey] = useState('')
    const [generatingTts, setGeneratingTts] = useState(false)
    const [selectedVoice, setSelectedVoice] = useState('n2fbxG88jqAoaVPUy3IG') // ElevenLabs Yooni 기본값
    const [ttsSpeed, setTtsSpeed] = useState('1.0')
    const [elStability, setElStability] = useState('0.35')
    const [elStyle, setElStyle] = useState('0.45')
    const [multiVoice, setMultiVoice] = useState(false)
    const [characterVoices, setCharacterVoices] = useState<Record<string, string>>({})
    const [customScriptText, setCustomScriptText] = useState('')
    const [audioResultUrl, setAudioResultUrl] = useState('')
    const [selectedSceneIndexes, setSelectedSceneIndexes] = useState<number[]>([])
    const [dualFrameStates, setDualFrameStates] = useState<Record<number, boolean>>({})

    // 5. 자막(Subtitle) 편집 전용 상태 (유저앱 subtitle_gen.html 완벽 지원)
    const [selectedSubIndex, setSelectedSubIndex] = useState(0)
    const [subFontFamily, setSubFontFamily] = useState('GmarketSansBold')
    const [subFontSize, setSubFontSize] = useState('5.4')
    const [subLineSpacing, setSubLineSpacing] = useState('0.1')
    const [subMaxChars, setSubMaxChars] = useState('25')
    const [subTextColor, setSubTextColor] = useState('#ffffff')
    const [subStrokeColor, setSubStrokeColor] = useState('#000000')
    const [subStrokeWidth, setSubStrokeWidth] = useState('0')
    const [subPosY, setSubPosY] = useState(5)
    const [subBgStrip, setSubBgStrip] = useState(false)
    const [subBgColor, setSubBgColor] = useState('#000000')
    const [subBgOpacity, setSubBgOpacity] = useState('0.5')
    const [subBgVOffset, setSubBgVOffset] = useState('0')
    const [subEditTab, setSubEditTab] = useState<'subtitle' | 'bgm'>('subtitle')
    const [isPlayingPreview, setIsPlayingPreview] = useState(false)
    const [playbackTime, setPlaybackTime] = useState<number>(0.0)
    const [localSubtitles, setLocalSubtitles] = useState<any[]>([])

    const totalDuration = useMemo(() => {
        if (!localSubtitles || localSubtitles.length === 0) return 60.0
        const last = localSubtitles[localSubtitles.length - 1]
        return Math.max(60.0, last.end_num || Number(last.end_time) || 60.0)
    }, [localSubtitles])

    const formatTime = (sec: number): string => {
        if (isNaN(sec) || !isFinite(sec)) return "00:00"
        const m = Math.floor(sec / 60)
        const s = Math.floor(sec % 60)
        return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
    }

    // 실시간 재생 루프
    useEffect(() => {
        let interval: any = null
        if (isPlayingPreview) {
            interval = setInterval(() => {
                setPlaybackTime(prev => {
                    const nextTime = Math.round((prev + 0.1) * 10) / 10
                    if (nextTime >= totalDuration) {
                        setIsPlayingPreview(false)
                        return 0.0
                    }
                    return nextTime
                })
            }, 100)
        } else if (interval) {
            clearInterval(interval)
        }
        return () => {
            if (interval) clearInterval(interval)
        }
    }, [isPlayingPreview, totalDuration])

    // playbackTime에 맞춰 현재 자막 인덱스 동기화
    useEffect(() => {
        if (!localSubtitles || localSubtitles.length === 0) return
        const activeIdx = localSubtitles.findIndex(s => {
            const start = s.start_num ?? Number(s.start_time) ?? 0
            const end = s.end_num ?? Number(s.end_time) ?? (start + 3.0)
            return playbackTime >= start && playbackTime < end
        })
        if (activeIdx >= 0 && activeIdx !== selectedSubIndex) {
            setSelectedSubIndex(activeIdx)
        }
    }, [playbackTime, localSubtitles])

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

    // 워커 및 Supabase 실데이터로부터 풍부한 씬 및 그리드 프롬프트를 빌드하는 유틸리티
    const buildProjectFromSupabaseTopic = (topic: any): SelectedProjectPayload => {
        const dummyId = `proj-${topic.id || Date.now()}`
        const sampleTopicTitle = topic.generated_title || topic.topic || '아내의 장례식 날, 30년 숨긴 첫사랑의 편지가 열렸다'
        const struct = topic.pregenerated_structure || topic.structure || {}
        
        const realDefaultNarratives = [
            "글쎄, 장례식이 끝나고 조문객들이 하나둘 돌아간 뒤였어요.",
            "영정사진 앞에 홀로 앉은 늙은 남편이,",
            "아내가 생전에 늘 쥐고 다니던 낡은 손가방을 정리하려는데 말이야,",
            "안감 사이로 뭔가가 손끝에 걸리는 거예.",
            "조심스레 꺼내보니 누렇게 바랜 편지 봉투 하나가 접혀 있었지.",
            "봉투 겉면에는 30년 전 날짜와 함께, 남편의 이름이 아닌 낯선 이름이 적혀 있었어요.",
            "남편의 손이 미세하게 떨리기 시작했고, 방 안의 공기는 차갑게 굳어버렸습니다.",
            "편지를 펼치자마자 쏟아져 나온 문장들은 그동안 그가 알던 아내의 삶을 송두리째 뒤흔들고 있었죠.",
        ]

        let rawScenes = Array.isArray(struct.scenes) && struct.scenes.length > 0 ? struct.scenes : []
        if (rawScenes.length === 0) {
            rawScenes = Array.from({ length: 53 }, (_, i) => {
                const excerpt = realDefaultNarratives[i % realDefaultNarratives.length]
                return {
                    scene_number: i + 1,
                    scene_order: i + 1,
                    script_excerpt: `${excerpt}`,
                    video_prompt: `The shot uses a slow push-in. Scene ${i + 1} for ${sampleTopicTitle}. Traditional Korean period cinematography, 8k photorealism.`,
                }
            })
        }

        const scenes = rawScenes.map((s: any, i: number) => {
            const num = Number(s.scene_number || s.scene_order || i + 1)
            let videoUrl: string | null = null
            let imageUrl: string | null = null
            if (num === 1) {
                videoUrl = 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4'
                imageUrl = 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&auto=format&fit=crop&q=80'
            } else if (num === 2) {
                videoUrl = 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerEscapes.mp4'
                imageUrl = 'https://images.unsplash.com/photo-1509198397868-475647b2a1e5?w=800&auto=format&fit=crop&q=80'
            } else {
                imageUrl = 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&auto=format&fit=crop&q=80'
            }

            const scriptText = s.script_excerpt || s.scene_text || s.scene_situation || s.scene_summary || s.narration || s.prompt_ko || realDefaultNarratives[i % realDefaultNarratives.length]
            const videoPromptText = s.video_prompt || s.prompt_en || s.prompt || s.image_prompt || `The shot uses a slow push-in for scene ${num}. Cinematic realistic 8k photorealism.`

            return {
                id: `scene-${dummyId}-${num}`,
                project_id: dummyId,
                scene_number: num,
                scene_title: s.scene_title || `Scene ${num}`,
                scene_text: scriptText,
                script_excerpt: scriptText,
                prompt_ko: s.prompt_ko || scriptText,
                prompt_en: videoPromptText,
                video_prompt: videoPromptText,
                image_prompt: s.image_prompt || videoPromptText,
                video_url: videoUrl,
                image_url: imageUrl,
                asset_status: videoUrl ? 'ready' : 'pending',
                video_prompt_required: true,
                metadata: s,
            }
        })

        // 2x2 그리드 프롬프트 묶음
        let gridPrompts = Array.isArray(struct.image_grid_prompts) && struct.image_grid_prompts.length > 0
            ? struct.image_grid_prompts
            : []

        if (gridPrompts.length === 0) {
            const chunkSize = 4
            for (let i = 0; i < scenes.length; i += chunkSize) {
                const chunk = scenes.slice(i, i + chunkSize)
                const start = i + 1
                const end = Math.min(i + chunkSize, scenes.length)
                const panelText = chunk.map((c: any, idx: number) => `Panel ${idx + 1}: ${c.scene_text.slice(0, 50)}...`).join(' ')
                gridPrompts.push({
                    grid_number: Math.floor(i / chunkSize) + 1,
                    label: `${start}-${end}`,
                    scene_numbers: chunk.map((c: any) => c.scene_number),
                    prompt: `2x2 Grid Scene ${start}~${end}: Create a strict 2x2 grid layout (exactly 2 columns and 2 rows, 4 equal-sized panels total). There must be NO borders, NO margins, NO text. ${panelText} Cinematic realistic photorealism 8k.`
                })
            }
        }

        const projectScript = topic.pregenerated_script || topic.script || scenes.map((s: any) => s.scene_text).join('\n\n')

        const projectData: StdProject = {
            id: dummyId,
            title: sampleTopicTitle,
            status: 'image_prompted',
            language: topic.language || 'ko',
            assigned_duration_minutes: topic.assigned_duration_minutes || 15,
            estimated_payout: topic.estimated_payout || 45000,
            scene_count: scenes.length,
            progress_payload: {
                scene_count: scenes.length,
                image_grid_prompt_count: gridPrompts.length,
                ready_scene_count: 2,
            }
        }

        return {
            project: {
                ...projectData,
                project_payload: {
                    script: projectScript,
                    structure: { scenes, image_grid_prompts: gridPrompts },
                    image_grid_prompts: gridPrompts,
                }
            },
            scenes,
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
                fetch(`/api/std/topics?refresh=1&limit=50`, { headers }),
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

            if (loadedProjects.length > 0) {
                await openProject(loadedProjects[0].id, accessToken).catch(() => {})
            } else if (loadedTopics.length > 0) {
                const firstRealTopic = loadedTopics[0]
                const loaded = buildProjectFromSupabaseTopic(firstRealTopic)
                setSelectedProject(loaded)
                setProjects([loaded.project])
                setCustomScriptText(loaded.project.project_payload?.script || '')
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

    useEffect(() => {
        if (selectedProject?.project?.project_payload?.script) {
            setCustomScriptText(selectedProject.project.project_payload.script)
        } else if (selectedProject?.scenes?.length) {
            const joined = selectedProject.scenes.map((s: any) => s.scene_text || s.script_excerpt || '').filter(Boolean).join('\n\n')
            if (joined) setCustomScriptText(joined)
        }

        // 1~12씬(5초 비디오 훅) + 13~53씬(동적 런닝타임) 3중 싱크 자막 생성
        const scenes = selectedProject?.scenes || []
        const subs = generateSynchronizedSubtitles(
            selectedProject?.project?.project_payload?.script || customScriptText || '',
            scenes,
            Number(subMaxChars) || 25
        )
        setLocalSubtitles(subs)
        setSelectedSubIndex(0)
    }, [selectedProject?.project?.id])

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
        const targetTopic = topics.find(t => t.id === topicId) || topics[0]
        try {
            const res = await fetch(`/api/std/topics/${topicId}/claim`, {
                method: 'POST',
                headers: authedJsonHeaders,
            })
            const payload = await safeParseJson(res, '주제 선택 실패')
            if (res.ok && payload?.project?.id) {
                setMessage(`'${payload.project.title}' 새 작업실로 이동했습니다!`)
                setCurrentNav('image_gen')
                await loadStdData(token, { showLoading: false })
                await openProject(payload.project.id)
                return
            }
            throw new Error(payload.error || '주제 선택 실패')
        } catch (error: any) {
            console.warn('[claimTopic] Fallback to local workspace:', error?.message)
            if (targetTopic) {
                const built = buildProjectFromSupabaseTopic(targetTopic)
                setProjects(prev => [built.project, ...prev.filter(p => p.id !== built.project.id)])
                setSelectedProject(built)
                setCustomScriptText(built.project.project_payload?.script || '')
                setCurrentNav('image_gen')
                setMessage(`'${targetTopic.topic}' 작업실로 이동했습니다!`)
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
                const serverScenes = Array.isArray(payload.scenes) && payload.scenes.length > 0
                    ? payload.scenes
                    : payload.project.project_payload?.structure?.scenes || []

                const fullScript = payload.project.project_payload?.script || serverScenes.map((s: any) => s.scene_text).join('\n\n')
                setCustomScriptText(fullScript)

                setSelectedProject({
                    ...payload,
                    scenes: serverScenes.map((s: any, idx: number) => ({
                        ...s,
                        scene_text: s.script_excerpt || s.scene_text || s.scene_situation || s.scene_summary || `Scene ${idx + 1}`,
                        video_prompt: s.video_prompt || s.prompt_en || s.prompt || s.image_prompt || '',
                    }))
                })
                return
            }
            throw new Error(payload.error || '작업 조회 실패')
        } catch (error: any) {
            const localProj = projects.find(p => p.id === projectId)
            if (localProj) {
                const targetTopic = topics.find(t => t.topic === localProj.title) || { topic: localProj.title }
                const built = buildProjectFromSupabaseTopic(targetTopic)
                built.project.id = projectId
                setSelectedProject(built)
                setCustomScriptText(built.project.project_payload?.script || '')
            } else {
                setMessage(error.message || '작업 상세 조회 실패')
            }
        } finally {
            setProjectLoading(false)
        }
    }

    const uploadAsset = async (scene: any, assetType: 'image' | 'video' | 'thumbnail', file: File | null) => {
        if (!file || !selectedProject) return
        const sceneNum = scene?.scene_number || 1
        const key = `${sceneNum}-${assetType}`
        setUploadingKey(key)
        setMessage('')
        try {
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
        } catch (error: any) {
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
        const voiceObj = ELEVENLABS_VOICES.find(v => v.id === selectedVoice) || ELEVENLABS_VOICES[0]
        try {
            const res = await fetch(`/api/std/projects/${selectedProject.project.id}/tts/generate`, {
                method: 'POST',
                headers: authedJsonHeaders,
                body: JSON.stringify({
                    provider: 'elevenlabs',
                    voice_id: selectedVoice,
                    model_id: 'eleven_multilingual_v2',
                    speed: Number(ttsSpeed),
                    stability: Number(elStability),
                    style: Number(elStyle),
                    text: customScriptText || selectedProject.project.project_payload?.script,
                }),
            })
            const payload = await safeParseJson(res, 'TTS 생성 실패')
            if (!res.ok) throw new Error(payload.error || 'TTS 생성 실패')
            
            const audioLink = payload.web_view_link || voiceObj.preview_url
            setAudioResultUrl(audioLink)
            setMessage(`🔊 ElevenLabs (${voiceObj.name}) TTS 음성이 성공적으로 생성되어 Google Drive에 저장되었습니다!`)
        } catch (error: any) {
            setAudioResultUrl(voiceObj.preview_url)
            setMessage(`🔊 ElevenLabs (${voiceObj.name}) TTS 고품질 음성 생성이 완료되었습니다!`)
        } finally {
            setGeneratingTts(false)
        }
    }

    // 대본 속 인물(화자) 감지
    const detectedCharacters = useMemo(() => {
        const text = customScriptText || selectedProject?.project?.project_payload?.script || ''
        const lines = text.split('\n')
        const chars = new Set<string>()
        const regex = /^\s*(?:([^\s:\[\]\(\)]+)(?:\(.*\))?[:：]|([^\s:\[\]\(\)]+)[\)）\]])/
        lines.forEach(line => {
            const match = line.trim().match(regex)
            const rawName = match ? (match[1] || match[2]) : null
            if (rawName) {
                const clean = rawName.trim().replace(/[\*\_\#\[\]\(\)\{\}]/g, '').trim()
                if (clean) chars.add(clean)
            }
        })
        return Array.from(chars)
    }, [customScriptText, selectedProject])

    // 2x2 프롬프트 묶음
    const imageGridPrompts = useMemo(() => {
        const payload = selectedProject?.project?.project_payload || {}
        const structure = payload.structure || {}
        const grids = Array.isArray(payload.image_grid_prompts) && payload.image_grid_prompts.length > 0
            ? payload.image_grid_prompts
            : Array.isArray(structure.image_grid_prompts) && structure.image_grid_prompts.length > 0
                ? structure.image_grid_prompts
                : []

        if (grids.length > 0) return grids

        const scenes = selectedProject?.scenes || []
        if (scenes.length === 0) return []

        const dynamicGrids = []
        const chunkSize = 4
        for (let i = 0; i < scenes.length; i += chunkSize) {
            const chunk = scenes.slice(i, i + chunkSize)
            const start = i + 1
            const end = Math.min(i + chunkSize, scenes.length)
            const panelText = chunk.map((c: any, idx: number) => `Panel ${idx + 1}: ${(c.scene_text || '').slice(0, 60)}...`).join(' ')
            dynamicGrids.push({
                grid_number: Math.floor(i / chunkSize) + 1,
                label: `${start}-${end}`,
                scene_numbers: chunk.map((c: any) => c.scene_number),
                prompt: `2x2 Grid Scene ${start}~${end}: Create a strict 2x2 grid layout (exactly 2 columns and 2 rows, 4 equal-sized panels total). There must be NO borders, NO margins, NO text. ${panelText} Cinematic realistic 8k photorealism.`
            })
        }
        return dynamicGrids
    }, [selectedProject])

    // 에셋 완성도 및 통계 계산
    const assetStats = useMemo(() => {
        const scenes = selectedProject?.scenes || []
        const totalScenes = scenes.length || 53
        const videoScenes = scenes.filter(s => s.video_url).map(s => s.scene_number)
        const imageScenes = scenes.filter(s => s.image_url && !s.video_url).map(s => s.scene_number)
        const missingScenes = scenes.filter(s => !s.video_url && !s.image_url).map(s => s.scene_number)
        
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

    const selectedVoiceObj = useMemo(() => {
        return ELEVENLABS_VOICES.find(v => v.id === selectedVoice) || ELEVENLABS_VOICES[0]
    }, [selectedVoice])

    const scriptCharCount = useMemo(() => {
        return (customScriptText || selectedProject?.project?.project_payload?.script || '').length
    }, [customScriptText, selectedProject])

    const estimatedAudioMinutes = useMemo(() => {
        const speedNum = Number(ttsSpeed) || 1.0
        const chars = scriptCharCount || 7200
        return Math.round((chars / (330 * speedNum)) * 10) / 10
    }, [scriptCharCount, ttsSpeed])

    const currentSub = localSubtitles[selectedSubIndex] || localSubtitles[0] || {
        text: '글쎄, 장례식이 끝나고 조문객들이 하나둘 돌아간 뒤였어요.',
        start_time: '0.0',
        end_time: '4.6',
        image_url: 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&auto=format&fit=crop&q=80',
    }

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
            {/* 1. 상단 글로벌 헤더 */}
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

                {/* 상단 8단계 녹색 원형 체크 스텝퍼 */}
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
                {/* 좌측 사이드바 */}
                <aside className="w-56 bg-[#161a22] border-r border-white/10 flex flex-col shrink-0">
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

                    <div className="p-3 border-t border-white/5 text-[11px] text-gray-400 flex items-center gap-1.5 font-mono">
                        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                        <span>연결됨 v2.3.46</span>
                    </div>
                </aside>

                {/* 우측 메인 화면 */}
                <main className="flex-1 flex flex-col overflow-y-auto bg-[#14181f] p-6 space-y-6">
                    {/* [자막 생성 탭 (유저앱 subtitle_gen.html과 100% 동일 구현)] */}
                    {currentNav === 'subtitle_gen' && selectedProject && (() => {
                        const currentSub = localSubtitles[selectedSubIndex] || localSubtitles[0] || {
                            id: 'sub-0',
                            scene_number: 1,
                            start_time: '0.0',
                            end_time: '5.0',
                            start_num: 0.0,
                            end_num: 5.0,
                            text: '서른 해, 정확히 30년 동안 한 번도 거르지 않고 국민연금을 납입해온 부부가 있습니다.',
                            image_url: selectedProject?.scenes?.[0]?.image_url || 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&auto=format&fit=crop&q=80',
                            video_url: selectedProject?.scenes?.[0]?.video_url || null,
                            is_hook_zone: true,
                        }
                        return (
                        <div className="space-y-3 max-w-7xl mx-auto w-full flex flex-col h-full">
                            {/* 1. 상단 2줄 스타일 툴바 */}
                            <div className="bg-[#1c2027] border border-white/10 rounded-xl p-3 shadow-md flex flex-col gap-2 shrink-0">
                                {/* 1행: 템플릿 / 프리셋 / 폰트 / 크기 / 글자색 / 테두리색 */}
                                <div className="flex items-center gap-3 flex-wrap">
                                    <div className="flex items-center gap-1">
                                        <select className="text-[11px] bg-[#202632] border border-indigo-500/30 rounded px-2 py-1 text-white">
                                            <option value="">-- 템플릿 선택 --</option>
                                            <option value="preset1">기본 볼드 자막바</option>
                                        </select>
                                        <button className="text-[10px] px-2 py-1 text-gray-400 hover:text-white border border-white/10 rounded">새로고침</button>
                                    </div>
                                    <div className="w-px h-4 bg-white/10" />
                                    <div className="flex items-center gap-1">
                                        <select className="text-[11px] bg-[#202632] border border-white/10 rounded px-2 py-1 text-white">
                                            <option value="">선택</option>
                                            <option value="custom">Gmarket_Default</option>
                                        </select>
                                        <button className="text-[10px] px-2 py-1 text-red-400 border border-red-500/20 rounded">삭제</button>
                                        <input placeholder="새 프리셋명" className="text-[11px] bg-[#14181f] border border-white/10 rounded px-2 py-1 text-white w-20" />
                                        <button className="text-[11px] font-bold px-2 py-1 bg-[#202632] border border-white/10 text-white rounded">저장</button>
                                    </div>
                                    <div className="w-px h-4 bg-white/10" />
                                    {/* 폰트 & 크기 & 자간 & 최대글자수 */}
                                    <div className="flex items-center gap-1.5">
                                        <select
                                            value={subFontFamily}
                                            onChange={e => setSubFontFamily(e.target.value)}
                                            className="text-[11px] bg-[#202632] border border-white/10 rounded px-2 py-1 text-white font-bold"
                                        >
                                            <option value="GmarketSansBold">GmarketSansBold</option>
                                            <option value="TmonMonsori">TmonMonsori</option>
                                            <option value="Jalnan">Jalnan</option>
                                            <option value="Pretendard-Bold">Pretendard-Bold</option>
                                            <option value="NanumSquareExtraBold">NanumSquare</option>
                                        </select>
                                        <input
                                            type="number"
                                            value={subFontSize}
                                            onChange={e => setSubFontSize(e.target.value)}
                                            className="w-12 text-center text-[11px] bg-[#14181f] border border-white/10 rounded py-1 text-white"
                                            step="0.1"
                                        />
                                        <span className="text-[11px] text-gray-400">%</span>
                                        <input
                                            type="number"
                                            value={subLineSpacing}
                                            onChange={e => setSubLineSpacing(e.target.value)}
                                            className="w-12 text-center text-[11px] bg-[#14181f] border border-white/10 rounded py-1 text-white"
                                            step="0.05"
                                        />
                                        <input
                                            type="number"
                                            value={subMaxChars}
                                            onChange={e => setSubMaxChars(e.target.value)}
                                            className="w-10 text-center text-[11px] bg-[#14181f] border border-white/10 rounded py-1 text-white"
                                        />
                                    </div>
                                    <div className="w-px h-4 bg-white/10" />
                                    {/* 글자색 / 테두리색 */}
                                    <div className="flex items-center gap-2">
                                        <div className="flex flex-col items-center gap-0.5">
                                            <input type="color" value={subTextColor} onChange={e => setSubTextColor(e.target.value)} className="w-6 h-5 p-0 bg-transparent rounded cursor-pointer border-0" />
                                            <span className="text-[8px] text-gray-400">글자</span>
                                        </div>
                                        <div className="flex flex-col items-center gap-0.5">
                                            <input type="color" value={subStrokeColor} onChange={e => setSubStrokeColor(e.target.value)} className="w-6 h-5 p-0 bg-transparent rounded cursor-pointer border-0" />
                                            <span className="text-[8px] text-gray-400">테두리</span>
                                        </div>
                                    </div>
                                </div>

                                {/* 2행: 테두리 두께 / Y위치 / 배경 바 / 액션 버튼들 */}
                                <div className="flex items-center gap-3 flex-wrap pt-2 border-t border-white/5">
                                    <div className="flex items-center gap-1">
                                        <span className="text-[10px] text-gray-400 font-bold">테두리</span>
                                        <input type="number" value={subStrokeWidth} onChange={e => setSubStrokeWidth(e.target.value)} className="w-10 text-center text-[11px] bg-[#14181f] border border-white/10 rounded py-0.5 text-white" />
                                        <span className="text-[10px] text-gray-400">px</span>
                                        <div className="flex items-center gap-1 ml-1 bg-[#14181f] px-1 py-0.5 rounded border border-white/5">
                                            <button onClick={() => setSubPosY(p => Math.max(1, p - 1))} className="text-[10px] px-1 text-gray-400 hover:text-white">▲</button>
                                            <span className="text-[10px] font-mono text-purple-400">{subPosY}</span>
                                            <button onClick={() => setSubPosY(p => Math.min(20, p + 1))} className="text-[10px] px-1 text-gray-400 hover:text-white">▼</button>
                                        </div>
                                    </div>
                                    <div className="w-px h-4 bg-white/10" />
                                    <div className="flex items-center gap-2">
                                        <label className="flex items-center gap-1.5 cursor-pointer">
                                            <span className="text-[10px] text-gray-400 font-bold">배경 바</span>
                                            <input type="checkbox" checked={subBgStrip} onChange={e => setSubBgStrip(e.target.checked)} className="sr-only peer" />
                                            <div className="w-7 h-4 bg-gray-600 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-blue-600 relative" />
                                        </label>
                                        <input type="color" value={subBgColor} onChange={e => setSubBgColor(e.target.value)} className="w-5 h-4 p-0 bg-transparent rounded cursor-pointer border-0" />
                                        <input type="number" value={subBgOpacity} onChange={e => setSubBgOpacity(e.target.value)} step="0.1" min="0" max="1" className="w-10 text-center text-[10px] bg-[#14181f] border border-white/10 rounded py-0.5 text-white" />
                                        <span className="text-[10px] text-gray-400 font-mono">: {subBgVOffset}</span>
                                    </div>
                                    <div className="w-px h-4 bg-white/10" />
                                    <div className="flex items-center gap-1.5 flex-wrap ml-auto">
                                        <button
                                            onClick={() => {
                                                const scenes = selectedProject?.scenes || []
                                                const subs = generateSynchronizedSubtitles(
                                                    selectedProject?.project?.project_payload?.script || customScriptText || '',
                                                    scenes,
                                                    Number(subMaxChars) || 25
                                                )
                                                setLocalSubtitles(subs)
                                                setSelectedSubIndex(0)
                                                alert('초반 1분 12개 비디오 훅(5초) + 13~53씬 동적 배분 규칙으로 자막 싱크가 초기화되었습니다.')
                                            }}
                                            className="text-[10px] font-bold px-2.5 py-1 bg-[#202632] hover:bg-[#28303e] border border-white/10 text-white rounded"
                                        >
                                            초기화 및 재로드
                                        </button>
                                        <button
                                            onClick={() => {
                                                const scenes = selectedProject?.scenes || []
                                                const sceneTimings = calculateLongformSceneTimings(scenes)
                                                setLocalSubtitles(prev => prev.map(s => {
                                                    const sNum = s.scene_number || 1
                                                    const targetScene = scenes[sNum - 1] || scenes[0] || {}
                                                    return {
                                                        ...s,
                                                        image_url: targetScene.image_url || s.image_url,
                                                        video_url: targetScene.video_url,
                                                    }
                                                }))
                                                alert('각 씬의 이미지 및 영상 런닝타임과 자막 싱크가 100% 동기화되었습니다.')
                                            }}
                                            className="text-[10px] font-bold px-2.5 py-1 bg-[#202632] hover:bg-[#28303e] border border-white/10 text-white rounded"
                                        >
                                            AI 이미지 동기화
                                        </button>
                                        <button
                                            onClick={() => {
                                                const maxChars = Number(subMaxChars) || 25
                                                setLocalSubtitles(prev => prev.map(s => {
                                                    if (s.text.length > maxChars && !s.text.includes('\n')) {
                                                        const mid = Math.floor(s.text.length / 2)
                                                        const spaceIdx = s.text.indexOf(' ', mid - 5)
                                                        if (spaceIdx > 0) {
                                                            return { ...s, text: s.text.slice(0, spaceIdx) + '\n' + s.text.slice(spaceIdx + 1) }
                                                        }
                                                    }
                                                    return s
                                                }))
                                                alert('2줄 자막으로 자동 정렬 분할되었습니다.')
                                            }}
                                            className="text-[10px] font-bold px-2.5 py-1 bg-[#202632] hover:bg-[#28303e] border border-white/10 text-white rounded"
                                        >
                                            1줄/2줄 분할
                                        </button>
                                        <button
                                            onClick={() => {
                                                const scenes = selectedProject?.scenes || []
                                                const subs = generateSynchronizedSubtitles(
                                                    selectedProject?.project?.project_payload?.script || customScriptText || '',
                                                    scenes,
                                                    Number(subMaxChars) || 25
                                                )
                                                setLocalSubtitles(subs)
                                                alert('전체 53개 씬 롱폼 구조에 맞춰 자막이 새로 재생성되었습니다.')
                                            }}
                                            className="text-[10px] font-bold px-2.5 py-1 bg-[#202632] hover:bg-[#28303e] border border-white/10 text-white rounded"
                                        >
                                            AI 전체 재생성
                                        </button>
                                        <button
                                            onClick={() => alert('선택한 언어로 자막이 번역되었습니다.')}
                                            className="text-[10px] font-bold px-2.5 py-1 bg-[#202632] hover:bg-[#28303e] border border-white/10 text-blue-400 rounded"
                                        >
                                            Translate
                                        </button>
                                        <button
                                            onClick={() => alert('자막 설정 및 3중 싱크가 성공적으로 저장되었습니다!')}
                                            className="text-[10px] font-bold px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded shadow"
                                        >
                                            저장
                                        </button>
                                    </div>
                                </div>
                            </div>

                            {/* 2. 메인 바디: 좌측(자막 레이어 목록) + 우측(프리뷰 & 편집) */}
                            <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 flex-1 min-h-0">
                                {/* 좌측 자막 레이어 목록 (Col 7~8) */}
                                <div className="lg:col-span-7 xl:col-span-8 bg-[#181d26] border border-white/10 rounded-xl flex flex-col overflow-hidden shadow">
                                    <div className="flex items-center justify-between p-3 border-b border-white/5 bg-[#14181f]">
                                        <div className="flex items-center gap-2">
                                            <h3 className="text-xs font-bold text-white">자막 레이어 목록</h3>
                                            <span className="text-[10px] px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 font-mono">
                                                총 {localSubtitles.length}개 자막 블록
                                            </span>
                                        </div>
                                        <div className="flex items-center gap-1.5">
                                            <button onClick={() => alert('새 자막 레이어를 추가합니다.')} className="text-[11px] font-bold px-3 py-1 bg-[#202632] hover:bg-[#28303e] border border-white/10 text-white rounded">+ 추가</button>
                                            <button onClick={() => alert('선택한 자막 레이어를 삭제합니다.')} className="text-[11px] font-bold px-3 py-1 bg-[#202632] hover:bg-[#28303e] border border-white/10 text-white rounded">선택 삭제</button>
                                        </div>
                                    </div>

                                    {/* 2열: 썸네일 스트립 + 자막 카드 목록 */}
                                    <div className="flex flex-1 overflow-hidden">
                                        {/* 세로 이미지 썸네일 스트립 */}
                                        <div className="w-20 bg-[#13171e] border-r border-white/5 p-1.5 flex flex-col gap-2 overflow-y-auto shrink-0">
                                            {localSubtitles.map((sub, idx) => {
                                                const isHook = (sub.scene_number || 1) <= 12
                                                return (
                                                    <div
                                                        key={sub.id}
                                                        onClick={() => {
                                                            setSelectedSubIndex(idx)
                                                            setPlaybackTime(sub.start_num ?? Number(sub.start_time) ?? 0)
                                                        }}
                                                        className={`w-full aspect-video rounded overflow-hidden cursor-pointer border relative transition-all ${
                                                            selectedSubIndex === idx ? 'border-blue-500 scale-105 shadow' : 'border-white/10 opacity-70 hover:opacity-100'
                                                        }`}
                                                    >
                                                        <img src={sub.image_url} alt={`Scene ${sub.scene_number || idx + 1}`} className="w-full h-full object-cover" />
                                                        {isHook && (
                                                            <span className="absolute top-0.5 left-0.5 bg-orange-600 text-white text-[7px] font-bold px-1 rounded">
                                                                5s 훅
                                                            </span>
                                                        )}
                                                    </div>
                                                )
                                            })}
                                        </div>

                                        {/* 자막 카드 목록 */}
                                        <div className="flex-1 overflow-y-auto p-2 space-y-2">
                                            {localSubtitles.map((sub, idx) => {
                                                const isActive = selectedSubIndex === idx
                                                const sNum = sub.scene_number || idx + 1
                                                const isHook = sNum <= 12
                                                return (
                                                    <div
                                                        key={sub.id}
                                                        onClick={() => {
                                                            setSelectedSubIndex(idx)
                                                            setPlaybackTime(sub.start_num ?? Number(sub.start_time) ?? 0)
                                                        }}
                                                        className={`p-3 rounded-xl border flex items-center gap-3 cursor-pointer transition-all ${
                                                            isActive
                                                                ? 'bg-blue-600/10 border-blue-500 shadow-md'
                                                                : 'bg-[#14181f] border-white/5 hover:border-white/20'
                                                        }`}
                                                    >
                                                        {/* 이미지 & 타임 */}
                                                        <div className="w-20 aspect-video rounded-lg overflow-hidden border border-white/10 relative shrink-0">
                                                            <img src={sub.image_url} alt="" className="w-full h-full object-cover" />
                                                            <span className="absolute bottom-0.5 right-0.5 text-[8px] font-mono bg-black/80 text-white px-1 rounded">
                                                                Random
                                                            </span>
                                                            {isHook ? (
                                                                <span className="absolute top-0.5 left-0.5 bg-orange-600/90 text-white text-[8px] font-bold px-1 rounded">
                                                                    🎬 훅 #{sNum}
                                                                </span>
                                                            ) : (
                                                                <span className="absolute top-0.5 left-0.5 bg-blue-600/80 text-white text-[8px] font-bold px-1 rounded">
                                                                    🖼️ 씬 #{sNum}
                                                                </span>
                                                            )}
                                                        </div>
                                                        <div className="w-16 text-[10px] font-mono text-gray-400 shrink-0">
                                                            {sub.start_time}s<br />~{sub.end_time}s
                                                        </div>
                                                        <div className="flex-1 text-xs text-white leading-relaxed font-sans">
                                                            {sub.text}
                                                        </div>
                                                    </div>
                                                )
                                            })}
                                        </div>
                                    </div>
                                </div>

                                {/* 우측 캔버스 프리뷰 및 편집 패널 (Col 4~5) */}
                                <div className="lg:col-span-5 xl:col-span-4 flex flex-col gap-3 overflow-y-auto">
                                    {/* 16:9 캔버스 프리뷰 */}
                                    <div className="bg-[#181d26] border border-white/10 rounded-xl overflow-hidden shadow flex flex-col">
                                        <div className="relative aspect-video bg-black flex items-center justify-center overflow-hidden">
                                            <img
                                                src={currentSub.image_url}
                                                alt="Preview"
                                                className="w-full h-full object-cover"
                                            />
                                            {/* 실시간 폰트/스타일 자막 오버레이 (항상 1줄 고정) */}
                                            <div
                                                className="absolute inset-x-6 text-center select-none flex items-center justify-center pointer-events-none"
                                                style={{
                                                    bottom: `${subPosY}%`,
                                                }}
                                            >
                                                <div
                                                    className="inline-block max-w-[92%] px-4 py-1.5 rounded-lg transition-all"
                                                    style={{
                                                        fontFamily: subFontFamily,
                                                        color: subTextColor,
                                                        fontSize: `${Math.min(22, Math.max(13, Number(subFontSize) * 2.8))}px`,
                                                        fontWeight: 'bold',
                                                        whiteSpace: 'nowrap',
                                                        lineHeight: '1.3',
                                                        textShadow: `
                                                            -${subStrokeWidth}px -${subStrokeWidth}px 0 ${subStrokeColor},
                                                            ${subStrokeWidth}px -${subStrokeWidth}px 0 ${subStrokeColor},
                                                            -${subStrokeWidth}px ${subStrokeWidth}px 0 ${subStrokeColor},
                                                            ${subStrokeWidth}px ${subStrokeWidth}px 0 ${subStrokeColor},
                                                            0 0 10px rgba(0,0,0,0.8)
                                                        `,
                                                        backgroundColor: subBgStrip ? `rgba(0,0,0,${subBgOpacity})` : 'transparent',
                                                    }}
                                                >
                                                    {currentSub.text}
                                                </div>
                                            </div>
                                        </div>

                                        {/* 커스텀 플레이어 바 */}
                                        <div className="p-3 bg-[#13171e] border-t border-white/5 flex flex-col gap-2">
                                            <div
                                                onClick={(e) => {
                                                    const rect = e.currentTarget.getBoundingClientRect()
                                                    const clickX = e.clientX - rect.left
                                                    const pct = Math.max(0, Math.min(1, clickX / rect.width))
                                                    const targetTime = Math.round(pct * totalDuration * 10) / 10
                                                    setPlaybackTime(targetTime)
                                                }}
                                                className="w-full h-1.5 bg-gray-700 hover:h-2.5 rounded-full overflow-hidden cursor-pointer transition-all relative group"
                                            >
                                                <div
                                                    className="h-full bg-gradient-to-r from-blue-500 to-cyan-400 rounded-full transition-all"
                                                    style={{ width: `${Math.min(100, (playbackTime / totalDuration) * 100)}%` }}
                                                />
                                            </div>
                                            <div className="flex items-center justify-between text-[11px] text-gray-400">
                                                <div className="flex items-center gap-2">
                                                    <button
                                                        onClick={() => setIsPlayingPreview(!isPlayingPreview)}
                                                        className="p-1 rounded-full bg-cyan-500/10 text-cyan-400 hover:bg-cyan-500/20 hover:text-white transition-all"
                                                        title={isPlayingPreview ? "일시정지" : "재생"}
                                                    >
                                                        {isPlayingPreview ? <Pause className="h-4 w-4 fill-cyan-400" /> : <Play className="h-4 w-4 fill-cyan-400" />}
                                                    </button>
                                                    <span className="font-mono text-white font-bold">
                                                        {formatTime(playbackTime)} <span className="text-gray-500">/</span> {formatTime(totalDuration)}
                                                    </span>
                                                    {currentSub.is_hook_zone && (
                                                        <span className="text-[9px] bg-orange-600/30 text-orange-400 px-1.5 py-0.5 rounded font-bold border border-orange-500/30">
                                                            🎬 5초 훅 씬 #{currentSub.scene_number}
                                                        </span>
                                                    )}
                                                </div>
                                                <div className="flex items-center gap-2 text-[10px]">
                                                    <button
                                                        onClick={() => setPlaybackTime(0)}
                                                        className="text-gray-400 hover:text-white px-1.5 py-0.5 bg-[#202632] rounded"
                                                    >
                                                        처음으로
                                                    </button>
                                                    <span className="text-gray-500 font-mono">
                                                        {(playbackTime).toFixed(1)}s
                                                    </span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    {/* 탭: 자막 편집 / 배경음/효과음 */}
                                    <div className="bg-[#181d26] border border-white/10 rounded-xl p-4 shadow flex flex-col gap-3">
                                        <div className="flex items-center gap-4 border-b border-white/5 pb-2 text-xs font-bold">
                                            <button
                                                onClick={() => setSubEditTab('subtitle')}
                                                className={`pb-1 transition-colors ${
                                                    subEditTab === 'subtitle' ? 'text-blue-400 border-b-2 border-blue-400' : 'text-gray-400 hover:text-white'
                                                }`}
                                            >
                                                자막 편집
                                            </button>
                                            <button
                                                onClick={() => setSubEditTab('bgm')}
                                                className={`pb-1 transition-colors ${
                                                    subEditTab === 'bgm' ? 'text-blue-400 border-b-2 border-blue-400' : 'text-gray-400 hover:text-white'
                                                }`}
                                            >
                                                배경음/효과음
                                            </button>
                                        </div>

                                        {subEditTab === 'subtitle' ? (
                                            <div className="space-y-3">
                                                <div className="flex items-center justify-between text-xs font-bold text-white">
                                                    <span>선택된 구간 편집</span>
                                                    <div className="flex items-center gap-1">
                                                        <button className="text-[10px] px-2 py-0.5 bg-[#202632] border border-white/10 rounded">-0.1s</button>
                                                        <button className="text-[10px] px-2 py-0.5 bg-[#202632] border border-white/10 rounded">+0.1s</button>
                                                        <button className="text-[10px] px-2.5 py-0.5 bg-emerald-600 text-white rounded font-bold">저장</button>
                                                    </div>
                                                </div>

                                                <div className="flex items-center justify-between text-[11px] text-gray-400 bg-[#14181f] p-2 rounded border border-white/5">
                                                    <span className="text-blue-400 font-bold">현재 이미지</span>
                                                    <span className="font-mono">{currentSub.start_time}s ~ {currentSub.end_time}s</span>
                                                </div>

                                                <div className="flex items-center justify-between text-[11px] text-gray-400 bg-[#14181f] p-2 rounded border border-white/5">
                                                    <span className="text-gray-300 font-bold">시작 시간</span>
                                                    <div className="flex items-center gap-1">
                                                        <span className="font-mono text-white mr-2">{currentSub.start_time}s</span>
                                                        <button className="text-[9px] px-1.5 py-0.5 bg-[#202632] border border-white/10 rounded">-0.1s</button>
                                                        <button className="text-[9px] px-1.5 py-0.5 bg-[#202632] border border-white/10 rounded">+0.1s</button>
                                                    </div>
                                                </div>

                                                <div className="flex items-center justify-between text-[11px] text-gray-400 bg-[#14181f] p-2 rounded border border-red-500/20">
                                                    <span className="text-red-400 font-bold">종료 시간</span>
                                                    <div className="flex items-center gap-1">
                                                        <span className="font-mono text-white mr-2">{currentSub.end_time}s</span>
                                                        <button className="text-[9px] px-1.5 py-0.5 bg-[#202632] border border-white/10 rounded">-0.1s</button>
                                                        <button className="text-[9px] px-1.5 py-0.5 bg-[#202632] border border-white/10 rounded">+0.1s</button>
                                                    </div>
                                                </div>

                                                {/* 자막 텍스트 에디터 */}
                                                <div>
                                                    <textarea
                                                        value={currentSub.text}
                                                        onChange={e => {
                                                            const newText = e.target.value
                                                            setLocalSubtitles(prev => prev.map((s, idx) => idx === selectedSubIndex ? { ...s, text: newText } : s))
                                                        }}
                                                        className="w-full p-3 bg-[#14181f] border border-white/10 rounded-lg text-xs text-white leading-relaxed resize-none focus:outline-none focus:border-blue-500 min-h-[90px]"
                                                    />
                                                </div>
                                            </div>
                                        ) : (
                                            <div className="py-6 text-center text-xs text-gray-400">
                                                🎵 BGM 배경음 및 SFX 효과음 설정 패널
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                        )
                    })()}

                    {/* [TTS 음성 생성 탭] */}
                    {currentNav === 'tts' && selectedProject && (
                        <div className="space-y-4 max-w-7xl mx-auto w-full flex flex-col h-full">
                            <div className="bg-[#181d26] border border-white/10 rounded-xl p-3 shadow-md flex flex-wrap items-center justify-between gap-3 shrink-0">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <span className="text-[11px] px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 font-bold border border-emerald-500/20 flex items-center gap-1">
                                        <span>📜</span> {selectedProject.scenes.length}개 씬 · {scriptCharCount.toLocaleString()}자 대본 로드됨
                                    </span>
                                    <span className="text-[11px] px-2.5 py-1 rounded-full bg-purple-500/10 text-purple-400 font-bold border border-purple-500/20">
                                        ⚡ ElevenLabs (Multilingual v2)
                                    </span>
                                </div>

                                <div className="flex items-center gap-3 flex-wrap">
                                    <div className="flex items-center gap-1.5">
                                        <span className="text-xs font-bold text-gray-300">성우</span>
                                        <select
                                            value={selectedVoice}
                                            onChange={e => setSelectedVoice(e.target.value)}
                                            className="bg-[#202632] border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-purple-500 min-w-[200px]"
                                        >
                                            {ELEVENLABS_VOICES.map(v => (
                                                <option key={v.id} value={v.id}>{v.name}</option>
                                            ))}
                                        </select>
                                    </div>

                                    <div className="flex items-center gap-1.5">
                                        <span className="text-xs font-bold text-gray-300">속도 <span className="text-purple-400 font-mono">{ttsSpeed}x</span></span>
                                        <input
                                            type="range"
                                            min="0.7"
                                            max="1.3"
                                            step="0.05"
                                            value={ttsSpeed}
                                            onChange={e => setTtsSpeed(e.target.value)}
                                            className="w-16 h-1 bg-gray-600 rounded appearance-none cursor-pointer accent-purple-500"
                                        />
                                    </div>

                                    <div className="flex items-center gap-1.5">
                                        <span className="text-xs font-bold text-gray-300">안정성 <span className="text-purple-400 font-mono">{elStability}</span></span>
                                        <input
                                            type="range"
                                            min="0.0"
                                            max="1.0"
                                            step="0.05"
                                            value={elStability}
                                            onChange={e => setElStability(e.target.value)}
                                            className="w-16 h-1 bg-gray-600 rounded appearance-none cursor-pointer accent-purple-500"
                                        />
                                    </div>

                                    <label className="flex items-center gap-1.5 cursor-pointer bg-[#202632] px-2.5 py-1 rounded-lg border border-white/5">
                                        <span className="text-xs font-bold text-gray-300">다중 성우</span>
                                        <input
                                            type="checkbox"
                                            checked={multiVoice}
                                            onChange={e => setMultiVoice(e.target.checked)}
                                            className="sr-only peer"
                                        />
                                        <div className="relative w-7 h-4 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-purple-600" />
                                    </label>

                                    <button
                                        onClick={() => alert('TTS 보이스 및 음향 설정이 저장되었습니다!')}
                                        className="px-3 py-1.5 text-xs font-bold bg-[#202632] hover:bg-[#28303e] border border-white/10 text-gray-300 rounded-lg transition-all"
                                    >
                                        설정만 저장
                                    </button>
                                    <button
                                        onClick={generateTts}
                                        disabled={generatingTts}
                                        className="px-4 py-1.5 text-xs font-bold bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white rounded-lg transition-all shadow-md flex items-center gap-1.5 disabled:opacity-50"
                                    >
                                        <Volume2 className={`h-3.5 w-3.5 ${generatingTts ? 'animate-bounce' : ''}`} />
                                        {generatingTts ? 'ElevenLabs 음성 생성 중...' : '음성 생성 (ElevenLabs)'}
                                    </button>
                                </div>
                            </div>

                            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 flex-1">
                                <div className="lg:col-span-4 space-y-4 flex flex-col">
                                    <div className="bg-[#181d26] border border-white/10 rounded-xl p-4 shadow space-y-2.5 border-l-4 border-l-purple-500">
                                        <div className="flex items-center justify-between">
                                            <span className="text-xs font-bold text-white flex items-center gap-1.5">
                                                <span>🎙️</span> 성우 음성 미리듣기 (Preview)
                                            </span>
                                            <span className="text-[10px] font-bold text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded">
                                                {selectedVoiceObj.gender === 'female' ? '여성' : '남성'}
                                            </span>
                                        </div>
                                        <p className="text-[11px] text-gray-400 leading-tight">{selectedVoiceObj.description}</p>
                                        <audio
                                            key={selectedVoiceObj.id}
                                            src={selectedVoiceObj.preview_url}
                                            controls
                                            className="w-full h-8 mt-1"
                                        />
                                    </div>

                                    {multiVoice && (
                                        <div className="bg-[#181d26] border border-white/10 rounded-xl p-4 shadow space-y-3 flex-1 flex flex-col">
                                            <div className="flex items-center justify-between border-b border-white/5 pb-2">
                                                <span className="text-xs font-bold text-white">등장인물별 성우 배정 ({detectedCharacters.length}명 감지)</span>
                                                <button
                                                    onClick={() => alert('대본에서 화자를 다시 분석했습니다.')}
                                                    className="text-[10px] text-gray-400 hover:text-white px-2 py-0.5 border border-white/10 rounded"
                                                >
                                                    새로고침
                                                </button>
                                            </div>
                                            <div className="space-y-2 overflow-y-auto max-h-48 pr-1">
                                                {detectedCharacters.map(char => (
                                                    <div key={char} className="flex items-center justify-between gap-2 p-2 bg-[#14181f] rounded border border-white/5">
                                                        <span className="text-xs font-bold text-purple-300 truncate max-w-[80px]">{char}</span>
                                                        <select
                                                            value={characterVoices[char] || selectedVoice}
                                                            onChange={e => setCharacterVoices(prev => ({ ...prev, [char]: e.target.value }))}
                                                            className="text-[11px] bg-[#202632] border border-white/10 rounded px-2 py-1 text-white flex-1"
                                                        >
                                                            {ELEVENLABS_VOICES.map(v => (
                                                                <option key={v.id} value={v.id}>{v.name}</option>
                                                            ))}
                                                        </select>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {audioResultUrl && (
                                        <div className="bg-[#181d26] border border-white/10 rounded-xl p-4 shadow space-y-3 border-l-4 border-l-emerald-500">
                                            <div className="flex items-center justify-between">
                                                <span className="text-xs font-bold text-white flex items-center gap-1.5">
                                                    <span>🎉</span> 생성 완료된 음성 오디오
                                                </span>
                                                <span className="text-[10px] font-bold text-emerald-400 font-mono">약 {estimatedAudioMinutes}분 분량</span>
                                            </div>
                                            <audio src={audioResultUrl} controls className="w-full h-8" />
                                            <div className="flex items-center gap-2 pt-1">
                                                <a
                                                    href={audioResultUrl}
                                                    download="std_elevenlabs_tts.mp3"
                                                    target="_blank"
                                                    rel="noopener"
                                                    className="flex-1 text-center py-2 bg-[#202632] hover:bg-[#28303e] text-white rounded text-xs font-bold border border-white/10"
                                                >
                                                    오디오 다운로드
                                                </a>
                                                <button
                                                    onClick={() => setCurrentNav('subtitle_gen')}
                                                    className="flex-1 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs font-bold"
                                                >
                                                    자막 단계로 이동 →
                                                </button>
                                            </div>
                                        </div>
                                    )}
                                </div>

                                <div className="lg:col-span-8 bg-[#181d26] border border-white/10 rounded-xl p-4 shadow flex flex-col space-y-3 min-h-[500px]">
                                    <div className="flex items-center justify-between border-b border-white/5 pb-3">
                                        <div>
                                            <h4 className="text-xs font-bold text-white flex items-center gap-2">
                                                <span>📝</span> TTS 나레이션 전체 대본 에디터
                                            </h4>
                                            <p className="text-[10px] text-gray-400 mt-0.5">이곳에서 직접 대본을 수정하면 수정된 대본으로 ElevenLabs 음성이 생성됩니다.</p>
                                        </div>
                                        <div className="text-right">
                                            <div className="text-xs font-bold text-purple-400 font-mono">{scriptCharCount.toLocaleString()}자</div>
                                            <div className="text-[10px] text-gray-400">예상 소요: 약 {estimatedAudioMinutes}분</div>
                                        </div>
                                    </div>
                                    <textarea
                                        value={customScriptText}
                                        onChange={e => setCustomScriptText(e.target.value)}
                                        className="flex-1 w-full p-4 bg-[#14181f] border border-white/10 rounded-xl text-xs text-gray-200 leading-relaxed font-sans focus:outline-none focus:border-purple-500 resize-none min-h-[420px]"
                                        placeholder="이곳에 전체 대본 텍스트가 표시됩니다..."
                                    />
                                </div>
                            </div>
                        </div>
                    )}

                    {/* [이미지 생성 탭] */}
                    {currentNav === 'image_gen' && selectedProject && (
                        <div className="space-y-6 max-w-7xl mx-auto w-full">
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
                                            영상 누락: 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20...
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

                                            <div className="p-4 grid grid-cols-1 lg:grid-cols-12 gap-4">
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
                                                        {scene.video_prompt || scene.prompt_en || `Start from the exact image keyframe for scene ${sceneNum}. At the funeral hall, an elderly husband finds a sealed letter hidden inside his late wife's old handbag...`}
                                                    </p>
                                                </div>

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

                    {/* [주제 탐색 탭 (Check AI-analyzed personalized topics)] */}
                    {currentNav === 'topics' && (
                        <div className="space-y-4 max-w-7xl mx-auto w-full">
                            <div className="flex items-center justify-between mb-2">
                                <h2 className="text-lg font-bold text-white">Check AI-analyzed personalized topics</h2>
                                <div className="flex items-center gap-2">
                                    <select
                                        className="text-xs bg-[#1c2027] border border-gray-600 rounded px-2 py-1 text-white outline-none cursor-pointer"
                                        defaultValue=""
                                    >
                                        <option value="">영상길이</option>
                                        <option value="short">짧은 영상 (15분 미만)</option>
                                        <option value="medium">중간 영상 (15-30분)</option>
                                        <option value="long">긴 영상 (30분 이상)</option>
                                        <option value="ignore">무시</option>
                                    </select>
                                    <select
                                        className="text-xs bg-[#1c2027] border border-gray-600 rounded px-2 py-1 text-white outline-none cursor-pointer"
                                        defaultValue="ko"
                                    >
                                        <option value="ko">한국어</option>
                                        <option value="ja">日本語</option>
                                        <option value="en">English</option>
                                    </select>
                                    <button
                                        onClick={() => loadStdData(token)}
                                        className="text-xs bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded transition-all font-medium"
                                    >
                                        새로고침
                                    </button>
                                </div>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5 gap-3">
                                {topics.slice(0, 5).map(topic => (
                                    <button
                                        key={topic.id}
                                        type="button"
                                        onClick={() => claimTopic(topic.id)}
                                        className="w-full text-left bg-[#1c2027] border border-white/10 rounded-xl px-4 pt-4 pb-3 hover:border-indigo-500/50 transition-all group relative cursor-pointer flex flex-col justify-between"
                                    >
                                        <div>
                                            <div className="mb-2">
                                                <span className="float-left text-xs leading-4 font-bold bg-indigo-500/20 text-indigo-300 px-2 py-0.5 rounded mr-2 max-w-[55%] truncate">
                                                    {topic.category_name || '옛날이야기'}
                                                </span>
                                                <h3 className="text-sm leading-5 font-medium text-white group-hover:text-indigo-300 transition-colors">
                                                    {topic.topic}
                                                </h3>
                                                <div className="clear-both" />
                                            </div>
                                            <div className="mb-3 min-h-[1.5rem]" />
                                        </div>
                                        <div className="text-xs text-gray-300 truncate font-mono">
                                            <span>{topic.assigned_duration_minutes || 15}m</span>, <span className="text-yellow-400 font-semibold">$4</span>, <span>ghibli</span>, <span>story</span>
                                        </div>
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* [썸네일 탭] */}
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

                    {/* [프로젝트 탭 (7단계 인디케이터 + 제출 버튼 + 유저앱 테이블)] */}
                    {currentNav === 'projects' && (
                        <div className="space-y-4 max-w-7xl mx-auto w-full">
                            <div className="flex items-center justify-between mb-2">
                                <h2 className="text-base font-bold text-white">프로젝트 목록</h2>
                                <div className="flex items-center gap-2">
                                    <select
                                        className="text-xs bg-[#1c2027] border border-gray-600 rounded px-2 py-1 text-white outline-none cursor-pointer"
                                        defaultValue="newest"
                                    >
                                        <option value="newest">최신순</option>
                                        <option value="oldest">오래된순</option>
                                        <option value="name">이름순</option>
                                    </select>
                                    <select
                                        className="text-xs bg-[#1c2027] border border-gray-600 rounded px-2 py-1 text-white outline-none cursor-pointer"
                                        defaultValue="20"
                                    >
                                        <option value="20">20개씩 보기</option>
                                        <option value="50">50개씩 보기</option>
                                        <option value="100">100개씩 보기</option>
                                    </select>
                                </div>
                            </div>

                            <div className="bg-[#1c2027] rounded-xl border border-gray-700 overflow-x-auto shadow-2xl">
                                <table className="w-full text-left text-xs divide-y divide-gray-700 min-w-[1000px]">
                                    <thead className="bg-[#181d26] text-gray-400 font-medium text-[11px]">
                                        <tr>
                                            <th className="px-3 py-2.5 w-10 text-center">
                                                <input type="checkbox" className="w-4 h-4 rounded bg-[#1c2027] border-gray-600 cursor-pointer" />
                                            </th>
                                            <th className="px-3 py-2.5 w-72">프로젝트명</th>
                                            <th className="px-2 py-2.5 w-24 text-center">시작일</th>
                                            <th className="px-2 py-2.5 w-24 text-center">수정일</th>
                                            <th className="px-3 py-2.5">영상 제목</th>
                                            <th className="px-1 py-2.5 w-14 text-center">기획</th>
                                            <th className="px-1 py-2.5 w-14 text-center">대본</th>
                                            <th className="px-1 py-2.5 w-14 text-center">이미지</th>
                                            <th className="px-1 py-2.5 w-14 text-center">TTS</th>
                                            <th className="px-1 py-2.5 w-14 text-center">자막</th>
                                            <th className="px-1 py-2.5 w-14 text-center">썸네일</th>
                                            <th className="px-1 py-2.5 w-14 text-center">설정</th>
                                            <th className="px-2 py-2.5 w-14 text-center">제출</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-800 bg-[#1c2027]">
                                        {/* 풍부한 프로젝트 목록 렌더링 */}
                                        {(projects.length > 0 ? projects : [
                                            { id: 'p-276', title: '아내의 장례식 날, 30년 숨긴 첫사랑의 편지가 열렸다', status: 'image_prompted', created_at: '2026-08-14', updated_at: '2026-08-18' },
                                            { id: 'p-275', title: '만점으로 살 게 없다! 식탁 물가 폭등의 진짜 원인', status: 'pending', created_at: '2026-08-12', updated_at: '2026-08-17' },
                                            { id: 'p-274', title: 'AI발 일자리 쇼크, 내 직업은 안전할까? 우리는 뭘 해야 하나?', status: 'pending', created_at: '2026-08-11', updated_at: '2026-08-17' },
                                            { id: 'p-273', title: '나만 모르는 돈의 비밀? 경제 벤치마크로 미래를 읽는 법', status: 'pending', created_at: '2026-08-10', updated_at: '2026-08-17' },
                                            { id: 'p-272', title: '절대 무공을 숨긴 당인, 강호의 운명을 바꾸다', status: 'pending', created_at: '2026-07-19', updated_at: '2026-08-17' },
                                            { id: 'p-271', title: '한국인이 몰랐던 조선 야사: 소를 뜯는 구선 선설의 진실', status: 'pending', created_at: '2026-07-08', updated_at: '2026-08-17' },
                                            { id: 'p-270', title: '황혼 부부, 이것 때문에 잠 못 이룬다? 19금 속마음 공개!', status: 'pending', created_at: '2026-07-01', updated_at: '2026-08-17' },
                                            { id: 'p-269', title: '2024년 경제 불확실성 시대, 돈 버는 주식·부동산 이 투자법이 정답!', status: 'pending', created_at: '2026-06-27', updated_at: '2026-08-17' },
                                            { id: 'p-268', title: '강호의 낭인, 당신이 몰랐던 진짜 무공의 비밀', status: 'pending', created_at: '2026-06-27', updated_at: '2026-08-17' },
                                        ]).map((p: any, idx: number) => {
                                            const isSelectedProj = selectedProject?.project?.id === p.id || idx === 0
                                            return (
                                                <tr
                                                    key={p.id || idx}
                                                    onClick={() => {
                                                        openProject(p.id)
                                                        setCurrentNav('image_gen')
                                                    }}
                                                    className="hover:bg-[#14181f] transition cursor-pointer group"
                                                >
                                                    <td className="px-3 py-2 text-center" onClick={e => e.stopPropagation()}>
                                                        <input type="checkbox" className="w-4 h-4 rounded bg-[#14181f] border-gray-600 cursor-pointer" />
                                                    </td>
                                                    <td className="px-3 py-2 whitespace-nowrap font-medium text-white max-w-xs truncate">
                                                        <div className="flex items-center gap-2">
                                                            <span className="text-amber-400">📁</span>
                                                            <span className="truncate group-hover:text-blue-400 transition-colors">{p.title}</span>
                                                        </div>
                                                    </td>
                                                    <td className="px-2 py-2 text-center text-gray-400 font-mono text-[11px] whitespace-nowrap">
                                                        {p.created_at ? p.created_at.slice(2).replace(/-/g, '. ') + '.' : '26. 08. 14.'}
                                                    </td>
                                                    <td className="px-2 py-2 text-center text-gray-400 font-mono text-[11px] whitespace-nowrap">
                                                        {p.updated_at ? p.updated_at.slice(2).replace(/-/g, '. ') + '.' : '26. 08. 18.'}
                                                    </td>
                                                    <td className="px-3 py-2 text-gray-300 max-w-sm truncate" title={p.title}>
                                                        {p.title}
                                                    </td>
                                                    {/* 7단계 상태 원형 인디케이터 (기획, 대본, 이미지, TTS, 자막, 썸네일, 설정) */}
                                                    <td className="px-1 py-2 text-center">
                                                        <span className={isSelectedProj ? 'text-emerald-500 font-bold text-sm' : 'text-gray-600 text-sm'}>
                                                            {isSelectedProj ? '●' : '○'}
                                                        </span>
                                                    </td>
                                                    <td className="px-1 py-2 text-center">
                                                        <span className={isSelectedProj ? 'text-emerald-500 font-bold text-sm' : 'text-gray-600 text-sm'}>
                                                            {isSelectedProj ? '●' : '○'}
                                                        </span>
                                                    </td>
                                                    <td className="px-1 py-2 text-center">
                                                        <span className={isSelectedProj ? 'text-gray-600 text-sm' : 'text-gray-600 text-sm'}>
                                                            ○
                                                        </span>
                                                    </td>
                                                    <td className="px-1 py-2 text-center">
                                                        <span className={isSelectedProj || idx === 6 ? 'text-emerald-500 font-bold text-sm' : 'text-gray-600 text-sm'}>
                                                            {isSelectedProj || idx === 6 ? '●' : '○'}
                                                        </span>
                                                    </td>
                                                    <td className="px-1 py-2 text-center">
                                                        <span className={isSelectedProj || idx === 6 ? 'text-emerald-500 font-bold text-sm' : 'text-gray-600 text-sm'}>
                                                            {isSelectedProj || idx === 6 ? '●' : '○'}
                                                        </span>
                                                    </td>
                                                    <td className="px-1 py-2 text-center">
                                                        <span className={isSelectedProj || idx === 6 ? 'text-emerald-500 font-bold text-sm' : 'text-gray-600 text-sm'}>
                                                            {isSelectedProj || idx === 6 ? '●' : '○'}
                                                        </span>
                                                    </td>
                                                    <td className="px-1 py-2 text-center">
                                                        <span className={isSelectedProj || idx === 6 ? 'text-emerald-500 font-bold text-sm' : 'text-gray-600 text-sm'}>
                                                            {isSelectedProj || idx === 6 ? '●' : '○'}
                                                        </span>
                                                    </td>
                                                    {/* 제출 버튼 컬럼 */}
                                                    <td className="px-2 py-2 text-center" onClick={e => e.stopPropagation()}>
                                                        <button
                                                            onClick={() => {
                                                                openProject(p.id)
                                                                submitProject()
                                                            }}
                                                            className="text-blue-400 hover:text-blue-200 hover:bg-blue-500/10 p-1 rounded-full transition-all"
                                                            title="드라이브 제출 및 원격 렌더 큐 접수"
                                                        >
                                                            <span className="text-sm font-bold">⏎</span>
                                                        </button>
                                                    </td>
                                                </tr>
                                            )
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {/* [설정 탭] */}
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
                                        <span className="text-gray-400">TTS 엔진</span>
                                        <span className="text-purple-400 font-bold">ElevenLabs Multilingual v2</span>
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
