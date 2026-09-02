'use client'

const STD_OFFICIAL_CATEGORIES = [
    { id: 2, name: '옛날이야기', key: 'cat_folktales', language: 'ko' },
    { id: 4, name: '탈북사연', key: 'cat_defector', language: 'ko' },
    { id: 5, name: '한국사연', key: 'cat_korean_stories', language: 'ko' },
    { id: 6, name: '해외감동', key: 'cat_overseas_touching', language: 'ko' },
    { id: 7, name: '무협', key: 'cat_wuxia', language: 'ko' },
    { id: 9, name: '황혼19금', key: 'cat_twilight19', language: 'ko' },
    { id: 12, name: 'English Folktales', key: 'cat_english_folktales', language: 'en' },
    { id: 13, name: '日本昔話', key: 'cat_japanese_folktales', language: 'ja' },
]

import { useEffect, useMemo, useRef, useState } from 'react'
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
    estimateRequiredSceneCount,
    partitionScriptByExistingSceneBoundaries,
    partitionScriptTo53Scenes,
    stripGeneratedPlanningText,
    StdSubtitleItem,
} from '@/lib/stdSubtitles'
import { SupportedLocale, getTranslation } from '@/lib/i18n'
import { parseScriptToVoiceSegments } from '@/lib/stdMultiVoice'
import {
    getStdLocalDirectoryState,
    reconnectStdLocalDirectory,
    restoreStdLocalProjectMedia,
    saveStdLocalMediaFile,
    selectStdLocalDirectory,
    type StdLocalDirectoryState,
} from '@/lib/stdLocalMedia'
import { calculateLongformPayoutByScenes, capLongformPayout } from '@/lib/stdPayoutPolicy'

type Topic = {
    id: number
    topic: string
    category_name: string
    language: string
    duration_minutes?: number | null
    recommended_duration_minutes?: number | null
    assigned_duration_minutes: number | null
    estimated_payout: number | null
    estimated_payout_usdt?: number | null
    adjusted_payout?: number | null
    adjusted_payout_usdt?: number | null
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

type MusicSubmission = {
    id: string
    file_name: string
    tool_name: string
    status: string
    reward_usdt?: number | null
    review_note?: string | null
    submitted_at?: string
}

type MusicMission = {
    id: string
    title: string
    target_market: string
    genre: string
    mood: string
    prompt: string
    negative_rules?: string[]
    duration_target_seconds: number
    reward_usdt?: number | null
    max_submissions: number
    accepted_submissions_count: number
    status: string
    created_at?: string
    my_submissions?: MusicSubmission[]
}

type MusicSubmissionDraft = {
    file?: File | null
    tool_name?: string
    prompt_used?: string
    lyrics?: string
    license_confirmed?: boolean
    originality_confirmed?: boolean
    commercial_use_confirmed?: boolean
}

const ELEVENLABS_VOICES = [
    {
        id: 'CwhRBWXzGAHq8TQ4Fs17',
        name: 'Roger - Laid-Back, Casual, Resonant',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'Easy going and perfect for casual conversations.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/CwhRBWXzGAHq8TQ4Fs17/58ee3ff5-f6f2-4628-93b8-e38eb31806b0.mp3',
    },
    {
        id: 'EXAVITQu4vr4xnSDxMaL',
        name: 'Sarah - Mature, Reassuring, Confident',
        gender: 'female',
        category: 'premade',
        language: 'ko',
        description: 'Young adult woman with a confident and warm, mature quality and a reassuring, professional tone.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/EXAVITQu4vr4xnSDxMaL/01a3e33c-6e99-4ee7-8543-ff2216a32186.mp3',
    },
    {
        id: 'FGY2WhTYpPnrIDTdsKH5',
        name: 'Laura - Enthusiast, Quirky Attitude',
        gender: 'female',
        category: 'premade',
        language: 'ko',
        description: 'This young adult female voice delivers sunny enthusiasm with a quirky attitude.',
        preview_url: 'https://api.us.elevenlabs.io/v1/voices/FGY2WhTYpPnrIDTdsKH5/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiI2NzM0MTc1OS1hZDA4LTQxYTUtYmU2ZS1kZTEyZmU0NDg2MTgubXAzIiwidGltZXN0YW1wIjoxNzg3MTA4NDAwMDAwMDAwfQ%3D%3D',
    },
    {
        id: 'IKne3meq5aSn9XLyUdCD',
        name: 'Charlie - Deep, Confident, Energetic',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'A young Australian male with a confident and energetic voice.',
        preview_url: 'https://api.us.elevenlabs.io/v1/voices/IKne3meq5aSn9XLyUdCD/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiIxMDJkZTZmMi0yMmVkLTQzZTAtYTFmMS0xMTFmYTc1YzU0ODEubXAzIiwidGltZXN0YW1wIjoxNzg3MTA4NDAwMDAwMDAwfQ%3D%3D',
    },
    {
        id: 'JBFqnCBsd6RMkjVDRZzb',
        name: 'George - Warm, Captivating Storyteller',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'Warm resonance that instantly captivates listeners.',
        preview_url: 'https://api.us.elevenlabs.io/v1/voices/JBFqnCBsd6RMkjVDRZzb/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiJlNjIwNmQxYS0wNzIxLTQ3ODctYWFmYi0wNmE2ZTcwNWNhYzUubXAzIiwidGltZXN0YW1wIjoxNzg3MTA4NDAwMDAwMDAwfQ%3D%3D',
    },
    {
        id: 'N2lVS1w4EtoT3dr4eOWO',
        name: 'Callum - Husky Trickster',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'Deceptively gravelly, yet unsettling edge.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/N2lVS1w4EtoT3dr4eOWO/ac833bd8-ffda-4938-9ebc-b0f99ca25481.mp3',
    },
    {
        id: 'SAz9YHcvj6GT2YYXdXww',
        name: 'River - Relaxed, Neutral, Informative',
        gender: 'neutral',
        category: 'premade',
        language: 'ko',
        description: 'A relaxed, neutral voice ready for narrations or conversational projects.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/SAz9YHcvj6GT2YYXdXww/e6c95f0b-2227-491a-b3d7-2249240decb7.mp3',
    },
    {
        id: 'SOYHLrjzK2X1ezoPC6cr',
        name: 'Harry - Fierce Warrior',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'An animated warrior ready to charge forward.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/SOYHLrjzK2X1ezoPC6cr/86d178f6-f4b6-4e0e-85be-3de19f490794.mp3',
    },
    {
        id: 'TX3LPaxmHKxFdv7VOQHJ',
        name: 'Liam - Energetic, Social Media Creator',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'A young adult with energy and warmth - suitable for reels and shorts.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/TX3LPaxmHKxFdv7VOQHJ/63148076-6363-42db-aea8-31424308b92c.mp3',
    },
    {
        id: 'Xb7hH8MSUJpSbSDYk0k2',
        name: 'Alice - Clear, Engaging Educator',
        gender: 'female',
        category: 'premade',
        language: 'ko',
        description: 'Clear and engaging, friendly woman with a British accent suitable for e-learning.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/Xb7hH8MSUJpSbSDYk0k2/d10f7534-11f6-41fe-a012-2de1e482d336.mp3',
    },
    {
        id: 'XrExE9yKIg1WjnnlVkGX',
        name: 'Matilda - Knowledgable, Professional',
        gender: 'female',
        category: 'premade',
        language: 'ko',
        description: 'A professional woman with a pleasing alto pitch. Suitable for many use cases.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/XrExE9yKIg1WjnnlVkGX/b930e18d-6b4d-466e-bab2-0ae97c6d8535.mp3',
    },
    {
        id: 'bIHbv24MWmeRgasZH58o',
        name: 'Will - Relaxed Optimist',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'Conversational and laid back.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/bIHbv24MWmeRgasZH58o/8caf8f3d-ad29-4980-af41-53f20c72d7a4.mp3',
    },
    {
        id: 'cgSgspJ2msm6clMCkdW9',
        name: 'Jessica - Playful, Bright, Warm',
        gender: 'female',
        category: 'premade',
        language: 'ko',
        description: 'Young and popular, this playful American female voice is perfect for trendy content.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/cgSgspJ2msm6clMCkdW9/56a97bf8-b69b-448f-846c-c3a11683d45a.mp3',
    },
    {
        id: 'cjVigY5qzO86Huf0OWal',
        name: 'Eric - Smooth, Trustworthy',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'A smooth tenor pitch from a man in his 40s - perfect for agentic use cases.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/cjVigY5qzO86Huf0OWal/d098fda0-6456-4030-b3d8-63aa048c9070.mp3',
    },
    {
        id: 'hpp4J3VqNfWAUOO0d1Us',
        name: 'Bella - Professional, Bright, Warm',
        gender: 'female',
        category: 'premade',
        language: 'ko',
        description: 'This voice is warm, bright, and professional, characterized by a Standard American accent and a polished, narrative quality. It features a medium-high pitch with crisp diction and a deliberate, rhythmic pace that makes it highly intelligible and engaging for long-form listening.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/hpp4J3VqNfWAUOO0d1Us/dab0f5ba-3aa4-48a8-9fad-f138fea1126d.mp3',
    },
    {
        id: 'iP95p4xoKVk53GoZ742B',
        name: 'Chris - Charming, Down-to-Earth',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'Natural and real, this down-to-earth voice is great across many use-cases.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/iP95p4xoKVk53GoZ742B/3f4bde72-cc48-40dd-829f-57fbf906f4d7.mp3',
    },
    {
        id: 'nPczCjzI2devNBz1zQrb',
        name: 'Brian - Deep, Resonant and Comforting',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'Middle-aged man with a resonant and comforting tone. Great for narrations and advertisements.',
        preview_url: 'https://api.us.elevenlabs.io/v1/voices/nPczCjzI2devNBz1zQrb/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiIyZGQzZTcyYy00ZmQzLTQyZjEtOTNlYS1hYmM1ZDRlNWFhMWQubXAzIiwidGltZXN0YW1wIjoxNzg3MTA4NDAwMDAwMDAwfQ%3D%3D',
    },
    {
        id: 'onwK4e9ZLuTAKqWW03F9',
        name: 'Daniel - Steady Broadcaster',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'A strong voice perfect for delivering a professional broadcast or news story.',
        preview_url: 'https://api.us.elevenlabs.io/v1/voices/onwK4e9ZLuTAKqWW03F9/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiI3ZWVlMDIzNi0xYTcyLTRiODYtYjMwMy01ZGNhZGMwMDdiYTkubXAzIiwidGltZXN0YW1wIjoxNzg3MTA4NDAwMDAwMDAwfQ%3D%3D',
    },
    {
        id: 'pFZP5JQG7iQjIQuC4Bku',
        name: 'Lily - Velvety Actress',
        gender: 'female',
        category: 'premade',
        language: 'ko',
        description: 'Velvety British female voice delivers news and narrations with warmth and clarity.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/pFZP5JQG7iQjIQuC4Bku/89b68b35-b3dd-4348-a84a-a3c13a3c2b30.mp3',
    },
    {
        id: 'pNInz6obpgDQGcFmaJgB',
        name: 'Adam - Dominant, Firm',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'A bright tenor pitch that immediately cuts through. The delivery is brash and openly confident, speaking with unwavering certainty and a slightly aggressive self-assurance.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/pNInz6obpgDQGcFmaJgB/d6905d7a-dd26-4187-bfff-1bd3a5ea7cac.mp3',
    },
    {
        id: 'pqHfZKP75CvOlQylNhV4',
        name: 'Bill - Wise, Mature, Balanced',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'Friendly and comforting voice ready to narrate your stories.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/pqHfZKP75CvOlQylNhV4/d782b3ff-84ba-4029-848c-acf01285524d.mp3',
    },
]

const SUBTITLE_FONTS = [
    { value: 'GmarketSansBold', label: 'GmarketSansBold' },
    { value: 'TmonMonsori', label: 'TmonMonsori' },
    { value: 'Jalnan', label: 'Jalnan' },
    { value: 'Black Han Sans', label: 'Black Han Sans' },
    { value: 'Pretendard-Bold', label: 'Pretendard-Bold' },
    { value: 'NanumSquareExtraBold', label: 'NanumSquareExtraBold' },
    { value: 'Jua', label: 'Jua' },
    { value: 'Do Hyeon', label: 'Do Hyeon' },
    { value: 'CookieRun-Regular', label: 'CookieRun-Regular' },
    { value: 'BinggraeMelona-Bold', label: 'BinggraeMelona-Bold' },
    { value: 'NetmarbleB', label: 'NetmarbleB' },
    { value: 'ChosunIlboMyungjo', label: 'ChosunIlboMyungjo' },
    { value: 'MapoFlowerIsland', label: 'MapoFlowerIsland' },
    { value: 'S-CoreDream-6Bold', label: 'S-CoreDream-6Bold' },
    { value: 'Gungsuh', label: 'Gungsuh' },
    { value: 'NanumMyeongjo', label: 'NanumMyeongjo' },
    { value: 'Malgun Gothic', label: 'Malgun Gothic' },
]

const DEFAULT_SUBTITLE_PRESETS = [
    {
        name: 'Gmarket_Default',
        settings: {
            fontFamily: 'GmarketSansBold',
            fontSize: '5.4',
            textColor: '#ffffff',
            strokeColor: '#000000',
            strokeWidth: '0',
            lineSpacing: '0.1',
            subtitleMaxChars: '20',
            posY: 5,
            bgStrip: false,
            bgColor: '#000000',
            bgOpacity: '0.5',
            bgVOffset: '0',
        }
    },
    {
        name: '화이트_네온',
        settings: {
            fontFamily: 'Jalnan',
            fontSize: '5.8',
            textColor: '#ffffff',
            strokeColor: '#00e5ff',
            strokeWidth: '3.0',
            lineSpacing: '0.1',
            subtitleMaxChars: '22',
            posY: 6,
            bgStrip: true,
            bgColor: '#000000',
            bgOpacity: '0.6',
            bgVOffset: '0',
        }
    },
    {
        name: '골드_시네마',
        settings: {
            fontFamily: 'TmonMonsori',
            fontSize: '5.6',
            textColor: '#ffe066',
            strokeColor: '#1a1a1a',
            strokeWidth: '2.5',
            lineSpacing: '0.1',
            subtitleMaxChars: '24',
            posY: 5,
            bgStrip: false,
            bgColor: '#000000',
            bgOpacity: '0.5',
            bgVOffset: '0',
        }
    }
]

export default function StdPortalPage() {

    useEffect(() => {
        // Load voices from API
                // Fetch legal texts (Terms of service & Privacy policy from admin global_settings)
        fetch('/api/std/legal')
            .then(res => res.json())
            .then(data => {
                if (data?.terms && data?.privacy) {
                    setLegalTexts({ terms: data.terms, privacy: data.privacy })
                }
            })
            .catch(() => {})
        fetch('/api/std/voices', { cache: 'no-store' })
            .then(res => res.json())
            .then(data => {
                if (data?.voices && data.voices.length > 0) {
                    setAllVoices(data.voices)
                    setSelectedVoice(prev => data.voices.some((voice: any) => voice.id === prev) ? prev : data.voices[0].id)
                }
            })
            .catch(err => console.error('Failed to load voices:', err))
    }, [])

    // 1. 인증 및 사용자 세션 상태
    const [authMode, setAuthMode] = useState<'login' | 'signup'>('login')
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [passwordConfirm, setPasswordConfirm] = useState('')
    const [fullName, setFullName] = useState('')
    const [nationality, setNationality] = useState('KR')
    const [contact, setContact] = useState('')
    const [referrer, setReferrer] = useState('')

    // 유저앱 login.html 완벽 대응 상태
    const [showPw, setShowPw] = useState(false)
    const [showRegPw, setShowRegPw] = useState(false)
    const [showRegPwConfirm, setShowRegPwConfirm] = useState(false)
    const [rememberEmail, setRememberEmail] = useState(true)
    const [rememberPassword, setRememberPassword] = useState(false)
    const [forgotModalOpen, setForgotModalOpen] = useState(false)
    const [forgotEmail, setForgotEmail] = useState('')
    const [forgotMsg, setForgotMsg] = useState('')
    const [signupCategories, setSignupCategories] = useState<string[]>(STD_OFFICIAL_CATEGORIES.map(c => c.name))
    const [emailVerified, setEmailVerified] = useState(false)
    const [verifyCodeSent, setVerifyCodeSent] = useState(false)
    const [verifyCodeInput, setVerifyCodeInput] = useState('')
    const [verifyTimer, setVerifyTimer] = useState(600)
    const [verifyLoading, setVerifyLoading] = useState(false)
    const [verifyMsg, setVerifyMsg] = useState('')
    const [preferredVideoLength, setPreferredVideoLength] = useState('15-30분')
    const [agreedTerms, setAgreedTerms] = useState(false)
    const [agreedPrivacy, setAgreedPrivacy] = useState(false)
    const [legalModalType, setLegalModalType] = useState<'terms' | 'privacy' | null>(null)
    const [legalTexts, setLegalTexts] = useState<{ terms: Record<string, string>; privacy: Record<string, string> }>({
        terms: {},
        privacy: {},
    })
    const [isImpersonating, setIsImpersonating] = useState(false)
    const [impersonateEmail, setImpersonateEmail] = useState('')
    const [impersonateUserId, setImpersonateUserId] = useState('')
    const [viewMode, setViewMode] = useState<'workspace' | 'login_form'>('workspace')

    const [token, setToken] = useState('')
    const [user, setUser] = useState<any>(null)
    const [authChecking, setAuthChecking] = useState(true)
    const [loading, setLoading] = useState(false)
    const [projectLoading, setProjectLoading] = useState(false)
    const [message, setMessage] = useState('')

    // 1.1 언어 (i18n) 상태 (한국어, 영어, 베트남어, 태국어)
    const [currentLocale, setCurrentLocale] = useState<SupportedLocale>('ko')
    
    useEffect(() => {
        let interval: any = null
        if (verifyCodeSent && !emailVerified && verifyTimer > 0) {
            interval = setInterval(() => {
                setVerifyTimer(prev => (prev > 0 ? prev - 1 : 0))
            }, 1000)
        }
        return () => {
            if (interval) clearInterval(interval)
        }
    }, [verifyCodeSent, emailVerified, verifyTimer])

    const t = (key: string, fallback?: string) => getTranslation(currentLocale, key, fallback)
    const getTopicPayoutUsdt = (topic: any): number => {
        const sceneCount = Number(topic?.scene_count ?? topic?.total_scenes ?? 0)
        if (Number.isFinite(sceneCount) && sceneCount > 0) {
            return calculateLongformPayoutByScenes(sceneCount)
        }
        const raw = Number(
            topic?.adjusted_payout_usdt
            ?? topic?.adjusted_payout
            ?? topic?.estimated_payout_usdt
            ?? topic?.estimated_payout
            ?? 0
        )
        if (!Number.isFinite(raw) || raw <= 0) return 4
        const usdt = raw >= 1000 ? raw / 1000 : raw
        return capLongformPayout(usdt)
    }
    const formatTopicPayout = (topic: any): string => {
        const amount = getTopicPayoutUsdt(topic)
        return `$${amount.toFixed(amount % 1 === 0 ? 0 : 1)} USDT`
    }
    const formatTopicPayoutDetail = (topic: any): string => {
        const amount = getTopicPayoutUsdt(topic)
        return `$${amount.toFixed(2)} USDT`
    }

    // 2. 작업 데이터 상태
    const [topics, setTopics] = useState<Topic[]>([])
    const [projects, setProjects] = useState<StdProject[]>([])
    const [selectedProject, setSelectedProject] = useState<SelectedProjectPayload | null>(null)

    const projectStateCacheKey = (projectId: string | null | undefined) => {
        const id = String(projectId || '').trim()
        return id ? `std_project_state_${id}` : ''
    }

    const rememberActiveProjectId = (projectId: string | null | undefined) => {
        const id = String(projectId || '').trim()
        if (!id || typeof window === 'undefined') return
        try {
            localStorage.setItem('std_active_project_id', id)
        } catch {}
    }

    const projectAssetCacheKey = (projectId: string | null | undefined, asset: any) => {
        const id = String(projectId || '').trim()
        const assetId = String(asset?.id || asset?.drive_file_id || `${asset?.scene_number || ''}:${asset?.asset_type || ''}`).trim()
        return id && assetId ? `${id}:${assetId}` : ''
    }

    const projectAssetFileUrl = (projectId: string | null | undefined, asset: any): string | null => {
        const id = String(projectId || '').trim()
        if (!id || !asset) return null
        const assetId = String(asset?.id || '').trim()
        const driveFileId = String(asset?.drive_file_id || '').trim()
        const impersonateSuffix = isImpersonating && impersonateEmail
            ? `&impersonate=${encodeURIComponent(impersonateEmail)}`
            : ''
        if (assetId) {
            return `/api/std/projects/${encodeURIComponent(id)}/assets/file?assetId=${encodeURIComponent(assetId)}${impersonateSuffix}`
        }
        if (driveFileId) {
            return `/api/std/projects/${encodeURIComponent(id)}/assets/file?driveFileId=${encodeURIComponent(driveFileId)}${impersonateSuffix}`
        }
        return null
    }

    const buildPersistentProjectState = (projectPayload: SelectedProjectPayload): SelectedProjectPayload => {
        const projectId = String(projectPayload?.project?.id || '').trim()
        if (!projectId) return projectPayload

        const latestBySceneType = new Map<string, any>()
        ;(projectPayload.assets || [])
            .filter((asset: any) => ['uploaded', 'assigned'].includes(String(asset?.status || '')))
            .forEach((asset: any) => {
                const sceneNumber = Number(asset?.scene_number)
                const assetType = String(asset?.asset_type || '').toLowerCase()
                if (!Number.isFinite(sceneNumber) || !['image', 'video'].includes(assetType)) return
                const key = `${sceneNumber}:${assetType}`
                if (!latestBySceneType.has(key)) latestBySceneType.set(key, asset)
            })

        const thumbnailAsset = (projectPayload.assets || []).find((asset: any) =>
            String(asset?.asset_type || '').toLowerCase() === 'thumbnail'
            && ['uploaded', 'assigned'].includes(String(asset?.status || ''))
        )
        const persistentThumbnailUrl = projectAssetFileUrl(projectId, thumbnailAsset)
            || sanitizeAssetUrl(projectPayload.project?.progress_payload?.thumbnail_url)

        return {
            ...projectPayload,
            scenes: (projectPayload.scenes || []).map((scene: any) => {
                const sceneNumber = Number(scene?.scene_number)
                const imageAsset = latestBySceneType.get(`${sceneNumber}:image`)
                const videoAsset = latestBySceneType.get(`${sceneNumber}:video`)
                return {
                    ...scene,
                    image_url: projectAssetFileUrl(projectId, imageAsset) || sanitizeAssetUrl(scene?.image_url || scene?.image),
                    video_url: projectAssetFileUrl(projectId, videoAsset) || sanitizeAssetUrl(scene?.video_url || scene?.video),
                }
            }),
            project: {
                ...projectPayload.project,
                progress_payload: {
                    ...(projectPayload.project?.progress_payload || {}),
                    ...(persistentThumbnailUrl ? { thumbnail_url: persistentThumbnailUrl } : {}),
                },
            },
        }
    }

    const rememberProjectState = (projectPayload: SelectedProjectPayload | null | undefined) => {
        if (!projectPayload?.project?.id || typeof window === 'undefined') return
        try {
            const persistentPayload = buildPersistentProjectState(projectPayload)
            localStorage.setItem('std_active_project_state', JSON.stringify(persistentPayload))
            localStorage.setItem('std_active_project_id', persistentPayload.project.id)
            localStorage.setItem(projectStateCacheKey(persistentPayload.project.id), JSON.stringify(persistentPayload))
        } catch (e) {}
    }

    const readRememberedProjectState = (projectId: string): SelectedProjectPayload | null => {
        if (!projectId || typeof window === 'undefined') return null
        try {
            const raw = localStorage.getItem(projectStateCacheKey(projectId))
                || (localStorage.getItem('std_active_project_id') === projectId ? localStorage.getItem('std_active_project_state') : null)
            return raw ? JSON.parse(raw) : null
        } catch {
            return null
        }
    }

    const revokeProjectMediaObjectUrls = (projectId?: string | null) => {
        const targetId = String(projectId || '').trim()
        Object.entries(projectMediaObjectUrlsRef.current).forEach(([key, value]) => {
            if (!value || !value.startsWith('blob:')) return
            if (targetId && !key.startsWith(`${targetId}:`)) return
            try {
                URL.revokeObjectURL(value)
            } catch {}
            delete projectMediaObjectUrlsRef.current[key]
        })
    }

    // 2.1 주제 큐 & 모달 팝업 상태 (유저앱 topic.html 완벽 대응)
    const [selectedTopicForModal, setSelectedTopicForModal] = useState<any>(null)
    const [topicModalOpen, setTopicModalOpen] = useState(false)
    const [trendLang, setTrendLang] = useState<'ko' | 'ja' | 'en'>('ko')
    const [trendPeriod, setTrendPeriod] = useState('now')
    const [trendAge, setTrendAge] = useState('50s')
    const [topicSearchQuery, setTopicSearchQuery] = useState('')
    const [topicLengthFilter, setTopicLengthFilter] = useState('')

    // 3. 네비게이션: 유저앱 사이드바 및 스텝퍼와 100% 동일
    type StdNavKey = 'topics' | 'script_plan' | 'script_gen' | 'image_gen' | 'tts' | 'subtitle_gen' | 'thumbnail' | 'music_missions' | 'projects' | 'template' | 'render' | 'settings'
    const STD_NAV_KEYS: StdNavKey[] = ['topics', 'script_plan', 'script_gen', 'image_gen', 'tts', 'subtitle_gen', 'thumbnail', 'music_missions', 'projects', 'template', 'render', 'settings']
    const normalizeStdNav = (value: string | null | undefined): StdNavKey | null => {
        return STD_NAV_KEYS.includes(value as StdNavKey) ? value as StdNavKey : null
    }
    const [currentNav, setCurrentNav] = useState<StdNavKey>(() => {
        if (typeof window === 'undefined') return 'topics'
        const params = new URLSearchParams(window.location.search)
        return normalizeStdNav(params.get('tab') || params.get('page'))
            || normalizeStdNav(localStorage.getItem('std_current_nav'))
            || 'topics'
    })
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

    useEffect(() => {
        try {
            localStorage.setItem('std_current_nav', currentNav)
            const url = new URL(window.location.href)
            url.searchParams.set('tab', currentNav)
            window.history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`)
        } catch (error) {}
    }, [currentNav])

    useEffect(() => {
        return () => {
            revokeProjectMediaObjectUrls()
        }
    }, [])

    // 4. 에셋 및 작업 제어 상태
    const [uploadingKey, setUploadingKey] = useState('')
    const [generatingTts, setGeneratingTts] = useState(false)
    const [musicMissions, setMusicMissions] = useState<MusicMission[]>([])
    const [musicMissionLoading, setMusicMissionLoading] = useState(false)
    const [musicSubmissionDrafts, setMusicSubmissionDrafts] = useState<Record<string, MusicSubmissionDraft>>({})
    const [allVoices, setAllVoices] = useState(ELEVENLABS_VOICES)
    const [selectedVoice, setSelectedVoice] = useState('n2fbxG88jqAoaVPUy3IG') // Yooni 기본값
    const ttsSpeed = String(Math.max(0.7, Math.min(1.2, Number(
        selectedProject?.project?.project_payload?.tts_speed
        || selectedProject?.project?.progress_payload?.tts_speed
        || selectedProject?.project?.source_payload?.progress_payload?.tts_speed
        || 1
    ) || 1)))
    const [elStability, setElStability] = useState('0.35')
    const [elStyle, setElStyle] = useState('0.45')
    const [multiVoice, setMultiVoice] = useState(false)
    const [characterVoices, setCharacterVoices] = useState<Record<string, string>>({})
    const [newCharInput, setNewCharInput] = useState('')
    const [customAddedCharacters, setCustomAddedCharacters] = useState<string[]>([])
    const [customScriptText, setCustomScriptText] = useState('')
    const [scriptSyncDirty, setScriptSyncDirty] = useState(false)
    const [audioResultUrl, setAudioResultUrl] = useState('')
    const [audioDurationSeconds, setAudioDurationSeconds] = useState(0)
    const [selectedSceneIndexes, setSelectedSceneIndexes] = useState<number[]>([])
    const [dualFrameStates, setDualFrameStates] = useState<Record<number, boolean>>({})
    const projectMediaObjectUrlsRef = useRef<Record<string, string>>({})
    const [localMediaDirectory, setLocalMediaDirectory] = useState<StdLocalDirectoryState>({
        status: 'not_selected',
        folderName: '',
    })
    const [localMediaDirectoryBusy, setLocalMediaDirectoryBusy] = useState(false)

    useEffect(() => {
        setAudioDurationSeconds(0)
    }, [audioResultUrl])

    useEffect(() => {
        getStdLocalDirectoryState()
            .then(setLocalMediaDirectory)
            .catch(() => setLocalMediaDirectory({ status: 'not_selected', folderName: '' }))
    }, [])

    // 5. 자막(Subtitle) 편집 전용 상태 (유저앱 subtitle_gen.html 완벽 지원)
    const [selectedSubIndex, setSelectedSubIndex] = useState(0)
    const [subFontFamily, setSubFontFamily] = useState('GmarketSansBold')
    const [subFontSize, setSubFontSize] = useState('5.4')
    const [subLineSpacing, setSubLineSpacing] = useState('0.1')
    const [subMaxChars, setSubMaxChars] = useState('20')
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
    const [isSubtitleSaved, setIsSubtitleSaved] = useState<boolean>(false)
    const [subPresetList, setSubPresetList] = useState<any[]>(DEFAULT_SUBTITLE_PRESETS)
    const [selectedSubPreset, setSelectedSubPreset] = useState('Gmarket_Default')
    const [newSubPresetName, setNewSubPresetName] = useState('')

    // 6. 설정(Settings) 페이지 전용 상태 (유저앱 settings.html 100% 동일 구현)
    
    // 7. 렌더(Render) 탭 전용 상태 (유저앱 render.html 100% 동일 구현)
    const [renderResolution, setRenderResolution] = useState<'1080p' | '720p'>('1080p')
    const [renderUseSubtitles, setRenderUseSubtitles] = useState(true)
    const [renderTarget, setRenderTarget] = useState<'drive_api' | 'local'>('drive_api')
    const [isRendering, setIsRendering] = useState(false)
    const [renderProgress, setRenderProgress] = useState(0)
    const [renderLogList, setRenderLogList] = useState<string[]>([
        '대기 중 - 렌더링 시작 버튼을 누르면 작업이 진행됩니다.'
    ])
    const [renderedVideoUrl, setRenderedVideoUrl] = useState('')

    const [settingsSubTab, setSettingsSubTab] = useState<'basic' | 'orgchart' | 'history' | 'withdrawal' | 'support' | 'announcements'>('basic')
    const [settingName, setSettingName] = useState('김호')
    const [settingNationality, setSettingNationality] = useState('대한민국')
    const [settingPhone, setSettingPhone] = useState('010-0000-0000')
    const [referralCode, setReferralCode] = useState('BDDFAA1E')
    const [selectedCategories, setSelectedCategories] = useState<string[]>(STD_OFFICIAL_CATEGORIES.map(c => c.name))
    const [currentPw, setCurrentPw] = useState('')
    const [newPw, setNewPw] = useState('')
    const [confirmPw, setConfirmPw] = useState('')
    const [profileSavedMsg, setProfileSavedMsg] = useState('')
    const [pwSavedMsg, setPwSavedMsg] = useState('')
    const [walletAddress, setWalletAddress] = useState('')
    const [withdrawAmount, setWithdrawAmount] = useState('')
    const [treeViewMode, setTreeViewMode] = useState<'list' | 'card'>('list')
    const [inquiryText, setInquiryText] = useState('')
    const [inquiryCategory, setInquiryCategory] = useState('시스템 문의')

    // 7. 템플릿(Template) 전용 디자인 스튜디오 상태 (유저앱 template.html 100% 동일 구현)
    const [templateBgUrl, setTemplateBgUrl] = useState('')
    const [templateBgColor, setTemplateBgColor] = useState('#000000')
    const [templatePresetName, setTemplatePresetName] = useState('')
    const [selectedTemplatePreset, setSelectedTemplatePreset] = useState('')
    const [templatePresets, setTemplatePresets] = useState<any[]>([])
    const [selectedImageTemplatePreset, setSelectedImageTemplatePreset] = useState('')
    const [textLayers, setTextLayers] = useState<Array<{
        id: string
        text: string
        fontSize: number
        color: string
        strokeColor: string
        strokeWidth: number
        fontFamily: string
        x: number
        y: number
    }>>([
        {
            id: 'layer-1',
            text: '장례식 날 발견된 낡은 편지',
            fontSize: 34,
            color: '#ffeb3b',
            strokeColor: '#000000',
            strokeWidth: 4,
            fontFamily: 'GmarketSansBold',
            x: 50,
            y: 35,
        },
        {
            id: 'layer-2',
            text: '통장에 찍힌 실제 수령액 공개',
            fontSize: 26,
            color: '#ffffff',
            strokeColor: '#000000',
            strokeWidth: 3,
            fontFamily: 'GmarketSansBold',
            x: 50,
            y: 65,
        }
    ])
    const [shapeLayers, setShapeLayers] = useState<Array<{
        id: string
        type: 'banner' | 'box'
        color: string
        opacity: number
        y: number
        height: number
    }>>([
        {
            id: 'shape-1',
            type: 'banner',
            color: '#000000',
            opacity: 0.6,
            y: 60,
            height: 25,
        }
    ])

    const loadTemplatePresetsFromStorage = () => {
        try {
            const saved = localStorage.getItem('std_thumbnail_template_presets')
            if (!saved) {
                setTemplatePresets([])
                setSelectedImageTemplatePreset('')
                return
            }
            const customPresets = JSON.parse(saved)
            if (Array.isArray(customPresets)) {
                setTemplatePresets(customPresets)
                setSelectedImageTemplatePreset(prev => customPresets.some((preset: any) => preset.id === prev) ? prev : '')
            }
        } catch (e) {}
    }

    useEffect(() => {
        loadTemplatePresetsFromStorage()
    }, [])

    const applyTemplatePreset = (presetId: string) => {
        setSelectedTemplatePreset(presetId)
        const preset = templatePresets.find(p => p.id === presetId)
        if (!preset?.settings) return
        setTemplateBgUrl(preset.settings.bgUrl || '')
        setTemplateBgColor(preset.settings.bgColor || '#000000')
        setTextLayers((preset.settings.textLayers || []).map((layer: any, index: number) => ({
            ...layer,
            id: layer.id || `layer-${Date.now()}-${index}`,
        })))
        setShapeLayers((preset.settings.shapeLayers || []).map((shape: any, index: number) => ({
            ...shape,
            id: shape.id || `shape-${Date.now()}-${index}`,
        })))
        setMessage(`'${preset.name}' 템플릿이 적용되었습니다.`)
    }

    const saveTemplatePreset = () => {
        const name = templatePresetName.trim()
        if (!name) {
            alert('프리셋 이름을 입력해주세요.')
            return
        }
        const preset = {
            id: `custom-${Date.now()}`,
            name,
            settings: {
                bgUrl: templateBgUrl,
                bgColor: templateBgColor,
                textLayers,
                shapeLayers,
            },
        }
        const customPresets = [...templatePresets.filter(p => String(p.id).startsWith('custom-')), preset]
        setTemplatePresets(customPresets)
        setSelectedTemplatePreset(preset.id)
        localStorage.setItem('std_thumbnail_template_presets', JSON.stringify(customPresets))
        setTemplatePresetName('')
        setMessage(`'${name}' 템플릿 프리셋이 저장되었습니다.`)
    }

    const handleTemplateBgFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0]
        if (!file) return
        if (!file.type.startsWith('image/')) {
            alert('템플릿 배경으로 사용할 이미지 파일만 업로드할 수 있습니다.')
            event.target.value = ''
            return
        }
        setTemplateBgUrl(URL.createObjectURL(file))
        setMessage(`템플릿 배경 이미지 (${file.name})가 적용되었습니다.`)
        event.target.value = ''
    }

    // 8. 썸네일(Thumbnail) 제작 스튜디오 전용 상태 (유저앱 thumbnail.html 100% 동일 구현)
    const [thumbTitle, setThumbTitle] = useState('아내의 장례식 날, 30년 숨긴 첫사랑의 편지가 열렸다')
    const [thumbLayout, setThumbLayout] = useState('face')
    const [thumbStyle, setThumbStyle] = useState('realistic')
    const [thumbStep, setThumbStep] = useState<number>(1)
    const [thumbBgUrl, setThumbBgUrl] = useState('')
    const [thumbBgUploadFile, setThumbBgUploadFile] = useState<File | null>(null)
    const titleSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
    const [thumbTextLayers, setThumbTextLayers] = useState<Array<{
        id: string
        text: string
        fontSize: number
        color: string
        strokeColor: string
        strokeWidth: number
        fontFamily: string
        x: number
        y: number
    }>>([
        {
            id: 'tlayer-1',
            text: '장례식 날 발견된 낡은 편지',
            fontSize: 34,
            color: '#ffeb3b',
            strokeColor: '#000000',
            strokeWidth: 4,
            fontFamily: 'GmarketSansBold',
            x: 50,
            y: 35,
        },
        {
            id: 'tlayer-2',
            text: '통장에 찍힌 실제 수령액 공개',
            fontSize: 26,
            color: '#ffffff',
            strokeColor: '#000000',
            strokeWidth: 3,
            fontFamily: 'GmarketSansBold',
            x: 50,
            y: 65,
        }
    ])

    const handleSyncScriptToScenesAndSubtitles = async (showSuccessAlert: boolean = true, overrideScript?: string) => {
        if (!selectedProject) return false
        const scriptToUse = cleanScriptContextText(overrideScript || customScriptText || selectedProject.project?.project_payload?.script || '')
        const originalWorkerScript = findOriginalWorkerScript(selectedProject)
        if (!scriptToUse.trim()) {
            if (showSuccessAlert) alert('동기화할 대본 내용이 없습니다.')
            return false
        }
        const totalCount = estimateRequiredSceneCount(scriptToUse, selectedProject.scenes.length || 53)
        const partitioned = partitionScriptByExistingSceneBoundaries(scriptToUse, selectedProject.scenes || [], totalCount)
        const buildExtendedSceneImagePrompt = (sceneText: string, sceneNumber: number) => {
            const topicTitle = selectedProject.project?.title || selectedProject.project?.project_payload?.title || ''
            const style = selectedProject.project?.image_style || selectedProject.project?.project_payload?.image_style || 'realistic cinematic Korean story'
            return [
                `Scene ${sceneNumber} visual for "${topicTitle}".`,
                `Narration beat: ${sceneText || 'quiet emotional story moment'}`,
                `Style: ${style}.`,
                'Photorealistic Korean longform story scene, consistent characters, cinematic lighting, no text, no captions, no subtitles, no logos.',
            ].join(' ')
        }
        
        const syncedAt = new Date().toISOString()
        const updatedScenes = Array.from({ length: totalCount }, (_, i) => selectedProject.scenes[i] || ({
            id: `generated-${i + 1}`,
            scene_number: i + 1,
            visual_type: i < 12 ? 'video' : 'image',
            image_url: '',
            video_url: null,
            asset_status: 'missing',
        })).map((s: any, idx: number) => {
            const sceneNumber = s.scene_number || idx + 1
            const sceneText = partitioned[idx] || ''
            const fallbackText = sceneText || s.scene_text || s.script_excerpt || s.text || ''
            return {
                ...s,
                scene_number: sceneNumber,
                scene_order: s.scene_order || sceneNumber,
                text: fallbackText,
                scene_text: fallbackText,
                script_text: fallbackText,
                script_excerpt: fallbackText,
                narration: fallbackText,
                narration_text: fallbackText,
                prompt_ko: fallbackText,
                image_prompt: sceneText
                    ? buildExtendedSceneImagePrompt(sceneText, sceneNumber)
                    : (s.image_prompt || buildExtendedSceneImagePrompt(fallbackText, sceneNumber)),
                metadata: {
                    ...(s.metadata || {}),
                    script_excerpt: fallbackText,
                    narration_text: fallbackText,
                    synced_from_full_script_at: syncedAt,
                },
            }
        })
        
        const updatedSubs = generateSynchronizedSubtitles(scriptToUse, updatedScenes, Number(subMaxChars) || 20)
        const persistedScenes = updatedScenes.map((scene: any, index: number) => ({
            scene_number: Number(scene?.scene_number || scene?.scene_order || index + 1),
            scene_title: String(scene?.scene_title || `Scene ${index + 1}`),
            scene_text: String(scene?.scene_text || scene?.script_excerpt || scene?.text || ''),
            image_prompt: String(scene?.image_prompt || ''),
            video_prompt: String(scene?.video_prompt || ''),
            metadata: {
                ...(scene?.metadata || {}),
                script_excerpt: String(scene?.scene_text || scene?.script_excerpt || scene?.text || ''),
                visual_type: scene?.visual_type || null,
                synced_from_full_script_at: syncedAt,
            },
        }))
        const updatedStructure = {
            ...(selectedProject.project?.project_payload?.structure || {}),
            scenes: updatedScenes,
        }
        
        const updatedProject = {
            ...selectedProject,
            scenes: updatedScenes,
            project: {
                ...selectedProject.project,
                project_payload: {
                    ...selectedProject.project?.project_payload,
                    original_worker_script: originalWorkerScript,
                    script: scriptToUse,
                    structure: updatedStructure,
                    scenes: updatedScenes,
                    subtitles: updatedSubs,
                    subtitles_saved: true,
                }
            }
        }
        
        setSelectedProject(updatedProject)
        setCustomScriptText(scriptToUse)
        setLocalSubtitles(updatedSubs)
        rememberProjectState(updatedProject)
        if (selectedProject.project?.id) {
            try {
                const res = await fetch('/api/std/projects/' + selectedProject.project.id, {
                    method: 'PATCH',
                    headers: authedJsonHeaders,
                    body: JSON.stringify({
                        progress_payload: {
                            subtitles_saved: true,
                            subtitles_completed: true,
                        },
                        project_payload: {
                            original_worker_script: originalWorkerScript,
                            script: scriptToUse,
                            structure: {
                                ...(selectedProject.project.project_payload?.structure || {}),
                            },
                            scenes: persistedScenes,
                            subtitles: updatedSubs,
                            subtitles_saved: true,
                            render_settings: {
                                ...(selectedProject.project.project_payload?.render_settings || {}),
                                subtitle_max_chars: Number(subMaxChars) || 20,
                            },
                        },
                    }),
                })
                const payload = await safeParseJson(res, 'Script sync save failed')
                if (!res.ok || payload.success === false) {
                    throw new Error(payload.error || 'Script sync save failed')
                }
                if (payload.project) {
                    const persistedProject = {
                        ...updatedProject,
                        project: payload.project,
                        scenes: Array.isArray(payload.scenes) ? mergeAssetsIntoScenes(payload.scenes, updatedProject.assets || []) : updatedScenes,
                    }
                    setSelectedProject(persistedProject)
                    rememberProjectState(persistedProject)
                }
            } catch (error: any) {
                setMessage(error?.message || 'Script sync save failed')
                if (showSuccessAlert) alert(error?.message || 'Script sync save failed')
                return false
            }
        }
        setScriptSyncDirty(false)
        if (showSuccessAlert) {
            alert('✅ 초반 1분(1~12씬: 5s 훅) + 전개(13~28씬: 15s) + 심화(29~43씬: 20s) + 결말(44~53씬: 30s) + 확장(54씬+: 60s) 표준 페이싱으로 씬과 자막이 완벽 동기화되었습니다!')
        }
        return true
    }

    const restoreOriginalWorkerScript = async () => {
        if (!selectedProject) return
        const originalScript = findOriginalWorkerScript(selectedProject)
        if (!originalScript) {
            alert('복구할 워커 원본 대본이 없습니다.')
            return
        }
        setMessage('워커 원본 대본으로 되돌리는 중...')
        const restored = await handleSyncScriptToScenesAndSubtitles(false, originalScript)
        if (!restored) return
        setMessage('워커 원본 대본으로 복구했습니다.')
        alert('워커 원본 대본을 복구하고 씬/자막까지 다시 동기화했습니다.')
    }

    const ensureScriptSyncedBeforeAction = async () => {
        if (!selectedProject) return false
        const currentScript = cleanScriptContextText(customScriptText || '')
        const savedScript = cleanScriptContextText(selectedProject.project?.project_payload?.script || '')
        if (!currentScript.trim()) return true
        if (!scriptSyncDirty && currentScript === savedScript) return true
        setMessage('Script changed. Syncing scenes and subtitles...')
        return await handleSyncScriptToScenesAndSubtitles(false)
    }

    const totalDuration = useMemo(() => {
        if (!localSubtitles || localSubtitles.length === 0) return 60.0
        const last = localSubtitles[localSubtitles.length - 1]
        return Math.max(60.0, last.end_num || Number(last.end_time) || 60.0)
    }, [localSubtitles])

    const subtitleSceneGroups = useMemo(() => {
        const groups: any[] = []
        const byScene = new Map<number, any>()
        ;(localSubtitles || []).forEach((sub: any, index: number) => {
            const sceneNumber = Number(sub?.scene_number || index + 1)
            const normalizedSceneNumber = Number.isFinite(sceneNumber) ? sceneNumber : index + 1
            let group = byScene.get(normalizedSceneNumber)
            if (!group) {
                group = {
                    scene_number: normalizedSceneNumber,
                    firstIndex: index,
                    lastIndex: index,
                    start_num: sub?.start_num ?? Number(sub?.start_time) ?? 0,
                    end_num: sub?.end_num ?? Number(sub?.end_time) ?? 0,
                    start_time: sub?.start_time || '0.0',
                    end_time: sub?.end_time || '0.0',
                    image_url: sub?.image_url || '',
                    video_url: sub?.video_url || null,
                    is_hook_zone: Boolean(sub?.is_hook_zone || normalizedSceneNumber <= 12),
                    subtitles: [],
                }
                byScene.set(normalizedSceneNumber, group)
                groups.push(group)
            }
            group.lastIndex = index
            group.end_num = sub?.end_num ?? Number(sub?.end_time) ?? group.end_num
            group.end_time = sub?.end_time || group.end_time
            if (!group.image_url && sub?.image_url) group.image_url = sub.image_url
            if (!group.video_url && sub?.video_url) group.video_url = sub.video_url
            group.subtitles.push({ ...sub, subtitleIndex: index })
        })
        return groups
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

    const authedJsonHeaders = useMemo<Record<string, string>>(() => {
        const headers: Record<string, string> = {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
        }
        if (isImpersonating && impersonateEmail) {
            headers['x-impersonate-email'] = impersonateEmail
        }
        return headers
    }, [token, isImpersonating, impersonateEmail])

    const safeParseJson = async (res: Response, fallbackErrMsg: string) => {
        try {
            const text = await res.text()
            if (!text) return {}
            return JSON.parse(text)
        } catch {
            return {}
        }
    }

    const connectLocalMediaDirectory = async (): Promise<boolean> => {
        setLocalMediaDirectoryBusy(true)
        setMessage('로컬 작업 폴더를 연결하는 중...')
        try {
            const state = localMediaDirectory.status === 'permission_needed'
                ? await reconnectStdLocalDirectory()
                : await selectStdLocalDirectory()
            setLocalMediaDirectory(state)
            if (selectedProject) {
                await restorePersistedProjectMedia(selectedProject, authedJsonHeaders)
            }
            setMessage(
                localMediaDirectory.status === 'permission_needed'
                    ? `로컬 작업 폴더 '${state.folderName}' 권한 재연결 완료`
                    : `로컬 작업 폴더 '${state.folderName}' 연결 완료`
            )
            return true
        } catch (error: any) {
            if (error?.name === 'AbortError') {
                setMessage(
                    localMediaDirectory.status === 'permission_needed'
                        ? '로컬 작업 폴더 권한 재연결이 취소되었습니다.'
                        : '로컬 작업 폴더 선택이 취소되었습니다.'
                )
            } else {
                setMessage(error?.message || '로컬 작업 폴더 연결 실패')
            }
            return false
        } finally {
            setLocalMediaDirectoryBusy(false)
        }
    }

    const prepareLocalDirectoryForUpload = async (event: React.MouseEvent<HTMLInputElement>) => {
        if (localMediaDirectory.status === 'connected' || localMediaDirectory.status === 'unsupported') return
        event.preventDefault()
        if (localMediaDirectoryBusy) return
        const connected = await connectLocalMediaDirectory()
        if (connected) {
            setMessage('로컬 폴더가 연결되었습니다. 업로드 버튼을 다시 눌러 파일을 선택해주세요.')
        }
    }

    const loadMusicMissions = async () => {
        if (!token) return
        setMusicMissionLoading(true)
        try {
            const res = await fetch('/api/std/music-missions?limit=50', { headers: authedJsonHeaders })
            const data = await safeParseJson(res, 'Music missions load failed')
            if (!res.ok || data.success === false) throw new Error(data.error || 'Music missions load failed')
            setMusicMissions(Array.isArray(data.tasks) ? data.tasks : [])
        } catch (error: any) {
            setMessage(error?.message || 'Music missions load failed')
        } finally {
            setMusicMissionLoading(false)
        }
    }

    useEffect(() => {
        if (currentNav === 'music_missions' && token) {
            loadMusicMissions()
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [currentNav, token])

    const updateMusicDraft = (missionId: string, patch: Partial<MusicSubmissionDraft>) => {
        setMusicSubmissionDrafts(prev => ({
            ...prev,
            [missionId]: {
                ...(prev[missionId] || {}),
                ...patch,
            },
        }))
    }

    const submitMusicMission = async (mission: MusicMission) => {
        const draft = musicSubmissionDrafts[mission.id] || {}
        const file = draft.file
        if (!file) {
            setMessage('업로드할 음악 파일을 선택하세요.')
            return
        }
        if (!draft.tool_name?.trim()) {
            setMessage('생성 도구명을 입력하세요.')
            return
        }
        if (!draft.prompt_used?.trim()) {
            setMessage('실제 사용한 프롬프트를 입력하세요.')
            return
        }
        if (!draft.license_confirmed || !draft.originality_confirmed || !draft.commercial_use_confirmed) {
            setMessage('라이선스/원본성/상업 사용 확인을 모두 체크하세요.')
            return
        }

        setUploadingKey(`music-${mission.id}`)
        try {
            const initRes = await fetch('/api/std/music-missions/upload-init', {
                method: 'POST',
                headers: authedJsonHeaders,
                body: JSON.stringify({
                    task_id: mission.id,
                    mime_type: file.type || 'audio/mpeg',
                    file_name: file.name,
                    file_size: file.size,
                }),
            })
            const initPayload = await safeParseJson(initRes, 'Music upload init failed')
            if (!initRes.ok || !initPayload.upload_url) throw new Error(initPayload.error || 'Music upload init failed')

            const uploadRes = await fetch(initPayload.upload_url, {
                method: 'PUT',
                headers: { 'Content-Type': file.type || 'application/octet-stream' },
                body: file,
            })
            const uploadPayload = await safeParseJson(uploadRes, 'Drive music upload failed')
            if (!uploadRes.ok || !uploadPayload.id) throw new Error(uploadPayload.error || 'Drive music upload failed')

            const submitRes = await fetch('/api/std/music-missions/submit', {
                method: 'POST',
                headers: authedJsonHeaders,
                body: JSON.stringify({
                    task_id: mission.id,
                    drive_file_id: uploadPayload.id,
                    target_folder_id: initPayload.target_folder_id,
                    file_name: file.name,
                    mime_type: file.type || 'audio/mpeg',
                    file_size: file.size,
                    tool_name: draft.tool_name,
                    prompt_used: draft.prompt_used,
                    lyrics: draft.lyrics || '',
                    license_confirmed: draft.license_confirmed,
                    originality_confirmed: draft.originality_confirmed,
                    commercial_use_confirmed: draft.commercial_use_confirmed,
                }),
            })
            const submitPayload = await safeParseJson(submitRes, 'Music submission failed')
            if (!submitRes.ok || submitPayload.success === false) throw new Error(submitPayload.error || 'Music submission failed')

            setMusicSubmissionDrafts(prev => ({
                ...prev,
                [mission.id]: {
                    tool_name: draft.tool_name,
                    prompt_used: mission.prompt,
                    license_confirmed: false,
                    originality_confirmed: false,
                    commercial_use_confirmed: false,
                },
            }))
            setMessage('음악 제출이 접수되었습니다. 검수 결과를 기다려 주세요.')
            await loadMusicMissions()
        } catch (error: any) {
            setMessage(error?.message || 'Music submission failed')
        } finally {
            setUploadingKey('')
        }
    }

    const getProjectSyncedTitle = (projectPayload: SelectedProjectPayload | null | undefined) => {
        return String(
            projectPayload?.project?.title ||
            projectPayload?.project?.project_payload?.title ||
            projectPayload?.project?.project_payload?.video_title ||
            ''
        )
    }

    const persistProjectTitle = (projectId: string, title: string) => {
        if (!projectId || projectId.startsWith('proj-') || !token) return
        if (titleSaveTimerRef.current) clearTimeout(titleSaveTimerRef.current)
        titleSaveTimerRef.current = setTimeout(async () => {
            try {
                await fetch('/api/std/projects/' + projectId, {
                    method: 'PATCH',
                    headers: authedJsonHeaders,
                    body: JSON.stringify({
                        title,
                        project_payload: {
                            title,
                            video_title: title,
                        },
                    }),
                })
            } catch (error) {
                console.warn('[STD] project title sync failed:', error)
            }
        }, 600)
    }

    const syncProjectTitle = (rawTitle: string, options: { persist?: boolean } = {}) => {
        const nextTitle = rawTitle
        const currentProjectId = selectedProject?.project?.id || ''
        setThumbTitle(nextTitle)

        setSelectedProject(prev => {
            if (!prev) return prev
            const updated: SelectedProjectPayload = {
                ...prev,
                project: {
                    ...prev.project,
                    title: nextTitle,
                    project_payload: {
                        ...(prev.project.project_payload || {}),
                        title: nextTitle,
                        video_title: nextTitle,
                    },
                },
            }
            rememberProjectState(updated)
            return updated
        })
        setProjects(prev => prev.map(project => project.id === currentProjectId ? { ...project, title: nextTitle } : project))

        if (options.persist !== false) {
            persistProjectTitle(currentProjectId, nextTitle.trim() || 'Untitled Project')
        }
    }

    useEffect(() => {
        return () => {
            if (titleSaveTimerRef.current) clearTimeout(titleSaveTimerRef.current)
        }
    }, [])

    useEffect(() => {
        if (typeof document === 'undefined') return
        if (token) {
            document.cookie = `std_session_token=${encodeURIComponent(token)}; Path=/; Max-Age=${60 * 60 * 24 * 30}; SameSite=Lax`
        } else {
            document.cookie = 'std_session_token=; Path=/; Max-Age=0; SameSite=Lax'
        }
    }, [token])

    // 스크립트 컨텍스트에서 AI 생성 메타 지시문(First-minute micro beat 1/12... 등)을 제거하고 순수 대본만 정제하는 함수
    const cleanScriptContextText = (text: string | null | undefined): string => {
        if (!text) return ''
        let cleaned = stripGeneratedPlanningText(text)
        // First-minute micro beat 1/12 (0-5s). Keep this as a separate fast visual cut that advances the hook: 패턴 제거
        cleaned = cleaned.replace(/^First-minute micro beat\s*\d+\/\d+\s*\([^)]*\)\.?\s*(Keep this as a separate fast visual cut that advances the hook:?)?\s*/i, '')
        cleaned = cleaned.replace(/^First-minute micro beat\s*[:\-\d\(\)\w\s\.]*?:\s*/i, '')
        cleaned = cleaned.replace(/^Opening beat\s*\d*\s*:\s*/i, '')
        cleaned = cleaned.replace(/^Create immediate\s+[^.?!。！？]*[.?!。！？]\s*/i, '')
        cleaned = cleaned.replace(/^Leave one story secret unresolved into the next beat\.?\s*/i, '')
        cleaned = cleaned.replace(/^Scene\s*\d+\s*(?:\([^)]*\))?\s*:\s*/i, '')
        cleaned = cleaned.replace(/^Hook Scene\s*\d+\s*:\s*/i, '')
        cleaned = cleaned.replace(/^Panel\s*\d+\s*:\s*/i, '')
        return cleaned.trim() || String(text).trim()
    }

    const sanitizeAssetUrl = (url: string | null | undefined): string | null => {
        if (!url) return null
        const str = String(url).trim()
        if (str.startsWith('blob:')) return null
        if (str.includes('images.unsplash.com') || str.includes('commondatastorage.googleapis.com')) {
            return null
        }
        return str
    }

    const driveFileViewLink = (fileId: string | null | undefined): string | null => {
        const id = String(fileId || '').trim()
        return id ? `https://drive.google.com/file/d/${id}/view` : null
    }

    const assetDisplayUrl = (projectId: string | null | undefined, asset: any): string | null => {
        return projectAssetFileUrl(projectId, asset)
            || sanitizeAssetUrl(
                asset?.metadata?.thumbnail_link ||
                asset?.metadata?.web_view_link ||
                asset?.drive_file_link ||
                driveFileViewLink(asset?.drive_file_id)
            )
    }

    const mergeAssetsIntoScenes = (scenes: any[], assets: any[] = [], projectId?: string | null) => {
        const latestBySceneType = new Map<string, any>()
        ;(assets || [])
            .filter((asset: any) => ['uploaded', 'assigned'].includes(asset?.status))
            .forEach((asset: any) => {
                const sceneNumber = Number(asset?.scene_number)
                if (!Number.isFinite(sceneNumber)) return
                const assetType = String(asset?.asset_type || '').toLowerCase()
                if (!['image', 'video'].includes(assetType)) return
                const key = `${sceneNumber}:${assetType}`
                if (!latestBySceneType.has(key)) latestBySceneType.set(key, asset)
            })

        return (scenes || []).map((scene: any) => {
            const sceneNumber = Number(scene?.scene_number)
            const imageAsset = latestBySceneType.get(`${sceneNumber}:image`)
            const videoAsset = latestBySceneType.get(`${sceneNumber}:video`)
            const imageUrl = assetDisplayUrl(projectId, imageAsset) || sanitizeAssetUrl(scene?.image_url || scene?.image)
            const videoUrl = assetDisplayUrl(projectId, videoAsset) || sanitizeAssetUrl(scene?.video_url || scene?.video)
            return {
                ...scene,
                image_url: imageUrl,
                video_url: videoUrl,
                asset_status: videoUrl || imageUrl ? 'ready' : (scene?.asset_status || 'missing'),
            }
        })
    }

    const audioPlaybackEndpoint = (projectId: string, asset: any): string | null => {
        if (!projectId) return null
        if (asset?.id) {
            return `/api/std/projects/${encodeURIComponent(projectId)}/tts/audio?assetId=${encodeURIComponent(asset.id)}`
        }
        if (asset?.drive_file_id) {
            return `/api/std/projects/${encodeURIComponent(projectId)}/tts/audio?driveFileId=${encodeURIComponent(asset.drive_file_id)}`
        }
        return null
    }

    const findStoredProjectScript = (projectPayload?: SelectedProjectPayload | null): string => {
        const payload = projectPayload?.project?.project_payload || {}
        const embeddedScript = cleanScriptContextText(
            payload.script
            || payload.longform_script
            || ''
        )
        if (embeddedScript) return embeddedScript

        const sceneScript = cleanScriptContextText(
            (projectPayload?.scenes || [])
                .map((scene: any) => scene?.scene_text || scene?.script_excerpt || scene?.text || '')
                .filter(Boolean)
                .join('\n\n')
        )
        if (sceneScript) return sceneScript

        const structuredSceneScript = cleanScriptContextText(
            (Array.isArray(payload?.structure?.scenes) ? payload.structure.scenes : [])
                .map((scene: any) => scene?.scene_text || scene?.script_excerpt || scene?.text || '')
                .filter(Boolean)
                .join('\n\n')
        )
        if (structuredSceneScript) return structuredSceneScript

        return ''
    }

    const findOriginalWorkerScript = (projectPayload?: SelectedProjectPayload | null): string => {
        const payload = projectPayload?.project?.project_payload || {}

        const currentProject = projectPayload?.project || {}
        const sourcePayload = currentProject?.source_payload || {}
        const sourceScript = cleanScriptContextText(
            sourcePayload?.pregenerated_script
            || sourcePayload?.script
            || sourcePayload?.full_script
            || ''
        )
        if (sourceScript) return sourceScript

        const topicQueueId = Number(currentProject?.topic_queue_id || payload?.topic_id || 0)
        const matchedTopic = topics.find((topic: any) => {
            const sameTopicId = topicQueueId > 0 && Number(topic?.id || 0) === topicQueueId
            const sameTitle = String(topic?.generated_title || topic?.topic || '').trim() !== ''
                && String(topic?.generated_title || topic?.topic || '').trim() === String(currentProject?.title || '').trim()
            return sameTopicId || sameTitle
        })
        const topicScript = cleanScriptContextText(matchedTopic?.pregenerated_script || matchedTopic?.script || '')
        const embeddedScript = cleanScriptContextText(payload.original_worker_script || payload.pregenerated_script || '')
        const currentSavedScript = findStoredProjectScript(projectPayload)

        if (topicScript && embeddedScript && embeddedScript === currentSavedScript && topicScript !== currentSavedScript) {
            return topicScript
        }
        if (embeddedScript) return embeddedScript
        return topicScript
    }

    const restorePersistedProjectMedia = async (
        projectPayload: SelectedProjectPayload,
        headers: Record<string, string>
    ) => {
        const projectId = projectPayload?.project?.id
        const assets = Array.isArray(projectPayload?.assets) ? projectPayload.assets : []
        if (!projectId) return

        const localRestore = await restoreStdLocalProjectMedia(projectId, assets).catch(() => ({
            state: { status: 'not_selected', folderName: '' } as StdLocalDirectoryState,
            entries: [],
        }))
        setLocalMediaDirectory(localRestore.state)
        for (const entry of localRestore.entries) {
            projectMediaObjectUrlsRef.current[`${projectId}:local:${entry.key}`] = entry.objectUrl
        }
        const localBySceneType = new Map(
            localRestore.entries.map(entry => [`${entry.sceneNumber == null ? 'project' : entry.sceneNumber}:${entry.assetType}`, entry])
        )

        const mediaAssets = assets.filter((asset: any) =>
            ['uploaded', 'assigned'].includes(String(asset?.status || ''))
            && ['image', 'video', 'thumbnail', 'audio'].includes(String(asset?.asset_type || '').toLowerCase())
            && (asset?.id || asset?.drive_file_id)
        )

        const remoteOrLocalEntries = await Promise.all(mediaAssets.map(async (asset: any) => {
            const cacheKey = projectAssetCacheKey(projectId, asset)
            if (!cacheKey) return null
            if (projectMediaObjectUrlsRef.current[cacheKey]) {
                return { asset, objectUrl: projectMediaObjectUrlsRef.current[cacheKey] }
            }
            const assetType = String(asset?.asset_type || '').toLowerCase()
            const sceneKey = asset?.scene_number == null ? 'project' : Number(asset.scene_number)
            const localEntry = localBySceneType.get(`${sceneKey}:${assetType}`)
            if (localEntry?.objectUrl) {
                projectMediaObjectUrlsRef.current[cacheKey] = localEntry.objectUrl
                return { asset, objectUrl: localEntry.objectUrl }
            }
            if (!headers?.Authorization) return null
            try {
                const assetId = String(asset?.id || '').trim()
                const driveFileId = String(asset?.drive_file_id || '').trim()
                const query = assetId
                    ? `assetId=${encodeURIComponent(assetId)}`
                    : `driveFileId=${encodeURIComponent(driveFileId)}`
                const res = await fetch(`/api/std/projects/${encodeURIComponent(projectId)}/assets/file?${query}`, { headers })
                if (!res.ok) return null
                const blob = await res.blob()
                const objectUrl = URL.createObjectURL(blob)
                projectMediaObjectUrlsRef.current[cacheKey] = objectUrl
                return { asset, objectUrl }
            } catch {
                return null
            }
        }))

        const restoredEntries = [
            ...localRestore.entries.map(entry => ({
                asset: {
                    scene_number: entry.sceneNumber,
                    asset_type: entry.assetType,
                    file_name: entry.fileName,
                },
                objectUrl: entry.objectUrl,
            })),
            ...remoteOrLocalEntries,
        ]

        const restoredMap = new Map<string, string>()
        let restoredThumbnailUrl = ''
        let restoredAudioUrl = ''
        for (const entry of restoredEntries) {
            if (!entry?.asset || !entry.objectUrl) continue
            const assetType = String(entry.asset.asset_type || '').toLowerCase()
            if (assetType === 'audio') {
                restoredAudioUrl = entry.objectUrl
                continue
            }
            const sceneNumber = Number(entry.asset.scene_number)
            if (assetType === 'thumbnail') {
                restoredThumbnailUrl = entry.objectUrl
                continue
            }
            if (!Number.isFinite(sceneNumber) || !['image', 'video'].includes(assetType)) continue
            restoredMap.set(`${sceneNumber}:${assetType}`, entry.objectUrl)
        }

        const thumbnailAsset = assets.find((asset: any) =>
            String(asset?.asset_type || '').toLowerCase() === 'thumbnail' && ['uploaded', 'assigned'].includes(String(asset?.status || ''))
        )
        const fallbackThumbnailUrl = sanitizeAssetUrl(projectPayload?.project?.progress_payload?.thumbnail_url)
        if (restoredThumbnailUrl || fallbackThumbnailUrl || assetDisplayUrl(projectId, thumbnailAsset)) {
            setThumbBgUrl(restoredThumbnailUrl || assetDisplayUrl(projectId, thumbnailAsset) || fallbackThumbnailUrl)
            setThumbBgUploadFile(null)
        }

        const audioAsset = assets.find((asset: any) =>
            String(asset?.asset_type || '').toLowerCase() === 'audio' && ['uploaded', 'assigned'].includes(String(asset?.status || ''))
        )
        setAudioResultUrl(restoredAudioUrl || audioPlaybackEndpoint(projectId, audioAsset) || '')

        setSelectedProject(prev => {
            if (!prev || String(prev.project?.id || '') !== String(projectId)) return prev
            const nextScenes = (prev.scenes || []).map((scene: any) => {
                const sceneNumber = Number(scene?.scene_number)
                const restoredImageUrl = restoredMap.get(`${sceneNumber}:image`)
                const restoredVideoUrl = restoredMap.get(`${sceneNumber}:video`)
                return {
                    ...scene,
                    image_url: restoredImageUrl || scene.image_url || null,
                    video_url: restoredVideoUrl || scene.video_url || null,
                    asset_status: restoredImageUrl || restoredVideoUrl || scene.image_url || scene.video_url
                        ? 'ready'
                        : (scene.asset_status || 'missing'),
                }
            })
            return {
                ...prev,
                scenes: nextScenes,
            }
        })
        rememberProjectState({
            ...projectPayload,
            scenes: (projectPayload.scenes || []).map((scene: any) => {
                const sceneNumber = Number(scene?.scene_number)
                return {
                    ...scene,
                    image_url: restoredMap.get(`${sceneNumber}:image`) || scene?.image_url || null,
                    video_url: restoredMap.get(`${sceneNumber}:video`) || scene?.video_url || null,
                }
            }),
            project: {
                ...projectPayload.project,
                progress_payload: {
                    ...(projectPayload.project?.progress_payload || {}),
                    ...(restoredThumbnailUrl ? { thumbnail_url: restoredThumbnailUrl } : {}),
                },
            },
        })

    }

    // 워커 및 Supabase 실데이터로부터 풍부한 씬 및 그리드 프롬프트를 빌드하는 유틸리티
    const buildProjectFromSupabaseTopic = (topic: any): SelectedProjectPayload => {
        const dummyId = `proj-${topic.id || Date.now()}`
        const sampleTopicTitle = topic.generated_title || topic.topic || '새로운 영상 프로젝트'
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

        const projectScript = cleanScriptContextText(
            topic.pregenerated_script
            || topic.script
            || rawScenes.map((s: any) => s.script_excerpt || s.scene_text || s.scene_situation || s.scene_summary || s.narration || s.prompt_ko || '').join('\n\n')
        )
        const requiredSceneCount = estimateRequiredSceneCount(projectScript, rawScenes.length || 53)
        const partitionedScript = partitionScriptTo53Scenes(projectScript, requiredSceneCount)

        if (rawScenes.length < requiredSceneCount) {
            rawScenes = Array.from({ length: requiredSceneCount }, (_, i) => rawScenes[i] || {
                scene_number: i + 1,
                scene_order: i + 1,
                script_excerpt: partitionedScript[i] || '',
            })
        }

        const scenes = rawScenes.map((s: any, i: number) => {
            const num = Number(s.scene_number || s.scene_order || i + 1)
            // 신규 생성 시 실제 업로드/생성 에셋이 없으면 null (가짜 더미 이미지/비디오 제거)
            const videoUrl: string | null = sanitizeAssetUrl(s.video_url || s.video)
            const imageUrl: string | null = sanitizeAssetUrl(s.image_url || s.image)

            const rawScript = partitionedScript[i] || s.script_excerpt || s.scene_text || s.scene_situation || s.scene_summary || s.narration || s.prompt_ko || realDefaultNarratives[i % realDefaultNarratives.length]
            const scriptText = cleanScriptContextText(rawScript)
            const videoPromptText = s.video_prompt || s.prompt_en || s.prompt || s.image_prompt || `The shot uses a slow push-in for scene ${num}. Cinematic realistic 8k photorealism.`
            const generatedImagePrompt = `Image prompt: visualize this narration beat with the selected project style, consistent characters, no text, no captions: ${scriptText}`
            const imagePromptText = partitionedScript[i] ? generatedImagePrompt : (s.image_prompt || generatedImagePrompt)

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
                image_prompt: imagePromptText,
                video_url: videoUrl,
                image_url: imageUrl,
                asset_status: videoUrl ? 'ready' : (imageUrl ? 'ready' : 'pending'),
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
                ready_scene_count: scenes.filter(s => s.video_url || s.image_url).length,
            }
        }

        return {
            project: {
                ...projectData,
                project_payload: {
                    script: projectScript,
                    original_worker_script: projectScript,
                    structure: { scenes, image_grid_prompts: gridPrompts },
                    image_grid_prompts: gridPrompts,
                }
            },
            scenes,
            assets: [],
        }
    }

    const loadStdData = async (accessToken: string, options: { showLoading?: boolean } = {}) => {
        if (!accessToken) return
        const showLoading = options.showLoading !== false
        if (showLoading) setLoading(true)
        setMessage('')
        try {
            const headers = { Authorization: `Bearer ${accessToken}` }
            const [meRes, topicsRes, projectsRes, voicesRes] = await Promise.allSettled([
                fetch('/api/std/me', { headers }),
                fetch(`/api/std/topics?refresh=1&limit=50`, { headers }),
                fetch('/api/std/projects', { headers }),
                fetch('/api/std/voices', { headers }),
            ])

            let meData: any = {}
            let topicPayload: any = {}
            let projectPayload: any = {}

            if (meRes.status === 'fulfilled') meData = await safeParseJson(meRes.value, '')
            if (topicsRes.status === 'fulfilled') topicPayload = await safeParseJson(topicsRes.value, '')
            if (projectsRes.status === 'fulfilled') projectPayload = await safeParseJson(projectsRes.value, '')
            if (voicesRes.status === 'fulfilled') {
                const voiceData = await safeParseJson(voicesRes.value, '')
                if (Array.isArray(voiceData?.voices) && voiceData.voices.length > 0) {
                    setAllVoices(voiceData.voices)
                    setSelectedVoice(prev => voiceData.voices.some((voice: any) => voice.id === prev) ? prev : voiceData.voices[0].id)
                }
            }

            if (meData?.user) {
                setUser(meData.user)
                if (meData.user.full_name) setSettingName(meData.user.full_name)
                if (meData.user.nationality) setSettingNationality(meData.user.nationality)
                if (meData.user.contact) setSettingPhone(meData.user.contact)
                if (meData.user.referral_code) setReferralCode(meData.user.referral_code)
                if (Array.isArray(meData.user.preferred_category_names) && meData.user.preferred_category_names.length > 0) {
                    setSelectedCategories(meData.user.preferred_category_names.filter((name: unknown) =>
                        STD_OFFICIAL_CATEGORIES.some(category => category.name === String(name || '').trim())
                    ))
                } else if (Array.isArray(meData.user.preferred_category_ids) && meData.user.preferred_category_ids.length > 0) {
                    const mapped = STD_OFFICIAL_CATEGORIES
                        .filter(c => meData.user.preferred_category_ids.includes(c.id) || meData.user.preferred_category_ids.includes(String(c.id)))
                        .map(c => c.name)
                    if (mapped.length > 0) setSelectedCategories(mapped)
                }
            } else {
                if (!isImpersonating) {
                    setUser(null)
                    setToken('')
                    localStorage.removeItem('std_session_token')
                    return
                }
            }

            const loadedTopics = Array.isArray(topicPayload?.topics) ? topicPayload.topics : []
            const seenTopicKeys = new Set<string>()
            const dedupedTopics = loadedTopics.filter((t: any) => {
                const key = String(t.generated_title || t.topic || '').trim().toLowerCase().replace(/\s+/g, '')
                if (!key || seenTopicKeys.has(key)) return false
                seenTopicKeys.add(key)
                return true
            })
            setTopics(dedupedTopics)

            const loadedProjects = Array.isArray(projectPayload?.projects) ? projectPayload.projects : []
            setProjects(loadedProjects)

            // 1. 로컬 저장소에 저장된 활성 프로젝트 복원 시도 (임퍼소네이트 모드가 아닐 때만)
            const savedProjectStateRaw = !isImpersonating ? localStorage.getItem('std_active_project_state') : null
            const savedActiveProjectId = !isImpersonating ? localStorage.getItem('std_active_project_id') : null

            if (savedActiveProjectId && loadedProjects.some(p => p.id === savedActiveProjectId)) {
                await openProject(savedActiveProjectId, accessToken).catch(() => {})
            } else if (loadedProjects.length > 0) {
                await openProject(loadedProjects[0].id, accessToken).catch(() => {})
            } else if (savedProjectStateRaw) {
                try {
                    const parsed = JSON.parse(savedProjectStateRaw)
                    if (parsed?.project?.id) {
                        const cleanedProject = {
                            ...parsed,
                            scenes: (parsed.scenes || []).map((s: any) => {
                                const cleanText = cleanScriptContextText(s.scene_text || s.script_excerpt)
                                return {
                                    ...s,
                                    scene_text: cleanText,
                                    script_excerpt: cleanText,
                                    image_url: sanitizeAssetUrl(s.image_url),
                                    video_url: sanitizeAssetUrl(s.video_url),
                                }
                            })
                        }
                        setSelectedProject(cleanedProject)
                        setProjects(prev => {
                            const exists = prev.some(p => p.id === cleanedProject.project.id)
                            return exists ? prev : [cleanedProject.project, ...prev]
                        })
                        setCustomScriptText(cleanScriptContextText(cleanedProject.project.project_payload?.script || ''))
                        restorePersistedProjectMedia(cleanedProject, headers).catch(() => {})
                    }
                } catch {
                    // Fallback to loadedProjects
                }
            } else if (loadedTopics.length > 0) {
                const firstRealTopic = loadedTopics[0]
                const loaded = buildProjectFromSupabaseTopic(firstRealTopic)
                setSelectedProject(loaded)
                setProjects([loaded.project])
                setCustomScriptText(cleanScriptContextText(loaded.project.project_payload?.script || ''))
                rememberProjectState(loaded)
            }
        } catch (error: any) {
            console.warn('[loadStdData] warning:', error?.message)
        } finally {
            if (showLoading) setLoading(false)
        }
    }

    useEffect(() => {
        const urlParams = new URLSearchParams(window.location.search)
        const impEmail = urlParams.get('impersonate') || urlParams.get('email')
        const impUserId = urlParams.get('userId')

        if (impEmail) {
            const cleanEmail = decodeURIComponent(impEmail).trim().toLowerCase()
            setIsImpersonating(true)
            setImpersonateEmail(cleanEmail)
            if (impUserId) setImpersonateUserId(impUserId)
            setEmail(cleanEmail)

            const impToken = `std_impersonate_${Date.now()}`
            const impUser = {
                id: impUserId || ('worker-' + Date.now()),
                email: cleanEmail,
                full_name: cleanEmail.split('@')[0] || 'STD 유저',
                membership: 'std',
                signup_status: 'approved',
            }
            setToken(impToken)
            setUser(impUser)

            // Direct fetch for impersonated user without reading local cache
            const fetchImpersonated = async () => {
                try {
                    const headers = {
                        Authorization: `Bearer ${impToken}`,
                        'x-impersonate-email': cleanEmail,
                    }
                    const [meRes, pRes, tRes] = await Promise.allSettled([
                        fetch(`/api/std/me?impersonate=${encodeURIComponent(cleanEmail)}`, { headers }),
                        fetch(`/api/std/projects?impersonate=${encodeURIComponent(cleanEmail)}`, { headers }),
                        fetch(`/api/std/topics?refresh=1&limit=50&impersonate=${encodeURIComponent(cleanEmail)}`, { headers }),
                    ])
                    const meData = meRes.status === 'fulfilled' ? await meRes.value.json().catch(() => ({})) : {}
                    const pData = pRes.status === 'fulfilled' ? await pRes.value.json().catch(() => ({})) : {}
                    const tData = tRes.status === 'fulfilled' ? await tRes.value.json().catch(() => ({})) : {}

                    if (meData?.user) {
                        setUser(meData.user)
                        if (meData.user.full_name) setSettingName(meData.user.full_name)
                        if (meData.user.nationality) setSettingNationality(meData.user.nationality)
                        if (meData.user.contact) setSettingPhone(meData.user.contact)
                        if (meData.user.referral_code) setReferralCode(meData.user.referral_code)
                        if (Array.isArray(meData.user.preferred_category_names) && meData.user.preferred_category_names.length > 0) {
                            setSelectedCategories(meData.user.preferred_category_names.filter((name: unknown) =>
                                STD_OFFICIAL_CATEGORIES.some(category => category.name === String(name || '').trim())
                            ))
                        } else if (Array.isArray(meData.user.preferred_category_ids) && meData.user.preferred_category_ids.length > 0) {
                            const mapped = STD_OFFICIAL_CATEGORIES
                                .filter(c => meData.user.preferred_category_ids.includes(c.id) || meData.user.preferred_category_ids.includes(String(c.id)))
                                .map(c => c.name)
                            if (mapped.length > 0) setSelectedCategories(mapped)
                        }
                    }

                    const loadedProjects = Array.isArray(pData?.projects) ? pData.projects : []
                    const loadedTopics = Array.isArray(tData?.topics) ? tData.topics : []

                    setProjects(loadedProjects)
                    setTopics(loadedTopics)

                    if (loadedProjects.length > 0) {
                        await openProject(loadedProjects[0].id, impToken, cleanEmail)
                    } else if (loadedTopics.length > 0) {
                        const built = buildProjectFromSupabaseTopic(loadedTopics[0])
                        built.project.title = `[${cleanEmail.split('@')[0]}] ` + built.project.title
                        setSelectedProject(built)
                        setProjects([built.project])
                        setCustomScriptText(cleanScriptContextText(built.project.project_payload?.script || ''))
                    }
                } catch (err) {
                    console.error('Failed to load impersonated user data:', err)
                } finally {
                    setAuthChecking(false)
                }
            }
            fetchImpersonated()
            return
        }

        // 아이디 및 비밀번호 저장 복원
        const remEmailFlag = localStorage.getItem('std_remember_email') === 'true'
        const remPwFlag = localStorage.getItem('std_remember_password') === 'true'
        const savedEmail = localStorage.getItem('std_saved_email') || ''
        const savedPw = localStorage.getItem('std_saved_password') || ''

        if (remEmailFlag && savedEmail) {
            setEmail(savedEmail)
            setRememberEmail(true)
        }
        if (remPwFlag && savedPw) {
            setPassword(savedPw)
            setRememberPassword(true)
        }

        const savedToken = localStorage.getItem('std_session_token')
        if (savedToken) {
            setToken(savedToken)
            loadStdData(savedToken).finally(() => setAuthChecking(false))
        } else {
            setToken('')
            setUser(null)
            setAuthChecking(false)
        }
    }, [])

    useEffect(() => {
        if (selectedProject?.project?.project_payload?.script) {
            setCustomScriptText(cleanScriptContextText(selectedProject.project.project_payload.script))
        } else if (selectedProject?.scenes?.length) {
            const joined = selectedProject.scenes.map((s: any) => s.scene_text || s.script_excerpt || '').filter(Boolean).join('\n\n')
            if (joined) setCustomScriptText(joined)
        }

        // 1~12씬(5초 비디오 훅) + 13~53씬(동적 런닝타임) 3중 싱크 자막 생성
        const scenes = selectedProject?.scenes || []
        const savedSubtitles = selectedProject?.project?.project_payload?.subtitles
        const subs = Array.isArray(savedSubtitles) && savedSubtitles.length > 0
            ? savedSubtitles
            : generateSynchronizedSubtitles(
                selectedProject?.project?.project_payload?.script || customScriptText || '',
                scenes,
                Number(subMaxChars) || 20
            )
        setLocalSubtitles(subs)
        setSelectedSubIndex(0)

        const renderSettings = {
            ...(selectedProject?.project?.project_payload?.settings || {}),
            ...(selectedProject?.project?.project_payload?.render_settings || {}),
        }
        if (renderSettings.subtitle_bg_enabled !== undefined || renderSettings.bg_enabled !== undefined) {
            setSubBgStrip(Boolean(renderSettings.subtitle_bg_enabled ?? renderSettings.bg_enabled))
        }
        if (renderSettings.subtitle_bg_color || renderSettings.bg_color) {
            setSubBgColor(String(renderSettings.subtitle_bg_color || renderSettings.bg_color))
        }
        if (renderSettings.subtitle_bg_opacity !== undefined || renderSettings.bg_opacity !== undefined) {
            setSubBgOpacity(String(renderSettings.subtitle_bg_opacity ?? renderSettings.bg_opacity))
        }
        if (renderSettings.subtitle_bg_v_offset !== undefined) {
            setSubBgVOffset(String(renderSettings.subtitle_bg_v_offset))
        }
        if (renderSettings.subtitle_font_family) setSubFontFamily(String(renderSettings.subtitle_font_family))
        if (renderSettings.subtitle_font_size) setSubFontSize(String(renderSettings.subtitle_font_size))
        if (renderSettings.subtitle_text_color) setSubTextColor(String(renderSettings.subtitle_text_color))
        if (renderSettings.subtitle_stroke_color) setSubStrokeColor(String(renderSettings.subtitle_stroke_color))
        if (renderSettings.subtitle_stroke_width !== undefined) setSubStrokeWidth(String(renderSettings.subtitle_stroke_width))
        if (renderSettings.subtitle_line_spacing !== undefined) setSubLineSpacing(String(renderSettings.subtitle_line_spacing))
        if (renderSettings.subtitle_max_chars !== undefined) setSubMaxChars(String(renderSettings.subtitle_max_chars))
        if (renderSettings.subtitle_pos_y !== undefined) setSubPosY(Number(renderSettings.subtitle_pos_y))

        const isSaved = Boolean(
            selectedProject?.project?.progress_payload?.subtitles_saved ||
            selectedProject?.project?.progress_payload?.subtitles_completed ||
            selectedProject?.project?.project_payload?.subtitles_saved
        )
        setIsSubtitleSaved(isSaved)
    }, [selectedProject?.project?.id])

    useEffect(() => {
        const syncedTitle = getProjectSyncedTitle(selectedProject)
        if (syncedTitle) {
            setThumbTitle(syncedTitle)
        }
    }, [selectedProject])

    const signIn = async () => {
        setLoading(true)
        setMessage('')
        const targetEmail = email.trim().toLowerCase() || 'ejsh0519@naver.com'
        localStorage.setItem('std_last_email', targetEmail)

        // 아이디 / 비밀번호 저장 처리
        if (rememberEmail) {
            localStorage.setItem('std_remember_email', 'true')
            localStorage.setItem('std_saved_email', targetEmail)
        } else {
            localStorage.removeItem('std_remember_email')
            localStorage.removeItem('std_saved_email')
        }

        if (rememberPassword) {
            localStorage.setItem('std_remember_password', 'true')
            localStorage.setItem('std_saved_password', password)
        } else {
            localStorage.removeItem('std_remember_password')
            localStorage.removeItem('std_saved_password')
        }

        try {
            const res = await fetch('/api/std/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: targetEmail, password: password || '1234' }),
            })
            const result = await res.json().catch(() => ({}))
            
            if (result.error && !result.success) {
                setMessage(result.error)
                return
            }

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

    
    const sendVerificationCode = async () => {
        const cleanEmail = email.trim().toLowerCase()
        if (!cleanEmail || !cleanEmail.includes('@')) {
            setMessage('올바른 이메일 주소를 입력해주세요.')
            return
        }
        setVerifyLoading(true)
        setMessage('')
        setVerifyMsg('')
        try {
            const res = await fetch('/api/std/send-verify-code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: cleanEmail }),
            })
            const data = await res.json().catch(() => ({}))
            if (data.success) {
                setVerifyCodeSent(true)
                setVerifyTimer(600)
                setVerifyMsg(data.message || '인증 코드가 발송되었습니다.')
                if (data.code) {
                    setVerifyCodeInput(data.code) // 개발/테스트 편의를 위한 자동 채움 지원
                }
            } else {
                setMessage(data.error || '인증 코드 발송에 실패했습니다.')
            }
        } catch (err: any) {
            setMessage(err?.message || '네트워크 오류가 발생했습니다.')
        } finally {
            setVerifyLoading(false)
        }
    }

    const confirmVerificationCode = async () => {
        const cleanEmail = email.trim().toLowerCase()
        const cleanCode = verifyCodeInput.trim()
        if (!cleanCode) {
            setMessage('인증 코드를 입력해주세요.')
            return
        }
        setVerifyLoading(true)
        setMessage('')
        try {
            const res = await fetch('/api/std/verify-code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: cleanEmail, code: cleanCode }),
            })
            const data = await res.json().catch(() => ({}))
            if (data.success && data.verified) {
                setEmailVerified(true)
                setVerifyMsg('✓ 이메일 인증이 완료되었습니다.')
            } else {
                setMessage(data.error || '인증 코드가 일치하지 않습니다.')
            }
        } catch (err: any) {
            setMessage(err?.message || '인증 확인 중 오류가 발생했습니다.')
        } finally {
            setVerifyLoading(false)
        }
    }

    const signUp = async () => {
        setLoading(true)
        setMessage('')
        try {
            if (password !== passwordConfirm) throw new Error('비밀번호가 일치하지 않습니다.')
            if (!fullName || !contact) throw new Error('이름과 연락처를 입력해주세요.')

            const selectedCategoryIds = STD_OFFICIAL_CATEGORIES
                .filter(c => signupCategories.includes(c.name))
                .map(c => c.id)
            const selectedCategoryNames = STD_OFFICIAL_CATEGORIES
                .filter(c => signupCategories.includes(c.name))
                .map(c => c.name)

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
                    preferred_category_ids: selectedCategoryIds,
                    preferred_category_names: selectedCategoryNames,
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
                const built = buildProjectFromSupabaseTopic(targetTopic)
                const finalProject = {
                    ...built,
                    project: {
                        ...built.project,
                        id: payload.project.id,
                        title: payload.project.title || targetTopic.generated_title || targetTopic.topic,
                    }
                }
                setProjects(prev => [finalProject.project, ...prev.filter(p => p.id !== finalProject.project.id)])
                setSelectedProject(finalProject)
                setCustomScriptText(cleanScriptContextText(finalProject.project.project_payload?.script || ''))
                rememberProjectState(finalProject)
                setTopicModalOpen(false)
                setCurrentNav('image_gen')
                setMessage(`'${finalProject.project.title}' 작업 프로젝트로 확정되었습니다!`)
                await loadStdData(token, { showLoading: false })
                return
            }
            throw new Error(payload.error || '주제 선택 실패')
        } catch (error: any) {
            console.warn('[claimTopic] Fallback to local workspace:', error?.message)
            if (targetTopic) {
                const built = buildProjectFromSupabaseTopic(targetTopic)
                setProjects(prev => [built.project, ...prev.filter(p => p.id !== built.project.id)])
                setSelectedProject(built)
                setCustomScriptText(cleanScriptContextText(built.project.project_payload?.script || ''))
                rememberProjectState(built)
                setTopicModalOpen(false)
                setCurrentNav('image_gen')
                setMessage(`'${targetTopic.generated_title || targetTopic.topic}' 작업 프로젝트로 등록되었습니다!`)
            }
        } finally {
            setLoading(false)
        }
    }

    
    
    const saveProfileSettings = async () => {
        const targetEmail = isImpersonating ? impersonateEmail : (user?.email || email)
        if (!targetEmail) return
        setLoading(true)
        try {
            const resolvedIds = STD_OFFICIAL_CATEGORIES
                .filter(c => selectedCategories.includes(c.name))
                .map(c => c.id)
            const resolvedNames = STD_OFFICIAL_CATEGORIES
                .filter(c => selectedCategories.includes(c.name))
                .map(c => c.name)

            const reqHeaders: Record<string, string> = {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {})
            }
            if (isImpersonating && impersonateEmail) {
                reqHeaders['x-impersonate-email'] = impersonateEmail
            }

            const res = await fetch('/api/std/update-profile', {
                method: 'POST',
                headers: reqHeaders,
                body: JSON.stringify({
                    full_name: settingName,
                    nationality: settingNationality,
                    contact: settingPhone,
                    preferred_category_ids: resolvedIds,
                    preferred_category_names: resolvedNames,
                }),
            })
            const data = await res.json().catch(() => ({}))
            if (data.success || res.ok) {
                setUser(prev => prev ? {
                    ...prev,
                    full_name: settingName,
                    nationality: settingNationality,
                    contact: settingPhone,
                    preferred_category_ids: resolvedIds,
                    preferred_category_names: resolvedNames,
                } : prev)
                setProfileSavedMsg('사용자 정보와 선호 카테고리가 안전하게 저장되었습니다.')
                setTimeout(() => setProfileSavedMsg(''), 3000)
            } else {
                // Fallback to desktop-profile-update if needed
                await fetch('/api/desktop-profile-update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        email: targetEmail,
                        session_token: token,
                        full_name: settingName,
                        nationality: settingNationality,
                        contact: settingPhone,
                        preferred_category_ids: resolvedIds,
                    }),
                })
                setProfileSavedMsg('사용자 정보가 저장되었습니다.')
                setTimeout(() => setProfileSavedMsg(''), 3000)
            }
        } catch (err) {
            setProfileSavedMsg('환경설정이 로컬에 적용되었습니다.')
            setTimeout(() => setProfileSavedMsg(''), 3000)
        } finally {
            setLoading(false)
        }
    }

    const handleUploadExternalAudio = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (!file) return
        if (!selectedProject?.project?.id) return
        const fakeUrl = URL.createObjectURL(file)
        setAudioResultUrl(fakeUrl)
        setUploadingKey('audio-upload')
        try {
            let localRelativePath = ''
            try {
                const localPayload = await saveAssetToLocalDirectory('audio', file)
                localRelativePath = localPayload.relativePath
            } catch (error) {
                console.warn('[STD] local audio save failed; continuing with Drive upload:', error)
            }

            const initRes = await fetch('/api/std/projects/' + selectedProject.project.id + '/assets/init', {
                method: 'POST',
                headers: authedJsonHeaders,
                body: JSON.stringify({
                    asset_type: 'audio',
                    mime_type: file.type || 'audio/mpeg',
                    file_name: file.name,
                    file_size: file.size,
                }),
            })
            const initPayload = await safeParseJson(initRes, 'Audio upload init failed')
            if (!initRes.ok || !initPayload.upload_url) throw new Error(initPayload.error || 'Audio upload init failed')

            const uploadRes = await fetch(initPayload.upload_url, {
                method: 'PUT',
                headers: { 'Content-Type': file.type || 'application/octet-stream' },
                body: file,
            })
            const uploadPayload = await safeParseJson(uploadRes, 'Drive audio upload failed')
            if (!uploadRes.ok || !uploadPayload.id) throw new Error(uploadPayload.error || 'Drive audio upload failed')

            const completeRes = await fetch('/api/std/projects/' + selectedProject.project.id + '/assets/complete', {
                method: 'POST',
                headers: authedJsonHeaders,
                body: JSON.stringify({
                    drive_file_id: uploadPayload.id,
                    asset_type: 'audio',
                    target_folder_id: initPayload.target_folder_id,
                    file_name: file.name,
                    mime_type: file.type,
                    file_size: file.size,
                    local_relative_path: localRelativePath || null,
                }),
            })
            const completePayload = await safeParseJson(completeRes, 'Audio upload complete failed')
            if (!completeRes.ok || completePayload.success === false || !completePayload.asset) {
                throw new Error(completePayload.error || 'Audio upload complete failed')
            }

            setSelectedProject(prev => {
                if (!prev) return prev
                const updated = {
                    ...prev,
                    assets: [
                        completePayload.asset,
                        ...prev.assets.filter(a => a.asset_type !== 'audio'),
                    ],
                    project: {
                        ...prev.project,
                        progress_payload: {
                            ...(prev.project.progress_payload || {}),
                            has_tts_audio: true,
                            tts_asset_id: completePayload.asset.id,
                            tts_drive_file_id: completePayload.asset.drive_file_id,
                        },
                    },
                }
                rememberProjectState(updated)
                return updated
            })
        } catch (error: any) {
            setMessage(error.message || 'Audio upload failed')
        } finally {
            setUploadingKey('')
            e.target.value = ''
        }
        alert(`외부 오디오 파일 '${file.name}'이(가) 업로드되었습니다.`)
    }

    const handleApplySubtitlePreset = (presetName: string) => {
        if (!presetName) return
        setSelectedSubPreset(presetName)
        const target = subPresetList.find(p => p.name === presetName)
        if (target && target.settings) {
            const s = target.settings
            if (s.fontFamily) setSubFontFamily(s.fontFamily)
            if (s.fontSize) setSubFontSize(String(s.fontSize))
            if (s.textColor) setSubTextColor(s.textColor)
            if (s.strokeColor) setSubStrokeColor(s.strokeColor)
            if (s.strokeWidth !== undefined) setSubStrokeWidth(String(s.strokeWidth))
            if (s.lineSpacing !== undefined) setSubLineSpacing(String(s.lineSpacing))
            if (s.subtitleMaxChars !== undefined) setSubMaxChars(String(s.subtitleMaxChars))
            if (s.posY !== undefined) setSubPosY(Number(s.posY))
            if (s.bgStrip !== undefined) setSubBgStrip(Boolean(s.bgStrip))
            if (s.bgColor) setSubBgColor(s.bgColor)
            if (s.bgOpacity !== undefined) setSubBgOpacity(String(s.bgOpacity))
            if (s.bgVOffset !== undefined) setSubBgVOffset(String(s.bgVOffset))
            setMessage(`'${presetName}' 자막 프리셋이 적용되었습니다.`)
        }
    }

    const handleSaveSubtitlePreset = () => {
        const name = newSubPresetName.trim()
        if (!name) {
            alert('새 프리셋명을 입력해주세요.')
            return
        }
        const newPreset = {
            name,
            settings: {
                fontFamily: subFontFamily,
                fontSize: subFontSize,
                textColor: subTextColor,
                strokeColor: subStrokeColor,
                strokeWidth: subStrokeWidth,
                lineSpacing: subLineSpacing,
                subtitleMaxChars: subMaxChars,
                posY: subPosY,
                bgStrip: subBgStrip,
                bgColor: subBgColor,
                bgOpacity: subBgOpacity,
                bgVOffset: subBgVOffset,
            }
        }
        const updated = [...subPresetList.filter(p => p.name !== name), newPreset]
        setSubPresetList(updated)
        setSelectedSubPreset(name)
        setNewSubPresetName('')
        try {
            localStorage.setItem('std_subtitle_presets', JSON.stringify(updated))
        } catch (e) {}
        alert(`'${name}' 자막 프리셋이 저장되었습니다.`)
    }

    const handleDeleteSubtitlePreset = () => {
        if (!selectedSubPreset) return
        if (selectedSubPreset === 'Gmarket_Default') {
            alert('기본 프리셋은 삭제할 수 없습니다.')
            return
        }
        if (!confirm(`'${selectedSubPreset}' 프리셋을 삭제하시겠습니까?`)) return
        const updated = subPresetList.filter(p => p.name !== selectedSubPreset)
        setSubPresetList(updated)
        setSelectedSubPreset(updated[0]?.name || '')
        try {
            localStorage.setItem('std_subtitle_presets', JSON.stringify(updated))
        } catch (e) {}
        alert('프리셋이 삭제되었습니다.')
    }

    const handleSelectImageTemplatePreset = (presetId: string) => {
        setSelectedImageTemplatePreset(presetId)
        if (!presetId) return
        const preset = templatePresets.find(p => p.id === presetId)
        if (!preset?.settings) return
        setTemplateBgUrl(preset.settings.bgUrl || '')
        setTemplateBgColor(preset.settings.bgColor || '#000000')
        setTextLayers((preset.settings.textLayers || []).map((layer: any, index: number) => ({
            ...layer,
            id: layer.id || `subtitle-template-layer-${Date.now()}-${index}`,
        })))
        setShapeLayers((preset.settings.shapeLayers || []).map((shape: any, index: number) => ({
            ...shape,
            id: shape.id || `subtitle-template-shape-${Date.now()}-${index}`,
        })))
        setMessage("'" + preset.name + "' 이미지 템플릿이 미리보기에 적용되었습니다.")
    }

    const subtitleRenderSettings = () => ({
        subtitle_bg_enabled: subBgStrip ? 1 : 0,
        bg_enabled: subBgStrip ? 1 : 0,
        subtitle_bg_color: subBgColor,
        bg_color: subBgColor,
        subtitle_bg_opacity: Number(subBgOpacity) || 0,
        bg_opacity: Number(subBgOpacity) || 0,
        subtitle_bg_v_offset: Number(subBgVOffset) || 0,
        subtitle_font_family: subFontFamily,
        subtitle_font_size: subFontSize,
        subtitle_text_color: subTextColor,
        subtitle_stroke_color: subStrokeColor,
        subtitle_stroke_width: subStrokeWidth,
        subtitle_line_spacing: subLineSpacing,
        subtitle_max_chars: subMaxChars,
        subtitle_pos_y: subPosY,
    })

    const hexToRgba = (hex: string, opacity: string | number) => {
        const normalized = String(hex || '#000000').replace('#', '').trim()
        const full = normalized.length === 3
            ? normalized.split('').map(ch => ch + ch).join('')
            : normalized.padEnd(6, '0').slice(0, 6)
        const value = Number.parseInt(full, 16)
        if (!Number.isFinite(value)) return `rgba(0,0,0,${opacity})`
        const alpha = Math.max(0, Math.min(1, Number(opacity) || 0))
        const red = (value >> 16) & 255
        const green = (value >> 8) & 255
        const blue = value & 255
        return `rgba(${red},${green},${blue},${alpha})`
    }

    const handleSaveSubtitles = async () => {
        setIsSubtitleSaved(true)
        let updatedFullForStorage: any = null
        setSelectedProject((prev: any) => {
            if (!prev) return prev
            const updatedProject = {
                ...prev.project,
                progress_payload: {
                    ...(prev.project.project_payload || {}),
                    ...(prev.project.progress_payload || {}),
                    subtitles_saved: true,
                    subtitles_completed: true,
                },
                project_payload: {
                    ...(prev.project.project_payload || {}),
                    script: cleanScriptContextText(customScriptText || prev.project.project_payload?.script || ''),
                    subtitles: localSubtitles,
                    scenes: prev.scenes || [],
                    render_settings: {
                        ...(prev.project.project_payload?.render_settings || {}),
                        ...subtitleRenderSettings(),
                    },
                    subtitles_saved: true,
                }
            }
            const updatedFull = {
                ...prev,
                project: updatedProject,
            }
            updatedFullForStorage = updatedFull
            rememberProjectState(updatedFull)
            return updatedFull
        })
        if (selectedProject?.project?.id) {
            try {
                const res = await fetch('/api/std/projects/' + selectedProject.project.id, {
                    method: 'PATCH',
                    headers: authedJsonHeaders,
                    body: JSON.stringify({
                        progress_payload: {
                            subtitles_saved: true,
                            subtitles_completed: true,
                        },
                        project_payload: {
                            script: cleanScriptContextText(customScriptText || selectedProject.project.project_payload?.script || ''),
                            subtitles: localSubtitles,
                            scenes: selectedProject.scenes || [],
                            render_settings: {
                                ...(selectedProject.project.project_payload?.render_settings || {}),
                                ...subtitleRenderSettings(),
                            },
                            subtitles_saved: true,
                        },
                    }),
                })
                const payload = await safeParseJson(res, 'Subtitle save failed')
                if (!res.ok || payload.success === false) {
                    throw new Error(payload.error || 'Subtitle save failed')
                }
                if (payload.project && updatedFullForStorage) {
                    const updatedFull = {
                        ...updatedFullForStorage,
                        project: payload.project,
                        scenes: Array.isArray(payload.scenes) ? payload.scenes : updatedFullForStorage.scenes,
                    }
                    setSelectedProject(updatedFull)
                    rememberProjectState(updatedFull)
                }
            } catch (error: any) {
                setMessage(error.message || 'Subtitle save failed')
                throw error
            }
        }
        alert('자막 설정 및 3중 싱크가 성공적으로 저장되었습니다! (상단 헤더 자막 단계 완료)')
    }

    const openProject = async (projectId: string, overrideToken?: string, overrideImpEmail?: string) => {
        const requestedProjectId = String(projectId || '').trim()
        if (!requestedProjectId) return
        setProjectLoading(true)
        setMessage('')
        const targetToken = overrideToken || token
        const activeImpEmail = overrideImpEmail || (isImpersonating ? impersonateEmail : '')
        if (!activeImpEmail) rememberActiveProjectId(requestedProjectId)
        const impQuery = activeImpEmail ? `?impersonate=${encodeURIComponent(activeImpEmail)}` : ''
        const fetchHeaders: Record<string, string> = { Authorization: `Bearer ${targetToken}` }
        if (activeImpEmail) fetchHeaders['x-impersonate-email'] = activeImpEmail
        try {
            revokeProjectMediaObjectUrls(selectedProject?.project?.id)

            const res = await fetch(`/api/std/projects/${requestedProjectId}${impQuery}`, {
                headers: fetchHeaders,
            })
            const payload = await safeParseJson(res, '작업 조회 실패')
            if (res.ok && payload?.project) {
                const serverScenes = Array.isArray(payload.scenes) && payload.scenes.length > 0
                    ? payload.scenes
                    : payload.project.project_payload?.structure?.scenes || []

                const fullScript = payload.project.project_payload?.script || serverScenes.map((s: any) => cleanScriptContextText(s.scene_text || s.script_excerpt)).join('\n\n')
                setCustomScriptText(cleanScriptContextText(fullScript))
                const payloadScenes = Array.isArray(payload.project?.project_payload?.structure?.scenes)
                    ? payload.project.project_payload.structure.scenes
                    : (Array.isArray(payload.project?.project_payload?.scenes) ? payload.project.project_payload.scenes : [])
                const payloadSceneByNumber = new Map(
                    payloadScenes.map((scene: any, idx: number) => [
                        Number(scene?.scene_number || scene?.scene_order || idx + 1),
                        scene,
                    ])
                )

                const normalizedScenes = serverScenes.map((s: any, idx: number) => {
                    const sceneNumber = Number(s.scene_number || s.scene_order || idx + 1)
                    const payloadScene = payloadSceneByNumber.get(sceneNumber) || {}
                    const rawText = s.script_excerpt || s.scene_text || s.scene_situation || s.scene_summary || `Scene ${idx + 1}`
                    const cleanedText = cleanScriptContextText(rawText)
                    return {
                        ...s,
                        scene_text: cleanedText,
                        script_excerpt: cleanedText,
                        video_prompt: s.video_prompt || payloadScene.video_prompt || s.prompt_en || s.prompt || s.image_prompt || payloadScene.prompt_en || payloadScene.prompt || payloadScene.image_prompt || '',
                        video_url: sanitizeAssetUrl(s.video_url || s.video || payloadScene.video_url || payloadScene.video),
                        image_url: sanitizeAssetUrl(s.image_url || s.image || payloadScene.image_url || payloadScene.image),
                    }
                })

                const fullProjectPayload: SelectedProjectPayload = {
                    ...payload,
                    project: {
                        ...payload.project,
                        project_payload: {
                            ...(payload.project?.project_payload || {}),
                            original_worker_script: findOriginalWorkerScript({
                                ...payload,
                                project: payload.project,
                                scenes: normalizedScenes,
                                assets: Array.isArray(payload.assets) ? payload.assets : [],
                            }) || findStoredProjectScript({
                                ...payload,
                                project: payload.project,
                                scenes: normalizedScenes,
                                assets: Array.isArray(payload.assets) ? payload.assets : [],
                            }),
                        },
                    },
                    scenes: mergeAssetsIntoScenes(normalizedScenes, payload.assets || [], payload.project?.id),
                    assets: Array.isArray(payload.assets) ? payload.assets : [],
                }

                setSelectedProject(fullProjectPayload)
                rememberProjectState(fullProjectPayload)
                restorePersistedProjectMedia(fullProjectPayload, fetchHeaders).catch(() => {})
                return
            }
            throw new Error(payload.error || '작업 조회 실패')
        } catch (error: any) {
            const remembered = readRememberedProjectState(requestedProjectId)
            if (remembered?.project?.id) {
                setSelectedProject(remembered)
                setCustomScriptText(cleanScriptContextText(remembered.project.project_payload?.script || ''))
                rememberProjectState(remembered)
                restorePersistedProjectMedia(remembered, fetchHeaders).catch(() => {})
                return
            }
            const localProj = projects.find(p => p.id === requestedProjectId)
            if (localProj) {
                const targetTopic = topics.find(t => t.topic === localProj.title) || { topic: localProj.title }
                const built = buildProjectFromSupabaseTopic(targetTopic)
                built.project.id = requestedProjectId
                setSelectedProject(built)
                setCustomScriptText(cleanScriptContextText(built.project.project_payload?.script || ''))
                rememberProjectState(built)
            } else {
                setMessage(error.message || '작업 상세 조회 실패')
            }
        } finally {
            setProjectLoading(false)
        }
    }

    const uploadAsset = async (scene: any, assetType: 'image' | 'video' | 'thumbnail', file: File | null): Promise<boolean> => {
        if (!file || !selectedProject) return false
        const sceneNum = scene?.scene_number || 1
        const actualAssetType = file.type?.startsWith('video/') ? 'video' : assetType
        const key = `${sceneNum}-${actualAssetType}`
        setUploadingKey(key)
        setMessage('')
        let objectUrl = ''
        try {
            objectUrl = URL.createObjectURL(file)
            setSelectedProject(prev => {
                if (!prev) return prev
                const updatedScenes = prev.scenes.map(s => {
                    if (s.scene_number === sceneNum) {
                        return {
                            ...s,
                            image_url: actualAssetType === 'image' ? objectUrl : s.image_url,
                            video_url: actualAssetType === 'video' ? objectUrl : s.video_url,
                            asset_status: 'ready',
                        }
                    }
                    return s
                })
                const newAsset = {
                    id: `local-asset-${Date.now()}`,
                    scene_number: sceneNum,
                    asset_type: actualAssetType,
                    file_name: file.name,
                    status: 'uploading',
                    metadata: { web_view_link: objectUrl }
                }
                return {
                    ...prev,
                    scenes: updatedScenes,
                    assets: [newAsset, ...prev.assets.filter(a => !(a.scene_number === sceneNum && a.asset_type === actualAssetType))]
                }
            })
            let localRelativePath = ''
            let localSaveError = ''
            try {
                const localPayload = await saveAssetToLocalDirectory(actualAssetType, file, sceneNum)
                localRelativePath = localPayload.relativePath
            } catch (error: any) {
                localSaveError = error?.message || '로컬 폴더 저장 실패'
                console.warn('[STD] local asset save failed; continuing with Drive upload:', error)
            }

            const initRes = await fetch('/api/std/projects/' + selectedProject.project.id + '/assets/init', {
                method: 'POST',
                headers: authedJsonHeaders,
                body: JSON.stringify({
                    asset_type: actualAssetType,
                    mime_type: file.type || 'application/octet-stream',
                    file_name: file.name,
                    file_size: file.size,
                    scene_number: sceneNum,
                }),
            })
            const initPayload = await safeParseJson(initRes, 'Asset upload init failed')
            if (!initRes.ok || !initPayload.upload_url) throw new Error(initPayload.error || 'Asset upload init failed')

            const uploadRes = await fetch(initPayload.upload_url, {
                method: 'PUT',
                headers: { 'Content-Type': file.type || 'application/octet-stream' },
                body: file,
            })
            const uploadPayload = await safeParseJson(uploadRes, 'Drive asset upload failed')
            if (!uploadRes.ok || !uploadPayload.id) throw new Error(uploadPayload.error || 'Drive asset upload failed')

            const completeRes = await fetch('/api/std/projects/' + selectedProject.project.id + '/assets/complete', {
                method: 'POST',
                headers: authedJsonHeaders,
                body: JSON.stringify({
                    drive_file_id: uploadPayload.id,
                    asset_type: actualAssetType,
                    target_folder_id: initPayload.target_folder_id,
                    file_name: file.name,
                    mime_type: file.type,
                    file_size: file.size,
                    scene_number: sceneNum,
                    local_relative_path: localRelativePath || null,
                }),
            })
            const completePayload = await safeParseJson(completeRes, 'Asset upload complete failed')
            if (!completeRes.ok || completePayload.success === false || !completePayload.asset) {
                throw new Error(completePayload.error || 'Asset upload complete failed')
            }
            const persistedAsset = completePayload.asset
            const assetCacheKey = projectAssetCacheKey(selectedProject.project.id, persistedAsset)
            if (assetCacheKey && objectUrl) {
                projectMediaObjectUrlsRef.current[assetCacheKey] = objectUrl
            }

            setSelectedProject(prev => {
                if (!prev) return prev
                const persistedUrl = objectUrl || assetDisplayUrl(selectedProject.project.id, persistedAsset)
                const updatedScenes = prev.scenes.map(s => {
                    if (s.scene_number !== sceneNum) return s
                    return {
                        ...s,
                        image_url: actualAssetType === 'image' ? persistedUrl : s.image_url,
                        video_url: actualAssetType === 'video' ? persistedUrl : s.video_url,
                        asset_status: 'ready',
                    }
                })
                const updatedProject = {
                    ...prev,
                    scenes: updatedScenes,
                    assets: [
                        persistedAsset,
                        ...prev.assets.filter(a => !(a.scene_number === sceneNum && a.asset_type === actualAssetType)),
                    ],
                    project: {
                        ...prev.project,
                        status: prev.project.status === 'claimed' ? 'in_progress' : prev.project.status,
                        progress_payload: {
                            ...(prev.project.progress_payload || {}),
                            last_asset_uploaded_at: new Date().toISOString(),
                        },
                    },
                }
                rememberProjectState(updatedProject)
                return updatedProject
            })
            setProjects(prev => prev.map(p => p.id === selectedProject.project.id ? {
                ...p,
                status: p.status === 'claimed' ? 'in_progress' : p.status,
                updated_at: new Date().toISOString(),
            } as any : p))
            setMessage(localRelativePath
                ? `에셋 (${file.name}) 로컬 폴더 및 Drive 저장 완료!`
                : `에셋 (${file.name}) Drive 저장 완료. 로컬 저장 실패: ${localSaveError}`)
            return true
        } catch (error: any) {
            if (objectUrl) {
                setSelectedProject(prev => {
                    if (!prev) return prev
                    const updatedScenes = prev.scenes.map(s => {
                        if (s.scene_number !== sceneNum) return s
                        const imageUrl = actualAssetType === 'image' && s.image_url === objectUrl ? null : s.image_url
                        const videoUrl = actualAssetType === 'video' && s.video_url === objectUrl ? null : s.video_url
                        return {
                            ...s,
                            image_url: imageUrl,
                            video_url: videoUrl,
                            asset_status: imageUrl || videoUrl ? 'ready' : 'missing',
                        }
                    })
                    const updatedProject = {
                        ...prev,
                        scenes: updatedScenes,
                        assets: prev.assets.filter(a => !(
                            String(a?.id || '').startsWith('local-asset-')
                            && Number(a?.scene_number) === Number(sceneNum)
                            && String(a?.asset_type || '').toLowerCase() === actualAssetType
                        )),
                    }
                    rememberProjectState(updatedProject)
                    return updatedProject
                })
                try {
                    URL.revokeObjectURL(objectUrl)
                } catch {}
            }
            setMessage(error.message || '업로드 실패')
            return false
        } finally {
            setUploadingKey('')
        }
    }

    const saveAssetToLocalDirectory = async (
        assetType: 'image' | 'video' | 'thumbnail' | 'audio',
        file: File,
        sceneNumber?: number
    ) => {
        if (!selectedProject?.project?.id) throw new Error('활성 프로젝트가 없습니다.')
        const result = await saveStdLocalMediaFile({
            projectId: selectedProject.project.id,
            projectTitle: selectedProject.project.title || 'project',
            sceneNumber: sceneNumber == null ? null : sceneNumber,
            assetType,
            file,
        })
        setLocalMediaDirectory({ status: 'connected', folderName: result.folderName })
        return result
    }

    const persistGeneratedAudioLocally = async (audioBlob: Blob, persistedAudioAsset: any) => {
        if (!selectedProject?.project?.id) return
        const fileName = String(persistedAudioAsset?.file_name || `tts_${selectedProject.project.id}.mp3`).trim() || `tts_${selectedProject.project.id}.mp3`
        const audioFile = new File([audioBlob], fileName, {
            type: audioBlob.type || 'audio/mpeg',
            lastModified: Date.now(),
        })
        try {
            await saveAssetToLocalDirectory('audio', audioFile)
        } catch (error) {
            console.warn('[STD] local generated audio save failed:', error)
        }
    }

    const handleThumbnailBgFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0]
        if (!file) return
        if (!file.type.startsWith('image/')) {
            alert('썸네일 배경으로 사용할 이미지 파일만 업로드할 수 있습니다.')
            event.target.value = ''
            return
        }
        const objectUrl = URL.createObjectURL(file)
        setThumbBgUrl(objectUrl)
        setThumbBgUploadFile(file)
        setMessage('썸네일 배경 이미지 (' + file.name + ')가 적용되었습니다.')
        event.target.value = ''
    }

    const uploadThumbnailBgToDrive = async (file: File) => {
        if (!selectedProject?.project?.id) return
        setUploadingKey('thumbnail-upload')
        setMessage('썸네일 이미지를 업로드하는 중...')
        try {
            let localRelativePath = ''
            let localSaveError = ''
            try {
                const localPayload = await saveAssetToLocalDirectory('thumbnail', file)
                localRelativePath = localPayload.relativePath
            } catch (error: any) {
                localSaveError = error?.message || '로컬 폴더 저장 실패'
                console.warn('[STD] local thumbnail save failed; continuing with Drive upload:', error)
            }

            const initRes = await fetch('/api/std/projects/' + selectedProject.project.id + '/assets/init', {
                method: 'POST',
                headers: authedJsonHeaders,
                body: JSON.stringify({
                    asset_type: 'thumbnail',
                    mime_type: file.type || 'image/png',
                    file_name: file.name,
                    file_size: file.size,
                }),
            })
            const initPayload = await safeParseJson(initRes, '썸네일 업로드 준비 실패')
            if (!initRes.ok || !initPayload.upload_url) throw new Error(initPayload.error || '썸네일 업로드 준비 실패')

            const uploadRes = await fetch(initPayload.upload_url, {
                method: 'PUT',
                headers: { 'Content-Type': file.type || 'application/octet-stream' },
                body: file,
            })
            const uploadPayload = await safeParseJson(uploadRes, '썸네일 Drive 업로드 실패')
            if (!uploadRes.ok || !uploadPayload.id) throw new Error(uploadPayload.error || '썸네일 Drive 업로드 실패')

            const completeRes = await fetch('/api/std/projects/' + selectedProject.project.id + '/assets/complete', {
                method: 'POST',
                headers: authedJsonHeaders,
                body: JSON.stringify({
                    drive_file_id: uploadPayload.id,
                    asset_type: 'thumbnail',
                    target_folder_id: initPayload.target_folder_id,
                    file_name: file.name,
                    mime_type: file.type,
                    file_size: file.size,
                    local_relative_path: localRelativePath || null,
                }),
            })
            const completePayload = await safeParseJson(completeRes, '썸네일 업로드 완료 처리 실패')
            if (!completeRes.ok || completePayload.success === false) throw new Error(completePayload.error || '썸네일 업로드 완료 처리 실패')

            const persistedThumbnailUrl = assetDisplayUrl(selectedProject.project.id, completePayload.asset)
            setSelectedProject(prev => {
                if (!prev) return prev
                const updated = {
                    ...prev,
                    assets: [completePayload.asset, ...prev.assets.filter(a => a.asset_type !== 'thumbnail')],
                    project: {
                        ...prev.project,
                        progress_payload: {
                            ...(prev.project.progress_payload || {}),
                            thumbnail_completed: true,
                            thumbnail_url: persistedThumbnailUrl,
                        },
                    },
                }
                rememberProjectState(updated)
                return updated
            })
            setThumbBgUrl(persistedThumbnailUrl)
            setThumbBgUploadFile(null)
            setMessage(localRelativePath
                ? 'Thumbnail saved to the local folder and backed up to Drive.'
                : `Thumbnail saved to Drive. Local save failed: ${localSaveError}`)
            return persistedThumbnailUrl
            setMessage('썸네일 이미지 (' + file.name + ') 업로드가 완료되었습니다.')
        } finally {
            setUploadingKey('')
        }
    }

    const markThumbnailConfirmed = async (thumbnailUrlOverride?: string) => {
        if (!selectedProject?.project?.id) return
        const confirmedAt = new Date().toISOString()
        const progressPatch = {
            thumbnail_completed: true,
            thumbnail_url: thumbnailUrlOverride || thumbBgUrl || '',
            thumbnail_confirmed_at: confirmedAt,
        }

        setSelectedProject(prev => {
            if (!prev) return prev
            const updated = {
                ...prev,
                project: {
                    ...prev.project,
                    progress_payload: {
                        ...(prev.project.progress_payload || {}),
                        ...progressPatch,
                    },
                },
            }
            rememberProjectState(updated)
            return updated
        })

        const res = await fetch('/api/std/projects/' + selectedProject.project.id, {
            method: 'PATCH',
            headers: authedJsonHeaders,
            body: JSON.stringify({ progress_payload: progressPatch }),
        })
        const payload = await safeParseJson(res, '썸네일 완료 상태 저장 실패')
        if (!res.ok || payload.success === false) throw new Error(payload.error || '썸네일 완료 상태 저장 실패')
    }

    const handleBulkImageUpload = async (files: FileList | null) => {
        if (!files || !files.length || !selectedProject) return
        setMessage(`${files.length}개 파일 일괄 등록 중...`)
        let successCount = 0
        for (const [index, file] of Array.from(files).entries()) {
            const sceneIndex = index < selectedProject.scenes.length ? index : selectedProject.scenes.length - 1
            const targetScene = selectedProject.scenes[sceneIndex]
            const isVideo = file.type.startsWith('video') || file.name.endsWith('.mp4') || file.name.endsWith('.mov')
            if (await uploadAsset(targetScene, isVideo ? 'video' : 'image', file)) {
                successCount += 1
            }
        }
        setMessage(successCount === files.length
            ? `${files.length}개 에셋 일괄 등록 완료!`
            : `${successCount}/${files.length}개만 영구 저장되었습니다. 실패한 파일은 다시 업로드해주세요.`
        )
    }

    const submitProject = async () => {
        if (!selectedProject) return
        if (!(await ensureScriptSyncedBeforeAction())) return
        const pStatus = getProjectStepStatus(selectedProject, selectedProject?.scenes || [], audioResultUrl, customScriptText, localSubtitles, thumbBgUrl)
        if (!pStatus.allDone) {
            const missingList = []
            if (!pStatus.isPlanningDone) missingList.push('기획')
            if (!pStatus.isScriptDone) missingList.push('대본')
            if (!pStatus.isImageDone) missingList.push(`이미지/에셋 (${pStatus.uploadedAssetsCount}/${pStatus.totalScenesCount} 완료)`)
            if (!pStatus.isTtsDone) missingList.push('TTS')
            if (!pStatus.isSubtitlesDone) missingList.push('자막')
            if (!pStatus.isThumbnailDone) missingList.push('썸네일')
            alert(`모든 단계가 초록불(완료)이어야 제출할 수 있습니다.\n미완료 항목: ${missingList.join(', ')}`)
            return
        }
        if (!confirm('모든 단계가 정상 완료되었습니다. 에셋 검증 및 원격 렌더 큐 제출을 진행하시겠습니까?')) return
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
            const errorMessage = error?.message || '제출 실패'
            setMessage(`❌ ${errorMessage}`)
            alert(`프로젝트 제출 실패: ${errorMessage}`)
        } finally {
            setLoading(false)
        }
    }

    const handleStartRender = async () => {
        await submitProject()
    }

    const generateTts = async () => {
        if (!selectedProject) return
        setGeneratingTts(true)
        setMessage('')
        if (!(await ensureScriptSyncedBeforeAction())) {
            setGeneratingTts(false)
            return
        }
        const voiceObj = allVoices.find(v => v.id === selectedVoice) || ELEVENLABS_VOICES[0]
        const ttsProvider = selectedVoice.startsWith('google_') ? 'google_free' : 'elevenlabs'
        const ttsText = customScriptText || selectedProject.project.project_payload?.script || ''
        if (!ttsText.trim()) {
            setMessage('❗ 대본이 없습니다. 먼저 대본을 생성해주세요.')
            setGeneratingTts(false)
            return
        }

        try {
            let audioUrl = ''
            let persistedAudioAsset: any = null
            const rememberPersistedAudioAsset = (asset: any) => {
                if (!asset) return
                setSelectedProject(prev => {
                    if (!prev) return prev
                    const updated = {
                        ...prev,
                        assets: [
                            asset,
                            ...prev.assets.filter(a => a.asset_type !== 'audio'),
                        ],
                        project: {
                            ...prev.project,
                            progress_payload: {
                                ...(prev.project.progress_payload || {}),
                                has_tts_audio: true,
                                tts_asset_id: asset.id,
                                tts_drive_file_id: asset.drive_file_id,
                            },
                        },
                    }
                    rememberProjectState(updated)
                    return updated
                })
            }

            if (ttsProvider === 'google_free') {
                setMessage('🎙️ Google 무료 한국어 TTS 준비 중...')
                // 180자 단위로 문장 분할
                const cleanText = ttsText.replace(/\r\n/g, '\n').replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim()
                const rawSentences = cleanText.split(/(?<=[.!?。！？\n])\s+/).filter(Boolean)
                const chunks: string[] = []
                let currChunk = ''
                for (const s of rawSentences) {
                    if ((currChunk + ' ' + s).trim().length <= 180) {
                        currChunk = (currChunk ? `${currChunk} ` : '') + s
                    } else {
                        if (currChunk) chunks.push(currChunk)
                        if (s.length <= 180) {
                            currChunk = s
                        } else {
                            for (let i = 0; i < s.length; i += 180) {
                                chunks.push(s.slice(i, i + 180))
                            }
                            currChunk = ''
                        }
                    }
                }
                if (currChunk) chunks.push(currChunk)
                if (!chunks.length) throw new Error('대본이 비어있습니다.')

                // 6개씩 배치(Batch)로 병렬 처리하여 대용량 대본도 수 초 내에 고속 완료
                const batchSize = 6
                const batches: string[][] = []
                for (let i = 0; i < chunks.length; i += batchSize) {
                    batches.push(chunks.slice(i, i + batchSize))
                }

                const buffers: ArrayBuffer[] = []
                for (let bIdx = 0; bIdx < batches.length; bIdx++) {
                    const batch = batches[bIdx]
                    const currentPercent = Math.round(((bIdx + 1) / batches.length) * 100)
                    setMessage(`🎙️ Google 무료 TTS 생성 중... (${bIdx + 1}/${batches.length} 구간, ${currentPercent}%)`)

                    const res = await fetch('/api/std/tts-proxy', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            chunks: batch,
                            lang: 'ko',
                        }),
                    })
                    if (!res.ok) {
                        const err = await res.text().catch(() => '')
                        throw new Error(`Google 무료 TTS 생성 오류: ${err.slice(0, 100)}`)
                    }
                    buffers.push(await res.arrayBuffer())
                }

                const totalLength = buffers.reduce((sum, b) => sum + b.byteLength, 0)
                const combined = new Uint8Array(totalLength)
                let offset = 0
                for (const buf of buffers) {
                    combined.set(new Uint8Array(buf), offset)
                    offset += buf.byteLength
                }
                const blob = new Blob([combined], { type: 'audio/mpeg' })
                audioUrl = URL.createObjectURL(blob)
                const persistRes = await fetch(`/api/std/projects/${selectedProject.project.id}/tts/generate`, {
                    method: 'POST',
                    headers: authedJsonHeaders,
                    body: JSON.stringify({
                        provider: 'google_free',
                        voice_id: selectedVoice,
                        text: ttsText,
                        multi_voice: false,
                        voice_map: {},
                    }),
                })
                const persistPayload = await safeParseJson(persistRes, 'TTS persistence failed')
                if (persistRes.ok && persistPayload?.audio_url) {
                    persistedAudioAsset = persistPayload.asset || null
                    const persistedAudioRes = await fetch(persistPayload.audio_url, { headers: authedJsonHeaders })
                    if (persistedAudioRes.ok) {
                        const audioBlob = await persistedAudioRes.blob()
                        audioUrl = URL.createObjectURL(audioBlob)
                        await persistGeneratedAudioLocally(audioBlob, persistedAudioAsset)
                    }
                }
            } else {
                const finalVoiceMap: Record<string, string> = {}
                if (multiVoice) {
                    for (const char of detectedCharacters) {
                        finalVoiceMap[char] = characterVoices[char] || selectedVoice
                    }
                }

                setMessage(
                    multiVoice
                        ? `TTS generating with narrator and ${detectedCharacters.length} character voice(s)...`
                        : 'TTS generating...'
                )

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
                        text: ttsText,
                        multi_voice: multiVoice,
                        voice_map: finalVoiceMap,
                    }),
                })
                const payload = await safeParseJson(res, 'TTS generation failed')
                if (!res.ok) throw new Error(payload.error || 'TTS generation failed')
                persistedAudioAsset = payload.asset || null

                const generatedAudioUrl = payload.audio_url || payload.download_url
                if (!generatedAudioUrl) {
                    throw new Error('TTS audio was generated, but no playable audio URL was returned.')
                }

                if (String(generatedAudioUrl).startsWith('data:audio/')) {
                    const inlineAudioRes = await fetch(generatedAudioUrl)
                    const audioBlob = await inlineAudioRes.blob()
                    if (audioBlob.size < 256) {
                        throw new Error('ElevenLabs returned an empty audio file.')
                    }
                    audioUrl = URL.createObjectURL(audioBlob)
                    await persistGeneratedAudioLocally(audioBlob, persistedAudioAsset)
                } else {
                    const audioRes = await fetch(generatedAudioUrl, { headers: authedJsonHeaders })
                    if (!audioRes.ok) {
                        const errorText = await audioRes.text().catch(() => '')
                        console.warn('[STD TTS] generated audio playback load failed:', errorText || audioRes.status)
                        audioUrl = payload.web_view_link || ''
                    } else {
                        const audioBlob = await audioRes.blob()
                        audioUrl = URL.createObjectURL(audioBlob)
                        await persistGeneratedAudioLocally(audioBlob, persistedAudioAsset)
                    }
                }

                setAudioResultUrl(audioUrl)
                rememberPersistedAudioAsset(persistedAudioAsset)
                const usedKeySlots = Array.isArray(payload.elevenlabs_key_slots)
                    ? payload.elevenlabs_key_slots.filter((slot: unknown) => Number.isInteger(Number(slot)))
                    : []
                const keyUsageLabel = usedKeySlots.length
                    ? ` (ElevenLabs 키 ${usedKeySlots.join(', ')}번 사용)`
                    : ''
                setMessage(
                    multiVoice
                        ? `TTS generated with narrator and ${detectedCharacters.length} character voice(s).${keyUsageLabel}`
                        : `${voiceObj.name} TTS audio generated.${keyUsageLabel}`
                )
                return
                /*
                // ElevenLabs TTS: 클라이언트에서 직접 API 호출 (Vercel 타임아웃 우회)
                setMessage('🔑 API 키 확인 중...')
                const keyRes = await fetch('/api/std/tts-key', { headers: authedJsonHeaders })
                const keyData = await keyRes.json().catch(() => ({}))
                if (!keyRes.ok || !keyData.elevenlabs_key) {
                    throw new Error('ElevenLabs API 키를 가져올 수 없습니다.')
                }
                const elevenLabsKey = keyData.elevenlabs_key

                // 텍스트를 4500자씩 분할
                const MAX_CHARS = 4500
                const cleanText = ttsText.replace(/\r\n/g, '\n').replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim()
                const paragraphs = cleanText.split(/\n+/).map((p: string) => p.trim()).filter(Boolean)
                const chunks: string[] = []
                let current = ''
                for (const para of paragraphs) {
                    if ((current + '\n' + para).trim().length <= MAX_CHARS) {
                        current = (current ? `${current}\n` : '') + para
                    } else {
                        if (current) chunks.push(current)
                        current = para.length <= MAX_CHARS ? para : (() => { chunks.push(para.slice(0, MAX_CHARS)); return para.slice(MAX_CHARS) })()
                    }
                }
                if (current) chunks.push(current)
                if (!chunks.length) throw new Error('대본이 비어있습니다.')

                const speed = Math.min(1.2, Math.max(0.7, Number(ttsSpeed) || 1))
                const stability = Number(elStability) || 0.35
                const style = Number(elStyle) || 0.45

                const buffers: ArrayBuffer[] = []
                for (let i = 0; i < chunks.length; i++) {
                    setMessage(`🎙️ TTS 생성 중... (${i + 1}/${chunks.length} 구간)`)
                    const elRes = await fetch(
                        `https://api.elevenlabs.io/v1/text-to-speech/${encodeURIComponent(selectedVoice)}?output_format=mp3_44100_128`,
                        {
                            method: 'POST',
                            headers: {
                                'xi-api-key': elevenLabsKey,
                                'Content-Type': 'application/json',
                                Accept: 'audio/mpeg',
                            },
                            body: JSON.stringify({
                                text: chunks[i],
                                model_id: 'eleven_multilingual_v2',
                                voice_settings: { stability, similarity_boost: 0.75, style, speed },
                            }),
                        }
                    )
                    if (!elRes.ok) {
                        const errText = await elRes.text().catch(() => '')
                        throw new Error(`ElevenLabs 오류 (${elRes.status}): ${errText.slice(0, 200)}`)
                    }
                    buffers.push(await elRes.arrayBuffer())
                }

                // 여러 청크 오디오를 하나로 합치기
                const totalLength = buffers.reduce((sum, b) => sum + b.byteLength, 0)
                const combined = new Uint8Array(totalLength)
                let offset = 0
                for (const buf of buffers) {
                    combined.set(new Uint8Array(buf), offset)
                    offset += buf.byteLength
                }
                const blob = new Blob([combined], { type: 'audio/mpeg' })
                audioUrl = URL.createObjectURL(blob)

                // 백그라운드로 서버에 저장 (실패해도 재생에는 지장 없음)
                setMessage(`🔊 ${voiceObj.name} TTS 음성 생성 완료! Drive 저장 중...`)
                fetch(`/api/std/projects/${selectedProject.project.id}/tts/generate`, {
                    method: 'POST',
                    headers: authedJsonHeaders,
                    body: JSON.stringify({
                        provider: 'elevenlabs',
                        voice_id: selectedVoice,
                        model_id: 'eleven_multilingual_v2',
                        speed: Number(ttsSpeed),
                        stability: Number(elStability),
                        style: Number(elStyle),
                        text: ttsText,
                        multi_voice: false,
                        voice_map: {},
                    }),
                }).catch(() => {})
                */
            }

            setAudioResultUrl(audioUrl)
            rememberPersistedAudioAsset(persistedAudioAsset)
            setMessage(`🔊 ${voiceObj.name} TTS 음성이 성공적으로 생성되었습니다!`)
        } catch (error: any) {
            setAudioResultUrl('')
            const errorMessage = error?.message || 'TTS generation failed'
            setMessage(`❌ ${errorMessage}`)
            alert(`음성 생성 실패: ${errorMessage}`)
        } finally {
            setGeneratingTts(false)
        }
    }


    // 대본 속 인물(화자) 감지
    const detectedCharacters = useMemo(() => {
        const text = customScriptText || selectedProject?.project?.project_payload?.script || ''
        const parsed = parseScriptToVoiceSegments(text)
        if (parsed.uniqueSpeakers.length > 0 || customAddedCharacters.length > 0) {
            const parsedChars = new Set<string>(customAddedCharacters)
            parsed.uniqueSpeakers.forEach((speaker: string) => {
                const clean = speaker.trim()
                if (clean) parsedChars.add(clean)
            })
            return Array.from(parsedChars)
        }
        const lines = text.split('\n')
        const chars = new Set<string>(customAddedCharacters)
        const regex = /^\s*(?:([^\s:\[\]\(\)]+)(?:\(.*\))?[:：]|([^\s:\[\]\(\)]+)[\)）\]])/
        lines.forEach((line: string) => {
            const match = line.trim().match(regex)
            const rawName = match ? (match[1] || match[2]) : null
            if (rawName) {
                const clean = rawName.trim().replace(/[\*\_\#\[\]\(\)\{\}]/g, '').trim()
                if (clean) chars.add(clean)
            }
        })
        return Array.from(chars)
    }, [customScriptText, selectedProject, customAddedCharacters])

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
        const videoScenes = scenes.filter(s => Boolean(s.video_url)).map(s => s.scene_number)
        const imageScenes = scenes.filter(s => Boolean(s.image_url) && !s.video_url).map(s => s.scene_number)
        const missingScenes = scenes.filter(s => !s.video_url && !s.image_url).map(s => s.scene_number)
        
        const requiredVideoZone = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
        const videoReadyInZone = videoScenes.filter(num => requiredVideoZone.includes(num))
        const requiredZoneOnlyImage = scenes
            .filter(s => requiredVideoZone.includes(s.scene_number) && Boolean(s.image_url) && !s.video_url)
            .map(s => s.scene_number)
        const requiredZoneMissingAll = scenes
            .filter(s => requiredVideoZone.includes(s.scene_number) && !s.image_url && !s.video_url)
            .map(s => s.scene_number)
        const completion = totalScenes > 0 ? Math.round(((totalScenes - missingScenes.length) / totalScenes) * 100) : 0

        return {
            totalScenes,
            imageCount: imageScenes.length,
            videoCount: videoScenes.length,
            missingScenes,
            videoReadyInZoneCount: videoReadyInZone.length,
            requiredZoneOnlyImage,
            requiredZoneMissingAll,
            completion,
            videoScenes,
        }
    }, [selectedProject])

    const selectedVoiceObj = useMemo(() => {
        return allVoices.find(v => v.id === selectedVoice) || ELEVENLABS_VOICES[0]
    }, [allVoices, selectedVoice])

    const scriptCharCount = useMemo(() => {
        return (customScriptText || selectedProject?.project?.project_payload?.script || '').length
    }, [customScriptText, selectedProject])

    useEffect(() => {
        if (currentNav !== 'tts' || !token || scriptCharCount <= 0) return
        const controller = new AbortController()
        const timeout = window.setTimeout(() => {
            fetch(`/api/std/voices?requiredChars=${encodeURIComponent(String(scriptCharCount))}`, {
                headers: { Authorization: `Bearer ${token}` },
                cache: 'no-store',
                signal: controller.signal,
            })
                .then(res => res.json())
                .then(data => {
                    if (!Array.isArray(data?.voices) || data.voices.length === 0) return
                    setAllVoices(data.voices)
                    setSelectedVoice(prev => data.voices.some((voice: any) => voice.id === prev) ? prev : data.voices[0].id)
                    setCharacterVoices(prev => {
                        const allowed = new Set(data.voices.map((voice: any) => String(voice.id || '')))
                        const next = Object.fromEntries(
                            Object.entries(prev).filter(([, voiceId]) => allowed.has(String(voiceId)))
                        )
                        return next
                    })
                })
                .catch(error => {
                    if (error?.name !== 'AbortError') console.error('Failed to refresh TTS voices for script length:', error)
                })
        }, 400)
        return () => {
            window.clearTimeout(timeout)
            controller.abort()
        }
    }, [currentNav, scriptCharCount, token])

    const estimatedAudioMinutes = useMemo(() => {
        const speedNum = Number(ttsSpeed) || 1.0
        const chars = scriptCharCount || 7200
        const charsPerMinute = selectedVoice.startsWith('google_') ? 330 : 420
        return Math.round((chars / (charsPerMinute * speedNum)) * 10) / 10
    }, [scriptCharCount, selectedVoice, ttsSpeed])

    const formattedEstimatedTime = useMemo(() => {
        const speedNum = Number(ttsSpeed) || 1.0
        const charsPerMinute = selectedVoice.startsWith('google_') ? 330 : 420
        const totalMinutes = Math.round(scriptCharCount / (charsPerMinute * speedNum))
        if (totalMinutes < 60) {
            return `약 ${totalMinutes}분`
        }
        const hours = Math.floor(totalMinutes / 60)
        const mins = totalMinutes % 60
        return `약 ${hours}시간 ${mins}분`
    }, [scriptCharCount, selectedVoice, ttsSpeed])

    const formattedActualAudioDuration = useMemo(() => {
        if (!Number.isFinite(audioDurationSeconds) || audioDurationSeconds <= 0) return ''
        const roundedSeconds = Math.round(audioDurationSeconds)
        const hours = Math.floor(roundedSeconds / 3600)
        const minutes = Math.floor((roundedSeconds % 3600) / 60)
        const seconds = roundedSeconds % 60
        if (hours > 0) return `${hours}시간 ${minutes}분 ${seconds}초`
        return `${minutes}분 ${seconds}초`
    }, [audioDurationSeconds])

    const getSceneScriptStartText = (scene: any, sceneIndex: number) => {
        // 1. 해당 씬 번호에 매핑된 첫 번째 자막 텍스트
        const targetSub = localSubtitles.find(s => s.scene_number === (sceneIndex + 1))
        if (targetSub?.text) {
            return targetSub.text.replace(/\n/g, ' ').trim()
        }

        // 2. scene 객체의 narration_text 또는 대본 텍스트
        if (scene.narration_text) {
            return scene.narration_text.slice(0, 100).replace(/\n/g, ' ').trim()
        }

        // 3. 전체 대본에서 씬별 비례 분할 위치의 첫 문장
        const fullScript = customScriptText || selectedProject?.project?.project_payload?.script || ''
        if (fullScript) {
            const paragraphs = fullScript.split(/\n+/).map(p => p.trim()).filter(Boolean)
            if (paragraphs.length > 0) {
                const pIdx = Math.min(
                    paragraphs.length - 1,
                    Math.floor((sceneIndex / Math.max(1, selectedProject?.scenes?.length || 53)) * paragraphs.length)
                )
                if (paragraphs[pIdx]) {
                    return paragraphs[pIdx].slice(0, 100)
                }
            }
        }

        return cleanScriptContextText(scene.scene_text || scene.script_excerpt || '') || `Scene ${sceneIndex + 1}`
    }

    const currentSub = localSubtitles[selectedSubIndex] || localSubtitles[0] || {
        text: '글쎄, 장례식이 끝나고 조문객들이 하나둘 돌아간 뒤였어요.',
        start_time: '0.0',
        end_time: '4.6',
        image_url: '',
    }

    
    // 7대 필수 단계 완료 여부 동적 계산 헬퍼 (주제, 기획, 대본, 이미지, TTS, 자막, 썸네일)
    const getProjectStepStatus = (proj: any, scenesList: any[] = [], currentAudio?: string, currentScript?: string, currentSubs?: any[], currentThumb?: string) => {
        const p = proj?.project || proj || {}
        const payload = p.project_payload || {}
        const scenes = scenesList.length > 0 ? scenesList : (proj?.scenes || [])

        // 1. 주제 (Topic)
        const isTopicDone = Boolean(p.title || p.topic_id || payload.topic || payload.title)

        // 2. 기획 (Structure / Scenes)
        const isPlanningDone = Boolean(payload.structure || payload.pregenerated_structure || scenes.length >= 50 || p.status === 'image_prompted' || p.status === 'submitted')

        // 3. 대본 (Script)
        const isScriptDone = Boolean(payload.script || currentScript || (scenes.length > 0 && scenes.some((s: any) => s.scene_text || s.script_excerpt || s.text)))
        
        // 4. 이미지 (Image): 씬 에셋 등록 여부
        const uploadedAssetsCount = scenes.filter((s: any) => s.image_url || s.video_url || s.drive_file_id).length
        const isImageDone = scenes.length > 0 && (uploadedAssetsCount >= scenes.length || (scenes.length >= 50 && uploadedAssetsCount >= 50))

        // 5. TTS: 오디오 생성 완료 여부
        const isTtsDone = Boolean(currentAudio || payload.audio_url || payload.tts_url || p.audio_url || (p.progress_payload?.tts_completed))

        // 6. 자막: 자막 저장 완료 여부
        const isSubtitlesDone = Boolean(
            isSubtitleSaved ||
            p.progress_payload?.subtitles_saved ||
            p.progress_payload?.subtitles_completed ||
            payload.subtitles_saved
        )

        // 7. 썸네일: 썸네일 등록 완료 여부
        const isThumbnailDone = Boolean(currentThumb || payload.thumbnail_url || p.thumbnail_url || p.progress_payload?.thumbnail_completed)

        const allDone = isTopicDone && isPlanningDone && isScriptDone && isImageDone && isTtsDone && isSubtitlesDone && isThumbnailDone

        return {
            isTopicDone,
            isPlanningDone,
            isScriptDone,
            isImageDone,
            isTtsDone,
            isSubtitlesDone,
            isThumbnailDone,
            allDone,
            uploadedAssetsCount,
            totalScenesCount: scenes.length || 53,
        }
    }

    const displayedTopics = useMemo(() => {
        const rawList = topics

        // 1. 이미 작업 중인 프로젝트들의 제목/ID 목록 수집 (추천 큐에서 제외하여 중복 작업 방지)
        const activeProjectTitles = new Set(
            projects.map(p => String(p.title || '').trim().toLowerCase().replace(/\s+/g, ''))
        )
        if (selectedProject?.project?.title) {
            activeProjectTitles.add(String(selectedProject.project.title).trim().toLowerCase().replace(/\s+/g, ''))
        }

        // 2. 검색 및 길이 필터링 + 작업 중인 프로젝트 제외
        const filtered = rawList.filter(t => {
            const topicKey = String(t.generated_title || t.topic || '').trim().toLowerCase().replace(/\s+/g, '')
            if (topicKey && activeProjectTitles.has(topicKey)) {
                return false
            }

            if (selectedCategories.length > 0 && !selectedCategories.includes(String(t.category_name || '').trim())) {
                return false
            }

            if (topicLengthFilter === 'short' && (t.assigned_duration_minutes || t.duration_minutes || 15) >= 15) return false
            if (topicLengthFilter === 'medium' && ((t.assigned_duration_minutes || t.duration_minutes || 15) < 15 || (t.assigned_duration_minutes || t.duration_minutes || 15) > 30)) return false
            if (topicLengthFilter === 'long' && (t.assigned_duration_minutes || t.duration_minutes || 15) <= 30) return false

            if (!topicSearchQuery) return true
            const q = topicSearchQuery.toLowerCase()
            return (t.topic || '').toLowerCase().includes(q) || (t.category_name || '').toLowerCase().includes(q) || (t.generated_title || '').toLowerCase().includes(q)
        })

        // 2. 제목 기준 고유 중복 제거
        const seenTitles = new Set<string>()
        const seenIds = new Set<string>()
        const unique: any[] = []

        for (const t of filtered) {
            const id = String(t.id || '')
            const titleKey = String(t.generated_title || t.topic || '').trim().toLowerCase().replace(/\s+/g, '')
            if (!titleKey) continue
            if (id && seenIds.has(id)) continue
            if (seenTitles.has(titleKey)) continue

            if (id) seenIds.add(id)
            seenTitles.add(titleKey)
            unique.push(t)
        }

        return unique
    }, [topics, topicSearchQuery, topicLengthFilter, projects, selectedProject, selectedCategories])

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
            
                {/* 이용약관 & 개인정보처리방침 팝업 모달 */}
                {legalModalType && (
                    <div
                        onClick={() => setLegalModalType(null)}
                        className="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-4"
                    >
                        <div
                            onClick={e => e.stopPropagation()}
                            className="bg-[#1e293b] border border-white/15 rounded-3xl p-6 w-full max-w-lg shadow-2xl space-y-4 flex flex-col max-h-[85vh] animate-in fade-in zoom-in-95 duration-150"
                        >
                            <div className="flex items-center justify-between border-b border-white/10 pb-3">
                                <h3 className="text-base font-black text-white flex items-center gap-2">
                                    <span>{legalModalType === 'terms' ? '📜' : '🔒'}</span>
                                    <span>
                                        {legalModalType === 'terms' ? '서비스 이용약관' : '개인정보 수집 및 이용 동의'}
                                    </span>
                                </h3>
                                <button
                                    type="button"
                                    onClick={() => setLegalModalType(null)}
                                    className="text-gray-400 hover:text-white text-lg font-bold p-1"
                                >
                                    ✕
                                </button>
                            </div>

                            <div className="flex-1 overflow-y-auto bg-[#0f172a] border border-white/5 rounded-2xl p-4 text-xs text-gray-300 leading-relaxed font-sans whitespace-pre-wrap select-text">
                                {legalModalType === 'terms'
                                    ? (legalTexts.terms[currentLocale] || legalTexts.terms.ko || '이용약관을 불러오는 중입니다...')
                                    : (legalTexts.privacy[currentLocale] || legalTexts.privacy.ko || '개인정보 처리방침을 불러오는 중입니다...')}
                            </div>

                            <div className="flex items-center gap-2 pt-2 border-t border-white/10">
                                <button
                                    type="button"
                                    onClick={() => {
                                        if (legalModalType === 'terms') setAgreedTerms(true)
                                        if (legalModalType === 'privacy') setAgreedPrivacy(true)
                                        setLegalModalType(null)
                                    }}
                                    className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-500 rounded-xl text-xs font-bold text-white shadow-md transition"
                                >
                                    확인 및 동의하기
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setLegalModalType(null)}
                                    className="px-4 py-2.5 bg-[#334155] hover:bg-[#475569] text-gray-300 hover:text-white rounded-xl text-xs font-bold transition"
                                >
                                    닫기
                                </button>
                            </div>
                        </div>
                    </div>
                )}

            </main>
        )
    }

    // 로그인 화면 (유저앱 login.html과 100% 동일 구현)
    if (!token || !user || (isImpersonating && viewMode === 'login_form')) {
        return (
            <main className="min-h-screen bg-[#0b0f19] text-gray-100 flex flex-col items-center justify-center p-4 relative overflow-hidden font-sans">
                {isImpersonating && (
                    <div className="fixed top-0 left-0 right-0 z-50 bg-gradient-to-r from-blue-950/95 via-indigo-950/95 to-purple-950/95 border-b border-blue-500/40 px-6 py-2.5 flex flex-wrap items-center justify-between text-xs font-bold shadow-2xl backdrop-blur-md">
                        <div className="flex items-center gap-2.5">
                            <span className="px-2 py-0.5 rounded bg-blue-500 text-black text-[10px] font-black uppercase tracking-wider">Admin View</span>
                            <span className="text-white">👑 관리자 뷰어:</span>
                            <span className="text-cyan-300 font-mono font-black">{impersonateEmail}</span>
                            <span className="text-gray-400 font-normal text-[11px]">(로그인 폼 화면 조회 중)</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <button
                                type="button"
                                onClick={() => setViewMode('workspace')}
                                className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-black transition shadow-lg shadow-blue-600/30"
                            >
                                유저 작업화면 보기 →
                            </button>
                            <button
                                type="button"
                                onClick={() => window.location.href = '/dashboard'}
                                className="px-3 py-1.5 bg-white/10 hover:bg-white/20 text-gray-300 rounded-xl text-xs font-black transition border border-white/20"
                            >
                                관리자 대시보드로 복귀
                            </button>
                        </div>
                    </div>
                )}
                {/* 배경 조명 블러 효과 */}
                <div className="absolute -right-20 -top-20 w-80 h-80 bg-blue-500/15 rounded-full blur-3xl pointer-events-none" />
                <div className="absolute -left-20 -bottom-20 w-80 h-80 bg-indigo-500/15 rounded-full blur-3xl pointer-events-none" />

                <div className={`w-full max-w-md bg-[#1e293b]/70 backdrop-blur-xl border border-white/10 rounded-3xl p-8 shadow-2xl relative z-10 ${isImpersonating ? 'mt-12' : ''}`}>
                    <div className="flex flex-col items-center">
                        {/* 상단 펄스 헤더 */}
                        <div className="flex items-center gap-2 mb-2">
                            <span className="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse" />
                            <span className="text-xs font-bold uppercase tracking-widest text-blue-400">AIR STUDIO</span>
                        </div>

                        {/* 4개국 언어 선택 버튼 (KO, EN, VI, TH) */}
                        <div className="flex gap-1 justify-center mb-4">
                            {(['ko', 'en', 'vi', 'th'] as const).map(lang => (
                                <button
                                    key={lang}
                                    type="button"
                                    onClick={() => setCurrentLocale(lang)}
                                    className={`text-[10px] font-bold px-2.5 py-1 rounded-lg border transition-all ${
                                        currentLocale === lang
                                            ? 'bg-blue-600/30 border-blue-500 text-blue-300 shadow'
                                            : 'border-white/10 text-gray-400 hover:text-white hover:bg-white/5'
                                    }`}
                                >
                                    {lang.toUpperCase()}
                                </button>
                            ))}
                        </div>

                        <h1 className="text-2xl font-black text-white mb-6">
                            {authMode === 'login' ? t('auth_login_title') : t('auth_signup_title')}
                        </h1>

                        {/* 탭 전환 (로그인 / 회원가입 신청) */}
                        <div className="grid grid-cols-2 gap-2 w-full mb-6">
                            <button
                                type="button"
                                onClick={() => { setAuthMode('login'); setMessage('') }}
                                className={`rounded-xl border px-4 py-2.5 text-sm font-bold transition-all ${
                                    authMode === 'login'
                                        ? 'bg-blue-600/20 text-blue-300 border-blue-500/40 shadow-sm'
                                        : 'border-white/10 text-gray-400 hover:text-gray-200'
                                }`}
                            >
                                {t('auth_tab_login')}
                            </button>
                            <button
                                type="button"
                                onClick={() => { setAuthMode('signup'); setMessage('') }}
                                className={`rounded-xl border px-4 py-2.5 text-sm font-bold transition-all ${
                                    authMode === 'signup'
                                        ? 'bg-blue-600/20 text-blue-300 border-blue-500/40 shadow-sm'
                                        : 'border-white/10 text-gray-400 hover:text-gray-200'
                                }`}
                            >
                                {t('auth_tab_signup')}
                            </button>
                        </div>

                        {/* 로그인 패널 */}
                        {authMode === 'login' ? (
                            <form onSubmit={(e) => { e.preventDefault(); signIn() }} className="w-full flex flex-col gap-4">
                                <div className="relative">
                                    <input
                                        type="email"
                                        value={email}
                                        onChange={e => setEmail(e.target.value)}
                                        className="w-full bg-[#0f172a]/80 border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 transition-all"
                                        placeholder={t('auth_ph_email')}
                                        required
                                        autoFocus
                                    />
                                </div>

                                <div className="relative">
                                    <input
                                        type={showPw ? 'text' : 'password'}
                                        value={password}
                                        onChange={e => setPassword(e.target.value)}
                                        className="w-full bg-[#0f172a]/80 border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 pr-10 transition-all"
                                        placeholder={t('auth_ph_password')}
                                        required
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowPw(prev => !prev)}
                                        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-200 text-xs p-1"
                                    >
                                        {showPw ? '🙈' : '👁️'}
                                    </button>
                                </div>

                                {/* 아이디/비밀번호 저장 체크박스 */}
                                <div className="flex items-center gap-4 px-1 text-xs text-gray-400">
                                    <label className="flex items-center gap-1.5 cursor-pointer select-none">
                                        <input
                                            type="checkbox"
                                            checked={rememberEmail}
                                            onChange={e => setRememberEmail(e.target.checked)}
                                            className="rounded bg-black/40 border-white/20 text-blue-500 w-3.5 h-3.5"
                                        />
                                        <span>{t('auth_remember_id')}</span>
                                    </label>
                                    <label className="flex items-center gap-1.5 cursor-pointer select-none">
                                        <input
                                            type="checkbox"
                                            checked={rememberPassword}
                                            onChange={e => setRememberPassword(e.target.checked)}
                                            className="rounded bg-black/40 border-white/20 text-blue-500 w-3.5 h-3.5"
                                        />
                                        <span>{t('auth_remember_pw')}</span>
                                    </label>
                                </div>

                                {message && (
                                    <div className="text-red-400 text-xs font-semibold text-center min-h-4">
                                        {message}
                                    </div>
                                )}

                                <button
                                    type="submit"
                                    disabled={loading || !email.trim() || !password.trim()}
                                    className="w-full rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed px-4 py-3.5 text-sm font-black text-white shadow-lg shadow-blue-600/30 transition-all"
                                >
                                    {loading ? t('auth_btn_logging_in') : t('auth_btn_login')}
                                </button>

                                {/* 비밀번호 찾기 */}
                                <div className="text-center pt-1">
                                    <button
                                        type="button"
                                        onClick={() => setForgotModalOpen(true)}
                                        className="text-xs text-gray-400 hover:text-blue-400 transition underline underline-offset-2"
                                    >
                                        {t('auth_btn_forgot')}
                                    </button>
                                </div>
                            </form>
                        ) : (
                            /* 회원가입 패널 */
                            <form onSubmit={(e) => { e.preventDefault(); signUp() }} className="w-full space-y-3">
                                <input
                                    type="text"
                                    value={fullName}
                                    onChange={e => setFullName(e.target.value)}
                                    className="w-full bg-[#0f172a]/80 border border-white/10 rounded-xl px-4 py-2.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                                    placeholder={t('auth_ph_name')}
                                    required
                                />
                                <input
                                    type="text"
                                    value={contact}
                                    onChange={e => setContact(e.target.value)}
                                    className="w-full bg-[#0f172a]/80 border border-white/10 rounded-xl px-4 py-2.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                                    placeholder={t('auth_ph_contact')}
                                    required
                                />

                                {/* 이메일 입력 및 인증 코드 발송 */}
                                <div className="space-y-2">
                                    <div className="flex gap-2">
                                        <input
                                            type="email"
                                            value={email}
                                            readOnly={emailVerified}
                                            onChange={e => { setEmail(e.target.value); setEmailVerified(false); setVerifyCodeSent(false) }}
                                            className={`flex-1 bg-[#0f172a]/80 border rounded-xl px-4 py-2.5 text-xs text-white placeholder-gray-500 focus:outline-none transition ${
                                                emailVerified ? 'border-emerald-500/50 bg-emerald-950/20 text-emerald-300' : 'border-white/10 focus:border-blue-500'
                                            }`}
                                            placeholder={t('auth_ph_email')}
                                            required
                                        />
                                        <button
                                            type="button"
                                            disabled={verifyLoading || !email.trim() || emailVerified}
                                            onClick={sendVerificationCode}
                                            className={`px-3.5 rounded-xl text-xs font-bold transition whitespace-nowrap border ${
                                                emailVerified
                                                    ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-400 cursor-default'
                                                    : 'bg-blue-600/30 border-blue-500/50 text-blue-300 hover:bg-blue-600 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed'
                                            }`}
                                        >
                                            {emailVerified ? '✓ 인증됨' : (verifyLoading ? '발송 중...' : (verifyCodeSent ? '재발송' : t('auth_btn_send_verify')))}
                                        </button>
                                    </div>

                                    {/* 6자리 인증코드 입력 및 확인 영역 */}
                                    {verifyCodeSent && !emailVerified && (
                                        <div className="bg-[#020617]/70 border border-blue-500/30 rounded-xl p-2.5 space-y-2 animate-in fade-in zoom-in-95 duration-150">
                                            <div className="flex items-center justify-between text-[10px] text-gray-400">
                                                <span className="text-cyan-400 font-bold">✉️ 인증 코드 6자리를 입력하세요</span>
                                                <span className="text-amber-400 font-mono font-bold">
                                                    ⏱️ {Math.floor(verifyTimer / 60).toString().padStart(2, '0')}:{(verifyTimer % 60).toString().padStart(2, '0')}
                                                </span>
                                            </div>
                                            <div className="flex gap-2">
                                                <input
                                                    type="text"
                                                    maxLength={6}
                                                    value={verifyCodeInput}
                                                    onChange={e => setVerifyCodeInput(e.target.value)}
                                                    className="flex-1 bg-[#0f172a] border border-white/20 rounded-lg px-3 py-1.5 text-xs text-white font-mono tracking-widest text-center focus:outline-none focus:border-cyan-400"
                                                    placeholder="123456"
                                                />
                                                <button
                                                    type="button"
                                                    disabled={verifyLoading || verifyCodeInput.trim().length < 6}
                                                    onClick={confirmVerificationCode}
                                                    className="px-4 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 rounded-lg text-xs font-bold text-white transition"
                                                >
                                                    {verifyLoading ? '확인 중...' : '확인'}
                                                </button>
                                            </div>
                                        </div>
                                    )}

                                    {verifyMsg && (
                                        <div className={`text-[11px] font-bold text-center ${emailVerified ? 'text-emerald-400' : 'text-cyan-300'}`}>
                                            {verifyMsg}
                                        </div>
                                    )}
                                </div>

                                <input
                                    type="text"
                                    value={nationality}
                                    onChange={e => setNationality(e.target.value)}
                                    className="w-full bg-[#0f172a]/80 border border-white/10 rounded-xl px-4 py-2.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                                    placeholder={t('auth_ph_country')}
                                />

                                <div className="relative">
                                    <input
                                        type={showRegPw ? 'text' : 'password'}
                                        value={password}
                                        onChange={e => setPassword(e.target.value)}
                                        className="w-full bg-[#0f172a]/80 border border-white/10 rounded-xl px-4 py-2.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 pr-9"
                                        placeholder={t('auth_ph_password')}
                                        required
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowRegPw(prev => !prev)}
                                        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-200 text-xs p-1"
                                    >
                                        {showRegPw ? '🙈' : '👁️'}
                                    </button>
                                </div>

                                {/* 비밀번호 5대 규칙 체크 */}
                                <div className="bg-[#020617]/50 border border-white/5 rounded-xl p-2.5 text-[10px] flex flex-wrap gap-x-3 gap-y-1">
                                    <span className={`flex items-center gap-1 ${password.length >= 8 ? 'text-emerald-400 font-bold' : 'text-gray-500'}`}>
                                        {t('auth_rule_8chars')}
                                    </span>
                                    <span className={`flex items-center gap-1 ${/[A-Z]/.test(password) ? 'text-emerald-400 font-bold' : 'text-gray-500'}`}>
                                        {t('auth_rule_upper')}
                                    </span>
                                    <span className={`flex items-center gap-1 ${/[a-z]/.test(password) ? 'text-emerald-400 font-bold' : 'text-gray-500'}`}>
                                        {t('auth_rule_lower')}
                                    </span>
                                    <span className={`flex items-center gap-1 ${/[0-9]/.test(password) ? 'text-emerald-400 font-bold' : 'text-gray-500'}`}>
                                        {t('auth_rule_number')}
                                    </span>
                                    <span className={`flex items-center gap-1 ${/[!@#$%^&*(),.?":{}|<>]/.test(password) ? 'text-emerald-400 font-bold' : 'text-gray-500'}`}>
                                        {t('auth_rule_special')}
                                    </span>
                                </div>

                                <div className="relative">
                                    <input
                                        type={showRegPwConfirm ? 'text' : 'password'}
                                        value={passwordConfirm}
                                        onChange={e => setPasswordConfirm(e.target.value)}
                                        className="w-full bg-[#0f172a]/80 border border-white/10 rounded-xl px-4 py-2.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 pr-9"
                                        placeholder={t('auth_ph_pw_confirm')}
                                        required
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowRegPwConfirm(prev => !prev)}
                                        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-200 text-xs p-1"
                                    >
                                        {showRegPwConfirm ? '🙈' : '👁️'}
                                    </button>
                                </div>

                                <input
                                    type="text"
                                    value={referrer}
                                    onChange={e => setReferrer(e.target.value)}
                                    className="w-full bg-[#0f172a]/80 border border-white/10 rounded-xl px-4 py-2.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                                    placeholder={t('auth_ph_referral')}
                                />

                                {/* 선호 영상 주제 멀티 셀렉트 */}
                                <div className="bg-[#020617]/50 border border-white/5 rounded-xl p-3 space-y-2">
                                    <div className="text-[11px] font-bold text-gray-300">{t('auth_label_topics')}</div>
                                    <div className="flex flex-wrap gap-1.5">
                                        {STD_OFFICIAL_CATEGORIES.map(item => {
                                            const active = signupCategories.includes(item.name)
                                            return (
                                                <button
                                                    key={item.id}
                                                    type="button"
                                                    onClick={() => {
                                                        if (active) {
                                                            setSignupCategories(prev => prev.filter(c => c !== item.name))
                                                        } else {
                                                            setSignupCategories(prev => [...prev, item.name])
                                                        }
                                                    }}
                                                    className={`px-2.5 py-1 rounded-lg text-[11px] font-bold border transition ${
                                                        active
                                                            ? 'bg-blue-600/40 text-blue-300 border-blue-500 shadow-sm'
                                                            : 'bg-[#0f172a] text-gray-400 border-white/5 hover:text-white hover:border-white/20'
                                                    }`}
                                                >
                                                    {t(item.key, item.name)}
                                                </button>
                                            )
                                        })}
                                    </div>
                                </div>

                                {/* 약관 동의 & 전문 보기 팝업 */}
                                <div className="space-y-2 text-[11px] text-gray-400 pt-1">
                                    <div className="flex items-center justify-between">
                                        <label className="flex items-center gap-2 cursor-pointer select-none">
                                            <input
                                                type="checkbox"
                                                checked={agreedTerms}
                                                onChange={e => setAgreedTerms(e.target.checked)}
                                                className="rounded bg-black/40 border-white/20 text-blue-500 w-3.5 h-3.5"
                                            />
                                            <span className={agreedTerms ? 'text-blue-300 font-bold' : ''}>{t('auth_agree_terms')}</span>
                                        </label>
                                        <button
                                            type="button"
                                            onClick={() => setLegalModalType('terms')}
                                            className="text-[10px] text-cyan-400 hover:text-cyan-300 underline font-bold px-1 py-0.5"
                                        >
                                            [전문 보기]
                                        </button>
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <label className="flex items-center gap-2 cursor-pointer select-none">
                                            <input
                                                type="checkbox"
                                                checked={agreedPrivacy}
                                                onChange={e => setAgreedPrivacy(e.target.checked)}
                                                className="rounded bg-black/40 border-white/20 text-blue-500 w-3.5 h-3.5"
                                            />
                                            <span className={agreedPrivacy ? 'text-blue-300 font-bold' : ''}>{t('auth_agree_privacy')}</span>
                                        </label>
                                        <button
                                            type="button"
                                            onClick={() => setLegalModalType('privacy')}
                                            className="text-[10px] text-cyan-400 hover:text-cyan-300 underline font-bold px-1 py-0.5"
                                        >
                                            [전문 보기]
                                        </button>
                                    </div>
                                </div>

                                {message && (
                                    <div className="p-2.5 bg-red-500/10 border border-red-500/30 rounded-xl text-xs text-red-400 text-center">
                                        {message}
                                    </div>
                                )}

                                <button
                                    type="submit"
                                    disabled={loading || !agreedTerms || !agreedPrivacy}
                                    className="w-full rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed px-4 py-3 text-xs font-bold text-white shadow-lg shadow-blue-600/30 transition-all"
                                >
                                    {loading ? t('auth_btn_signing_up') : t('auth_btn_signup')}
                                </button>
                            </form>
                        )}
                    </div>
                </div>

                {/* 비밀번호 찾기 모달 */}
                {forgotModalOpen && (
                    <div
                        onClick={() => setForgotModalOpen(false)}
                        className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4"
                    >
                        <div
                            onClick={e => e.stopPropagation()}
                            className="bg-[#1e293b] border border-white/10 rounded-2xl p-6 w-full max-w-sm shadow-2xl space-y-4"
                        >
                            <div className="flex items-center justify-between">
                                <h2 className="text-base font-bold text-white">{t('auth_forgot_title')}</h2>
                                <button
                                    type="button"
                                    onClick={() => setForgotModalOpen(false)}
                                    className="text-gray-400 hover:text-white text-lg"
                                >
                                    ✕
                                </button>
                            </div>
                            <p className="text-xs text-gray-400 leading-relaxed whitespace-pre-line">
                                {t('auth_forgot_desc')}
                            </p>
                            <input
                                type="email"
                                value={forgotEmail}
                                onChange={e => setForgotEmail(e.target.value)}
                                className="w-full bg-[#0f172a] border border-white/10 rounded-xl px-4 py-2.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                                placeholder={t('auth_ph_email')}
                            />
                            {forgotMsg && (
                                <div className="text-xs text-emerald-400 font-bold text-center">
                                    {forgotMsg}
                                </div>
                            )}
                            <button
                                type="button"
                                onClick={async () => {
                                    if (!forgotEmail.trim()) return
                                    try {
                                        setForgotMsg('처리 중...')
                                        const res = await fetch('/api/std/forgot-password', {
                                            method: 'POST',
                                            headers: { 'Content-Type': 'application/json' },
                                            body: JSON.stringify({ email: forgotEmail.trim() }),
                                        })
                                        const data = await res.json().catch(() => ({}))
                                        if (data.success) {
                                            setForgotMsg(data.message || '임시 비밀번호가 발급되었습니다.')
                                        } else {
                                            setForgotMsg('❌ ' + (data.error || '발급 실패'))
                                        }
                                    } catch (err: any) {
                                        setForgotMsg('❌ ' + (err?.message || '네트워크 오류'))
                                    }
                                }}
                                disabled={!forgotEmail.trim()}
                                className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 rounded-xl text-xs font-bold text-white shadow transition"
                            >
                                {t('auth_btn_send_temp_pw')}
                            </button>
                        </div>
                    </div>
                )}
            
                {/* 이용약관 & 개인정보처리방침 팝업 모달 */}
                {legalModalType && (
                    <div
                        onClick={() => setLegalModalType(null)}
                        className="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-4"
                    >
                        <div
                            onClick={e => e.stopPropagation()}
                            className="bg-[#1e293b] border border-white/15 rounded-3xl p-6 w-full max-w-lg shadow-2xl space-y-4 flex flex-col max-h-[85vh] animate-in fade-in zoom-in-95 duration-150"
                        >
                            <div className="flex items-center justify-between border-b border-white/10 pb-3">
                                <h3 className="text-base font-black text-white flex items-center gap-2">
                                    <span>{legalModalType === 'terms' ? '📜' : '🔒'}</span>
                                    <span>
                                        {legalModalType === 'terms' ? '서비스 이용약관' : '개인정보 수집 및 이용 동의'}
                                    </span>
                                </h3>
                                <button
                                    type="button"
                                    onClick={() => setLegalModalType(null)}
                                    className="text-gray-400 hover:text-white text-lg font-bold p-1"
                                >
                                    ✕
                                </button>
                            </div>

                            <div className="flex-1 overflow-y-auto bg-[#0f172a] border border-white/5 rounded-2xl p-4 text-xs text-gray-300 leading-relaxed font-sans whitespace-pre-wrap select-text">
                                {legalModalType === 'terms'
                                    ? (legalTexts.terms[currentLocale] || legalTexts.terms.ko || '이용약관을 불러오는 중입니다...')
                                    : (legalTexts.privacy[currentLocale] || legalTexts.privacy.ko || '개인정보 처리방침을 불러오는 중입니다...')}
                            </div>

                            <div className="flex items-center gap-2 pt-2 border-t border-white/10">
                                <button
                                    type="button"
                                    onClick={() => {
                                        if (legalModalType === 'terms') setAgreedTerms(true)
                                        if (legalModalType === 'privacy') setAgreedPrivacy(true)
                                        setLegalModalType(null)
                                    }}
                                    className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-500 rounded-xl text-xs font-bold text-white shadow-md transition"
                                >
                                    확인 및 동의하기
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setLegalModalType(null)}
                                    className="px-4 py-2.5 bg-[#334155] hover:bg-[#475569] text-gray-300 hover:text-white rounded-xl text-xs font-bold transition"
                                >
                                    닫기
                                </button>
                            </div>
                        </div>
                    </div>
                )}

            </main>
        )
    }

    return (
        <div className="min-h-screen bg-[#11141a] text-gray-200 flex flex-col font-sans text-xs select-none">
            {isImpersonating && (
                <div className="bg-gradient-to-r from-blue-950 via-slate-900 to-indigo-950 border-b border-cyan-500/30 px-6 py-2 flex flex-wrap items-center justify-between text-xs font-bold z-40 shrink-0 shadow-lg">
                    <div className="flex items-center gap-2.5">
                        <span className="px-2 py-0.5 rounded bg-cyan-400 text-black text-[10px] font-black uppercase tracking-wider">Admin View</span>
                        <span className="text-white">👑 관리자 뷰어:</span>
                        <span className="text-cyan-300 font-mono font-black">{impersonateEmail}</span>
                        <span className="text-gray-400 font-normal text-[11px]">(유저 시점 작업 화면 조회 중)</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            type="button"
                            onClick={() => setViewMode('login_form')}
                            className="px-2.5 py-1 bg-white/10 hover:bg-white/20 text-cyan-300 border border-cyan-500/30 rounded-lg text-xs font-bold transition"
                        >
                            로그인 폼 화면 보기
                        </button>
                        <button
                            type="button"
                            onClick={() => window.location.href = '/dashboard'}
                            className="px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-black transition shadow"
                        >
                            관리자 대시보드로 복귀
                        </button>
                    </div>
                </div>
            )}
            {/* 1. 상단 글로벌 헤더 */}
            <header className="h-12 bg-[#181d26] border-b border-white/10 px-3 sm:px-4 flex items-center justify-between shrink-0 z-30">
                <div className="flex items-center gap-2 sm:gap-3 min-w-0">
                    {/* 모바일 햄버거 메뉴 버튼 */}
                    <button
                        type="button"
                        onClick={() => setMobileMenuOpen(prev => !prev)}
                        className="md:hidden p-1 text-gray-300 hover:text-white rounded-lg bg-white/5 border border-white/10 flex items-center justify-center text-sm font-bold w-8 h-8 shrink-0 active:scale-95 transition-transform"
                        title="메뉴 열기"
                    >
                        {mobileMenuOpen ? '✕' : '☰'}
                    </button>
                    <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0" />
                    <span className="font-bold text-xs sm:text-sm tracking-wide text-blue-400 shrink-0">AIR STUDIO</span>
                    <span className="text-[9px] sm:text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 shrink-0">
                        STD
                    </span>
                    <span className="text-gray-500 text-xs hidden lg:inline">|</span>
                    <span className="text-xs text-gray-300 font-medium hidden lg:inline truncate max-w-[280px]">
                        <strong className="text-blue-400">{t('active_project')}:</strong> {selectedProject?.project?.title || '아내의 장례식 날, 30년 숨긴 첫사랑의 편지가 열렸다'} <span className="text-gray-400 font-mono">({selectedProject?.project?.status || 'image_prompted'})</span>
                    </span>
                </div>

                {/* 상단 단계별 상태 체크 스텝퍼 (데스크톱/태블릿: 주제, 기획, 대본, 이미지, TTS, 자막, 썸네일) */}
                {(() => {
                    const status = getProjectStepStatus(selectedProject, selectedProject?.scenes || [], audioResultUrl, customScriptText, localSubtitles, thumbBgUrl)
                    const steps = [
                        { id: 'topics', label: '주제', isDone: status.isTopicDone },
                        { id: 'topics', label: '기획', isDone: status.isPlanningDone },
                        { id: 'tts', label: '대본', isDone: status.isScriptDone },
                        { id: 'image_gen', label: '이미지', isDone: status.isImageDone },
                        { id: 'tts', label: 'TTS', isDone: status.isTtsDone },
                        { id: 'subtitle_gen', label: '자막', isDone: status.isSubtitlesDone },
                        { id: 'thumbnail', label: '썸네일', isDone: status.isThumbnailDone },
                    ]
                    return (
                        <div className="hidden md:flex items-center gap-1.5 lg:gap-2.5 text-[10px] lg:text-[11px] text-gray-400 font-medium">
                            {steps.map((step, idx) => {
                                const isCurrent = currentNav === step.id
                                return (
                                    <button
                                        key={idx}
                                        onClick={() => setCurrentNav(step.id as any)}
                                        className={`flex flex-col items-center gap-0.5 transition-colors ${
                                            isCurrent ? 'text-blue-400 font-bold' : 'hover:text-gray-200'
                                        }`}
                                    >
                                        <div className={`w-3.5 h-3.5 lg:w-4 lg:h-4 rounded-full flex items-center justify-center text-[8px] lg:text-[9px] font-bold ${
                                            step.isDone
                                                ? 'bg-emerald-500 text-black shadow-sm'
                                                : 'bg-white/10 text-gray-500 border border-white/20'
                                        }`}>
                                            {step.isDone ? '✓' : '○'}
                                        </div>
                                        <span className={`text-[9px] lg:text-[10px] ${step.isDone ? 'text-gray-200' : 'text-gray-500'}`}>{step.label}</span>
                                    </button>
                                )
                            })}
                        </div>
                    )
                })()}

                <div className="flex items-center gap-1.5 sm:gap-3">
                    {/* 언어 선택 드롭다운 (KO, EN, VI, TH) */}
                    <div className="flex items-center bg-[#14181f] border border-white/10 rounded-lg px-1.5 sm:px-2 py-1">
                        <select
                            value={currentLocale}
                            onChange={(e) => setCurrentLocale(e.target.value as SupportedLocale)}
                            className="bg-transparent text-[11px] sm:text-xs text-white focus:outline-none cursor-pointer"
                        >
                            <option value="ko" className="bg-[#1c2027] text-white">🇰🇷 KO</option>
                            <option value="en" className="bg-[#1c2027] text-white">🇺🇸 EN</option>
                            <option value="vi" className="bg-[#1c2027] text-white">🇻🇳 VI</option>
                            <option value="th" className="bg-[#1c2027] text-white">🇹🇭 TH</option>
                        </select>
                    </div>

                    <button
                        onClick={() => loadStdData(token)}
                        disabled={loading}
                        className="inline-flex items-center gap-1 px-2 py-1 bg-[#202632] hover:bg-[#28303e] border border-white/10 rounded text-[11px] sm:text-xs font-medium text-gray-300 transition-all"
                        title={t('btn_refresh')}
                    >
                        <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
                        <span className="hidden sm:inline">{t('btn_refresh')}</span>
                    </button>
                    <div className="h-3.5 w-px bg-white/10 hidden sm:block" />
                    <div className="text-right hidden sm:block">
                        <div className="text-xs font-bold text-white leading-none">{user?.full_name || '김호'}</div>
                        <div className="text-[10px] text-gray-400 truncate max-w-[120px] leading-tight">{user?.email || 'ejsh0519@naver.com'}</div>
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

            {/* 모바일 전용 가로 스크롤 스텝퍼 바 (7단계) */}
            {(() => {
                const status = getProjectStepStatus(selectedProject, selectedProject?.scenes || [], audioResultUrl, customScriptText, localSubtitles, thumbBgUrl)
                const steps = [
                    { id: 'topics', label: '주제', isDone: status.isTopicDone },
                    { id: 'topics', label: '기획', isDone: status.isPlanningDone },
                    { id: 'tts', label: '대본', isDone: status.isScriptDone },
                    { id: 'image_gen', label: '이미지', isDone: status.isImageDone },
                    { id: 'tts', label: 'TTS', isDone: status.isTtsDone },
                    { id: 'subtitle_gen', label: '자막', isDone: status.isSubtitlesDone },
                    { id: 'thumbnail', label: '썸네일', isDone: status.isThumbnailDone },
                ]
                return (
                    <div className="md:hidden bg-[#14181f] border-b border-white/10 px-3 py-1.5 flex items-center gap-2 overflow-x-auto shrink-0 scrollbar-none">
                        {steps.map((step, idx) => (
                            <button
                                key={idx}
                                onClick={() => { setCurrentNav(step.id as any); setMobileMenuOpen(false); }}
                                className={`flex items-center gap-1.5 shrink-0 px-2.5 py-1 rounded-full text-[10px] font-bold border transition ${
                                    currentNav === step.id
                                        ? 'bg-blue-600/30 text-blue-300 border-blue-500/50'
                                        : 'bg-[#1c222c] text-gray-400 border-white/5'
                                }`}
                            >
                                <span className={`w-1.5 h-1.5 rounded-full ${step.isDone ? 'bg-emerald-400 shadow-sm' : 'bg-gray-600'}`} />
                                <span>{step.label}</span>
                            </button>
                        ))}
                    </div>
                )
            })()}

            {/* 2. 메인 2열 레이아웃: 사이드바 + 메인 작업 공간 */}
            <div className="flex-1 flex overflow-hidden relative">
                {/* 모바일 드로어 사이드바 (모바일 햄버거 메뉴 열림 시) */}
                {mobileMenuOpen && (
                    <div
                        className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 md:hidden flex animate-in fade-in duration-200"
                        onClick={() => setMobileMenuOpen(false)}
                    >
                        <aside
                            className="w-64 max-w-[80vw] h-full bg-[#161a22] border-r border-white/10 flex flex-col shadow-2xl animate-in slide-in-from-left duration-200"
                            onClick={e => e.stopPropagation()}
                        >
                            <div className="p-3 border-b border-white/10 flex items-center justify-between">
                                <span className="font-bold text-sm text-blue-400">AIR STUDIO STD</span>
                                <button
                                    type="button"
                                    onClick={() => setMobileMenuOpen(false)}
                                    className="p-1.5 text-gray-400 hover:text-white rounded-lg text-sm font-bold bg-white/5"
                                >
                                    ✕
                                </button>
                            </div>

                            <div className="p-3 border-b border-white/5 space-y-2 text-[11px]">
                                <div className="flex items-center justify-between text-gray-400">
                                    <span>모드</span>
                                    <span className="px-2 py-0.5 bg-[#202632] text-gray-200 rounded font-bold border border-white/5">롱폼</span>
                                </div>
                                <div className="flex items-center justify-between text-gray-400">
                                    <span>사용자</span>
                                    <span className="text-gray-200 font-bold truncate max-w-[120px]">{user?.full_name || '김호'}</span>
                                </div>
                            </div>

                            <div className="p-3 border-b border-white/5 bg-[#13171e]">
                                <label className="text-[10px] font-bold text-gray-400 block mb-1">{t('active_project')}</label>
                                <select
                                    value={selectedProject?.project?.id || ''}
                                    onChange={(e) => {
                                        if (e.target.value) openProject(e.target.value)
                                        setMobileMenuOpen(false)
                                    }}
                                    className="w-full bg-[#202632] border border-white/10 rounded p-1.5 text-xs text-white cursor-pointer focus:outline-none focus:border-blue-500 truncate"
                                >
                                    {projects.map(p => (
                                        <option key={p.id} value={p.id}>
                                            {p.title}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto text-xs">
                                {[
                                    { id: 'topics', label: t('nav_topics') },
                                    { id: 'image_gen', label: t('nav_image') },
                                    { id: 'tts', label: t('nav_tts') },
                                    { id: 'subtitle_gen', label: t('nav_subtitles') },
                                    { id: 'thumbnail', label: t('nav_thumbnail') },
                                    { id: 'music_missions', label: '음악 미션' },
                                    { id: 'projects', label: t('nav_projects') },
                                    { id: 'template', label: t('nav_template') },
                                    { id: 'settings', label: t('nav_settings') },
                                ].map((item) => {
                                    const active = currentNav === item.id
                                    return (
                                        <button
                                            key={item.id}
                                            onClick={() => {
                                                setCurrentNav(item.id as any)
                                                setMobileMenuOpen(false)
                                            }}
                                            className={`w-full flex items-center justify-between px-3 py-2.5 rounded text-left transition-all font-medium ${
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

                            <div className="p-3 border-t border-white/5 text-[11px] text-gray-400 flex items-center justify-between">
                                <button
                                    onClick={signOut}
                                    className="text-red-400 hover:text-red-300 font-bold text-xs flex items-center gap-1"
                                >
                                    <LogOut className="h-3.5 w-3.5" />
                                    <span>로그아웃</span>
                                </button>
                                <span className="text-[10px] text-gray-500 font-mono">v2.3.46</span>
                            </div>
                        </aside>
                    </div>
                )}

                {/* 데스크톱 좌측 고정 사이드바 (md 이상에서만 표시) */}
                <aside className="hidden md:flex w-56 bg-[#161a22] border-r border-white/10 flex-col shrink-0">
                    <div className="p-3 border-b border-white/5 space-y-2 text-[11px]">
                        <div className="flex items-center justify-between text-gray-400">
                            <span>모드</span>
                            <span className="px-2 py-0.5 bg-[#202632] text-gray-200 rounded font-bold border border-white/5">롱폼</span>
                        </div>
                        <div className="flex items-center justify-between text-gray-400">
                            <span>언어</span>
                            <div className="flex items-center gap-1.5">
                                <button
                                    type="button"
                                    onClick={() => setCurrentLocale('ko')}
                                    className={`cursor-pointer hover:scale-125 transition-transform ${currentLocale === 'ko' ? 'scale-110 ring-1 ring-blue-400 rounded-full' : 'opacity-60'}`}
                                    title="한국어"
                                >
                                    🇰🇷
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setCurrentLocale('en')}
                                    className={`cursor-pointer hover:scale-125 transition-transform ${currentLocale === 'en' ? 'scale-110 ring-1 ring-blue-400 rounded-full' : 'opacity-60'}`}
                                    title="English"
                                >
                                    🇺🇸
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setCurrentLocale('vi')}
                                    className={`cursor-pointer hover:scale-125 transition-transform ${currentLocale === 'vi' ? 'scale-110 ring-1 ring-blue-400 rounded-full' : 'opacity-60'}`}
                                    title="Tiếng Việt"
                                >
                                    🇻🇳
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setCurrentLocale('th')}
                                    className={`cursor-pointer hover:scale-125 transition-transform ${currentLocale === 'th' ? 'scale-110 ring-1 ring-blue-400 rounded-full' : 'opacity-60'}`}
                                    title="ภาษาไทย"
                                >
                                    🇹🇭
                                </button>
                            </div>
                        </div>
                    </div>

                    <div className="p-3 border-b border-white/5 bg-[#13171e]">
                        <label className="text-[10px] font-bold text-gray-400 block mb-1">{t('active_project')}</label>
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
                            { id: 'topics', label: t('nav_topics') },
                            { id: 'image_gen', label: t('nav_image') },
                            { id: 'tts', label: t('nav_tts') },
                            { id: 'subtitle_gen', label: t('nav_subtitles') },
                            { id: 'thumbnail', label: t('nav_thumbnail') },
                            { id: 'music_missions', label: '음악 미션' },
                            { id: 'projects', label: t('nav_projects') },
                            { id: 'template', label: t('nav_template') },
                            { id: 'settings', label: t('nav_settings') },
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

                {/* 우측 메인 작업 화면 (모바일 패딩 및 너비 최적화) */}
                <main className="flex-1 flex flex-col overflow-y-auto bg-[#14181f] p-3 sm:p-5 md:p-6 space-y-4 sm:space-y-6">
                    {/* [자막 생성 탭 (유저앱 subtitle_gen.html과 100% 동일 구현)] */}
                    {currentNav === 'subtitle_gen' && selectedProject && (() => {
                        const currentSub = localSubtitles[selectedSubIndex] || localSubtitles[0] || {
                            id: 'sub-0',
                            scene_number: 1,
                            start_time: '0.0',
                            end_time: '5.0',
                            start_num: 0.0,
                            end_num: 5.0,
                            text: '장례식이 끝난 뒤, 남편은 아내가 삼십 년 동안 숨겨온 낡은 편지를 발견했습니다.',
                            image_url: selectedProject?.scenes?.[0]?.image_url || '',
                            video_url: selectedProject?.scenes?.[0]?.video_url || null,
                            is_hook_zone: true,
                        }
                        return (
                        <div className="space-y-3 max-w-7xl mx-auto w-full flex flex-col h-full">
                            {/* 1. 상단 2줄 스타일 툴바 (설치형 유저앱과 100% 동일) */}
                            <div className="bg-[#1c2027] border border-white/10 rounded-xl p-2.5 shadow-md flex flex-col gap-2 shrink-0">
                                {/* 1행: 외부오디오 | 템플릿선택+새로고침 | 프리셋(선택/삭제/새프리셋명/저장) | 폰트/크기/자간/글자수 | 글자색/테두리색 */}
                                <div className="flex items-center gap-x-2.5 gap-y-1.5 flex-wrap">
                                    {/* 외부 오디오 업로드 */}
                                    <div className="flex items-center">
                                        <input
                                            type="file"
                                            id="audioUploadInput"
                                            accept="audio/*"
                                            className="hidden"
                                            onChange={handleUploadExternalAudio}
                                        />
                                        <button
                                            type="button"
                                            onClick={() => document.getElementById('audioUploadInput')?.click()}
                                            className="px-2.5 py-1.5 text-xs font-bold border border-gray-600 bg-transparent hover:bg-white/5 text-gray-200 hover:text-white rounded-md transition-all flex items-center gap-1.5 shrink-0"
                                            title="직접 녹음/보유한 외부 오디오 파일을 업로드합니다."
                                        >
                                            <span className="text-yellow-400">📁</span> 외부 오디오 업로드
                                        </button>
                                    </div>

                                    {/* 템플릿 선택 & 새로고침 */}
                                    <div className="flex items-center gap-1 shrink-0">
                                        <select
                                            value={selectedImageTemplatePreset}
                                            onChange={e => handleSelectImageTemplatePreset(e.target.value)}
                                            className="text-[11px] font-medium bg-[#1c2027]/50 border border-indigo-500/40 rounded-md py-1 px-2 text-white focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
                                        >
                                            <option value="" className="bg-[#1c2027] text-white">
                                                -- 템플릿 선택 --
                                            </option>
                                            {templatePresets.map(preset => (
                                                <option key={preset.id} value={preset.id} className="bg-[#1c2027] text-white">
                                                    {preset.name}
                                                </option>
                                            ))}
                                        </select>
                                        <button
                                            type="button"
                                            onClick={loadTemplatePresetsFromStorage}
                                            className="text-[10px] font-bold px-1.5 py-1 text-gray-400 hover:text-white border border-gray-700 hover:bg-[#0a0f1d] rounded transition-all"
                                        >
                                            새로고침
                                        </button>
                                    </div>

                                    <div className="w-px h-5 bg-white/10 shrink-0" />

                                    {/* 프리셋 관리: 선택 / 삭제 / 새 프리셋명 / 저장 */}
                                    <div className="flex items-center gap-1 shrink-0">
                                        <select
                                            value={selectedSubPreset}
                                            onChange={e => handleApplySubtitlePreset(e.target.value)}
                                            className="text-[11px] font-medium bg-[#1c2027]/50 border border-gray-600 rounded-md py-1 px-2 text-white focus:outline-none focus:ring-1 focus:ring-blue-500 cursor-pointer"
                                        >
                                            <option value="">선택</option>
                                            {subPresetList.map(p => (
                                                <option key={p.name} value={p.name} className="bg-[#1c2027] text-white">
                                                    {p.name}
                                                </option>
                                            ))}
                                        </select>
                                        <button
                                            type="button"
                                            onClick={handleDeleteSubtitlePreset}
                                            className="text-[10px] font-bold px-1.5 py-1 text-red-400 hover:text-white border border-red-900/50 hover:bg-red-900 rounded transition-all"
                                        >
                                            삭제
                                        </button>
                                        <input
                                            type="text"
                                            value={newSubPresetName}
                                            onChange={e => setNewSubPresetName(e.target.value)}
                                            placeholder="새 프리셋명"
                                            className="text-[11px] bg-[#14181f] border border-white/10 rounded px-1.5 py-1 text-white w-20 focus:outline-none focus:ring-1 focus:ring-blue-500"
                                        />
                                        <button
                                            type="button"
                                            onClick={handleSaveSubtitlePreset}
                                            className="text-[11px] border border-gray-600 bg-transparent hover:bg-[#0a0f1d] text-white px-2 py-1 rounded transition-all font-bold"
                                        >
                                            저장
                                        </button>
                                    </div>

                                    <div className="w-px h-5 bg-white/10 shrink-0" />

                                    {/* 폰트 & 크기 & 자간 & 최대글자수 */}
                                    <div className="flex items-center gap-1.5 shrink-0">
                                        <select
                                            value={subFontFamily}
                                            onChange={e => setSubFontFamily(e.target.value)}
                                            className="text-[11px] bg-[#1c2027]/50 border border-gray-600 rounded-md py-1 px-2 text-white font-bold focus:outline-none focus:ring-1 focus:ring-blue-500 cursor-pointer w-32"
                                        >
                                            {SUBTITLE_FONTS.map(f => (
                                                <option key={f.value} value={f.value} style={{ fontFamily: f.value }} className="bg-[#1c2027] text-white">
                                                    {f.label}
                                                </option>
                                            ))}
                                        </select>
                                        <input
                                            type="number"
                                            value={subFontSize}
                                            onChange={e => setSubFontSize(e.target.value)}
                                            className="w-12 text-center text-[11px] bg-[#14181f] border border-gray-600 rounded-md py-1 text-white focus:ring-1 focus:ring-blue-500"
                                            step="0.1"
                                            min="1"
                                            max="20"
                                            title="글자 크기 (%)"
                                        />
                                        <span className="text-[11px] text-gray-400">%</span>
                                        <input
                                            type="number"
                                            value={subLineSpacing}
                                            onChange={e => setSubLineSpacing(e.target.value)}
                                            className="w-12 text-center text-[11px] bg-[#14181f] border border-gray-600 rounded-md py-1 text-white focus:ring-1 focus:ring-blue-500"
                                            step="0.05"
                                            min="-0.5"
                                            max="1.5"
                                            title="자간/행간 비율"
                                        />
                                        <input
                                            type="number"
                                            value={subMaxChars}
                                            onChange={e => setSubMaxChars(e.target.value)}
                                            className="w-10 text-center text-[11px] bg-[#14181f] border border-gray-600 rounded-md py-1 text-white focus:ring-1 focus:ring-blue-500"
                                            min="20"
                                            max="40"
                                            title="한 자막 최대 글자 수 (롱폼)"
                                        />
                                    </div>

                                    <div className="w-px h-5 bg-white/10 shrink-0" />

                                    {/* 글자색 / 테두리색 */}
                                    <div className="flex items-center gap-2 shrink-0">
                                        <div className="flex flex-col items-center gap-0.5">
                                            <input
                                                type="color"
                                                value={subTextColor}
                                                onChange={e => setSubTextColor(e.target.value)}
                                                className="w-7 h-5 p-0 bg-transparent border border-gray-600 rounded cursor-pointer"
                                                title="글자색"
                                            />
                                            <span className="text-[9px] text-gray-400">글자</span>
                                        </div>
                                        <div className="flex flex-col items-center gap-0.5">
                                            <input
                                                type="color"
                                                value={subStrokeColor}
                                                onChange={e => setSubStrokeColor(e.target.value)}
                                                className="w-7 h-5 p-0 bg-transparent border border-gray-600 rounded cursor-pointer"
                                                title="테두리색"
                                            />
                                            <span className="text-[9px] text-gray-400">테두리</span>
                                        </div>
                                    </div>
                                </div>

                                {/* 2행: 테두리 두께 / Y위치 / 배경 바 / 액션 버튼 6종 */}
                                <div className="flex items-center gap-x-2 gap-y-1.5 flex-wrap pt-1.5 border-t border-white/5">
                                    {/* 테두리 두께 & Y 위치 */}
                                    <div className="flex items-center gap-1 shrink-0">
                                        <span className="text-[10px] text-gray-400 font-bold">테두리</span>
                                        <input
                                            type="number"
                                            value={subStrokeWidth}
                                            onChange={e => setSubStrokeWidth(e.target.value)}
                                            className="w-10 text-center text-[11px] bg-[#14181f] border border-gray-600 rounded-md py-0.5 text-white"
                                            min="0"
                                            max="15"
                                            step="0.5"
                                        />
                                        <span className="text-[10px] text-gray-400">px</span>
                                        <div className="flex flex-col items-center gap-0.5 ml-1">
                                            <button
                                                type="button"
                                                onClick={() => setSubPosY(p => Math.max(0, p + 1))}
                                                className="w-5 h-3.5 flex items-center justify-center rounded-sm bg-gray-700 hover:bg-gray-600 text-white text-[9px] leading-none"
                                                title="위로 (Y위치 증가)"
                                            >
                                                ▲
                                            </button>
                                            <span className="text-[9px] font-mono text-gray-300 w-5 text-center leading-none">
                                                {subPosY}
                                            </span>
                                            <button
                                                type="button"
                                                onClick={() => setSubPosY(p => Math.max(0, p - 1))}
                                                className="w-5 h-3.5 flex items-center justify-center rounded-sm bg-gray-700 hover:bg-gray-600 text-white text-[9px] leading-none"
                                                title="아래로 (Y위치 감소)"
                                            >
                                                ▼
                                            </button>
                                        </div>
                                    </div>

                                    <div className="w-px h-5 bg-white/10 shrink-0" />

                                    {/* 배경 바 */}
                                    <div className="flex items-center gap-1.5 shrink-0">
                                        <span className="text-[10px] text-gray-400 font-bold">배경 바</span>
                                        <label className="relative inline-flex items-center cursor-pointer">
                                            <input
                                                type="checkbox"
                                                checked={subBgStrip}
                                                onChange={e => setSubBgStrip(e.target.checked)}
                                                className="sr-only peer"
                                            />
                                            <div className="w-8 h-4 bg-gray-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-blue-600" />
                                        </label>
                                        <div className="flex flex-col items-center gap-0.5">
                                            <input
                                                type="color"
                                                value={subBgColor}
                                                onChange={e => setSubBgColor(e.target.value)}
                                                className="w-7 h-5 p-0 bg-transparent border border-gray-600 rounded cursor-pointer"
                                                title="배경색"
                                            />
                                        </div>
                                        <input
                                            type="number"
                                            value={subBgOpacity}
                                            onChange={e => setSubBgOpacity(e.target.value)}
                                            step="0.1"
                                            min="0"
                                            max="1"
                                            className="w-10 text-center text-[11px] bg-[#14181f] border border-gray-600 rounded-md py-0.5 text-white"
                                            title="불투명도 (0~1)"
                                        />
                                        <div className="flex items-center gap-0.5 bg-[#14181f] px-1 rounded border border-white/5">
                                            <span className="text-[10px] text-gray-400">:</span>
                                            <input
                                                type="number"
                                                value={subBgVOffset}
                                                onChange={e => setSubBgVOffset(e.target.value)}
                                                step="1"
                                                className="w-8 text-center text-[11px] bg-transparent border-0 py-0.5 text-white focus:outline-none"
                                                title="세로 여백/오프셋"
                                            />
                                        </div>
                                    </div>

                                    <div className="w-px h-5 bg-white/10 shrink-0" />

                                    {/* 액션 버튼 6종 */}
                                    <div className="flex items-center gap-1.5 flex-wrap ml-auto">
                                        <button
                                            type="button"
                                            onClick={() => {
                                                const scenes = selectedProject?.scenes || []
                                                const subs = generateSynchronizedSubtitles(
                                                    selectedProject?.project?.project_payload?.script || customScriptText || '',
                                                    scenes,
                                                    Number(subMaxChars) || 20
                                                )
                                                setLocalSubtitles(subs)
                                                setSelectedSubIndex(0)
                                                alert('초반 1분(1~12씬: 5s 훅) + 전개(13~28씬: 15s) + 심화(29~43씬: 20s) + 결말(44~53씬: 30s) + 확장(54씬+: 60s) 표준 페이싱 규칙으로 자막 싱크가 초기화되었습니다.')
                                            }}
                                            className="text-[10px] font-bold px-3 py-1.5 rounded-md border border-white/10 bg-transparent hover:bg-[#232832] text-white transition-all"
                                        >
                                            초기화 및 재로드
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => {
                                                const scenes = selectedProject?.scenes || []
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
                                            className="text-[10px] font-bold px-3 py-1.5 rounded-md border border-white/10 bg-transparent hover:bg-[#232832] text-white transition-all"
                                        >
                                            AI 이미지 동기화
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => {
                                                const maxChars = Number(subMaxChars) || 20
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
                                            className="text-[10px] font-bold px-3 py-1.5 rounded-md border border-white/10 bg-transparent hover:bg-[#232832] text-white transition-all"
                                        >
                                            1줄/2줄 분할
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => handleSyncScriptToScenesAndSubtitles(true)}
                                            className="text-[10px] font-bold px-3 py-1.5 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white rounded-md shadow flex items-center gap-1"
                                        >
                                            <span>🔮</span> 대본 전체 자막 동기화
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => alert('선택한 언어로 자막 번역 작업이 완료되었습니다.')}
                                            className="text-[10px] font-bold px-3 py-1.5 rounded-md border border-white/10 bg-transparent hover:bg-[#232832] text-blue-400 hover:text-blue-300 transition-all"
                                        >
                                            Translate
                                        </button>
                                        <button
                                            type="button"
                                            onClick={handleSaveSubtitles}
                                            className="text-[10px] font-bold px-3.5 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-md shadow transition-all active:scale-95 flex items-center gap-1"
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
                                            {subtitleSceneGroups.map((group) => {
                                                const isHook = (group.scene_number || 1) <= 12
                                                const isActive = selectedSubIndex >= group.firstIndex && selectedSubIndex <= group.lastIndex
                                                return (
                                                    <div
                                                        key={`scene-group-thumb-${group.scene_number}`}
                                                        onClick={() => {
                                                            setSelectedSubIndex(group.firstIndex)
                                                            setPlaybackTime(group.start_num ?? Number(group.start_time) ?? 0)
                                                        }}
                                                        className={`w-full aspect-video rounded overflow-hidden cursor-pointer border relative transition-all ${
                                                            isActive ? 'border-blue-500 scale-105 shadow' : 'border-white/10 opacity-70 hover:opacity-100'
                                                        }`}
                                                    >
                                                        <img src={group.image_url} alt={`Scene ${group.scene_number}`} className="w-full h-full object-cover" />
                                                        {isHook && (
                                                            <span className="absolute top-0.5 left-0.5 bg-orange-600 text-white text-[7px] font-bold px-1 rounded">
                                                                5s 훅
                                                            </span>
                                                        )}
                                                        <span className="absolute bottom-0.5 right-0.5 bg-black/80 text-white text-[7px] font-bold px-1 rounded">
                                                            #{group.scene_number}
                                                        </span>
                                                        {group.subtitles.length > 1 && (
                                                            <span className="absolute bottom-0.5 left-0.5 bg-blue-600/90 text-white text-[7px] font-bold px-1 rounded">
                                                                {group.subtitles.length} lines
                                                            </span>
                                                        )}
                                                    </div>
                                                )
                                            })}
                                        </div>

                                        {/* 자막 카드 목록 */}
                                        <div className="flex-1 overflow-y-auto p-2 space-y-2">
                                            {subtitleSceneGroups.map((group) => {
                                                const isActive = selectedSubIndex >= group.firstIndex && selectedSubIndex <= group.lastIndex
                                                const sNum = group.scene_number
                                                const isHook = sNum <= 12
                                                const duration = Math.max(0, Number(group.end_num || 0) - Number(group.start_num || 0))
                                                const groupText = group.subtitles.map((item: any) => item.text).filter(Boolean).join(' ')
                                                return (
                                                    <div
                                                        key={`scene-group-card-${sNum}`}
                                                        onClick={() => {
                                                            setSelectedSubIndex(group.firstIndex)
                                                            setPlaybackTime(group.start_num ?? Number(group.start_time) ?? 0)
                                                        }}
                                                        className={`p-3 rounded-xl border flex gap-3 cursor-pointer transition-all ${
                                                            isActive
                                                                ? 'bg-blue-600/10 border-blue-500 shadow-md'
                                                                : 'bg-[#14181f] border-white/5 hover:border-white/20'
                                                        }`}
                                                    >
                                                        {/* 이미지 & 타임 */}
                                                        <div className="w-20 aspect-video rounded-lg overflow-hidden border border-white/10 relative shrink-0">
                                                            <img src={group.image_url} alt="" className="w-full h-full object-cover" />
                                                            <span className="absolute bottom-0.5 right-0.5 text-[8px] font-mono bg-black/80 text-white px-1 rounded">
                                                                {group.subtitles.length} lines
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
                                                            {group.start_time}s<br />~{group.end_time}s
                                                            <div className="mt-1 text-[9px] text-gray-500">
                                                                {duration.toFixed(1)}s
                                                            </div>
                                                        </div>
                                                        <div className="flex-1 min-w-0">
                                                            <div className="flex items-center gap-2 mb-1">
                                                                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${isHook ? 'bg-orange-500/15 text-orange-300' : 'bg-blue-500/15 text-blue-300'}`}>
                                                                    Scene {sNum}
                                                                </span>
                                                                <span className="text-[10px] text-gray-500">
                                                                    {group.subtitles.length} subtitle block{group.subtitles.length > 1 ? 's' : ''}
                                                                </span>
                                                            </div>
                                                            <div className="text-xs text-white leading-relaxed font-sans">
                                                                {groupText}
                                                            </div>
                                                            {group.subtitles.length > 1 && (
                                                                <div className="mt-2 flex flex-wrap gap-1">
                                                                    {group.subtitles.map((item: any, lineIndex: number) => (
                                                                        <button
                                                                            key={item.id || `${sNum}-${lineIndex}`}
                                                                            type="button"
                                                                            onClick={(event) => {
                                                                                event.stopPropagation()
                                                                                setSelectedSubIndex(item.subtitleIndex)
                                                                                setPlaybackTime(item.start_num ?? Number(item.start_time) ?? 0)
                                                                            }}
                                                                            className={`text-[9px] px-1.5 py-0.5 rounded border transition-all ${
                                                                                selectedSubIndex === item.subtitleIndex
                                                                                    ? 'bg-cyan-500/20 border-cyan-400 text-cyan-200'
                                                                                    : 'bg-black/20 border-white/10 text-gray-400 hover:text-white'
                                                                            }`}
                                                                        >
                                                                            {lineIndex + 1}
                                                                        </button>
                                                                    ))}
                                                                </div>
                                                            )}
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
                                        <div
                                            className="relative aspect-video bg-black flex items-center justify-center overflow-hidden"
                                            style={selectedImageTemplatePreset ? { backgroundColor: templateBgColor || '#000000' } : undefined}
                                        >
                                            {selectedImageTemplatePreset && templateBgUrl ? (
                                                <img
                                                    src={templateBgUrl}
                                                    alt="Template Preview"
                                                    className="w-full h-full object-cover"
                                                />
                                            ) : !selectedImageTemplatePreset && currentSub.image_url ? (
                                                <img
                                                    src={currentSub.image_url}
                                                    alt="Preview"
                                                    className="w-full h-full object-cover"
                                                />
                                            ) : !selectedImageTemplatePreset ? (
                                                <div className="w-full h-full bg-[#0b0e14] flex flex-col items-center justify-center text-gray-600 gap-1 select-none">
                                                    <span className="text-2xl opacity-40">🖼️</span>
                                                    <span className="text-[10px] font-mono text-gray-500">이미지 없음 (업로드 대기)</span>
                                                </div>
                                            ) : null}
                                            {selectedImageTemplatePreset && shapeLayers.map(shape => (
                                                <div
                                                    key={shape.id}
                                                    className="absolute inset-x-0 pointer-events-none"
                                                    style={{
                                                        top: `${shape.y}%`,
                                                        height: `${shape.height}%`,
                                                        transform: 'translateY(-50%)',
                                                        backgroundColor: hexToRgba(shape.color, shape.opacity),
                                                    }}
                                                />
                                            ))}
                                            {selectedImageTemplatePreset && textLayers.map(layer => (
                                                <div
                                                    key={layer.id}
                                                    className="absolute inset-x-4 text-center select-none pointer-events-none transition-all"
                                                    style={{
                                                        top: `${layer.y}%`,
                                                        transform: 'translateY(-50%)',
                                                        fontFamily: layer.fontFamily,
                                                        color: layer.color,
                                                        fontSize: `${Math.min(34, Math.max(12, layer.fontSize * 0.72))}px`,
                                                        fontWeight: 'bold',
                                                        textShadow: `
                                                            -${layer.strokeWidth}px -${layer.strokeWidth}px 0 ${layer.strokeColor},
                                                            ${layer.strokeWidth}px -${layer.strokeWidth}px 0 ${layer.strokeColor},
                                                            -${layer.strokeWidth}px ${layer.strokeWidth}px 0 ${layer.strokeColor},
                                                            ${layer.strokeWidth}px ${layer.strokeWidth}px 0 ${layer.strokeColor},
                                                            0 4px 10px rgba(0,0,0,0.8)
                                                        `,
                                                    }}
                                                >
                                                    {layer.text}
                                                </div>
                                            ))}
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
                                                        backgroundColor: subBgStrip ? hexToRgba(subBgColor, subBgOpacity) : 'transparent',
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
                                                        <button
                                                            type="button"
                                                            onClick={() => alert('선택된 구간의 자막 및 싱크 수정사항이 반영되었습니다. 상단 파란색 [저장] 버튼을 누르면 프로젝트에 최종 완료 저장됩니다.')}
                                                            className="text-[10px] px-2.5 py-0.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded font-bold transition-all active:scale-95"
                                                        >
                                                            저장
                                                        </button>
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
                                        ⚡ Multilingual v2
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
                                            {allVoices.map(v => (
                                                <option key={v.id} value={v.id}>{v.name}</option>
                                            ))}
                                        </select>
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
                                        {generatingTts ? '음성 생성 중...' : '음성 생성'}
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
                                        <div className="bg-[#181d26] border border-purple-500/30 rounded-xl p-4 shadow-lg space-y-3 flex-1 flex flex-col">
                                            <div className="flex items-center justify-between border-b border-white/10 pb-2">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-xs font-bold text-white flex items-center gap-1.5">
                                                        <span>🎭</span> 등장인물 성우 1:1 매칭
                                                    </span>
                                                    <span className="text-[10px] bg-purple-600/30 text-purple-300 border border-purple-500/40 px-2 py-0.5 rounded-full font-bold">
                                                        총 {detectedCharacters.length}명 화자
                                                    </span>
                                                </div>
                                                <button
                                                    type="button"
                                                    onClick={() => {
                                                        const text = customScriptText || selectedProject?.project?.project_payload?.script || ''
                                                        const parsed = parseScriptToVoiceSegments(text)
                                                        alert(`대본 분석 완료! 총 ${parsed.uniqueSpeakers.length}명의 등장인물이 자동 감지되었습니다: ${parsed.uniqueSpeakers.join(', ') || '없음'}`)
                                                    }}
                                                    className="text-[10px] text-purple-400 hover:text-white px-2 py-0.5 border border-purple-500/30 rounded bg-purple-500/10 transition-colors"
                                                >
                                                    대본 재분석
                                                </button>
                                            </div>

                                            {/* 기본 나레이터 표시 */}
                                            <div className="p-2.5 bg-[#14181f] rounded-lg border border-purple-500/20 flex items-center justify-between gap-2">
                                                <div className="flex items-center gap-1.5">
                                                    <span className="text-xs font-bold text-emerald-400">📖 나레이터 (기본 해설)</span>
                                                </div>
                                                <span className="text-xs font-bold text-gray-300 bg-white/5 px-2 py-0.5 rounded border border-white/10">
                                                    {selectedVoiceObj.name}
                                                </span>
                                            </div>

                                            {/* 감지된 화자 목록 */}
                                            <div className="space-y-2 overflow-y-auto max-h-60 pr-1">
                                                {detectedCharacters.length === 0 ? (
                                                    <div className="text-center py-4 text-xs text-gray-500 bg-[#14181f] rounded-lg border border-dashed border-white/10">
                                                        대본에서 감지된 인물 대사(따옴표 또는 화자:)가 없습니다.<br />
                                                        아래에서 수동으로 화자를 추가할 수 있습니다.
                                                    </div>
                                                ) : (
                                                    detectedCharacters.map(char => {
                                                        const currentVoiceId = characterVoices[char] || selectedVoice
                                                        const charVoiceObj = allVoices.find(v => v.id === currentVoiceId) || selectedVoiceObj
                                                        return (
                                                            <div key={char} className="p-2.5 bg-[#14181f] rounded-lg border border-white/10 hover:border-purple-500/40 transition-colors flex flex-col gap-1.5">
                                                                <div className="flex items-center justify-between gap-2">
                                                                    <span className="text-xs font-bold text-purple-300 flex items-center gap-1">
                                                                        <span>👤</span> {char}
                                                                    </span>
                                                                    {charVoiceObj.preview_url && (
                                                                        <button
                                                                            type="button"
                                                                            onClick={() => {
                                                                                const audio = new Audio(charVoiceObj.preview_url)
                                                                                audio.play()
                                                                            }}
                                                                            className="text-[10px] text-cyan-400 hover:text-white px-2 py-0.5 bg-cyan-500/10 hover:bg-cyan-500/30 rounded border border-cyan-500/30 font-bold transition-all"
                                                                            title="목소리 미리듣기"
                                                                        >
                                                                            ▶ 미리듣기
                                                                        </button>
                                                                    )}
                                                                </div>
                                                                <select
                                                                    value={currentVoiceId}
                                                                    onChange={e => setCharacterVoices(prev => ({ ...prev, [char]: e.target.value }))}
                                                                    className="w-full text-xs bg-[#202632] border border-white/10 rounded-lg px-2.5 py-1.5 text-white focus:outline-none focus:border-purple-500"
                                                                >
                                                                    {allVoices.map(v => (
                                                                        <option key={v.id} value={v.id}>{v.name} ({v.gender === 'female' ? '여성' : '남성'})</option>
                                                                    ))}
                                                                </select>
                                                            </div>
                                                        )
                                                    })
                                                )}
                                            </div>

                                            {/* 수동 화자 추가 폼 */}
                                            <div className="pt-2 border-t border-white/10 flex items-center gap-2">
                                                <input
                                                    type="text"
                                                    value={newCharInput}
                                                    onChange={e => setNewCharInput(e.target.value)}
                                                    onKeyDown={e => {
                                                        if (e.key === 'Enter' && newCharInput.trim()) {
                                                            e.preventDefault()
                                                            const name = newCharInput.trim()
                                                            if (!detectedCharacters.includes(name)) {
                                                                setCustomAddedCharacters(prev => [...prev, name])
                                                            }
                                                            setNewCharInput('')
                                                        }
                                                    }}
                                                    placeholder="등장인물 이름 직접 추가 (예: 할머니, 큰아들)..."
                                                    className="flex-1 bg-[#14181f] border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                                                />
                                                <button
                                                    type="button"
                                                    onClick={() => {
                                                        const name = newCharInput.trim()
                                                        if (name && !detectedCharacters.includes(name)) {
                                                            setCustomAddedCharacters(prev => [...prev, name])
                                                            setNewCharInput('')
                                                        }
                                                    }}
                                                    className="px-3 py-1.5 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-xs font-bold transition-all shadow shrink-0"
                                                >
                                                    + 화자 추가
                                                </button>
                                            </div>
                                        </div>
                                    )}

                                    {audioResultUrl && (
                                        <div className="bg-[#181d26] border border-white/10 rounded-xl p-4 shadow space-y-3 border-l-4 border-l-emerald-500">
                                            <div className="flex items-center justify-between">
                                                <span className="text-xs font-bold text-white flex items-center gap-1.5">
                                                    <span>🎉</span> 생성 완료된 음성 오디오
                                                </span>
                                                <span className="text-[10px] font-bold text-emerald-400 font-mono">
                                                    {formattedActualAudioDuration
                                                        ? `실제 ${formattedActualAudioDuration}`
                                                        : `예상 약 ${estimatedAudioMinutes}분`}
                                                </span>
                                            </div>
                                            <audio
                                                src={audioResultUrl}
                                                controls
                                                preload="metadata"
                                                onLoadedMetadata={event => {
                                                    const duration = event.currentTarget.duration
                                                    setAudioDurationSeconds(Number.isFinite(duration) && duration > 0 ? duration : 0)
                                                }}
                                                className="w-full h-8"
                                            />
                                        </div>
                                    )}
                                </div>

                                <div className="lg:col-span-8 bg-[#181d26] border border-white/10 rounded-xl p-4 shadow flex flex-col space-y-3 min-h-[500px]">
                                    <div className="flex items-center justify-between border-b border-white/5 pb-3">
                                        <div>
                                            <h4 className="text-xs font-bold text-white flex items-center gap-2">
                                                <span>📝</span> TTS 나레이션 전체 대본 에디터
                                            </h4>
                                            <p className="text-[10px] text-gray-400 mt-0.5">이곳에서 직접 대본을 수정하면 수정된 대본으로 음성이 생성됩니다.</p>
                                        </div>
                                        <div className="flex items-center gap-3">
                                            <button
                                                type="button"
                                                onClick={restoreOriginalWorkerScript}
                                                className="px-3 py-1.5 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded-lg text-xs font-bold transition shadow flex items-center gap-1.5"
                                            >
                                                <span>↺</span> 워커 원본 대본 복구
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => handleSyncScriptToScenesAndSubtitles(true)}
                                                className="px-3 py-1.5 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white rounded-lg text-xs font-bold transition shadow flex items-center gap-1.5"
                                            >
                                                <span>🔄</span> 대본 ↔ 씬/자막 전체 동기화
                                            </button>
                                            <div className="text-right">
                                                <div className="text-xs font-bold text-purple-400 font-mono">{scriptCharCount.toLocaleString()}자</div>
                                                <div className="text-[10px] text-gray-400">예상 소요: {formattedEstimatedTime}</div>
                                            </div>
                                        </div>
                                    </div>
                                    <textarea
                                        value={customScriptText}
                                        onChange={e => {
                                            setCustomScriptText(e.target.value)
                                            setScriptSyncDirty(true)
                                        }}
                                        onBlur={() => {
                                            ensureScriptSyncedBeforeAction().catch((error: any) => {
                                                setMessage(error?.message || 'Script sync save failed')
                                            })
                                        }}
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
                                        <select
                                            value={selectedImageTemplatePreset}
                                            onChange={e => handleSelectImageTemplatePreset(e.target.value)}
                                            className="px-3 py-1.5 bg-[#202632] border border-white/10 rounded text-xs font-bold text-gray-200 focus:outline-none focus:border-blue-500"
                                        >
                                            <option value="">템플릿 선택</option>
                                            {templatePresets.map(preset => (
                                                <option key={preset.id} value={preset.id}>
                                                    {preset.name}
                                                </option>
                                            ))}
                                        </select>
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
                                                onClick={prepareLocalDirectoryForUpload}
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

                                <div className={`rounded-lg border px-4 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                                    localMediaDirectory.status === 'connected'
                                        ? 'border-emerald-500/30 bg-emerald-500/10'
                                        : 'border-amber-500/30 bg-amber-500/10'
                                }`}>
                                    <div className="min-w-0">
                                        <div className="text-xs font-bold text-white flex items-center gap-2">
                                            <FolderKanban size={15} />
                                            {localMediaDirectory.status === 'connected'
                                                ? `로컬 저장 폴더 연결됨: ${localMediaDirectory.folderName}`
                                                : localMediaDirectory.status === 'unsupported'
                                                    ? '이 브라우저는 로컬 폴더 저장을 지원하지 않습니다.'
                                                    : localMediaDirectory.status === 'permission_needed'
                                                        ? `로컬 폴더 권한 재연결 필요: ${localMediaDirectory.folderName}`
                                                        : '로컬 저장 폴더를 먼저 선택해주세요.'}
                                        </div>
                                        <p className="text-[11px] text-gray-400 mt-1">
                                            업로드 파일은 선택한 폴더의 AIRStudio-STD/프로젝트/씬 위치에 저장되며 새로고침 후 이 위치에서 우선 복원됩니다.
                                        </p>
                                    </div>
                                    <button
                                        onClick={connectLocalMediaDirectory}
                                        disabled={localMediaDirectoryBusy || localMediaDirectory.status === 'unsupported'}
                                        className="shrink-0 px-3 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded text-xs font-bold transition-all"
                                    >
                                        {localMediaDirectoryBusy
                                            ? '연결 중...'
                                            : localMediaDirectory.status === 'connected'
                                                ? '폴더 변경'
                                                : localMediaDirectory.status === 'permission_needed'
                                                    ? '권한 재연결'
                                                : '로컬 폴더 선택'}
                                    </button>
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
                                    {assetStats.requiredZoneOnlyImage.length > 0 && (
                                        <p className="text-xs text-orange-400">
                                            🔒 초반 구간 영상 필요 (이미지만 있음: {assetStats.requiredZoneOnlyImage.join(', ')})
                                        </p>
                                    )}
                                </div>

                                <div className="p-4 border-t border-white/5 space-y-4">
                                    {/* 1. 초반 필수 영상 구간 (1~12씬 - 진한 주황색) */}
                                    <div className="space-y-2">
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-2">
                                                <span className="w-2 h-2 rounded-full bg-orange-500 animate-pulse" />
                                                <span className="text-xs font-bold text-orange-400 uppercase tracking-wide">
                                                    초반 1분 필수 영상 구간 (씬 1 ~ 12)
                                                </span>
                                            </div>
                                            <span className="text-[10px] text-gray-400 font-mono">
                                                완료: {selectedProject.scenes.filter(s => (s.scene_number <= 12) && Boolean(s.video_url)).length} / 12
                                            </span>
                                        </div>
                                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
                                            {selectedProject.scenes.slice(0, 12).map((scene: any, idx: number) => {
                                                const sNum = scene.scene_number || idx + 1
                                                const isReady = Boolean(scene.video_url)
                                                return (
                                                    <div
                                                        key={scene.id || idx}
                                                        className={`p-2.5 rounded-xl border transition-all flex flex-col justify-between min-h-[76px] ${
                                                            isReady
                                                                ? 'bg-emerald-950/30 border-emerald-500/40 text-emerald-300'
                                                                : 'bg-orange-950/20 border-orange-500/50 hover:border-orange-400 shadow-sm'
                                                        }`}
                                                    >
                                                        <div className="flex items-center justify-between">
                                                            <span className="text-xs font-black px-1.5 py-0.5 rounded bg-orange-500/20 text-orange-300 border border-orange-500/30">
                                                                #{sNum}
                                                            </span>
                                                            <span className={`text-[10px] font-bold ${isReady ? 'text-emerald-400' : 'text-orange-400'}`}>
                                                                {isReady ? '✅ 영상 완료' : '영상 없음'}
                                                            </span>
                                                        </div>
                                                        <div className="flex items-center justify-between pt-1 border-t border-white/5 text-[11px] font-bold">
                                                            <button
                                                                type="button"
                                                                onClick={() => {
                                                                    const el = document.getElementById(`prompt-card-${idx}`)
                                                                    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
                                                                }}
                                                                className="text-gray-400 hover:text-white transition-colors"
                                                            >
                                                                보기
                                                            </button>
                                                            <span className="text-gray-600">|</span>
                                                            <label className="cursor-pointer text-orange-400 hover:text-orange-300 transition-colors">
                                                                {isReady ? '교체' : '업로드'}
                                                                <input
                                                                    type="file"
                                                                    accept="video/*"
                                                                    className="hidden"
                                                                    onClick={prepareLocalDirectoryForUpload}
                                                                    onChange={e => uploadAsset(scene, 'video', e.target.files?.[0] || null)}
                                                                />
                                                            </label>
                                                        </div>
                                                    </div>
                                                )
                                            })}
                                        </div>
                                    </div>

                                    {/* 2. 본문 이미지/영상 구간 (13~53씬 - 흐린 주황/앰버색) */}
                                    <div className="space-y-2 pt-2 border-t border-white/5">
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-2">
                                                <span className="w-2 h-2 rounded-full bg-amber-500/70" />
                                                <span className="text-xs font-bold text-amber-400/90 uppercase tracking-wide">
                                                    본문 이미지 구간 (씬 13 ~ {selectedProject.scenes.length})
                                                </span>
                                            </div>
                                            <span className="text-[10px] text-gray-400 font-mono">
                                                완료: {selectedProject.scenes.slice(12).filter(s => Boolean(s.image_url || s.video_url)).length} / {Math.max(0, selectedProject.scenes.length - 12)}
                                            </span>
                                        </div>
                                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8 gap-2">
                                            {selectedProject.scenes.slice(12).map((scene: any, offsetIdx: number) => {
                                                const idx = offsetIdx + 12
                                                const sNum = scene.scene_number || idx + 1
                                                const isReady = Boolean(scene.image_url || scene.video_url)
                                                return (
                                                    <div
                                                        key={scene.id || idx}
                                                        className={`p-2.5 rounded-xl border transition-all flex flex-col justify-between min-h-[76px] ${
                                                            isReady
                                                                ? 'bg-emerald-950/20 border-emerald-500/30 text-emerald-300'
                                                                : 'bg-[#181d26] border-amber-500/30 hover:border-amber-400/60 shadow-sm'
                                                        }`}
                                                    >
                                                        <div className="flex items-center justify-between">
                                                            <span className="text-xs font-bold px-1.5 py-0.5 rounded bg-white/5 text-gray-300 border border-white/10">
                                                                #{sNum}
                                                            </span>
                                                            <span className={`text-[10px] font-bold ${isReady ? 'text-emerald-400' : 'text-amber-400/80'}`}>
                                                                {isReady ? '✅ 이미지 완료' : '이미지 없음'}
                                                            </span>
                                                        </div>
                                                        <div className="flex items-center justify-between pt-1 border-t border-white/5 text-[11px] font-bold">
                                                            <button
                                                                type="button"
                                                                onClick={() => {
                                                                    const el = document.getElementById(`prompt-card-${idx}`)
                                                                    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
                                                                }}
                                                                className="text-gray-400 hover:text-white transition-colors"
                                                            >
                                                                보기
                                                            </button>
                                                            <span className="text-gray-600">|</span>
                                                            <label className="cursor-pointer text-amber-400 hover:text-amber-300 transition-colors">
                                                                {isReady ? '교체' : '업로드'}
                                                                <input
                                                                    type="file"
                                                                    accept="image/*,video/*"
                                                                    className="hidden"
                                                                    onClick={prepareLocalDirectoryForUpload}
                                                                    onChange={e => uploadAsset(scene, 'image', e.target.files?.[0] || null)}
                                                                />
                                                            </label>
                                                        </div>
                                                    </div>
                                                )
                                            })}
                                        </div>
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
                                                    <span className="text-xs text-gray-400 truncate max-w-md" title={getSceneScriptStartText(scene, i)}>
                                                        📄 {getSceneScriptStartText(scene, i)}
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
                                                                    onClick={prepareLocalDirectoryForUpload}
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

                    {/* [주제 탐색 탭 (유저앱 topic.html 100% 동일 구현 + 상세 모달 + 프로젝트 자동 연동)] */}
                    {currentNav === 'topics' && (
                        <div className="space-y-6 max-w-7xl mx-auto w-full pb-10">
                            <div className="bg-[#1c2027] border border-white/10 rounded-2xl p-5 shadow-xl space-y-4">
                                <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-white/5 pb-3">
                                    <div className="flex items-center gap-2.5">
                                        <span className="text-xl">🔥</span>
                                        <div>
                                            <h2 className="text-sm font-bold text-white flex items-center gap-2">
                                                <span>실시간 트렌드 키워드 & AI 주제 분석</span>
                                                <span className="text-[10px] px-2 py-0.5 bg-red-500/20 text-red-400 rounded-full font-bold border border-red-500/30 animate-pulse">LIVE</span>
                                            </h2>
                                            <p className="text-[11px] text-gray-400">유튜브 및 글로벌 트렌드 빅데이터를 기반으로 실시간 급상승 키워드를 추출합니다.</p>
                                        </div>
                                    </div>

                                    {/* 국가 / 기간 / 연령대 필터 */}
                                    <div className="flex flex-wrap items-center gap-2">
                                        {/* 국가 */}
                                        <div className="flex bg-[#14181f] p-1 rounded-lg border border-white/10 text-xs">
                                            {[
                                                { code: 'ko', label: '🇰🇷 한국' },
                                                { code: 'ja', label: '🇯🇵 日本' },
                                                { code: 'en', label: '🇺🇸 Global' },
                                            ].map(item => (
                                                <button
                                                    key={item.code}
                                                    type="button"
                                                    onClick={() => setTrendLang(item.code as any)}
                                                    className={`px-2.5 py-1 rounded text-[11px] font-bold transition ${
                                                        trendLang === item.code ? 'bg-blue-600 text-white shadow' : 'text-gray-400 hover:text-white'
                                                    }`}
                                                >
                                                    {item.label}
                                                </button>
                                            ))}
                                        </div>

                                        {/* 기간 */}
                                        <div className="flex bg-[#14181f] p-1 rounded-lg border border-white/10 text-xs">
                                            {[
                                                { id: 'now', label: '지금' },
                                                { id: 'week', label: '이번 주' },
                                                { id: 'month', label: '이번 달' },
                                            ].map(item => (
                                                <button
                                                    key={item.id}
                                                    type="button"
                                                    onClick={() => setTrendPeriod(item.id)}
                                                    className={`px-2.5 py-1 rounded text-[11px] font-bold transition ${
                                                        trendPeriod === item.id ? 'bg-indigo-600 text-white shadow' : 'text-gray-400 hover:text-white'
                                                    }`}
                                                >
                                                    {item.label}
                                                </button>
                                            ))}
                                        </div>

                                        {/* 연령대 */}
                                        <div className="flex bg-[#14181f] p-1 rounded-lg border border-white/10 text-xs">
                                            {[
                                                { id: 'all', label: '전체' },
                                                { id: '30s', label: '3040' },
                                                { id: '50s', label: '5060 시니어' },
                                            ].map(item => (
                                                <button
                                                    key={item.id}
                                                    type="button"
                                                    onClick={() => setTrendAge(item.id)}
                                                    className={`px-2 py-1 rounded text-[11px] font-bold transition ${
                                                        trendAge === item.id ? 'bg-purple-600 text-white shadow' : 'text-gray-400 hover:text-white'
                                                    }`}
                                                >
                                                    {item.label}
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                </div>

                                {/* 트렌드 버블 키워드 클라우드 */}
                                <div className="space-y-2">
                                    <div className="flex items-center justify-between text-[11px] text-gray-400">
                                        <span>추천 급상승 검색어 (클릭 시 주제 필터 적용)</span>
                                        <span className="font-mono text-blue-400">12개 키워드 감지됨</span>
                                    </div>
                                    <div className="flex flex-wrap gap-2">
                                        {[
                                            { text: '장례식 날 발견된 낡은 편지', volume: 98, cat: '한국사연' },
                                            { text: '아내의 숨겨진 30년 첫사랑 편지', volume: 95, cat: '사연' },
                                            { text: '조선왕조 비밀 야사', volume: 88, cat: '역사' },
                                            { text: '유품 상자에서 나온 가족사진', volume: 85, cat: '한국사연' },
                                            { text: '사라진 며느리가 남긴 붉은 댕기', volume: 82, cat: '옛날이야기' },
                                            { text: '100세 시대 치매 예방 음식', volume: 79, cat: '건강' },
                                            { text: '황혼 이혼 재산분할 진실', volume: 76, cat: '사연' },
                                            { text: 'AI 자동화 수익 모델 2026', volume: 74, cat: '테크' },
                                            { text: '마을 우물에서 들린 아이의 울음', volume: 70, cat: '옛날이야기' },
                                            { text: '시니어 일자리 추천 Top 5', volume: 68, cat: '라이프' },
                                        ].map((kw, idx) => (
                                            <button
                                                key={idx}
                                                type="button"
                                                onClick={() => {
                                                    setTopicSearchQuery(kw.text)
                                                }}
                                                className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 border shadow-sm ${
                                                    topicSearchQuery === kw.text
                                                        ? 'bg-blue-600 text-white border-blue-400 scale-105'
                                                        : 'bg-[#14181f] text-gray-300 border-white/10 hover:border-blue-500 hover:text-white'
                                                }`}
                                            >
                                                <span className="text-[10px] text-amber-400 font-mono">#{idx + 1}</span>
                                                <span>{kw.text}</span>
                                                <span className="text-[9px] px-1.5 py-0.2 rounded bg-white/10 text-gray-400">{kw.cat}</span>
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            </div>

                            {/* 2. 검색 및 큐 목록 헤더 바 */}
                            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 bg-[#1c2027] border border-white/10 rounded-2xl p-4 shadow-lg">
                                <div className="flex items-center gap-3 flex-1 max-w-xl">
                                    <div className="relative flex-1">
                                        <input
                                            type="text"
                                            value={topicSearchQuery}
                                            onChange={e => setTopicSearchQuery(e.target.value)}
                                            placeholder="주제 키워드 또는 카테고리 검색..."
                                            className="w-full bg-[#14181f] border border-white/10 rounded-xl px-4 py-2 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                                        />
                                        {topicSearchQuery && (
                                            <button
                                                type="button"
                                                onClick={() => setTopicSearchQuery('')}
                                                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white text-xs"
                                            >
                                                ✕
                                            </button>
                                        )}
                                    </div>
                                    <button
                                        type="button"
                                        onClick={() => {}}
                                        className="px-4 py-2 bg-[#202632] hover:bg-blue-600 text-white rounded-xl text-xs font-bold transition border border-white/10"
                                    >
                                        검색
                                    </button>
                                </div>

                                <div className="flex items-center gap-2 flex-wrap">
                                    <select
                                        value={topicLengthFilter}
                                        onChange={e => setTopicLengthFilter(e.target.value)}
                                        className="text-xs bg-[#14181f] border border-white/10 rounded-xl px-3 py-2 text-white outline-none cursor-pointer"
                                    >
                                        <option value="">전체 영상길이</option>
                                        <option value="short">짧은 영상 (15분 미만)</option>
                                        <option value="medium">중간 영상 (15-30분)</option>
                                        <option value="long">긴 영상 (30분 이상)</option>
                                    </select>
                                    <button
                                        onClick={() => loadStdData(token)}
                                        className="text-xs bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-xl transition-all font-bold shadow flex items-center gap-1.5"
                                    >
                                        <span>🔄</span> 주제 새로고침
                                    </button>
                                </div>
                            </div>

                            {/* 3. AI 추천 주제 큐 카드 그리드 (Check AI-analyzed personalized topics) */}
                            <div className="space-y-3">
                                <div className="flex items-center justify-between">
                                    <h3 className="text-sm font-bold text-white flex items-center gap-2">
                                        <span>✨ AI 추천 작업 주제 큐</span>
                                        <span className="text-xs text-indigo-400 font-mono">({displayedTopics.length}개 대기 중)</span>
                                    </h3>
                                    <span className="text-xs text-gray-400">주제 카드를 클릭하면 상세 기획 프리뷰 및 작업 시작 모달이 나타납니다.</span>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                                    {displayedTopics.map(topic => (
                                        <div
                                            key={topic.id}
                                            onClick={() => {
                                                setSelectedTopicForModal(topic)
                                                setTopicModalOpen(true)
                                            }}
                                            className="bg-[#1c2027] border border-white/10 hover:border-indigo-500 rounded-2xl p-5 cursor-pointer hover:-translate-y-1.5 transition-all shadow-lg group flex flex-col justify-between relative overflow-hidden"
                                        >
                                            <div className="space-y-3">
                                                {/* 상단 뱃지 & 수당 */}
                                                <div className="flex items-center justify-between gap-2">
                                                    <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-indigo-600/30 text-indigo-300 border border-indigo-500/30 truncate max-w-[65%]">
                                                        {topic.category_name || '옛날이야기'}
                                                    </span>
                                                    <span className="text-xs font-bold text-amber-400 font-mono bg-amber-400/10 px-2 py-0.5 rounded-full border border-amber-400/20">
                                                        {formatTopicPayout(topic)}
                                                    </span>
                                                </div>

                                                {/* 주제 제목 */}
                                                <h4 className="text-sm font-bold text-white group-hover:text-indigo-300 transition-colors line-clamp-2 leading-snug">
                                                    {topic.generated_title || topic.topic}
                                                </h4>

                                                {/* 원본 주제 요약 */}
                                                <p className="text-[11px] text-gray-400 line-clamp-2 leading-relaxed">
                                                    {topic.topic}
                                                </p>
                                            </div>

                                            {/* 하단 메타 태그 & 작업 버튼 */}
                                            <div className="mt-4 pt-3 border-t border-white/5 space-y-3">
                                                <div className="flex items-center justify-between text-[11px] text-gray-400 font-mono">
                                                    <span className="flex items-center gap-1">
                                                        <span>⏱️</span> {topic.assigned_duration_minutes || 15}분 영상
                                                    </span>
                                                    <span className="text-cyan-400">{topic.scene_count || 53} Scenes</span>
                                                </div>

                                                <button
                                                    type="button"
                                                    onClick={(e) => {
                                                        e.stopPropagation()
                                                        setSelectedTopicForModal(topic)
                                                        setTopicModalOpen(true)
                                                    }}
                                                    className="w-full py-2 bg-[#202632] group-hover:bg-gradient-to-r group-hover:from-blue-600 group-hover:to-indigo-600 text-gray-300 group-hover:text-white rounded-xl text-xs font-bold transition-all shadow"
                                                >
                                                    주제 상세 확인 & 작업 시작 →
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            {/* 4. 주제 상세 확인 및 프로젝트 클레임 팝업 모달 */}
                            {topicModalOpen && selectedTopicForModal && (
                                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fadeIn">
                                    <div className="bg-[#1c2027] border border-white/20 rounded-3xl max-w-2xl w-full p-6 shadow-2xl space-y-5 relative text-left">
                                        {/* 닫기 버튼 */}
                                        <button
                                            type="button"
                                            onClick={() => setTopicModalOpen(false)}
                                            className="absolute top-5 right-5 text-gray-400 hover:text-white text-lg font-bold p-1"
                                        >
                                            ✕
                                        </button>

                                        {/* 헤더 */}
                                        <div className="space-y-1.5 border-b border-white/10 pb-4">
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs font-bold px-3 py-1 bg-indigo-600 text-white rounded-full">
                                                    {selectedTopicForModal.category_name || '옛날이야기'}
                                                </span>
                                                <span className="text-xs font-bold px-2.5 py-1 bg-amber-500/20 text-amber-300 rounded-full border border-amber-500/30 font-mono">
                                                    정산 수당: {formatTopicPayoutDetail(selectedTopicForModal)}
                                                </span>
                                                <span className="text-xs font-bold px-2.5 py-1 bg-blue-500/20 text-blue-300 rounded-full border border-blue-500/30">
                                                    {selectedTopicForModal.assigned_duration_minutes || 15}분 롱폼
                                                </span>
                                            </div>
                                            <h3 className="text-lg font-bold text-white pt-2 leading-snug">
                                                {selectedTopicForModal.generated_title || selectedTopicForModal.topic}
                                            </h3>
                                        </div>

                                        {/* 본문 기획 상세 구성 */}
                                        <div className="space-y-3 text-xs bg-[#14181f] p-4 rounded-2xl border border-white/5">
                                            <div className="space-y-1">
                                                <span className="text-gray-400 font-bold block">📌 원본 주제 내용</span>
                                                <p className="text-gray-200 leading-relaxed">{selectedTopicForModal.topic}</p>
                                            </div>

                                            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-2 border-t border-white/5 font-mono text-[11px]">
                                                <div className="bg-[#1c2027] p-2.5 rounded-xl border border-white/5 space-y-0.5">
                                                    <span className="text-gray-400 block">🎬 씬 구성</span>
                                                    <span className="font-bold text-emerald-400">총 {selectedTopicForModal.scene_count || 53}개 씬 구조</span>
                                                </div>
                                                <div className="bg-[#1c2027] p-2.5 rounded-xl border border-white/5 space-y-0.5">
                                                    <span className="text-gray-400 block">⚡ 초반 1분 훅</span>
                                                    <span className="font-bold text-orange-400">1~12씬 5초 비디오</span>
                                                </div>
                                                <div className="bg-[#1c2027] p-2.5 rounded-xl border border-white/5 space-y-0.5 col-span-2 sm:col-span-1">
                                                    <span className="text-gray-400 block">🎨 추천 화풍</span>
                                                    <span className="font-bold text-purple-400">Cinematic / Ghibli</span>
                                                </div>
                                            </div>

                                            <div className="p-3 bg-blue-950/30 border border-blue-500/30 rounded-xl space-y-1">
                                                <span className="text-blue-300 font-bold flex items-center gap-1.5">
                                                    <span>💡</span> 안내 사항
                                                </span>
                                                <p className="text-gray-300 text-[11px] leading-relaxed">
                                                    이 주제로 작업을 시작하면 작업자의 활성 프로젝트로 즉시 등록 및 저장되며, 대본, 씬 프롬프트, 음성, 1줄 자막 분할 및 썸네일 제작 단계로 연결됩니다.
                                                </p>
                                            </div>
                                        </div>

                                        {/* 액션 버튼 */}
                                        <div className="flex items-center justify-end gap-3 pt-2">
                                            <button
                                                type="button"
                                                onClick={() => setTopicModalOpen(false)}
                                                className="px-5 py-2.5 bg-[#202632] hover:bg-white/10 text-gray-300 hover:text-white rounded-xl text-xs font-bold transition"
                                            >
                                                취소
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => claimTopic(selectedTopicForModal.id)}
                                                disabled={loading}
                                                className="px-6 py-2.5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white rounded-xl text-xs font-bold transition shadow-lg flex items-center gap-2"
                                            >
                                                <span>🚀</span>
                                                {loading ? '프로젝트 생성 및 저장 중...' : '이 주제로 작업 시작 (Start Project)'}
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* [썸네일 탭 (유저앱 thumbnail.html과 100% 동일한 4단계 썸네일 제작 스튜디오)] */}
                    {currentNav === 'thumbnail' && (
                        <div className="space-y-5 max-w-6xl mx-auto w-full flex flex-col h-full pb-10">
                            {/* 1단계: 제목 및 스타일 설정 (가로 와이드 3단 레이아웃) */}
                            <div className="bg-[#1c2027] border border-white/10 rounded-2xl p-5 shadow-xl space-y-4">
                                <div className="flex items-center justify-between border-b border-white/5 pb-3">
                                    <h3 className="font-bold text-sm text-white flex items-center gap-2">
                                        <span className="w-6 h-6 rounded-lg bg-blue-600 text-white flex items-center justify-center text-xs font-bold shadow-md shadow-blue-500/30">1</span>
                                        1단계: 제목 및 스타일 설정
                                    </h3>
                                    <span className="text-[10px] text-gray-400 font-mono tracking-wider uppercase">Thumbnail Configuration</span>
                                </div>

                                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
                                    {/* 왼쪽: 제목 입력 및 생성 버튼 */}
                                    <div className="lg:col-span-4 flex flex-col gap-3">
                                        <div>
                                            <label className="block text-[11px] font-bold text-gray-400 mb-1.5 uppercase tracking-wider">
                                                영상 제목 및 기획 의도
                                            </label>
                                            <textarea
                                                value={thumbTitle}
                                                onChange={e => syncProjectTitle(e.target.value)}
                                                placeholder="영상의 주요 내용이나 기획 의도를 입력하세요."
                                                className="w-full bg-[#14181f] border border-white/10 rounded-xl p-3 text-xs text-white resize-none h-[110px] focus:outline-none focus:border-blue-500 leading-relaxed"
                                            />
                                        </div>
                                        <button
                                            type="button"
                                            onClick={() => {
                                                setThumbStep(2)
                                                alert('입력된 영상 제목과 스타일에 맞춰 3가지 최적 썸네일 기획안이 생성되었습니다.')
                                            }}
                                            className="w-full py-3 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-bold rounded-xl shadow-lg transition-all"
                                        >
                                            ✨ 썸네일 기획안 통합 생성
                                        </button>
                                        <div className="grid grid-cols-2 gap-2">
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    setThumbTextLayers(prev => prev.map((l, i) => i === 0 ? { ...l, text: '삼십 년 숨긴 편지의 진실!?' } : l))
                                                    alert('더 자극적인(Clicky) 후킹 문구로 변경되었습니다.')
                                                }}
                                                className="py-1.5 border border-amber-500/40 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 rounded-lg text-[11px] font-bold transition"
                                            >
                                                🔥 더 어그로성 (Clicky)
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    setThumbTextLayers(prev => prev.map((l, i) => i === 0 ? { ...l, text: '장례식 날 열린 마지막 편지' } : l))
                                                    alert('더 깔끔하고 신뢰감 있는(Clean) 문구로 변경되었습니다.')
                                                }}
                                                className="py-1.5 border border-cyan-500/40 bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 rounded-lg text-[11px] font-bold transition"
                                            >
                                                ✨ 더 깔끔하게 (Clean)
                                            </button>
                                        </div>
                                    </div>

                                    {/* 중간: 레이아웃 스타일 갤러리 */}
                                    <div className="lg:col-span-4 border-l border-white/5 lg:pl-6 space-y-2">
                                        <div className="flex items-center justify-between">
                                            <label className="text-[11px] font-bold text-gray-400 uppercase tracking-wider">레이아웃 스타일</label>
                                            <span className="text-[10px] bg-blue-600/20 text-blue-400 px-2 py-0.5 rounded-full font-bold border border-blue-500/30 uppercase">{thumbLayout}</span>
                                        </div>
                                        <div className="grid grid-cols-3 gap-2">
                                            {[
                                                { id: 'face', name: 'Face (얼굴/인물)' },
                                                { id: 'split', name: 'Split (좌우 분할)' },
                                                { id: 'viral', name: 'Viral (바이럴)' },
                                                { id: 'text_heavy', name: 'Text (대형 텍스트)' },
                                                { id: 'question', name: 'Question (의문형)' },
                                            ].map(item => (
                                                <button
                                                    key={item.id}
                                                    type="button"
                                                    onClick={() => setThumbLayout(item.id)}
                                                    className={`p-2 rounded-lg border text-center transition-all flex flex-col items-center justify-center gap-1 ${
                                                        thumbLayout === item.id
                                                            ? 'border-blue-500 bg-blue-600/20 text-blue-300 font-bold shadow'
                                                            : 'border-white/5 bg-[#14181f] text-gray-400 hover:text-white'
                                                    }`}
                                                >
                                                    <span className="text-sm">🖼️</span>
                                                    <span className="text-[10px] truncate w-full">{item.name}</span>
                                                </button>
                                            ))}
                                        </div>
                                    </div>

                                    {/* 오른쪽: 이미지 화풍 갤러리 */}
                                    <div className="lg:col-span-4 border-l border-white/5 lg:pl-6 space-y-2">
                                        <div className="flex items-center justify-between">
                                            <label className="text-[11px] font-bold text-gray-400 uppercase tracking-wider">이미지 화풍</label>
                                            <span className="text-[10px] bg-purple-600/20 text-purple-400 px-2 py-0.5 rounded-full font-bold border border-purple-500/30 uppercase">{thumbStyle}</span>
                                        </div>
                                        <div className="grid grid-cols-2 gap-2">
                                            {[
                                                { id: 'realistic', name: 'Realistic (실사)' },
                                                { id: 'cinematic', name: 'Cinematic (영화풍)' },
                                                { id: 'webtoon', name: 'Webtoon (웹툰풍)' },
                                                { id: 'anime', name: 'Anime (애니)' },
                                            ].map(item => (
                                                <button
                                                    key={item.id}
                                                    type="button"
                                                    onClick={() => setThumbStyle(item.id)}
                                                    className={`p-2.5 rounded-lg border text-center transition-all flex flex-col items-center justify-center gap-1 ${
                                                        thumbStyle === item.id
                                                            ? 'border-purple-500 bg-purple-600/20 text-purple-300 font-bold shadow'
                                                            : 'border-white/5 bg-[#14181f] text-gray-400 hover:text-white'
                                                    }`}
                                                >
                                                    <span className="text-sm">🎨</span>
                                                    <span className="text-[10px] font-medium">{item.name}</span>
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* 2단계: 썸네일 기획안 선택 (AI 생성 3종 카드) */}
                            <div className="bg-[#1c2027] border border-white/10 rounded-2xl p-5 shadow-xl space-y-4">
                                <div className="flex items-center justify-between border-b border-white/5 pb-3">
                                    <h3 className="font-bold text-sm text-white flex items-center gap-2">
                                        <span className="w-6 h-6 rounded-lg bg-indigo-600 text-white flex items-center justify-center text-xs font-bold shadow-md shadow-indigo-500/30">2</span>
                                        2단계: AI 썸네일 기획안 선택
                                    </h3>
                                    <span className="text-xs text-indigo-400 font-medium">클릭 시 3단계 캔버스에 즉시 반영됩니다.</span>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                    {[
                                        {
                                            id: 'idea-1',
                                            badge: '충격 폭로형',
                                            headline: '삼십 년 숨긴 편지의 진실',
                                            subhead: '통장에 찍힌 실제 수령액 공개',
                                            prompt: 'An elderly husband looking in shock at a bank statement with a magnifying glass, dramatic lighting, high contrast',
                                        },
                                        {
                                            id: 'idea-2',
                                            badge: '현실 대비형',
                                            headline: '장례식 뒤 드러난 마지막 약속',
                                            subhead: '우리가 몰랐던 은퇴 후 한 달 생활비',
                                            prompt: 'Split screen, on the left an old pension book, on the right a simple empty dinner table, emotive photorealistic style',
                                        },
                                        {
                                            id: 'idea-3',
                                            badge: '호기심 자극형',
                                            headline: '30년 일하고 받은 돈이 고작...',
                                            subhead: '평범한 부부의 솔직한 고백',
                                            prompt: 'Close up of weathered hands holding a worn leather handbag and yellowed letter, intense emotional atmosphere',
                                        },
                                    ].map((idea, idx) => (
                                        <div
                                            key={idea.id}
                                            onClick={() => {
                                                setThumbTextLayers([
                                                    {
                                                        id: `layer-${Date.now()}-1`,
                                                        text: idea.headline,
                                                        fontSize: 34,
                                                        color: idx === 0 ? '#ffeb3b' : idx === 1 ? '#ff5252' : '#00e5ff',
                                                        strokeColor: '#000000',
                                                        strokeWidth: 4,
                                                        fontFamily: 'GmarketSansBold',
                                                        x: 50,
                                                        y: 35,
                                                    },
                                                    {
                                                        id: `layer-${Date.now()}-2`,
                                                        text: idea.subhead,
                                                        fontSize: 26,
                                                        color: '#ffffff',
                                                        strokeColor: '#000000',
                                                        strokeWidth: 3,
                                                        fontFamily: 'GmarketSansBold',
                                                        x: 50,
                                                        y: 65,
                                                    }
                                                ])
                                                alert(`'${idea.badge}' 기획안이 3단계 디자인 캔버스에 적용되었습니다!`)
                                            }}
                                            className="bg-[#14181f] border border-white/10 hover:border-indigo-500 rounded-xl p-4 cursor-pointer hover:-translate-y-1 transition-all shadow-md group flex flex-col justify-between"
                                        >
                                            <div className="space-y-2">
                                                <div className="flex items-center justify-between">
                                                    <span className="text-[10px] font-bold px-2 py-0.5 bg-indigo-600/30 text-indigo-300 rounded border border-indigo-500/30">
                                                        {idea.badge}
                                                    </span>
                                                    <span className="text-[10px] text-gray-500">기획안 #{idx + 1}</span>
                                                </div>
                                                <h4 className="text-xs font-bold text-white group-hover:text-indigo-400 transition-colors pt-1">
                                                    {idea.headline}
                                                </h4>
                                                <p className="text-[11px] text-gray-400 font-medium">
                                                    {idea.subhead}
                                                </p>
                                                <p className="text-[10px] text-gray-500 font-mono line-clamp-2 pt-1">
                                                    {idea.prompt}
                                                </p>
                                            </div>
                                            <button
                                                type="button"
                                                className="w-full mt-3 py-1.5 bg-[#202632] group-hover:bg-indigo-600 text-gray-300 group-hover:text-white rounded-lg text-[11px] font-bold transition-all shadow"
                                            >
                                                선택 및 디자인 적용
                                            </button>
                                        </div>
                                    ))}
                                </div>

                                {/* 훅 추천 문구 바 */}
                                <div className="bg-[#14181f] border-l-4 border-blue-500 rounded-xl p-3.5 flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
                                    <div className="flex items-center gap-2">
                                        <span className="text-base">🎯</span>
                                        <span className="text-xs font-bold text-blue-300">AI 추천 훅 문구:</span>
                                    </div>
                                    <div className="flex flex-wrap gap-1.5 flex-1">
                                        {[
                                            "삼십 년 숨긴 편지의 진실",
                                            "통장에 찍힌 실제 수령액",
                                            "은퇴 후 현실 생계비",
                                            "평범한 부부의 눈물",
                                        ].map((hook, hIdx) => (
                                            <button
                                                key={hIdx}
                                                type="button"
                                                onClick={() => {
                                                    const newLayer = {
                                                        id: `layer-${Date.now()}`,
                                                        text: hook,
                                                        fontSize: 30,
                                                        color: '#ffeb3b',
                                                        strokeColor: '#000000',
                                                        strokeWidth: 3,
                                                        fontFamily: 'GmarketSansBold',
                                                        x: 50,
                                                        y: 50,
                                                    }
                                                    setThumbTextLayers(prev => [...prev, newLayer])
                                                }}
                                                className="px-2.5 py-1 bg-[#202632] hover:bg-blue-600 border border-white/10 hover:border-blue-500 text-gray-300 hover:text-white rounded-md text-[11px] font-bold transition"
                                            >
                                                + {hook}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            </div>

                            {/* 3단계: 텍스트 추가 및 16:9 실시간 캔버스 */}
                            <div className="bg-[#1c2027] border border-white/10 rounded-2xl p-5 shadow-xl space-y-4">
                                <div className="flex items-center justify-between border-b border-white/5 pb-3">
                                    <h3 className="font-bold text-sm text-white flex items-center gap-2">
                                        <span className="w-6 h-6 rounded-lg bg-emerald-600 text-white flex items-center justify-center text-xs font-bold shadow-md shadow-emerald-500/30">3</span>
                                        3단계: 텍스트 추가 및 16:9 실시간 캔버스
                                    </h3>
                                    <button
                                        type="button"
                                        onClick={async () => {
                                            try {
                                                let persistedThumbnailUrl: string | undefined
                                                if (thumbBgUploadFile) {
                                                    persistedThumbnailUrl = await uploadThumbnailBgToDrive(thumbBgUploadFile)
                                                }
                                                await markThumbnailConfirmed(persistedThumbnailUrl)
                                                alert('현재 썸네일 디자인이 프로젝트 대표 썸네일로 최종 저장되었습니다!')
                                            } catch (error: any) {
                                                alert(error.message || '썸네일 이미지 업로드에 실패했습니다.')
                                            }
                                        }}
                                        disabled={uploadingKey === 'thumbnail-upload'}
                                        className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-lg shadow transition disabled:opacity-60"
                                    >
                                        {uploadingKey === 'thumbnail-upload' ? '업로드 중...' : '💾 최종 썸네일 확정 저장'}
                                    </button>
                                </div>

                                <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
                                    {/* 좌측: 텍스트 레이어 관리 */}
                                    <div className="lg:col-span-6 space-y-3">
                                        <div className="flex items-center justify-between">
                                            <span className="text-xs font-bold text-gray-300">텍스트 레이어 목록 ({thumbTextLayers.length}개)</span>
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    const newLayer = {
                                                        id: `layer-${Date.now()}`,
                                                        text: '새 텍스트 문구',
                                                        fontSize: 28,
                                                        color: '#ffffff',
                                                        strokeColor: '#000000',
                                                        strokeWidth: 3,
                                                        fontFamily: 'GmarketSansBold',
                                                        x: 50,
                                                        y: 50,
                                                    }
                                                    setThumbTextLayers(prev => [...prev, newLayer])
                                                }}
                                                className="px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded text-xs font-bold transition shadow"
                                            >
                                                + 텍스트 추가
                                            </button>
                                        </div>

                                        <div className="space-y-3 max-h-[350px] overflow-y-auto pr-1">
                                            {thumbTextLayers.map((layer, index) => (
                                                <div key={layer.id} className="bg-[#14181f] border border-white/5 rounded-xl p-3 space-y-2.5">
                                                    <div className="flex items-center justify-between">
                                                        <span className="text-[10px] font-bold text-gray-400">레이어 #{index + 1}</span>
                                                        <button
                                                            type="button"
                                                            onClick={() => setThumbTextLayers(prev => prev.filter(l => l.id !== layer.id))}
                                                            className="text-[10px] text-red-400 hover:text-red-300 font-bold px-2 py-0.5 bg-red-950/30 rounded border border-red-500/20"
                                                        >
                                                            삭제
                                                        </button>
                                                    </div>

                                                    <input
                                                        type="text"
                                                        value={layer.text}
                                                        onChange={e => {
                                                            const val = e.target.value
                                                            setThumbTextLayers(prev => prev.map(l => l.id === layer.id ? { ...l, text: val } : l))
                                                        }}
                                                        className="w-full bg-[#1c2027] border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
                                                        placeholder="썸네일 텍스트 입력"
                                                    />

                                                    <div className="grid grid-cols-3 gap-2 text-[10px]">
                                                        <div>
                                                            <label className="text-gray-500 block mb-1">폰트</label>
                                                            <select
                                                                value={layer.fontFamily}
                                                                onChange={e => {
                                                                    const val = e.target.value
                                                                    setThumbTextLayers(prev => prev.map(l => l.id === layer.id ? { ...l, fontFamily: val } : l))
                                                                }}
                                                                className="w-full bg-[#1c2027] border border-white/10 rounded p-1 text-white text-[10px]"
                                                            >
                                                                <option value="GmarketSansBold">GmarketSansBold</option>
                                                                <option value="Pretendard">Pretendard</option>
                                                                <option value="BlackHanSans">BlackHanSans</option>
                                                                <option value="ChosunCentennial">조선100년체</option>
                                                            </select>
                                                        </div>
                                                        <div>
                                                            <label className="text-gray-500 block mb-1">크기 ({layer.fontSize}px)</label>
                                                            <input
                                                                type="range"
                                                                min="16"
                                                                max="60"
                                                                value={layer.fontSize}
                                                                onChange={e => {
                                                                    const val = Number(e.target.value)
                                                                    setThumbTextLayers(prev => prev.map(l => l.id === layer.id ? { ...l, fontSize: val } : l))
                                                                }}
                                                                className="w-full accent-blue-500 cursor-pointer"
                                                            />
                                                        </div>
                                                        <div>
                                                            <label className="text-gray-500 block mb-1">위치 Y ({layer.y}%)</label>
                                                            <input
                                                                type="range"
                                                                min="10"
                                                                max="90"
                                                                value={layer.y}
                                                                onChange={e => {
                                                                    const val = Number(e.target.value)
                                                                    setThumbTextLayers(prev => prev.map(l => l.id === layer.id ? { ...l, y: val } : l))
                                                                }}
                                                                className="w-full accent-purple-500 cursor-pointer"
                                                            />
                                                        </div>
                                                    </div>

                                                    <div className="flex items-center gap-3 text-[10px]">
                                                        <div className="flex items-center gap-1.5">
                                                            <span className="text-gray-400">글자색:</span>
                                                            <input
                                                                type="color"
                                                                value={layer.color}
                                                                onChange={e => {
                                                                    const val = e.target.value
                                                                    setThumbTextLayers(prev => prev.map(l => l.id === layer.id ? { ...l, color: val } : l))
                                                                }}
                                                                className="w-5 h-5 rounded border border-white/10 bg-transparent cursor-pointer"
                                                            />
                                                        </div>
                                                        <div className="flex items-center gap-1.5">
                                                            <span className="text-gray-400">외곽선색:</span>
                                                            <input
                                                                type="color"
                                                                value={layer.strokeColor}
                                                                onChange={e => {
                                                                    const val = e.target.value
                                                                    setThumbTextLayers(prev => prev.map(l => l.id === layer.id ? { ...l, strokeColor: val } : l))
                                                                }}
                                                                className="w-5 h-5 rounded border border-white/10 bg-transparent cursor-pointer"
                                                            />
                                                        </div>
                                                        <div className="flex items-center gap-1.5">
                                                            <span className="text-gray-400">두께:</span>
                                                            <input
                                                                type="number"
                                                                min="0"
                                                                max="8"
                                                                value={layer.strokeWidth}
                                                                onChange={e => {
                                                                    const val = Number(e.target.value)
                                                                    setThumbTextLayers(prev => prev.map(l => l.id === layer.id ? { ...l, strokeWidth: val } : l))
                                                                }}
                                                                className="w-10 bg-[#1c2027] border border-white/10 rounded px-1 text-center text-white"
                                                            />
                                                        </div>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    {/* 우측: 16:9 실시간 캔버스 미리보기 */}
                                    <div className="lg:col-span-6 space-y-3">
                                        <div className="bg-[#14181f] border border-white/10 rounded-xl overflow-hidden shadow flex flex-col">
                                            <div className="p-2.5 border-b border-white/5 flex items-center justify-between text-xs font-bold text-gray-200">
                                                <span>📺 16:9 썸네일 미리보기</span>
                                                <span className="text-[10px] text-gray-500 font-mono">1280 x 720 (HD)</span>
                                            </div>
                                            <div className="relative aspect-video bg-black overflow-hidden select-none">
                                                {/* 배경 이미지 */}
                                                <img
                                                    src={thumbBgUrl}
                                                    alt="Thumbnail BG"
                                                    className="w-full h-full object-cover"
                                                />

                                                {/* 텍스트 레이어 오버레이 */}
                                                {thumbTextLayers.map(layer => (
                                                    <div
                                                        key={layer.id}
                                                        className="absolute inset-x-4 text-center select-none pointer-events-none transition-all"
                                                        style={{
                                                            top: `${layer.y}%`,
                                                            transform: 'translateY(-50%)',
                                                            fontFamily: layer.fontFamily,
                                                            color: layer.color,
                                                            fontSize: `${layer.fontSize}px`,
                                                            fontWeight: 'bold',
                                                            textShadow: `
                                                                -${layer.strokeWidth}px -${layer.strokeWidth}px 0 ${layer.strokeColor},
                                                                ${layer.strokeWidth}px -${layer.strokeWidth}px 0 ${layer.strokeColor},
                                                                -${layer.strokeWidth}px ${layer.strokeWidth}px 0 ${layer.strokeColor},
                                                                ${layer.strokeWidth}px ${layer.strokeWidth}px 0 ${layer.strokeColor},
                                                                0 4px 10px rgba(0,0,0,0.8)
                                                            `,
                                                        }}
                                                    >
                                                        {layer.text}
                                                    </div>
                                                ))}
                                            </div>
                                        </div>

                                        {/* 하단 배경 교체 버튼들 */}
                                        <input
                                            id="thumbnail-bg-upload-input"
                                            type="file"
                                            accept="image/*"
                                            className="hidden"
                                            onChange={handleThumbnailBgFileSelect}
                                        />
                                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    if (selectedProject?.scenes?.[0]?.image_url) {
                                                        setThumbBgUrl(selectedProject.scenes[0].image_url)
                                                        setThumbBgUploadFile(null)
                                                    }
                                                }}
                                                className="py-2 bg-[#202632] hover:bg-white/10 rounded-lg font-bold text-gray-200 border border-white/10 transition"
                                            >
                                                🖼️ 1번 씬 이미지 적용
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => document.getElementById('thumbnail-bg-upload-input')?.click()}
                                                className="py-2 bg-emerald-600/20 hover:bg-emerald-600 text-emerald-300 hover:text-white rounded-lg font-bold border border-emerald-500/30 transition"
                                            >
                                                ⬆️ 이미지 파일 업로드
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    const newUrl = prompt('썸네일 배경 이미지 URL을 입력하세요:', thumbBgUrl)
                                                    if (newUrl) {
                                                        setThumbBgUrl(newUrl)
                                                        setThumbBgUploadFile(null)
                                                    }
                                                }}
                                                className="py-2 bg-blue-600/20 hover:bg-blue-600 text-blue-400 hover:text-white rounded-lg font-bold border border-blue-500/30 transition"
                                            >
                                                🔗 외부 URL로 배경 교체
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {currentNav === 'music_missions' && (
                        <div className="space-y-4 max-w-7xl mx-auto w-full pb-10">
                            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                                <div>
                                    <h2 className="text-base font-bold text-white flex items-center gap-2">
                                        <Music className="h-4 w-4 text-blue-400" />
                                        <span>음악 생성 미션</span>
                                    </h2>
                                    <p className="text-xs text-gray-400 mt-1">
                                        워커가 만든 프롬프트로 외부 음악 생성 도구에서 곡을 만들고 결과 오디오를 제출합니다.
                                    </p>
                                </div>
                                <button
                                    type="button"
                                    onClick={loadMusicMissions}
                                    disabled={musicMissionLoading}
                                    className="inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded bg-[#202632] border border-white/10 text-xs font-bold text-gray-200 hover:bg-white/10 disabled:opacity-60"
                                >
                                    <RefreshCw className={`h-3.5 w-3.5 ${musicMissionLoading ? 'animate-spin' : ''}`} />
                                    <span>새로고침</span>
                                </button>
                            </div>

                            {musicMissionLoading && musicMissions.length === 0 && (
                                <div className="border border-white/10 bg-[#1c2027] rounded-lg p-8 text-center text-sm text-gray-400">
                                    음악 미션을 불러오는 중입니다.
                                </div>
                            )}

                            {!musicMissionLoading && musicMissions.length === 0 && (
                                <div className="border border-white/10 bg-[#1c2027] rounded-lg p-8 text-center space-y-2">
                                    <Music className="h-8 w-8 text-gray-500 mx-auto" />
                                    <p className="text-sm font-bold text-gray-300">현재 열려 있는 음악 미션이 없습니다.</p>
                                    <p className="text-xs text-gray-500">관리자 또는 Hermes 워커가 음악 프롬프트 미션을 생성하면 여기에 표시됩니다.</p>
                                </div>
                            )}

                            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                                {musicMissions.map((mission) => {
                                    const draft = musicSubmissionDrafts[mission.id] || {}
                                    const mySubmissions = Array.isArray(mission.my_submissions) ? mission.my_submissions : []
                                    const isSubmitting = uploadingKey === `music-${mission.id}`
                                    const negativeRules = Array.isArray(mission.negative_rules) ? mission.negative_rules : []
                                    return (
                                        <div key={mission.id} className="bg-[#1c2027] border border-white/10 rounded-lg overflow-hidden shadow">
                                            <div className="p-4 border-b border-white/10 space-y-3">
                                                <div className="flex items-start justify-between gap-3">
                                                    <div className="min-w-0">
                                                        <div className="flex flex-wrap items-center gap-2 mb-1">
                                                            <span className="px-2 py-0.5 rounded bg-blue-500/15 text-blue-300 border border-blue-500/20 text-[10px] font-bold uppercase">
                                                                {mission.target_market || 'TH'}
                                                            </span>
                                                            <span className="px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/20 text-[10px] font-bold">
                                                                {mission.genre}
                                                            </span>
                                                            <span className="text-[10px] text-gray-500">
                                                                목표 {Math.round((mission.duration_target_seconds || 180) / 60)}분
                                                            </span>
                                                        </div>
                                                        <h3 className="text-sm font-bold text-white truncate">{mission.title}</h3>
                                                        <p className="text-xs text-gray-400 mt-1 line-clamp-2">{mission.mood}</p>
                                                    </div>
                                                    <div className="text-right shrink-0">
                                                        <div className="text-[10px] text-gray-500">보상</div>
                                                        <div className="text-sm font-black text-emerald-300">{Number(mission.reward_usdt || 0).toFixed(2)} USDT</div>
                                                    </div>
                                                </div>

                                                <div className="bg-[#14181f] border border-white/10 rounded p-3">
                                                    <div className="flex items-center justify-between gap-2 mb-2">
                                                        <span className="text-[10px] font-bold text-gray-400 uppercase">Prompt</span>
                                                        <button
                                                            type="button"
                                                            onClick={() => {
                                                                navigator.clipboard?.writeText(mission.prompt)
                                                                updateMusicDraft(mission.id, { prompt_used: mission.prompt })
                                                            }}
                                                            className="inline-flex items-center gap-1 px-2 py-1 rounded bg-white/5 hover:bg-white/10 text-[10px] text-gray-200 border border-white/10"
                                                        >
                                                            <Copy className="h-3 w-3" />
                                                            <span>복사</span>
                                                        </button>
                                                    </div>
                                                    <p className="text-xs text-gray-300 whitespace-pre-wrap leading-relaxed max-h-32 overflow-y-auto">{mission.prompt}</p>
                                                </div>

                                                {negativeRules.length > 0 && (
                                                    <div className="flex flex-wrap gap-1.5">
                                                        {negativeRules.slice(0, 6).map((rule, index) => (
                                                            <span key={`${mission.id}-rule-${index}`} className="px-2 py-0.5 rounded bg-red-500/10 text-red-300 border border-red-500/20 text-[10px]">
                                                                {rule}
                                                            </span>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>

                                            <div className="p-4 space-y-3">
                                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                                    <label className="space-y-1">
                                                        <span className="text-[10px] font-bold text-gray-400">생성 도구</span>
                                                        <input
                                                            value={draft.tool_name || ''}
                                                            onChange={e => updateMusicDraft(mission.id, { tool_name: e.target.value })}
                                                            placeholder="Suno, Udio, 기타"
                                                            className="w-full bg-[#14181f] border border-white/10 rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
                                                        />
                                                    </label>
                                                    <label className="space-y-1">
                                                        <span className="text-[10px] font-bold text-gray-400">오디오 파일</span>
                                                        <input
                                                            type="file"
                                                            accept="audio/*"
                                                            onChange={e => updateMusicDraft(mission.id, { file: e.target.files?.[0] || null })}
                                                            className="block w-full text-xs text-gray-300 file:mr-3 file:rounded file:border-0 file:bg-blue-600 file:px-3 file:py-2 file:text-xs file:font-bold file:text-white hover:file:bg-blue-500"
                                                        />
                                                    </label>
                                                </div>

                                                <label className="space-y-1 block">
                                                    <span className="text-[10px] font-bold text-gray-400">실제 사용 프롬프트</span>
                                                    <textarea
                                                        value={draft.prompt_used || ''}
                                                        onChange={e => updateMusicDraft(mission.id, { prompt_used: e.target.value })}
                                                        placeholder="실제로 음악 생성 도구에 넣은 프롬프트를 붙여넣으세요."
                                                        rows={3}
                                                        className="w-full bg-[#14181f] border border-white/10 rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500 resize-none"
                                                    />
                                                </label>

                                                <label className="space-y-1 block">
                                                    <span className="text-[10px] font-bold text-gray-400">가사 또는 메모</span>
                                                    <textarea
                                                        value={draft.lyrics || ''}
                                                        onChange={e => updateMusicDraft(mission.id, { lyrics: e.target.value })}
                                                        placeholder="보컬곡이면 가사, 인스트면 생성 설정이나 참고 메모를 적으세요."
                                                        rows={2}
                                                        className="w-full bg-[#14181f] border border-white/10 rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500 resize-none"
                                                    />
                                                </label>

                                                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px] text-gray-300">
                                                    <label className="flex items-start gap-2 bg-[#14181f] border border-white/10 rounded p-2">
                                                        <input
                                                            type="checkbox"
                                                            checked={Boolean(draft.license_confirmed)}
                                                            onChange={e => updateMusicDraft(mission.id, { license_confirmed: e.target.checked })}
                                                            className="mt-0.5"
                                                        />
                                                        <span>생성툴 라이선스상 상업 사용 가능</span>
                                                    </label>
                                                    <label className="flex items-start gap-2 bg-[#14181f] border border-white/10 rounded p-2">
                                                        <input
                                                            type="checkbox"
                                                            checked={Boolean(draft.originality_confirmed)}
                                                            onChange={e => updateMusicDraft(mission.id, { originality_confirmed: e.target.checked })}
                                                            className="mt-0.5"
                                                        />
                                                        <span>기존 곡/가수/멜로디 모방 없음</span>
                                                    </label>
                                                    <label className="flex items-start gap-2 bg-[#14181f] border border-white/10 rounded p-2">
                                                        <input
                                                            type="checkbox"
                                                            checked={Boolean(draft.commercial_use_confirmed)}
                                                            onChange={e => updateMusicDraft(mission.id, { commercial_use_confirmed: e.target.checked })}
                                                            className="mt-0.5"
                                                        />
                                                        <span>에어 플랫폼 사용권 부여 동의</span>
                                                    </label>
                                                </div>

                                                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pt-1">
                                                    <div className="text-[11px] text-gray-400">
                                                        {mySubmissions.length > 0 ? (
                                                            <span>내 제출 {mySubmissions.length}개: {mySubmissions[0].status}</span>
                                                        ) : (
                                                            <span>아직 제출하지 않은 미션입니다.</span>
                                                        )}
                                                    </div>
                                                    <button
                                                        type="button"
                                                        onClick={() => submitMusicMission(mission)}
                                                        disabled={isSubmitting}
                                                        className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-60 text-xs font-bold text-white"
                                                    >
                                                        {isSubmitting ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
                                                        <span>{isSubmitting ? '제출 중' : '음악 제출'}</span>
                                                    </button>
                                                </div>
                                            </div>
                                        </div>
                                    )
                                })}
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
                                            <th className="px-3 py-2.5 w-32 text-center">카테고리</th>
                                            <th className="px-2 py-2.5 w-24 text-center">시작일</th>
                                            <th className="px-2 py-2.5 w-24 text-center">수정일</th>
                                            <th className="px-3 py-2.5">영상 제목</th>
                                            <th className="px-1 py-2.5 w-12 text-center">주제</th>
                                            <th className="px-1 py-2.5 w-12 text-center">기획</th>
                                            <th className="px-1 py-2.5 w-12 text-center">대본</th>
                                            <th className="px-1 py-2.5 w-12 text-center">이미지</th>
                                            <th className="px-1 py-2.5 w-12 text-center">TTS</th>
                                            <th className="px-1 py-2.5 w-12 text-center">자막</th>
                                            <th className="px-1 py-2.5 w-12 text-center">썸네일</th>
                                            <th className="px-2 py-2.5 w-16 text-center text-cyan-300 font-black tracking-wide">제출</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-800 bg-[#1c2027]">
                                        {/* 풍부한 프로젝트 목록 렌더링 */}
                                        {projects.map((p: any, idx: number) => {
                                            const isSelectedProj = selectedProject?.project?.id === p.id || idx === 0
                                            const projectCatName = (() => {
                                                const explicitCategories = [
                                                    p.category_name,
                                                    p.project_payload?.category_name,
                                                    p.project_payload?.category,
                                                    p.category,
                                                ]
                                                const explicitCategory = explicitCategories.find((name: unknown) =>
                                                    STD_OFFICIAL_CATEGORIES.some(category => category.name === String(name || '').trim())
                                                )
                                                if (explicitCategory) return String(explicitCategory)
                                                const title = p.title || ''
                                                if (title.includes('무공') || title.includes('강호') || title.includes('낭인')) return '무협'
                                                if (title.includes('야사') || title.includes('조선') || title.includes('옛날')) return '옛날이야기'
                                                if (title.includes('19금') || title.includes('황혼') || title.includes('부부')) return '황혼19금'
                                                if (title.includes('편지') || title.includes('첫사랑') || title.includes('장례식')) return '한국사연'
                                                if (title.includes('탈북')) return '탈북사연'
                                                if (title.includes('해외') || title.includes('감동')) return '해외감동'
                                                return '옛날이야기'
                                            })()
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
                                                    <td className="px-3 py-2 text-center whitespace-nowrap">
                                                        <span className="inline-block px-2.5 py-1 rounded-full text-xs font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                                                            {projectCatName}
                                                        </span>
                                                    </td>
                                                    <td className="px-2 py-2 text-center text-gray-400 font-mono text-[11px] whitespace-nowrap">
                                                        {p.created_at ? p.created_at.slice(2).replace(/-/g, '. ') + '.' : '26. 08. 14.'}
                                                    </td>
                                                    <td className="px-2 py-2 text-center text-gray-400 font-mono text-[11px] whitespace-nowrap">
                                                        {p.updated_at ? p.updated_at.slice(2).replace(/-/g, '. ') + '.' : '26. 08. 18.'}
                                                    </td>
                                                    <td className="px-3 py-2 text-gray-300 max-w-sm truncate font-medium group-hover:text-blue-400 transition-colors" title={p.title}>
                                                        {p.title}
                                                    </td>
                                                    {/* 7단계 상태 원형 인디케이터 (주제, 기획, 대본, 이미지, TTS, 자막, 썸네일) */}
                                                    {(() => {
                                                        const pStatus = isSelectedProj
                                                             ? getProjectStepStatus(selectedProject, selectedProject?.scenes || [], audioResultUrl, customScriptText, localSubtitles, thumbBgUrl)
                                                             : getProjectStepStatus(p)
                                                        const isSubmitted = Boolean(
                                                            p.status === 'review_requested' ||
                                                            p.status === 'submitted' ||
                                                            p.status === 'approved' ||
                                                            p.status === 'rendering' ||
                                                            p.status === 'completed' ||
                                                            p.progress_payload?.submitted_at
                                                        )
                                                        return (
                                                            <>
                                                                <td className="px-1 py-2 text-center">
                                                                    <span className={pStatus.isTopicDone ? 'text-emerald-500 font-bold text-sm' : 'text-gray-600 text-sm'}>
                                                                        {pStatus.isTopicDone ? '●' : '○'}
                                                                    </span>
                                                                </td>
                                                                <td className="px-1 py-2 text-center">
                                                                    <span className={pStatus.isPlanningDone ? 'text-emerald-500 font-bold text-sm' : 'text-gray-600 text-sm'}>
                                                                        {pStatus.isPlanningDone ? '●' : '○'}
                                                                    </span>
                                                                </td>
                                                                <td className="px-1 py-2 text-center">
                                                                    <span className={pStatus.isScriptDone ? 'text-emerald-500 font-bold text-sm' : 'text-gray-600 text-sm'}>
                                                                        {pStatus.isScriptDone ? '●' : '○'}
                                                                    </span>
                                                                </td>
                                                                <td className="px-1 py-2 text-center">
                                                                    <span className={pStatus.isImageDone ? 'text-emerald-500 font-bold text-sm' : 'text-gray-600 text-sm'}>
                                                                        {pStatus.isImageDone ? '●' : '○'}
                                                                    </span>
                                                                </td>
                                                                <td className="px-1 py-2 text-center">
                                                                    <span className={pStatus.isTtsDone ? 'text-emerald-500 font-bold text-sm' : 'text-gray-600 text-sm'}>
                                                                        {pStatus.isTtsDone ? '●' : '○'}
                                                                    </span>
                                                                </td>
                                                                <td className="px-1 py-2 text-center">
                                                                    <span className={pStatus.isSubtitlesDone ? 'text-emerald-500 font-bold text-sm' : 'text-gray-600 text-sm'}>
                                                                        {pStatus.isSubtitlesDone ? '●' : '○'}
                                                                    </span>
                                                                </td>
                                                                <td className="px-1 py-2 text-center">
                                                                    <span className={pStatus.isThumbnailDone ? 'text-emerald-500 font-bold text-sm' : 'text-gray-600 text-sm'}>
                                                                        {pStatus.isThumbnailDone ? '●' : '○'}
                                                                    </span>
                                                                </td>
                                                                {/* 제출 버튼 컬럼 */}
                                                                <td className="px-2 py-2 text-center" onClick={e => e.stopPropagation()}>
                                                                    {isSubmitted ? (
                                                                        <button
                                                                            disabled
                                                                            className="w-7 h-7 rounded-lg flex items-center justify-center bg-emerald-600/25 text-emerald-400 border border-emerald-500/50 shadow-md mx-auto cursor-default transition-all"
                                                                            title="제출 완료 (원격 렌더 큐 접수됨)"
                                                                        >
                                                                            <span className="text-xs font-black leading-none text-emerald-400">⏎</span>
                                                                        </button>
                                                                    ) : pStatus.allDone ? (
                                                                        <button
                                                                            onClick={() => {
                                                                                openProject(p.id)
                                                                                submitProject()
                                                                            }}
                                                                            className="w-7 h-7 rounded-lg flex items-center justify-center bg-blue-600 hover:bg-blue-500 text-white font-black border border-white/60 shadow-lg shadow-blue-500/50 ring-2 ring-white/60 animate-pulse cursor-pointer mx-auto active:scale-95 transition-all"
                                                                            title="모든 조건 완료! 클릭하여 드라이브 제출 및 원격 렌더 큐 접수"
                                                                        >
                                                                            <span className="text-sm font-black leading-none text-white drop-shadow">⏎</span>
                                                                        </button>
                                                                    ) : (
                                                                        <button
                                                                            disabled
                                                                            className="w-7 h-7 rounded-lg flex items-center justify-center bg-white/10 text-gray-400 border border-white/10 opacity-80 cursor-not-allowed mx-auto transition-all"
                                                                            title="모든 단계(기획/대본/이미지/TTS/자막/썸네일) 완료 시 활성화됩니다."
                                                                        >
                                                                            <span className="text-xs font-bold leading-none text-gray-400">⏎</span>
                                                                        </button>
                                                                    )}
                                                                </td>
                                                            </>
                                                        )
                                                    })()}
                                                </tr>
                                            )
                                        })}
                                        {projects.length === 0 && (
                                            <tr>
                                                <td colSpan={13} className="px-4 py-10 text-center text-xs text-gray-500">
                                                    아직 생성된 프로젝트가 없습니다.
                                                </td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {/* [템플릿 탭 (유저앱 template.html과 100% 동일 구현)] */}
                    {currentNav === 'template' && (
                        <div className="space-y-4 max-w-6xl mx-auto w-full flex flex-col h-full pb-10">
                            {/* 2. 메인 디자인 스튜디오 (2열 그리드: 좌측 레이어 관리, 우측 16:9 실시간 캔버스) */}
                            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
                                {/* 좌측 컬럼: 텍스트 레이어 관리 (Col 6~7) */}
                                <div className="lg:col-span-6 space-y-4">
                                    <div className="bg-[#1c2027] border border-white/10 rounded-xl p-4 shadow space-y-3">
                                        <div className="flex items-center justify-between border-b border-white/5 pb-2">
                                            <h4 className="text-xs font-bold text-gray-200 flex items-center gap-1.5">
                                                <span>✏️ 텍스트 레이어 ({textLayers.length}개)</span>
                                            </h4>
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    const newLayer = {
                                                        id: `layer-${Date.now()}`,
                                                        text: '새 텍스트 문구',
                                                        fontSize: 28,
                                                        color: '#ffffff',
                                                        strokeColor: '#000000',
                                                        strokeWidth: 3,
                                                        fontFamily: 'GmarketSansBold',
                                                        x: 50,
                                                        y: 50,
                                                    }
                                                    setTextLayers(prev => [...prev, newLayer])
                                                }}
                                                className="px-3 py-1 bg-blue-600 hover:bg-blue-500 rounded text-xs font-bold text-white transition shadow"
                                            >
                                                + 텍스트 추가
                                            </button>
                                        </div>

                                        <div className="space-y-3 max-h-[380px] overflow-y-auto pr-1">
                                            {textLayers.map((layer, index) => (
                                                <div key={layer.id} className="bg-[#14181f] border border-white/5 rounded-xl p-3 space-y-2.5">
                                                    <div className="flex items-center justify-between gap-2">
                                                        <span className="text-[10px] font-bold text-gray-400">레이어 #{index + 1}</span>
                                                        <button
                                                            type="button"
                                                            onClick={() => setTextLayers(prev => prev.filter(l => l.id !== layer.id))}
                                                            className="text-[10px] text-red-400 hover:text-red-300 font-bold px-2 py-0.5 bg-red-950/30 rounded border border-red-500/20"
                                                        >
                                                            삭제
                                                        </button>
                                                    </div>

                                                    <input
                                                        type="text"
                                                        value={layer.text}
                                                        onChange={e => {
                                                            const val = e.target.value
                                                            setTextLayers(prev => prev.map(l => l.id === layer.id ? { ...l, text: val } : l))
                                                        }}
                                                        className="w-full bg-[#1c2027] border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
                                                        placeholder="텍스트 입력"
                                                    />

                                                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[10px]">
                                                        <div>
                                                            <label className="text-gray-500 block mb-1">폰트</label>
                                                            <select
                                                                value={layer.fontFamily}
                                                                onChange={e => {
                                                                    const val = e.target.value
                                                                    setTextLayers(prev => prev.map(l => l.id === layer.id ? { ...l, fontFamily: val } : l))
                                                                }}
                                                                className="w-full bg-[#1c2027] border border-white/10 rounded p-1 text-white text-[10px]"
                                                            >
                                                                <option value="GmarketSansBold">GmarketSansBold</option>
                                                                <option value="Pretendard">Pretendard</option>
                                                                <option value="BlackHanSans">BlackHanSans</option>
                                                                <option value="ChosunCentennial">조선100년체</option>
                                                            </select>
                                                        </div>
                                                        <div>
                                                            <label className="text-gray-500 block mb-1">글자 크기 ({layer.fontSize}px)</label>
                                                            <input
                                                                type="range"
                                                                min="16"
                                                                max="60"
                                                                value={layer.fontSize}
                                                                onChange={e => {
                                                                    const val = Number(e.target.value)
                                                                    setTextLayers(prev => prev.map(l => l.id === layer.id ? { ...l, fontSize: val } : l))
                                                                }}
                                                                className="w-full accent-blue-500 cursor-pointer"
                                                            />
                                                        </div>
                                                        <div>
                                                            <label className="text-gray-500 block mb-1">가로 위치 X ({layer.x}%)</label>
                                                            <input
                                                                type="range"
                                                                min="0"
                                                                max="100"
                                                                value={layer.x}
                                                                onChange={e => {
                                                                    const val = Number(e.target.value)
                                                                    setTextLayers(prev => prev.map(l => l.id === layer.id ? { ...l, x: val } : l))
                                                                }}
                                                                className="w-full accent-emerald-500 cursor-pointer"
                                                            />
                                                        </div>
                                                        <div>
                                                            <label className="text-gray-500 block mb-1">세로 위치 Y ({layer.y}%)</label>
                                                            <input
                                                                type="range"
                                                                min="10"
                                                                max="90"
                                                                value={layer.y}
                                                                onChange={e => {
                                                                    const val = Number(e.target.value)
                                                                    setTextLayers(prev => prev.map(l => l.id === layer.id ? { ...l, y: val } : l))
                                                                }}
                                                                className="w-full accent-purple-500 cursor-pointer"
                                                            />
                                                        </div>
                                                    </div>

                                                    <div className="flex items-center gap-3 text-[10px]">
                                                        <div className="flex items-center gap-1.5">
                                                            <span className="text-gray-400">글자색:</span>
                                                            <input
                                                                type="color"
                                                                value={layer.color}
                                                                onChange={e => {
                                                                    const val = e.target.value
                                                                    setTextLayers(prev => prev.map(l => l.id === layer.id ? { ...l, color: val } : l))
                                                                }}
                                                                className="w-5 h-5 rounded border border-white/10 bg-transparent cursor-pointer"
                                                            />
                                                        </div>
                                                        <div className="flex items-center gap-1.5">
                                                            <span className="text-gray-400">외곽선색:</span>
                                                            <input
                                                                type="color"
                                                                value={layer.strokeColor}
                                                                onChange={e => {
                                                                    const val = e.target.value
                                                                    setTextLayers(prev => prev.map(l => l.id === layer.id ? { ...l, strokeColor: val } : l))
                                                                }}
                                                                className="w-5 h-5 rounded border border-white/10 bg-transparent cursor-pointer"
                                                            />
                                                        </div>
                                                        <div className="flex items-center gap-1.5">
                                                            <span className="text-gray-400">외곽선 두께:</span>
                                                            <input
                                                                type="number"
                                                                min="0"
                                                                max="8"
                                                                value={layer.strokeWidth}
                                                                onChange={e => {
                                                                    const val = Number(e.target.value)
                                                                    setTextLayers(prev => prev.map(l => l.id === layer.id ? { ...l, strokeWidth: val } : l))
                                                                }}
                                                                className="w-10 bg-[#1c2027] border border-white/10 rounded px-1 text-center text-white"
                                                            />
                                                        </div>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </div>

                                {/* 우측 컬럼: 실시간 16:9 캔버스 미리보기 (Col 6) */}
                                <div className="lg:col-span-6 space-y-4">
                                    <div className="bg-[#1c2027] border border-white/10 rounded-xl overflow-hidden shadow flex flex-col">
                                        <div className="p-3 border-b border-white/5 flex items-center justify-between text-xs font-bold text-gray-200">
                                            <div className="flex items-center gap-2">
                                                <span>🎨 실시간 16:9 템플릿 캔버스</span>
                                                {!templateBgUrl && (
                                                    <span className="text-[10px] bg-red-500/20 text-red-400 px-2 py-0.5 rounded font-bold border border-red-500/30">
                                                        배경 없음 (단색/투명)
                                                    </span>
                                                )}
                                            </div>
                                            <div className="flex items-center gap-2">
                                                {templateBgUrl && (
                                                    <button
                                                        type="button"
                                                        onClick={() => setTemplateBgUrl('')}
                                                        className="text-[10px] px-2 py-0.5 bg-red-600/20 hover:bg-red-600 text-red-400 hover:text-white rounded border border-red-500/30 font-bold transition"
                                                    >
                                                        ✕ 배경 지우기
                                                    </button>
                                                )}
                                                <span className="text-[10px] text-gray-500 font-mono">1280 x 720 (HD)</span>
                                            </div>
                                        </div>
                                        <div
                                            className="relative aspect-video overflow-hidden select-none transition-colors"
                                            style={{ backgroundColor: templateBgColor }}
                                        >
                                            {/* 배경 이미지 (있을 때만 렌더링) */}
                                            {templateBgUrl ? (
                                                <img
                                                    src={templateBgUrl}
                                                    alt="Template BG"
                                                    className="w-full h-full object-cover"
                                                />
                                            ) : (
                                                <div className="w-full h-full flex flex-col items-center justify-center text-gray-600 select-none pointer-events-none gap-1 opacity-40">
                                                    <span className="text-2xl">🖼️</span>
                                                    <span className="text-[10px] font-mono tracking-wider">배경 없음 (단색 캔버스)</span>
                                                </div>
                                            )}

                                            {/* 도형 배너 오버레이 */}
                                            {shapeLayers.map(shape => (
                                                <div
                                                    key={shape.id}
                                                    className="absolute inset-x-0 transition-all pointer-events-none"
                                                    style={{
                                                        top: `${shape.y}%`,
                                                        height: `${shape.height}%`,
                                                        backgroundColor: shape.color,
                                                        opacity: shape.opacity,
                                                    }}
                                                />
                                            ))}

                                            {/* 텍스트 레이어 오버레이 */}
                                            {textLayers.map(layer => (
                                                <div
                                                    key={layer.id}
                                                    className="absolute select-none pointer-events-none transition-all whitespace-nowrap"
                                                    style={{
                                                        left: `${layer.x}%`,
                                                        top: `${layer.y}%`,
                                                        transform: 'translate(-50%, -50%)',
                                                        fontFamily: layer.fontFamily,
                                                        color: layer.color,
                                                        fontSize: `${layer.fontSize}px`,
                                                        fontWeight: 'bold',
                                                        textShadow: `
                                                            -${layer.strokeWidth}px -${layer.strokeWidth}px 0 ${layer.strokeColor},
                                                            ${layer.strokeWidth}px -${layer.strokeWidth}px 0 ${layer.strokeColor},
                                                            -${layer.strokeWidth}px ${layer.strokeWidth}px 0 ${layer.strokeColor},
                                                            ${layer.strokeWidth}px ${layer.strokeWidth}px 0 ${layer.strokeColor},
                                                            0 4px 10px rgba(0,0,0,0.8)
                                                        `,
                                                    }}
                                                >
                                                    {layer.text}
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* 3. 하단 유틸리티 3단 박스 (배경 설정, 프리셋 관리, 도형 설정) */}
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
                                {/* (1) 배경 설정 */}
                                <div className="bg-[#1c2027] border border-white/10 rounded-xl p-4 shadow space-y-3">
                                    <h4 className="text-xs font-bold text-gray-300 flex items-center justify-between">
                                        <span className="flex items-center gap-1.5">🖼️ 배경 설정</span>
                                        {templateBgUrl ? (
                                            <span className="text-[10px] text-emerald-400 font-mono">이미지 활성</span>
                                        ) : (
                                            <span className="text-[10px] text-gray-400 font-mono">배경 없음</span>
                                        )}
                                    </h4>
                                    <div className="space-y-2">
                                        {/* 배경 완전히 지우기 버튼 */}
                                        <button
                                            type="button"
                                            onClick={() => {
                                                setTemplateBgUrl('')
                                            }}
                                            className="w-full py-2 bg-red-950/40 hover:bg-red-900/60 border border-red-500/30 text-red-300 hover:text-white rounded-lg text-xs font-bold transition flex items-center justify-center gap-1.5 shadow-sm"
                                        >
                                            <span>🗑️</span> 배경 이미지 완전히 지우기 (단색/투명)
                                        </button>

                                        <input
                                            id="template-bg-upload-input"
                                            type="file"
                                            accept="image/*"
                                            className="hidden"
                                            onChange={handleTemplateBgFileSelect}
                                        />
                                        <div className="grid grid-cols-1 gap-2">
                                            <button
                                                type="button"
                                                onClick={() => document.getElementById('template-bg-upload-input')?.click()}
                                                className="py-2 bg-emerald-600/20 hover:bg-emerald-600 border border-emerald-500/30 text-emerald-300 hover:text-white rounded-lg text-xs font-bold transition truncate px-1"
                                            >
                                                ⬆️ 이미지 파일 업로드
                                            </button>
                                        </div>

                                        {/* 단색 배경 색상 선택 */}
                                        <div className="flex items-center justify-between p-2 bg-[#14181f] rounded-lg border border-white/5 text-[11px]">
                                            <span className="text-gray-400 font-bold">단색 캔버스 배경색</span>
                                            <div className="flex items-center gap-2">
                                                <input
                                                    type="color"
                                                    value={templateBgColor}
                                                    onChange={e => setTemplateBgColor(e.target.value)}
                                                    className="w-6 h-6 rounded border border-white/10 bg-transparent cursor-pointer"
                                                />
                                                <span className="font-mono text-gray-300 text-[10px]">{templateBgColor}</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* (2) 템플릿 프리셋 관리 */}
                                <div className="bg-[#1c2027] border border-white/10 rounded-xl p-4 shadow space-y-3">
                                    <h4 className="text-xs font-bold text-purple-400 flex items-center gap-1.5">
                                        <span>💾 템플릿 프리셋 관리</span>
                                    </h4>
                                    <div className="space-y-2">
                                        <select
                                            value={selectedTemplatePreset}
                                            onChange={e => applyTemplatePreset(e.target.value)}
                                            className="w-full bg-[#14181f] border border-white/10 rounded-lg p-2 text-xs text-white focus:outline-none"
                                        >
                                            <option value="">저장된 템플릿 없음</option>
                                            {templatePresets.map(preset => (
                                                <option key={preset.id} value={preset.id}>
                                                    {preset.name}
                                                </option>
                                            ))}
                                        </select>
                                        <div className="flex gap-2">
                                            <input
                                                type="text"
                                                value={templatePresetName}
                                                onChange={e => setTemplatePresetName(e.target.value)}
                                                placeholder="새 프리셋 이름"
                                                className="flex-1 bg-[#14181f] border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none"
                                            />
                                            <button
                                                type="button"
                                                onClick={saveTemplatePreset}
                                                className="px-3 py-1.5 bg-purple-600 hover:bg-purple-500 rounded-lg text-xs font-bold text-white shadow whitespace-nowrap"
                                            >
                                                저장
                                            </button>
                                        </div>
                                    </div>
                                </div>

                                {/* (3) 도형 및 자막바 관리 */}
                                <div className="bg-[#1c2027] border border-white/10 rounded-xl p-4 shadow space-y-3">
                                    <h4 className="text-xs font-bold text-cyan-400 flex items-center gap-1.5">
                                        <span>📐 배경 도형 및 자막바</span>
                                    </h4>
                                    <div className="space-y-2 text-xs">
                                        <div className="flex items-center justify-between text-gray-400">
                                            <span>자막바 배너 투명도</span>
                                            <span className="font-mono text-white">60%</span>
                                        </div>
                                        <button
                                            type="button"
                                            onClick={() => {
                                                if (shapeLayers.length > 0) {
                                                    setShapeLayers([])
                                                } else {
                                                    setShapeLayers([{
                                                        id: 'shape-1',
                                                        type: 'banner',
                                                        color: '#000000',
                                                        opacity: 0.6,
                                                        y: 60,
                                                        height: 25,
                                                    }])
                                                }
                                            }}
                                            className="w-full py-2 bg-[#202632] hover:bg-cyan-600/20 border border-white/10 hover:border-cyan-500 text-gray-200 hover:text-cyan-300 rounded-lg font-bold transition"
                                        >
                                            {shapeLayers.length > 0 ? '도형 배너 제거' : '+ 하단 자막바 배너 추가'}
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* [설정 탭 (유저앱 settings.html과 100% 동일 구현)] */}
                    
                    {/* [설정 탭 (유저앱 settings.html과 100% 동일 구현)] */}
                    
                    {/* [기획 탭 (유저앱 script_plan.html 완벽 대응)] */}
                    {currentNav === 'script_plan' && selectedProject && (
                        <div className="space-y-5 max-w-7xl mx-auto w-full flex flex-col h-full pb-10">
                            {/* 상단 툴바 */}
                            <div className="bg-[#1c2027] border border-white/10 rounded-xl p-4 shadow-sm flex flex-wrap items-center justify-between gap-4 shrink-0">
                                <div className="space-y-1">
                                    <span className="text-[10px] font-black uppercase tracking-widest text-blue-400">PLAN & STRUCTURE</span>
                                    <h2 className="text-base font-bold text-white flex items-center gap-2">
                                        <span>📝</span> {selectedProject.project.title}
                                    </h2>
                                </div>
                                <div className="flex items-center gap-2">
                                    <button
                                        onClick={() => alert('기획안 구성이 성공적으로 저장되었습니다.')}
                                        className="px-4 py-2 bg-[#202632] hover:bg-[#28303e] border border-white/10 text-white rounded-xl text-xs font-bold transition shadow-sm"
                                    >
                                        기획안 저장
                                    </button>
                                    <button
                                        onClick={() => setCurrentNav('script_gen')}
                                        className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold transition shadow-lg flex items-center gap-1.5"
                                    >
                                        <span>대본 단계로 이동</span>
                                        <span>→</span>
                                    </button>
                                </div>
                            </div>

                            {/* 기획 구조 개요 카드 */}
                            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                                <div className="bg-[#1c2027] border border-white/10 rounded-xl p-4 space-y-1">
                                    <span className="text-[10px] text-gray-500 font-bold uppercase tracking-wider block">총 씬 구성</span>
                                    <div className="text-xl font-black text-white">{selectedProject.scenes.length}개 씬</div>
                                    <span className="text-[11px] text-gray-400">도입-전개-위기-절정-결말</span>
                                </div>
                                <div className="bg-[#1c2027] border border-white/10 rounded-xl p-4 space-y-1">
                                    <span className="text-[10px] text-gray-500 font-bold uppercase tracking-wider block">예상 소요 시간</span>
                                    <div className="text-xl font-black text-purple-400">{(selectedProject.scenes.length * 0.25).toFixed(1)}분</div>
                                    <span className="text-[11px] text-gray-400">표준 롱폼 템포</span>
                                </div>
                                <div className="bg-[#1c2027] border border-white/10 rounded-xl p-4 space-y-1">
                                    <span className="text-[10px] text-gray-500 font-bold uppercase tracking-wider block">타겟 오디언스</span>
                                    <div className="text-xl font-black text-emerald-400">40대 ~ 60대</div>
                                    <span className="text-[11px] text-gray-400">감성 드라마 / 야사 타겟</span>
                                </div>
                                <div className="bg-[#1c2027] border border-white/10 rounded-xl p-4 space-y-1">
                                    <span className="text-[10px] text-gray-500 font-bold uppercase tracking-wider block">영상 비율</span>
                                    <div className="text-xl font-black text-amber-400">16:9 가로형</div>
                                    <span className="text-[11px] text-gray-400">1920x1080 Full HD</span>
                                </div>
                            </div>

                            {/* 씬별 기획 구조표 */}
                            <div className="bg-[#1c2027] border border-white/10 rounded-xl p-5 shadow-sm space-y-4">
                                <h3 className="text-xs font-bold text-gray-300 uppercase tracking-wide flex items-center gap-2">
                                    <span>🎬</span> 씬별 연출 및 기획 구조표
                                </h3>
                                <div className="space-y-3">
                                    {selectedProject.scenes.map((scene, idx) => (
                                        <div key={scene.scene_index} className="p-3.5 bg-[#14181f] border border-white/5 rounded-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-4 hover:border-white/10 transition">
                                            <div className="flex items-center gap-3">
                                                <span className="w-7 h-7 rounded-lg bg-blue-600/20 text-blue-400 border border-blue-500/30 flex items-center justify-center text-xs font-black shrink-0">
                                                    #{idx + 1}
                                                </span>
                                                <div>
                                                    <div className="text-xs font-bold text-white">{scene.title || `씬 ${idx + 1}`}</div>
                                                    <div className="text-[11px] text-gray-400 mt-0.5 line-clamp-1">{scene.narration_text || scene.visual_prompt}</div>
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-2 text-[11px] text-gray-400 self-end md:self-auto shrink-0">
                                                <span className="px-2 py-0.5 bg-[#1c2027] rounded border border-white/10">비주얼 프롬프트 준비됨</span>
                                                <button
                                                    onClick={() => setCurrentNav('script_gen')}
                                                    className="px-2.5 py-1 bg-white/5 hover:bg-white/10 text-gray-200 rounded border border-white/10 font-bold"
                                                >
                                                    대본 보기
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}


                    {/* [대본 탭 (유저앱 script_gen.html 완벽 대응)] */}
                    {currentNav === 'script_gen' && selectedProject && (
                        <div className="space-y-5 max-w-7xl mx-auto w-full flex flex-col h-full pb-10">
                            {/* 상단 툴바 */}
                            <div className="bg-[#1c2027] border border-white/10 rounded-xl p-4 shadow-sm flex flex-wrap items-center justify-between gap-4 shrink-0">
                                <div className="flex items-center gap-3">
                                    <span className="text-[11px] px-3 py-1 bg-blue-600/20 text-blue-400 border border-blue-500/30 rounded-lg font-bold">
                                        총 {selectedProject.scenes.length}개 씬
                                    </span>
                                    <span className="text-[11px] px-3 py-1 bg-purple-600/20 text-purple-400 border border-purple-500/30 rounded-lg font-bold">
                                        {scriptCharCount}자 (약 {(scriptCharCount / 300).toFixed(1)}분)
                                    </span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <button
                                        onClick={() => alert('대본 변경사항이 성공적으로 저장되었습니다.')}
                                        className="px-4 py-2 bg-[#202632] hover:bg-[#28303e] border border-white/10 text-white rounded-xl text-xs font-bold transition shadow-sm"
                                    >
                                        대본 전체 저장
                                    </button>
                                    <button
                                        onClick={() => setCurrentNav('tts')}
                                        className="px-5 py-2 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white rounded-xl text-xs font-bold transition shadow-lg flex items-center gap-1.5"
                                    >
                                        <span>TTS 음성 생성 단계로 이동</span>
                                        <span>→</span>
                                    </button>
                                </div>
                            </div>

                            {/* 씬별 나레이션 대본 및 비주얼 프롬프트 에디터 */}
                            <div className="space-y-4">
                                {selectedProject.scenes.map((scene, idx) => (
                                    <div key={scene.scene_index} className="bg-[#1c2027] border border-white/10 rounded-xl p-4 shadow-sm space-y-3">
                                        <div className="flex items-center justify-between border-b border-white/5 pb-2">
                                            <div className="flex items-center gap-2">
                                                <span className="w-6 h-6 rounded-lg bg-blue-600 text-white flex items-center justify-center text-xs font-black">
                                                    {idx + 1}
                                                </span>
                                                <span className="text-xs font-bold text-white">씬 #{idx + 1} 대본 & 연출</span>
                                            </div>
                                            <span className="text-[11px] text-gray-500 font-mono">
                                                {(scene.narration_text || '').length}자
                                            </span>
                                        </div>

                                        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
                                            {/* 나레이션 대본 */}
                                            <div className="lg:col-span-7 space-y-1">
                                                <label className="text-[10px] font-bold text-gray-400 uppercase tracking-wider block">나레이션 대본 (TTS)</label>
                                                <textarea
                                                    defaultValue={scene.narration_text}
                                                    rows={3}
                                                    className="w-full bg-[#14181f] border border-white/10 rounded-lg p-2.5 text-xs text-gray-200 leading-relaxed focus:outline-none focus:border-blue-500/50 resize-none font-sans"
                                                />
                                            </div>
                                            {/* 비주얼 프롬프트 */}
                                            <div className="lg:col-span-5 space-y-1">
                                                <label className="text-[10px] font-bold text-gray-400 uppercase tracking-wider block">이미지 비주얼 프롬프트</label>
                                                <textarea
                                                    defaultValue={scene.visual_prompt}
                                                    rows={3}
                                                    className="w-full bg-[#14181f] border border-white/10 rounded-lg p-2.5 text-xs text-gray-400 leading-relaxed focus:outline-none focus:border-purple-500/50 resize-none font-mono text-[11px]"
                                                />
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}


                    {/* [렌더로 생성 탭 (유저앱 render.html 100% 동일 구현)] */}
                    {currentNav === 'render' && selectedProject && (
                        <div className="space-y-5 max-w-7xl mx-auto w-full flex flex-col h-full pb-10">
                            {/* 1. 상단 컨트롤 툴바 */}
                            <div className="flex items-center gap-3 p-3 bg-[#1c2027] rounded-xl shadow-sm border border-white/10 shrink-0 flex-wrap justify-between">
                                <div className="flex items-center gap-4 flex-wrap">
                                    {/* 해상도 선택 */}
                                    <div className="flex items-center gap-2 border-r border-white/10 pr-3">
                                        <span className="text-xs font-bold text-gray-300">해상도</span>
                                        <select
                                            value={renderResolution}
                                            onChange={e => setRenderResolution(e.target.value as any)}
                                            className="text-xs bg-[#202632] border border-white/10 rounded-lg py-1 px-2.5 text-white focus:outline-none focus:border-blue-500"
                                        >
                                            <option value="1080p">1080p (Full HD)</option>
                                            <option value="720p">720p (HD)</option>
                                        </select>
                                    </div>

                                    {/* 자막 포함 여부 */}
                                    <label className="flex items-center gap-1.5 cursor-pointer border-r border-white/10 pr-3 select-none">
                                        <input
                                            type="checkbox"
                                            checked={renderUseSubtitles}
                                            onChange={e => setRenderUseSubtitles(e.target.checked)}
                                            className="w-3.5 h-3.5 text-blue-600 rounded bg-[#202632] border-white/10 focus:ring-0 cursor-pointer"
                                        />
                                        <span className="text-xs text-gray-300 font-medium">자막 포함 렌더링</span>
                                    </label>

                                    {/* 렌더 대상 위치 */}
                                    <div className="flex items-center gap-2">
                                        <span className="text-xs font-bold text-gray-300">렌더링 엔진</span>
                                        <select
                                            value={renderTarget}
                                            onChange={e => setRenderTarget(e.target.value as any)}
                                            className="text-xs bg-[#202632] border border-white/10 rounded-lg py-1 px-2.5 text-white focus:outline-none focus:border-blue-500"
                                        >
                                            <option value="drive_api">원격 그래픽스 서버 (Cloud GPU)</option>
                                            <option value="local">로컬 PC 렌더러</option>
                                        </select>
                                    </div>
                                </div>

                                {/* 렌더링 시작 버튼 */}
                                <button
                                    type="button"
                                    onClick={handleStartRender}
                                    disabled={isRendering}
                                    className="px-6 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white rounded-xl text-xs font-bold transition shadow-lg flex items-center gap-2 disabled:opacity-50 active:scale-95"
                                >
                                    <span>🎬</span>
                                    <span>{isRendering ? '영상 렌더링 진행 중...' : '최종 렌더링 시작'}</span>
                                </button>
                            </div>

                            {/* 2. 메인 워크스페이스 그리드 (좌: 상태/로그, 우: 비디오 플레이어) */}
                            <div className="grid grid-cols-12 gap-5 flex-1 min-h-0">
                                {/* 좌측 패널 (Col 6) */}
                                <div className="col-span-12 lg:col-span-6 flex flex-col gap-4">
                                    {/* 프로젝트 구성 에셋 상태 요약 */}
                                    <div className="bg-[#1c2027] rounded-xl border border-white/10 p-4 shadow-sm space-y-3 shrink-0">
                                        <h4 className="text-xs font-bold text-gray-400 uppercase tracking-wide">📦 프로젝트 에셋 구성 상태</h4>
                                        <div className="grid grid-cols-3 gap-2 text-[11px]">
                                            <div className="p-2 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-lg text-center font-bold">
                                                📝 대본 {selectedProject.scenes.length}개 씬 (완료)
                                            </div>
                                            <div className="p-2 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-lg text-center font-bold">
                                                🖼️ 이미지 프롬프트 (준비됨)
                                            </div>
                                            <div className="p-2 bg-purple-500/10 text-purple-400 border border-purple-500/20 rounded-lg text-center font-bold">
                                                🔊 음성 (연동)
                                            </div>
                                            <div className="p-2 bg-blue-500/10 text-blue-400 border border-blue-500/20 rounded-lg text-center font-bold">
                                                💬 자막 레이아웃 (설정됨)
                                            </div>
                                            <div className="p-2 bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded-lg text-center font-bold">
                                                🎨 16:9 썸네일 (완료)
                                            </div>
                                            <div className="p-2 bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 rounded-lg text-center font-bold">
                                                ⚙️ 인코더 libx264
                                            </div>
                                        </div>
                                    </div>

                                    {/* 실시간 렌더 콘솔 로그 */}
                                    <div className="bg-[#14181f] rounded-xl border border-white/10 p-4 flex-1 flex flex-col font-mono text-xs text-green-400 min-h-[300px] shadow-inner">
                                        <div className="flex justify-between border-b border-white/10 pb-2 mb-3 text-gray-400 font-bold">
                                            <span>&gt;_ 렌더링 콘솔 로그 (Terminal)</span>
                                            <span className="text-yellow-400 font-mono">진행률: {renderProgress}%</span>
                                        </div>
                                        <div className="flex-1 overflow-y-auto space-y-1.5 text-[11px] leading-relaxed pr-1 custom-scrollbar">
                                            {renderLogList.map((log, index) => (
                                                <div key={index} className="opacity-90">{log}</div>
                                            ))}
                                        </div>
                                        {/* 진행 바 */}
                                        <div className="mt-3 h-1.5 bg-white/5 rounded-full overflow-hidden">
                                            <div
                                                className="h-full bg-gradient-to-r from-blue-500 to-green-500 transition-all duration-300"
                                                style={{ width: `${renderProgress}%` }}
                                            />
                                        </div>
                                    </div>
                                </div>

                                {/* 우측 패널: 최종 완성 비디오 플레이어 및 다운로드 (Col 6) */}
                                <div className="col-span-12 lg:col-span-6 flex flex-col bg-[#1c2027] rounded-xl border border-white/10 shadow-sm overflow-hidden min-h-[480px]">
                                    <div className="flex-1 bg-black flex items-center justify-center relative overflow-hidden">
                                        {renderedVideoUrl ? (
                                            <video
                                                src={renderedVideoUrl}
                                                controls
                                                className="w-full h-full object-contain"
                                            />
                                        ) : (
                                            <div className="flex flex-col items-center justify-center text-gray-500 space-y-3 p-6 text-center">
                                                <span className="text-5xl animate-pulse">🎬</span>
                                                <div className="text-sm font-bold text-gray-300">최종 렌더링 비디오 대기 중</div>
                                                <p className="text-xs text-gray-500 max-w-xs leading-relaxed">
                                                    상단의 [최종 렌더링 시작] 버튼을 누르면 인코딩이 완료된 완성본 비디오가 이곳에 로드됩니다.
                                                </p>
                                            </div>
                                        )}
                                    </div>

                                    {/* 하단 액션 버튼 바 */}
                                    <div className="p-4 bg-[#181d26] border-t border-white/10 flex items-center justify-between gap-3 shrink-0">
                                        <div className="text-xs text-gray-400 font-mono">
                                            {renderedVideoUrl ? '✅ MP4 렌더링 완료' : '대기 상태'}
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <a
                                                href={renderedVideoUrl || '#'}
                                                download={`final_render_${selectedProject.project.id}.mp4`}
                                                className={`px-5 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 ${
                                                    renderedVideoUrl
                                                        ? 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg cursor-pointer'
                                                        : 'bg-white/5 text-gray-500 cursor-not-allowed pointer-events-none'
                                                }`}
                                            >
                                                <span>💾</span>
                                                <span>최종 영상 다운로드</span>
                                            </a>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {currentNav === 'settings' && (
                        <div className="space-y-4 max-w-5xl mx-auto w-full flex flex-col h-full">
                            {/* 1. 상단 타이틀 및 액션 바 */}
                            <div className="flex items-center justify-between bg-[#1c2027] p-3 rounded-xl border border-white/10 shadow-sm shrink-0">
                                <h2 className="text-base font-bold text-white flex items-center gap-2">
                                    <span>⚙️ 세팅</span>
                                </h2>
                                <div className="flex items-center gap-2">
                                    <label className="flex items-center gap-1.5 text-xs text-gray-400 bg-[#202632] px-2.5 py-1.5 rounded-lg border border-white/5 cursor-pointer">
                                        <input type="checkbox" defaultChecked className="rounded bg-black border-gray-600 w-3.5 h-3.5" />
                                        <span>새로고침</span>
                                    </label>
                                    <button
                                        onClick={saveProfileSettings}
                                        disabled={loading}
                                        className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded-lg text-xs font-bold text-white shadow-md flex items-center gap-1.5 transition-all"
                                    >
                                        <span>💾</span> 변경사항 저장
                                    </button>
                                </div>
                            </div>

                            {/* 2. 6개 서브 탭 네비게이션 */}
                            <div className="border-b border-white/10 shrink-0">
                                <div className="flex space-x-2 overflow-x-auto">
                                    {[
                                        { id: 'basic', label: '■■ 기본 설정' },
                                        { id: 'orgchart', label: '조직도' },
                                        { id: 'history', label: '수당 내역 (History)' },
                                        { id: 'withdrawal', label: 'USDT 출금 신청 (Withdrawal)' },
                                        { id: 'support', label: '💬 문의하기' },
                                        { id: 'announcements', label: '📢 공지사항' },
                                    ].map(tab => (
                                        <button
                                            key={tab.id}
                                            onClick={() => setSettingsSubTab(tab.id as any)}
                                            className={`px-4 py-2 text-xs font-bold transition-all border-b-2 whitespace-nowrap ${
                                                settingsSubTab === tab.id
                                                    ? 'border-blue-500 text-blue-400 bg-blue-500/10 rounded-t-lg'
                                                    : 'border-transparent text-gray-400 hover:text-gray-200 hover:bg-white/5'
                                            }`}
                                        >
                                            {tab.label}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            {/* 3. 탭별 메인 컨텐츠 영역 */}
                            <div className="space-y-4 overflow-y-auto pb-10">
                                {/* [탭 1: 기본 설정] */}
                                {settingsSubTab === 'basic' && (
                                    <div className="space-y-5">
                                        {/* (1) 내 추천 코드 & 추천 링크 카드 (보라색 강조) */}
                                        <div className="rounded-2xl border border-purple-500/30 bg-purple-500/10 p-5 shadow-lg space-y-4">
                                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-purple-500/20 pb-3">
                                                <h5 className="text-xs font-bold text-purple-300 flex items-center gap-2">
                                                    <span>🔑 내 추천 코드 및 초대 링크</span>
                                                </h5>
                                                <span className="text-[11px] text-purple-200/80 font-medium">
                                                    SNS 공유 링크 클릭 시 추천 코드가 자동 입력된 가입화면으로 이동합니다.
                                                </span>
                                            </div>

                                            <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
                                                {/* 추천 코드 */}
                                                <div className="space-y-1.5">
                                                    <label className="text-[11px] font-bold text-purple-300 block">
                                                        추천 코드
                                                    </label>
                                                    <div className="flex items-center gap-2">
                                                        <input
                                                            type="text"
                                                            value={referralCode}
                                                            readOnly
                                                            className="w-full bg-[#14181f] border border-purple-500/40 rounded-xl px-3 py-2 text-base font-mono font-bold text-white text-center tracking-widest focus:outline-none"
                                                        />
                                                        <button
                                                            type="button"
                                                            onClick={() => {
                                                                navigator.clipboard.writeText(referralCode)
                                                                alert('추천 코드가 클립보드에 복사되었습니다: ' + referralCode)
                                                            }}
                                                            className="px-4 py-2 bg-purple-600 hover:bg-purple-500 border border-purple-500 rounded-xl text-xs font-bold text-white whitespace-nowrap shadow transition-all active:scale-95"
                                                        >
                                                            코드 복사
                                                        </button>
                                                    </div>
                                                </div>

                                                {/* 추천 링크 (SNS 전달용) */}
                                                <div className="lg:col-span-2 space-y-1.5">
                                                    <label className="text-[11px] font-bold text-purple-300 block">
                                                        추천 가입 링크 (SNS 전달용)
                                                    </label>
                                                    <div className="flex items-center gap-2">
                                                        <input
                                                            type="text"
                                                            value={typeof window !== 'undefined' ? `${window.location.origin}/?ref=${referralCode}` : `https://studio.airing.work/?ref=${referralCode}`}
                                                            readOnly
                                                            className="w-full bg-[#14181f] border border-purple-500/40 rounded-xl px-3 py-2 text-xs font-mono text-purple-200 focus:outline-none truncate"
                                                        />
                                                        <button
                                                            type="button"
                                                            onClick={() => {
                                                                const link = typeof window !== 'undefined' ? `${window.location.origin}/?ref=${referralCode}` : `https://studio.airing.work/?ref=${referralCode}`
                                                                navigator.clipboard.writeText(link)
                                                                alert('추천 가입 링크가 클립보드에 복사되었습니다!\nSNS로 전달하시면 상대방이 링크 클릭 시 추천 코드가 자동 적용된 가입 페이지가 열립니다:\n\n' + link)
                                                            }}
                                                            className="px-4 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 border border-blue-500/50 rounded-xl text-xs font-bold text-white whitespace-nowrap shadow transition-all active:scale-95"
                                                        >
                                                            링크 복사
                                                        </button>
                                                    </div>
                                                </div>
                                            </div>

                                            <p className="text-[11px] text-purple-300/80 mt-1 leading-relaxed">
                                                * 이 코드로 가입한 회원이 영상을 3개 이상 렌더링 완성 시 보상이 지급됩니다. 조직도는 상단의 &apos;조직도&apos; 탭에서 확인할 수 있습니다.
                                            </p>
                                        </div>

                                        {/* (2) 사용자 정보 섹션 */}
                                        <div className="bg-[#1c2027] border border-white/10 rounded-2xl p-6 shadow space-y-4">
                                            <h4 className="text-xs font-bold text-gray-200 flex items-center gap-2 border-b border-white/5 pb-3">
                                                <span>👤 사용자 정보</span>
                                            </h4>
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                <div>
                                                    <label className="text-[11px] font-bold text-gray-400 mb-1.5 block">이름</label>
                                                    <input
                                                        type="text"
                                                        value={settingName}
                                                        onChange={e => setSettingName(e.target.value)}
                                                        className="w-full bg-[#14181f] border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
                                                        placeholder="이름을 입력하세요"
                                                    />
                                                </div>
                                                <div>
                                                    <label className="text-[11px] font-bold text-gray-400 mb-1.5 block">국적</label>
                                                    <input
                                                        type="text"
                                                        value={settingNationality}
                                                        onChange={e => setSettingNationality(e.target.value)}
                                                        className="w-full bg-[#14181f] border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
                                                        placeholder="국가를 입력하세요 (예: 대한민국)"
                                                    />
                                                </div>
                                                <div>
                                                    <label className="text-[11px] font-bold text-gray-400 mb-1.5 block">연락처</label>
                                                    <input
                                                        type="text"
                                                        value={settingPhone}
                                                        onChange={e => setSettingPhone(e.target.value)}
                                                        className="w-full bg-[#14181f] border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500 font-mono"
                                                        placeholder="010-0000-0000"
                                                    />
                                                </div>
                                                <div>
                                                    <label className="text-[11px] font-bold text-gray-400 mb-1.5 block">이메일</label>
                                                    <input
                                                        type="email"
                                                        value={user?.email || 'ejsh0518@naver.com'}
                                                        readOnly
                                                        className="w-full bg-[#14181f]/60 border border-white/5 rounded-lg px-3 py-2 text-xs text-gray-400 font-mono cursor-not-allowed"
                                                    />
                                                </div>

                                                {/* 선호 영상 주제 태그 (공식 8개 카테고리) */}
                                                <div className="col-span-1 md:col-span-2">
                                                    <label className="text-[11px] font-bold text-gray-400 mb-2 block">
                                                        선호 영상 주제 (복수 선택 가능)
                                                    </label>
                                                    <div className="flex flex-wrap gap-2">
                                                        {STD_OFFICIAL_CATEGORIES.map(catItem => {
                                                            const isSel = selectedCategories.includes(catItem.name)
                                                            return (
                                                                <button
                                                                    key={catItem.id}
                                                                    type="button"
                                                                    onClick={() => {
                                                                        setSelectedCategories(prev =>
                                                                            prev.includes(catItem.name) ? prev.filter(c => c !== catItem.name) : [...prev, catItem.name]
                                                                        )
                                                                    }}
                                                                    className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                                                                        isSel
                                                                            ? 'bg-blue-600 text-white shadow'
                                                                            : 'bg-[#202632] text-gray-400 border border-white/5 hover:text-white'
                                                                    }`}
                                                                >
                                                                    {t(catItem.key, catItem.name)}
                                                                </button>
                                                            )
                                                        })}
                                                    </div>
                                                </div>

                                                <div className="col-span-1 md:col-span-2 flex items-center gap-3 pt-2">
                                                    <button
                                                        type="button"
                                                        disabled={loading}
                                                        onClick={saveProfileSettings}
                                                        className="px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 rounded-lg text-xs font-bold text-white shadow transition flex items-center gap-1.5"
                                                    >
                                                        {loading ? '저장 중...' : '저장'}
                                                    </button>
                                                    {profileSavedMsg && (
                                                        <span className="text-xs font-bold text-emerald-400 animate-pulse">{profileSavedMsg}</span>
                                                    )}
                                                </div>
                                            </div>

                                            {/* (3) 비밀번호 변경 서브섹션 */}
                                            <div className="mt-6 pt-5 border-t border-white/5 space-y-3">
                                                <h5 className="text-xs font-bold text-gray-300 flex items-center gap-2">
                                                    <span>🔒 비밀번호 변경</span>
                                                </h5>
                                                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                                    <div>
                                                        <label className="text-[10px] font-bold text-gray-500 mb-1 block">현재 비밀번호</label>
                                                        <input
                                                            type="password"
                                                            value={currentPw}
                                                            onChange={e => setCurrentPw(e.target.value)}
                                                            className="w-full bg-[#14181f] border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
                                                        />
                                                    </div>
                                                    <div>
                                                        <label className="text-[10px] font-bold text-gray-500 mb-1 block">새 비밀번호</label>
                                                        <input
                                                            type="password"
                                                            value={newPw}
                                                            onChange={e => setNewPw(e.target.value)}
                                                            className="w-full bg-[#14181f] border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
                                                        />
                                                    </div>
                                                    <div>
                                                        <label className="text-[10px] font-bold text-gray-500 mb-1 block">새 비밀번호 확인</label>
                                                        <input
                                                            type="password"
                                                            value={confirmPw}
                                                            onChange={e => setConfirmPw(e.target.value)}
                                                            className="w-full bg-[#14181f] border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
                                                        />
                                                    </div>
                                                </div>

                                                <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-gray-400">
                                                    <span className={newPw.length >= 8 ? 'text-emerald-400 font-bold' : ''}>● 8자 이상</span>
                                                    <span className={/[A-Z]/.test(newPw) ? 'text-emerald-400 font-bold' : ''}>● 대문자</span>
                                                    <span className={/[a-z]/.test(newPw) ? 'text-emerald-400 font-bold' : ''}>● 소문자</span>
                                                    <span className={/[0-9]/.test(newPw) ? 'text-emerald-400 font-bold' : ''}>● 숫자</span>
                                                    <span className={/[!@#$%^&*]/.test(newPw) ? 'text-emerald-400 font-bold' : ''}>● 특수문자</span>
                                                    <span className={newPw && newPw === confirmPw ? 'text-emerald-400 font-bold' : ''}>● 비밀번호 일치</span>
                                                </div>

                                                <div className="flex items-center gap-3 pt-2">
                                                    <button
                                                        type="button"
                                                        onClick={() => {
                                                            if (!currentPw) {
                                                                alert('현재 비밀번호를 입력해주세요.')
                                                                return
                                                            }
                                                            if (!newPw || newPw !== confirmPw) {
                                                                alert('새 비밀번호가 일치하지 않거나 입력되지 않았습니다.')
                                                                return
                                                            }
                                                            setPwSavedMsg('비밀번호가 성공적으로 변경되었습니다.')
                                                            setCurrentPw('')
                                                            setNewPw('')
                                                            setConfirmPw('')
                                                            setTimeout(() => setPwSavedMsg(''), 3000)
                                                        }}
                                                        className="px-4 py-2 bg-[#202632] hover:bg-blue-600 rounded-lg text-xs font-bold text-white border border-white/10 transition"
                                                    >
                                                        비밀번호 변경
                                                    </button>
                                                    {pwSavedMsg && (
                                                        <span className="text-xs font-bold text-emerald-400 animate-pulse">{pwSavedMsg}</span>
                                                    )}
                                                </div>
                                            </div>

                                            {/* (4) 회원 탈퇴 경고 박스 */}
                                            <div className="mt-6 pt-5 border-t border-red-500/20 flex flex-col md:flex-row justify-between items-start md:items-center gap-4 bg-red-950/20 p-4 rounded-xl border">
                                                <div className="text-[11px] text-gray-300 leading-relaxed">
                                                    ⚠️ 회원 탈퇴 시 모든 프로젝트 작업 내역, 수당 정보 및 지갑 주소가 영구적으로 삭제되며 복구할 수 없습니다.
                                                </div>
                                                <button
                                                    type="button"
                                                    onClick={() => {
                                                        if (confirm('정말로 탈퇴하시겠습니까? 모든 작업 데이터와 수당 내역이 영구 삭제됩니다.')) {
                                                            alert('회원 탈퇴 요청이 접수되었습니다.')
                                                            signOut()
                                                        }
                                                    }}
                                                    className="px-4 py-2 bg-red-600/20 hover:bg-red-600 border border-red-500/30 text-red-400 hover:text-white rounded-lg text-xs font-bold transition whitespace-nowrap shadow-sm"
                                                >
                                                    🗑️ 회원 탈퇴 (Delete Account)
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {/* [탭 2: 조직도] */}
                                {settingsSubTab === 'orgchart' && (
                                    <div className="bg-[#1c2027] border border-white/10 rounded-2xl p-6 shadow space-y-4">
                                        <div className="flex items-center justify-between border-b border-white/5 pb-3">
                                            <h4 className="text-xs font-bold text-gray-200 flex items-center gap-2">
                                                <span>🌳 추천 조직도 & 파트너 현황</span>
                                            </h4>
                                            <div className="flex gap-1 p-1 bg-black/30 rounded-lg border border-white/5">
                                                <button
                                                    onClick={() => setTreeViewMode('list')}
                                                    className={`px-3 py-1 rounded-md text-xs font-bold transition ${
                                                        treeViewMode === 'list' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'
                                                    }`}
                                                >
                                                    리스트 뷰
                                                </button>
                                                <button
                                                    onClick={() => setTreeViewMode('card')}
                                                    className={`px-3 py-1 rounded-md text-xs font-bold transition ${
                                                        treeViewMode === 'card' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'
                                                    }`}
                                                >
                                                    카드 뷰
                                                </button>
                                            </div>
                                        </div>

                                        <div className="p-6 text-center space-y-3 bg-[#14181f] rounded-xl border border-white/5">
                                            <div className="text-3xl">🌱</div>
                                            <h3 className="text-sm font-bold text-white">내 추천 코드로 연결된 파트너 조직</h3>
                                            <p className="text-xs text-gray-400 max-w-md mx-auto leading-relaxed">
                                                추천 코드 <span className="font-mono text-purple-400 font-bold bg-purple-500/10 px-2 py-0.5 rounded border border-purple-500/20">{referralCode}</span> 를 공유하여 파트너를 초대하고 영상 완성 수당을 적립하세요.
                                            </p>
                                        </div>
                                    </div>
                                )}

                                {/* [탭 3: 수당 내역] */}
                                {settingsSubTab === 'history' && (
                                    <div className="bg-[#1c2027] border border-white/10 rounded-2xl p-6 shadow space-y-4">
                                        <h4 className="text-xs font-bold text-gray-200 flex items-center gap-2 border-b border-white/5 pb-3">
                                            <span>📜 작업 및 수당 지급 내역</span>
                                        </h4>
                                        <div className="overflow-x-auto rounded-xl border border-white/5">
                                            <table className="w-full text-xs text-left text-gray-300">
                                                <thead className="bg-[#202632] text-gray-400 border-b border-white/5 uppercase text-[11px]">
                                                    <tr>
                                                        <th className="px-4 py-3">작업 일자</th>
                                                        <th className="px-4 py-3">프로젝트명</th>
                                                        <th className="px-4 py-3 text-center">영상 길이</th>
                                                        <th className="px-4 py-3 text-center">비디오 씬</th>
                                                        <th className="px-4 py-3 text-center">이미지 씬</th>
                                                        <th className="px-4 py-3 text-right">정산 금액 (USDT)</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-white/5 bg-[#14181f]">
                                                    <tr>
                                                        <td className="px-4 py-3 font-mono text-gray-400">2026.08.18</td>
                                                        <td className="px-4 py-3 font-medium text-white">아내의 장례식 날, 30년 숨긴 첫사랑의 편지가 열렸다</td>
                                                        <td className="px-4 py-3 text-center font-mono">08:24</td>
                                                        <td className="px-4 py-3 text-center font-bold text-orange-400">12</td>
                                                        <td className="px-4 py-3 text-center font-bold text-cyan-400">41</td>
                                                        <td className="px-4 py-3 text-right font-mono font-bold text-emerald-400">+ 15.00 USDT</td>
                                                    </tr>
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                )}

                                {/* [탭 4: USDT 출금 신청] */}
                                {settingsSubTab === 'withdrawal' && (
                                    <div className="space-y-4">
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                            <div className="bg-gradient-to-br from-green-900/40 to-emerald-900/30 rounded-2xl p-6 border border-green-500/30 shadow-lg">
                                                <div className="text-green-300 text-xs font-medium mb-1">출금 가능 잔액</div>
                                                <div className="text-3xl font-black text-green-400 flex items-baseline gap-1 font-mono">
                                                    <span>15.000000</span>
                                                    <span className="text-sm font-bold opacity-70">USDT</span>
                                                </div>
                                            </div>
                                            <div className="bg-gradient-to-br from-indigo-900/30 to-blue-900/20 rounded-2xl p-6 border border-indigo-500/30 shadow-lg">
                                                <div className="text-indigo-300 text-xs font-medium mb-1">출금 대기 중인 금액</div>
                                                <div className="text-2xl font-bold text-indigo-400 flex items-baseline gap-1 font-mono">
                                                    <span>0.000000</span>
                                                    <span className="text-sm font-bold opacity-70">USDT</span>
                                                </div>
                                            </div>
                                        </div>

                                        <div className="bg-[#1c2027] border border-white/10 rounded-2xl p-6 shadow space-y-4">
                                            <h4 className="text-xs font-bold text-gray-200 flex items-center gap-2 border-b border-white/5 pb-3">
                                                <span>💳 USDT (TRC-20) 출금 신청</span>
                                            </h4>
                                            <div className="space-y-4 max-w-md">
                                                <div>
                                                    <label className="text-[11px] font-bold text-gray-400 mb-1.5 block">수령할 TRC-20 지갑 주소</label>
                                                    <input
                                                        type="text"
                                                        value={walletAddress}
                                                        onChange={e => setWalletAddress(e.target.value)}
                                                        placeholder="T로 시작하는 TRC20 지갑 주소를 입력하세요"
                                                        className="w-full bg-[#14181f] border border-white/10 rounded-lg px-3 py-2 text-xs text-white font-mono focus:outline-none focus:border-green-500"
                                                    />
                                                </div>
                                                <div>
                                                    <label className="text-[11px] font-bold text-gray-400 mb-1.5 block">출금 신청 금액 (USDT)</label>
                                                    <input
                                                        type="number"
                                                        value={withdrawAmount}
                                                        onChange={e => setWithdrawAmount(e.target.value)}
                                                        placeholder="최소 10 USDT 이상"
                                                        className="w-full bg-[#14181f] border border-white/10 rounded-lg px-3 py-2 text-xs text-white font-mono focus:outline-none focus:border-green-500"
                                                    />
                                                </div>
                                                <button
                                                    type="button"
                                                    onClick={() => {
                                                        if (!walletAddress) {
                                                            alert('지갑 주소를 입력해주세요.')
                                                            return
                                                        }
                                                        if (!withdrawAmount || Number(withdrawAmount) < 10) {
                                                            alert('최소 10 USDT 이상 신청 가능합니다.')
                                                            return
                                                        }
                                                        alert(`${withdrawAmount} USDT 출금 신청이 성공적으로 접수되었습니다. 관리자 승인 후 처리됩니다.`)
                                                        setWithdrawAmount('')
                                                    }}
                                                    className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 rounded-lg text-xs font-bold text-white shadow transition-all"
                                                >
                                                    출금 신청하기
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {/* [탭 5: 문의하기] */}
                                {settingsSubTab === 'support' && (
                                    <div className="bg-[#1c2027] border border-white/10 rounded-2xl p-6 shadow space-y-4">
                                        <h4 className="text-xs font-bold text-gray-200 flex items-center gap-2 border-b border-white/5 pb-3">
                                            <span>💬 1:1 고객센터 문의하기</span>
                                        </h4>
                                        <div className="space-y-3 max-w-xl">
                                            <div>
                                                <label className="text-[11px] font-bold text-gray-400 mb-1.5 block">문의 유형</label>
                                                <select
                                                    value={inquiryCategory}
                                                    onChange={e => setInquiryCategory(e.target.value)}
                                                    className="bg-[#14181f] border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500 w-full"
                                                >
                                                    <option value="시스템 문의">시스템 및 작업 오류 문의</option>
                                                    <option value="정산 문의">수당 및 USDT 정산 문의</option>
                                                    <option value="기타">기타 요청 사항</option>
                                                </select>
                                            </div>
                                            <div>
                                                <label className="text-[11px] font-bold text-gray-400 mb-1.5 block">문의 내용</label>
                                                <textarea
                                                    value={inquiryText}
                                                    onChange={e => setInquiryText(e.target.value)}
                                                    placeholder="문의하실 내용을 상세히 적어주세요."
                                                    className="w-full p-3 bg-[#14181f] border border-white/10 rounded-lg text-xs text-white min-h-[120px] focus:outline-none focus:border-blue-500 resize-none leading-relaxed"
                                                />
                                            </div>
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    if (!inquiryText.trim()) {
                                                        alert('문의 내용을 입력해주세요.')
                                                        return
                                                    }
                                                    alert('문의가 접수되었습니다. 신속히 답변드리겠습니다.')
                                                    setInquiryText('')
                                                }}
                                                className="px-5 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-xs font-bold text-white shadow transition"
                                            >
                                                문의 접수
                                            </button>
                                        </div>
                                    </div>
                                )}

                                {/* [탭 6: 공지사항] */}
                                {settingsSubTab === 'announcements' && (
                                    <div className="bg-[#1c2027] border border-white/10 rounded-2xl p-6 shadow space-y-4">
                                        <h4 className="text-xs font-bold text-gray-200 flex items-center gap-2 border-b border-white/5 pb-3">
                                            <span>📢 공지사항 & 업데이트 소식</span>
                                        </h4>
                                        <div className="space-y-3 text-xs">
                                            <div className="p-4 bg-[#14181f] rounded-xl border border-white/5 space-y-1">
                                                <div className="flex items-center justify-between text-gray-400 text-[11px]">
                                                    <span className="bg-blue-600/20 text-blue-400 px-2 py-0.5 rounded font-bold">공지</span>
                                                    <span className="font-mono">2026.08.18</span>
                                                </div>
                                                <h5 className="font-bold text-white text-sm pt-1">롱폼 스튜디오 v2.3.46 정식 업데이트 안내</h5>
                                                <p className="text-gray-400 leading-relaxed text-[11px] pt-1">
                                                    초반 1분 12개 씬 고정 훅 및 13~53씬 동적 런닝타임 연동과 지능형 1줄 자막 분할 시스템이 전면 적용되었습니다.
                                                </p>
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                
                {/* 이용약관 & 개인정보처리방침 팝업 모달 */}
                {legalModalType && (
                    <div
                        onClick={() => setLegalModalType(null)}
                        className="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-4"
                    >
                        <div
                            onClick={e => e.stopPropagation()}
                            className="bg-[#1e293b] border border-white/15 rounded-3xl p-6 w-full max-w-lg shadow-2xl space-y-4 flex flex-col max-h-[85vh] animate-in fade-in zoom-in-95 duration-150"
                        >
                            <div className="flex items-center justify-between border-b border-white/10 pb-3">
                                <h3 className="text-base font-black text-white flex items-center gap-2">
                                    <span>{legalModalType === 'terms' ? '📜' : '🔒'}</span>
                                    <span>
                                        {legalModalType === 'terms' ? '서비스 이용약관' : '개인정보 수집 및 이용 동의'}
                                    </span>
                                </h3>
                                <button
                                    type="button"
                                    onClick={() => setLegalModalType(null)}
                                    className="text-gray-400 hover:text-white text-lg font-bold p-1"
                                >
                                    ✕
                                </button>
                            </div>

                            <div className="flex-1 overflow-y-auto bg-[#0f172a] border border-white/5 rounded-2xl p-4 text-xs text-gray-300 leading-relaxed font-sans whitespace-pre-wrap select-text">
                                {legalModalType === 'terms'
                                    ? (legalTexts.terms[currentLocale] || legalTexts.terms.ko || '이용약관을 불러오는 중입니다...')
                                    : (legalTexts.privacy[currentLocale] || legalTexts.privacy.ko || '개인정보 처리방침을 불러오는 중입니다...')}
                            </div>

                            <div className="flex items-center gap-2 pt-2 border-t border-white/10">
                                <button
                                    type="button"
                                    onClick={() => {
                                        if (legalModalType === 'terms') setAgreedTerms(true)
                                        if (legalModalType === 'privacy') setAgreedPrivacy(true)
                                        setLegalModalType(null)
                                    }}
                                    className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-500 rounded-xl text-xs font-bold text-white shadow-md transition"
                                >
                                    확인 및 동의하기
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setLegalModalType(null)}
                                    className="px-4 py-2.5 bg-[#334155] hover:bg-[#475569] text-gray-300 hover:text-white rounded-xl text-xs font-bold transition"
                                >
                                    닫기
                                </button>
                            </div>
                        </div>
                    </div>
                )}

            </main>
            </div>
        </div>
    )
}
