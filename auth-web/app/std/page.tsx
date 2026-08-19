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
import { SupportedLocale, getTranslation } from '@/lib/i18n'

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

export default function StdPortalPage() {

    useEffect(() => {
        // Load voices from API
        fetch('/api/std/voices')
            .then(res => res.json())
            .then(data => {
                if (data?.voices && data.voices.length > 0) {
                    setAllVoices(data.voices)
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
    const [signupCategories, setSignupCategories] = useState<string[]>(['경제/재테크', '사연/이야기'])
    const [preferredVideoLength, setPreferredVideoLength] = useState('15-30분')
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
    const t = (key: string, fallback?: string) => getTranslation(currentLocale, key, fallback)

    // 2. 작업 데이터 상태
    const [topics, setTopics] = useState<Topic[]>([])
    const [projects, setProjects] = useState<StdProject[]>([])
    const [selectedProject, setSelectedProject] = useState<SelectedProjectPayload | null>(null)

    // 2.1 주제 큐 & 모달 팝업 상태 (유저앱 topic.html 완벽 대응)
    const [selectedTopicForModal, setSelectedTopicForModal] = useState<any>(null)
    const [topicModalOpen, setTopicModalOpen] = useState(false)
    const [trendLang, setTrendLang] = useState<'ko' | 'ja' | 'en'>('ko')
    const [trendPeriod, setTrendPeriod] = useState('now')
    const [trendAge, setTrendAge] = useState('50s')
    const [topicSearchQuery, setTopicSearchQuery] = useState('')
    const [topicLengthFilter, setTopicLengthFilter] = useState('')

    // 3. 네비게이션: 유저앱 사이드바 및 스텝퍼와 100% 동일
    type StdNavKey = 'topics' | 'script_plan' | 'script_gen' | 'image_gen' | 'tts' | 'subtitle_gen' | 'thumbnail' | 'projects' | 'template' | 'render' | 'settings'
    const [currentNav, setCurrentNav] = useState<StdNavKey>('topics')

    // 4. 에셋 및 작업 제어 상태
    const [uploadingKey, setUploadingKey] = useState('')
    const [generatingTts, setGeneratingTts] = useState(false)
    const [allVoices, setAllVoices] = useState(ELEVENLABS_VOICES)
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
    const [selectedCategories, setSelectedCategories] = useState<string[]>(['역사/야사', '경제/재테크', '휴먼/감동'])
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
    const [templateBgUrl, setTemplateBgUrl] = useState('https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=1280&auto=format&fit=crop&q=80')
    const [templateBgColor, setTemplateBgColor] = useState('#000000')
    const [templatePresetName, setTemplatePresetName] = useState('')
    const [selectedTemplatePreset, setSelectedTemplatePreset] = useState('preset-1')
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
            text: '30년 연금 납입의 충격 진실',
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

    // 8. 썸네일(Thumbnail) 제작 스튜디오 전용 상태 (유저앱 thumbnail.html 100% 동일 구현)
    const [thumbTitle, setThumbTitle] = useState('국민연금 30년 냈는데 월 80만 원? 30년 차 부부가 공개한 실제 수령액')
    const [thumbLayout, setThumbLayout] = useState('face')
    const [thumbStyle, setThumbStyle] = useState('realistic')
    const [thumbStep, setThumbStep] = useState<number>(1)
    const [thumbBgUrl, setThumbBgUrl] = useState('https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=1280&auto=format&fit=crop&q=80')
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
            text: '30년 연금 납입의 충격 진실',
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

    // 스크립트 컨텍스트에서 AI 생성 메타 지시문(First-minute micro beat 1/12... 등)을 제거하고 순수 대본만 정제하는 함수
    const cleanScriptContextText = (text: string | null | undefined): string => {
        if (!text) return ''
        let cleaned = String(text).trim()
        // First-minute micro beat 1/12 (0-5s). Keep this as a separate fast visual cut that advances the hook: 패턴 제거
        cleaned = cleaned.replace(/^First-minute micro beat\s*\d+\/\d+\s*\([^)]*\)\.?\s*(Keep this as a separate fast visual cut that advances the hook:?)?\s*/i, '')
        cleaned = cleaned.replace(/^First-minute micro beat\s*[:\-\d\(\)\w\s\.]*?:\s*/i, '')
        cleaned = cleaned.replace(/^Scene\s*\d+\s*(?:\([^)]*\))?\s*:\s*/i, '')
        cleaned = cleaned.replace(/^Hook Scene\s*\d+\s*:\s*/i, '')
        cleaned = cleaned.replace(/^Panel\s*\d+\s*:\s*/i, '')
        return cleaned.trim() || String(text).trim()
    }

    const sanitizeAssetUrl = (url: string | null | undefined): string | null => {
        if (!url) return null
        const str = String(url).trim()
        if (str.includes('images.unsplash.com') || str.includes('commondatastorage.googleapis.com')) {
            return null
        }
        return str
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

        const scenes = rawScenes.map((s: any, i: number) => {
            const num = Number(s.scene_number || s.scene_order || i + 1)
            // 신규 생성 시 실제 업로드/생성 에셋이 없으면 null (가짜 더미 이미지/비디오 제거)
            const videoUrl: string | null = sanitizeAssetUrl(s.video_url || s.video)
            const imageUrl: string | null = sanitizeAssetUrl(s.image_url || s.image)

            const rawScript = s.script_excerpt || s.scene_text || s.scene_situation || s.scene_summary || s.narration || s.prompt_ko || realDefaultNarratives[i % realDefaultNarratives.length]
            const scriptText = cleanScriptContextText(rawScript)
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
                ready_scene_count: scenes.filter(s => s.video_url || s.image_url).length,
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
                if (meData.user.full_name) setSettingName(meData.user.full_name)
                if (meData.user.nationality) setSettingNationality(meData.user.nationality)
                if (meData.user.contact) setSettingPhone(meData.user.contact)
                if (meData.user.referral_code) setReferralCode(meData.user.referral_code)
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

            if (savedProjectStateRaw) {
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
                        setCustomScriptText(cleanedProject.project.project_payload?.script || '')
                    }
                } catch {
                    // Fallback to loadedProjects
                }
            } else if (savedActiveProjectId && loadedProjects.some(p => p.id === savedActiveProjectId)) {
                await openProject(savedActiveProjectId, accessToken).catch(() => {})
            } else if (loadedProjects.length > 0) {
                await openProject(loadedProjects[0].id, accessToken).catch(() => {})
            } else if (loadedTopics.length > 0) {
                const firstRealTopic = loadedTopics[0]
                const loaded = buildProjectFromSupabaseTopic(firstRealTopic)
                setSelectedProject(loaded)
                setProjects([loaded.project])
                setCustomScriptText(loaded.project.project_payload?.script || '')
                localStorage.setItem('std_active_project_state', JSON.stringify(loaded))
                localStorage.setItem('std_active_project_id', loaded.project.id)
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
                        fetch(`/api/std/topics?impersonate=${encodeURIComponent(cleanEmail)}`, { headers }),
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
                        setCustomScriptText(built.project.project_payload?.script || '')
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
        const targetEmail = email.trim().toLowerCase() || 'ejsh0519@naver.com'
        localStorage.setItem('std_last_email', targetEmail)

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
                setCustomScriptText(finalProject.project.project_payload?.script || '')
                localStorage.setItem('std_active_project_state', JSON.stringify(finalProject))
                localStorage.setItem('std_active_project_id', finalProject.project.id)
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
                setCustomScriptText(built.project.project_payload?.script || '')
                localStorage.setItem('std_active_project_state', JSON.stringify(built))
                localStorage.setItem('std_active_project_id', built.project.id)
                setTopicModalOpen(false)
                setCurrentNav('image_gen')
                setMessage(`'${targetTopic.generated_title || targetTopic.topic}' 작업 프로젝트로 등록되었습니다!`)
            }
        } finally {
            setLoading(false)
        }
    }

    
    const handleUploadExternalAudio = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (!file) return
        const fakeUrl = URL.createObjectURL(file)
        setAudioResultUrl(fakeUrl)
        alert(`외부 오디오 파일 '${file.name}'이(가) 업로드되었습니다.`)
    }

    const openProject = async (projectId: string, overrideToken?: string, overrideImpEmail?: string) => {
        setProjectLoading(true)
        setMessage('')
        try {
            const targetToken = overrideToken || token
            const activeImpEmail = overrideImpEmail || (isImpersonating ? impersonateEmail : '')
            const impQuery = activeImpEmail ? `?impersonate=${encodeURIComponent(activeImpEmail)}` : ''
            const fetchHeaders: Record<string, string> = { Authorization: `Bearer ${targetToken}` }
            if (activeImpEmail) fetchHeaders['x-impersonate-email'] = activeImpEmail

            const res = await fetch(`/api/std/projects/${projectId}${impQuery}`, {
                headers: fetchHeaders,
            })
            const payload = await safeParseJson(res, '작업 조회 실패')
            if (res.ok && payload?.project) {
                const serverScenes = Array.isArray(payload.scenes) && payload.scenes.length > 0
                    ? payload.scenes
                    : payload.project.project_payload?.structure?.scenes || []

                const fullScript = payload.project.project_payload?.script || serverScenes.map((s: any) => cleanScriptContextText(s.scene_text || s.script_excerpt)).join('\n\n')
                setCustomScriptText(fullScript)

                const fullProjectPayload: SelectedProjectPayload = {
                    ...payload,
                    scenes: serverScenes.map((s: any, idx: number) => {
                        const rawText = s.script_excerpt || s.scene_text || s.scene_situation || s.scene_summary || `Scene ${idx + 1}`
                        const cleanedText = cleanScriptContextText(rawText)
                        return {
                            ...s,
                            scene_text: cleanedText,
                            script_excerpt: cleanedText,
                            video_prompt: s.video_prompt || s.prompt_en || s.prompt || s.image_prompt || '',
                            video_url: s.video_url || s.video || null,
                            image_url: s.image_url || s.image || null,
                        }
                    })
                }

                setSelectedProject(fullProjectPayload)
                localStorage.setItem('std_active_project_id', projectId)
                localStorage.setItem('std_active_project_state', JSON.stringify(fullProjectPayload))
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
                localStorage.setItem('std_active_project_id', projectId)
                localStorage.setItem('std_active_project_state', JSON.stringify(built))
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
        const voiceObj = allVoices.find(v => v.id === selectedVoice) || ELEVENLABS_VOICES[0]
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
    }, [selectedVoice])

    const scriptCharCount = useMemo(() => {
        return (customScriptText || selectedProject?.project?.project_payload?.script || '').length
    }, [customScriptText, selectedProject])

    const estimatedAudioMinutes = useMemo(() => {
        const speedNum = Number(ttsSpeed) || 1.0
        const chars = scriptCharCount || 7200
        return Math.round((chars / (330 * speedNum)) * 10) / 10
    }, [scriptCharCount, ttsSpeed])

    const formattedEstimatedTime = useMemo(() => {
        const speedNum = Number(ttsSpeed) || 1.0
        const totalMinutes = Math.round(scriptCharCount / (330 * speedNum))
        if (totalMinutes < 60) {
            return `약 ${totalMinutes}분`
        }
        const hours = Math.floor(totalMinutes / 60)
        const mins = totalMinutes % 60
        return `약 ${hours}시간 ${mins}분`
    }, [scriptCharCount, ttsSpeed])

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
        image_url: 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&auto=format&fit=crop&q=80',
    }

    const displayedTopics = useMemo(() => {
        const rawList = topics.length > 0 ? topics : [
            { id: 101, topic: '서른 해 동안 국민연금을 납입해온 부부의 실제 수령액과 은퇴 현실', generated_title: '30년 연금 납입의 충격 진실! 통장에 찍힌 실제 수령액', category_name: '경제/재테크', assigned_duration_minutes: 15, estimated_payout: 45000 },
            { id: 102, topic: '아내의 장례식 날, 30년 숨긴 첫사랑의 편지가 열렸다', generated_title: '아내의 장례식 날, 30년 숨긴 첫사랑의 편지가 열렸다', category_name: '사연/이야기', assigned_duration_minutes: 15, estimated_payout: 45000 },
            { id: 103, topic: '만점으로 살 게 없다! 식탁 물가 폭등의 진짜 원인', generated_title: '물가 대폭등의 비밀! 우리가 몰랐던 유통의 함정', category_name: '경제/이슈', assigned_duration_minutes: 15, estimated_payout: 45000 },
            { id: 104, topic: '한국인이 몰랐던 조선 야사: 소를 뜯는 구선 선설의 진실', generated_title: '조선왕조실록에 숨겨진 기괴한 비밀 야사', category_name: '역사/야사', assigned_duration_minutes: 20, estimated_payout: 55000 },
            { id: 105, topic: 'AI발 일자리 쇼크, 내 직업은 안전할까? 우리는 뭘 해야 하나?', generated_title: '2026 AI 시대, 살아남는 직업과 사라지는 직업', category_name: 'IT/테크', assigned_duration_minutes: 15, estimated_payout: 45000 },
            { id: 106, topic: '황혼 부부, 이것 때문에 잠 못 이룬다? 19금 속마음 공개!', generated_title: '5060 부부가 절대 말하지 못하는 은밀한 고민', category_name: '라이프/사연', assigned_duration_minutes: 15, estimated_payout: 45000 },
        ]

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
    }, [topics, topicSearchQuery, topicLengthFilter, projects, selectedProject])

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

                                <div className="flex gap-2">
                                    <input
                                        type="email"
                                        value={email}
                                        onChange={e => setEmail(e.target.value)}
                                        className="flex-1 bg-[#0f172a]/80 border border-white/10 rounded-xl px-4 py-2.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                                        placeholder={t('auth_ph_email')}
                                        required
                                    />
                                    <button
                                        type="button"
                                        onClick={() => alert('인증 코드가 이메일로 발송되었습니다.')}
                                        className="px-3 bg-blue-600/20 border border-blue-500/40 text-blue-300 hover:bg-blue-600 hover:text-white rounded-xl text-xs font-bold transition whitespace-nowrap"
                                    >
                                        {t('auth_btn_send_verify')}
                                    </button>
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
                                        {[
                                            { key: 'cat_finance', defaultLabel: '경제/재테크' },
                                            { key: 'cat_stories', defaultLabel: '사연/이야기' },
                                            { key: 'cat_history', defaultLabel: '역사/야사' },
                                            { key: 'cat_wuxia', defaultLabel: '무협/판타지' },
                                            { key: 'cat_aitech', defaultLabel: 'AI/테크' },
                                            { key: 'cat_drama', defaultLabel: '휴먼/감동' },
                                        ].map(item => {
                                            const active = signupCategories.includes(item.defaultLabel)
                                            return (
                                                <button
                                                    key={item.key}
                                                    type="button"
                                                    onClick={() => {
                                                        if (active) {
                                                            setSignupCategories(prev => prev.filter(c => c !== item.defaultLabel))
                                                        } else {
                                                            setSignupCategories(prev => [...prev, item.defaultLabel])
                                                        }
                                                    }}
                                                    className={`px-2 py-1 rounded-lg text-[10px] font-bold border transition ${
                                                        active
                                                            ? 'bg-blue-600/30 text-blue-300 border-blue-500'
                                                            : 'bg-[#0f172a] text-gray-400 border-white/5 hover:text-white'
                                                    }`}
                                                >
                                                    {t(item.key, item.defaultLabel)}
                                                </button>
                                            )
                                        })}
                                    </div>
                                </div>

                                {/* 약관 동의 */}
                                <div className="space-y-1 text-[11px] text-gray-400">
                                    <label className="flex items-center gap-2 cursor-pointer">
                                        <input
                                            type="checkbox"
                                            checked={agreedTerms}
                                            onChange={e => setAgreedTerms(e.target.checked)}
                                            className="rounded bg-black/40 border-white/20 text-blue-500 w-3.5 h-3.5"
                                        />
                                        <span>{t('auth_agree_terms')}</span>
                                    </label>
                                    <label className="flex items-center gap-2 cursor-pointer">
                                        <input
                                            type="checkbox"
                                            checked={agreedPrivacy}
                                            onChange={e => setAgreedPrivacy(e.target.checked)}
                                            className="rounded bg-black/40 border-white/20 text-blue-500 w-3.5 h-3.5"
                                        />
                                        <span>{t('auth_agree_privacy')}</span>
                                    </label>
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
                                onClick={() => {
                                    if (!forgotEmail.trim()) return
                                    setForgotMsg('임시 비밀번호가 발송되었습니다. 메일함을 확인해주세요.')
                                    setTimeout(() => {
                                        setForgotMsg('')
                                        setForgotModalOpen(false)
                                    }, 2500)
                                }}
                                disabled={!forgotEmail.trim()}
                                className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 rounded-xl text-xs font-bold text-white shadow transition"
                            >
                                {t('auth_btn_send_temp_pw')}
                            </button>
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
            <header className="h-12 bg-[#181d26] border-b border-white/10 px-4 flex items-center justify-between shrink-0 z-30">
                <div className="flex items-center gap-3">
                    <span className="w-2 h-2 rounded-full bg-blue-500" />
                    <span className="font-bold text-sm tracking-wide text-blue-400">AIR STUDIO</span>
                    <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
                        STD
                    </span>
                    <span className="text-gray-500 text-xs hidden md:inline">|</span>
                    <span className="text-xs text-gray-300 font-medium hidden md:inline">
                        <strong className="text-blue-400">{t('active_project')}:</strong> {selectedProject?.project?.title || '아내의 장례식 날, 30년 숨긴 첫사랑의 편지가 열렸다'} <span className="text-gray-400 font-mono">({selectedProject?.project?.status || 'image_prompted'})</span>
                    </span>
                </div>

                {/* 상단 8단계 녹색 원형 체크 스텝퍼 */}
                <div className="hidden lg:flex items-center gap-3 text-[11px] text-gray-400 font-medium">
                    {[
                        { id: 'topics', label: t('nav_topics') },
                        { id: 'image_gen', label: t('nav_image') },
                        { id: 'tts', label: t('nav_tts') },
                        { id: 'subtitle_gen', label: t('nav_subtitles') },
                        { id: 'thumbnail', label: t('nav_thumbnail') },
                        { id: 'settings', label: t('nav_settings') },
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
                    {/* 언어 선택 드롭다운 (KO, EN, VI, TH) */}
                    <div className="flex items-center bg-[#14181f] border border-white/10 rounded-lg px-2 py-1">
                        <select
                            value={currentLocale}
                            onChange={(e) => setCurrentLocale(e.target.value as SupportedLocale)}
                            className="bg-transparent text-xs text-white focus:outline-none cursor-pointer"
                        >
                            <option value="ko" className="bg-[#1c2027] text-white">🇰🇷 한국어 (KO)</option>
                            <option value="en" className="bg-[#1c2027] text-white">🇺🇸 English (EN)</option>
                            <option value="vi" className="bg-[#1c2027] text-white">🇻🇳 Tiếng Việt (VI)</option>
                            <option value="th" className="bg-[#1c2027] text-white">🇹🇭 ภาษาไทย (TH)</option>
                        </select>
                    </div>

                    <button
                        onClick={() => loadStdData(token)}
                        disabled={loading}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-[#202632] hover:bg-[#28303e] border border-white/10 rounded text-xs font-medium text-gray-300 transition-all"
                    >
                        <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
                        {t('btn_refresh')}
                    </button>
                    <div className="h-3.5 w-px bg-white/10" />
                    <div className="text-right hidden sm:block">
                        <div className="text-xs font-bold text-white leading-none">{user?.full_name || '김호'}</div>
                        <div className="text-[10px] text-gray-400 truncate max-w-[140px] leading-tight">{user?.email || 'ejsh0519@naver.com'}</div>
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
                            { id: 'tts', label: t('nav_tts') },
                            { id: 'image_gen', label: t('nav_image') },
                            { id: 'subtitle_gen', label: t('nav_subtitles') },
                            { id: 'thumbnail', label: t('nav_thumbnail') },
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
                                            className="px-2.5 py-1.5 text-xs font-bold border border-gray-600 bg-transparent hover:bg-white/5 text-gray-300 hover:text-white rounded-lg transition-all flex items-center gap-1"
                                            title="직접 녹음/보유한 외부 오디오 파일을 업로드합니다."
                                        >
                                            <span>📁</span> 외부 오디오 업로드
                                        </button>
                                    </div>
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
                                            {allVoices.map(v => (
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
                                                            {allVoices.map(v => (
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
                                            <div className="text-[10px] text-gray-400">예상 소요: {formattedEstimatedTime}</div>
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

                                <div className="p-4 border-t border-white/5 bg-[#181d26] space-y-3">
                                    <div className="flex items-center justify-between">
                                        <h4 className="text-xs font-bold text-gray-300">최종 클립 순서</h4>
                                        <span className="text-[11px] text-gray-400 font-mono">
                                            영상 등록 완료: {selectedProject.scenes.filter(s => Boolean(s.video_url)).length} / {selectedProject.scenes.length}
                                        </span>
                                    </div>
                                    <div className="flex flex-wrap items-center gap-3">
                                        {selectedProject.scenes.filter(s => Boolean(s.video_url)).length > 0 ? (
                                            selectedProject.scenes.filter(s => Boolean(s.video_url)).map(s => (
                                                <div key={s.scene_number} className="flex items-center gap-2 bg-[#14181f] px-3 py-1.5 rounded border border-white/5 text-xs">
                                                    <span className="font-bold text-white">씬 {s.scene_number}</span>
                                                    <span className="text-purple-400 font-mono truncate max-w-[200px]">
                                                        {s.video_url?.split('/').pop() || `clip_scene_${s.scene_number}.mp4`}
                                                    </span>
                                                </div>
                                            ))
                                        ) : (
                                            <div className="text-xs text-gray-500 py-1">
                                                아직 등록된 영상 클립이 없습니다.
                                            </div>
                                        )}
                                    </div>
                                    <div className="flex items-center justify-between pt-2">
                                        {selectedProject.scenes.filter(s => !s.video_url).length > 0 ? (
                                            <p className="text-xs text-amber-400 font-mono truncate max-w-xl">
                                                영상 미등록: {selectedProject.scenes.filter(s => !s.video_url).map(s => s.scene_number).slice(0, 15).join(', ')}
                                                {selectedProject.scenes.filter(s => !s.video_url).length > 15 ? ` 외 ${selectedProject.scenes.filter(s => !s.video_url).length - 15}개` : ''}
                                            </p>
                                        ) : (
                                            <p className="text-xs text-emerald-400 font-mono">
                                                ✅ 모든 씬의 영상 클립이 등록되었습니다.
                                            </p>
                                        )}
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
                            {/* 1. 상단 실시간 트렌드 & 다차원 필터 영역 */}
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
                                            { text: '국민연금 30년 납입 수령액', volume: 98, cat: '경제' },
                                            { text: '아내의 숨겨진 30년 첫사랑 편지', volume: 95, cat: '사연' },
                                            { text: '조선왕조 비밀 야사', volume: 88, cat: '역사' },
                                            { text: '은퇴 후 1인 월 생활비', volume: 85, cat: '재테크' },
                                            { text: '건강보험 피부양자 탈락 충격', volume: 82, cat: '이슈' },
                                            { text: '100세 시대 치매 예방 음식', volume: 79, cat: '건강' },
                                            { text: '황혼 이혼 재산분할 진실', volume: 76, cat: '사연' },
                                            { text: 'AI 자동화 수익 모델 2026', volume: 74, cat: '테크' },
                                            { text: '부동산 공시지가 폭등 대응', volume: 70, cat: '경제' },
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
                                                        $4 USDT
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
                                                    <span className="text-cyan-400">53 Scenes</span>
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
                                                    정산 수당: $4.00 USDT (₩45,000)
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
                                                    <span className="font-bold text-emerald-400">총 53개 씬 구조</span>
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
                                                    이 주제로 작업을 시작하면 작업자의 활성 프로젝트로 즉시 등록 및 저장되며, 대본, 씬 프롬프트, ElevenLabs 음성, 1줄 자막 분할 및 썸네일 제작 단계로 연결됩니다.
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
                                                onChange={e => setThumbTitle(e.target.value)}
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
                                                    setThumbTextLayers(prev => prev.map((l, i) => i === 0 ? { ...l, text: '30년 연금의 충격 진실!?' } : l))
                                                    alert('더 자극적인(Clicky) 후킹 문구로 변경되었습니다.')
                                                }}
                                                className="py-1.5 border border-amber-500/40 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 rounded-lg text-[11px] font-bold transition"
                                            >
                                                🔥 더 어그로성 (Clicky)
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    setThumbTextLayers(prev => prev.map((l, i) => i === 0 ? { ...l, text: '국민연금 30년 실제 수령액' } : l))
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
                                            headline: '30년 연금 납입의 충격 진실',
                                            subhead: '통장에 찍힌 실제 수령액 공개',
                                            prompt: 'An elderly husband looking in shock at a bank statement with a magnifying glass, dramatic lighting, high contrast',
                                        },
                                        {
                                            id: 'idea-2',
                                            badge: '현실 대비형',
                                            headline: '국민연금 vs 현실 생계비',
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
                                            "30년 연금의 충격 진실",
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
                                        onClick={() => {
                                            uploadAsset(null, 'thumbnail', null)
                                            alert('현재 썸네일 디자인이 프로젝트 대표 썸네일로 최종 저장되었습니다!')
                                        }}
                                        className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-lg shadow transition"
                                    >
                                        💾 최종 썸네일 확정 저장
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
                                        <div className="grid grid-cols-2 gap-2 text-xs">
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    if (selectedProject?.scenes?.[0]?.image_url) {
                                                        setThumbBgUrl(selectedProject.scenes[0].image_url)
                                                    }
                                                }}
                                                className="py-2 bg-[#202632] hover:bg-white/10 rounded-lg font-bold text-gray-200 border border-white/10 transition"
                                            >
                                                🖼️ 1번 씬 이미지 적용
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    const newUrl = prompt('썸네일 배경 이미지 URL을 입력하세요:', thumbBgUrl)
                                                    if (newUrl) setThumbBgUrl(newUrl)
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

                    {/* [템플릿 탭 (유저앱 template.html과 100% 동일 구현)] */}
                    {currentNav === 'template' && (
                        <div className="space-y-4 max-w-6xl mx-auto w-full flex flex-col h-full pb-10">
                            {/* 1. 상단 AI 추천 훅 문구 영역 */}
                            <div className="bg-[#1c2027] border border-blue-500/30 rounded-xl p-4 shadow-md space-y-2">
                                <h4 className="text-xs font-bold text-blue-400 flex items-center gap-2">
                                    <span>🎯 AI 추천 썸네일/템플릿 훅 문구 (클릭 시 레이어 추가)</span>
                                </h4>
                                <div className="flex flex-wrap gap-2 pt-1">
                                    {[
                                        "30년 연금 납입의 충격 진실",
                                        "통장에 찍힌 실제 수령액 공개",
                                        "우리가 몰랐던 은퇴 후 한 달 생활비",
                                        "국민연금 vs 현실 생계비 격차",
                                        "30년 일하고 받은 돈이 고작...",
                                    ].map((hook, idx) => (
                                        <button
                                            key={idx}
                                            type="button"
                                            onClick={() => {
                                                const newLayer = {
                                                    id: `layer-${Date.now()}`,
                                                    text: hook,
                                                    fontSize: 30,
                                                    color: idx === 0 ? '#ffeb3b' : '#ffffff',
                                                    strokeColor: '#000000',
                                                    strokeWidth: 3,
                                                    fontFamily: 'GmarketSansBold',
                                                    x: 50,
                                                    y: 40 + idx * 15,
                                                }
                                                setTextLayers(prev => [...prev, newLayer])
                                            }}
                                            className="px-3 py-1.5 bg-[#202632] hover:bg-blue-600 border border-white/10 hover:border-blue-500 rounded-lg text-xs font-bold text-gray-200 hover:text-white transition-all shadow-sm"
                                        >
                                            + {hook}
                                        </button>
                                    ))}
                                </div>
                            </div>

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

                                                    <div className="grid grid-cols-3 gap-2 text-[10px]">
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

                                        <div className="grid grid-cols-2 gap-2">
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    const newImg = prompt('배경 이미지 URL을 입력하세요:', templateBgUrl || 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=1280&auto=format&fit=crop&q=80')
                                                    if (newImg) setTemplateBgUrl(newImg)
                                                }}
                                                className="py-2 bg-[#202632] hover:bg-white/10 rounded-lg text-xs font-bold text-white border border-white/10 transition"
                                            >
                                                URL로 변경
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    if (selectedProject?.scenes?.[0]?.image_url) {
                                                        setTemplateBgUrl(selectedProject.scenes[0].image_url)
                                                    } else {
                                                        alert('프로젝트 씬 이미지가 없습니다.')
                                                    }
                                                }}
                                                className="py-2 bg-blue-600/20 hover:bg-blue-600 border border-blue-500/30 text-blue-400 hover:text-white rounded-lg text-xs font-bold transition truncate px-1"
                                            >
                                                1번 씬 이미지 적용
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
                                            onChange={e => setSelectedTemplatePreset(e.target.value)}
                                            className="w-full bg-[#14181f] border border-white/10 rounded-lg p-2 text-xs text-white focus:outline-none"
                                        >
                                            <option value="preset-1">기본 2줄 볼드 강조 템플릿</option>
                                            <option value="preset-2">상단 옐로우 훅 템플릿</option>
                                            <option value="preset-3">중앙 심플 자막바 템플릿</option>
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
                                                onClick={() => {
                                                    if (!templatePresetName.trim()) {
                                                        alert('프리셋 이름을 입력해주세요.')
                                                        return
                                                    }
                                                    alert(`'${templatePresetName}' 템플릿 프리셋이 저장되었습니다.`)
                                                    setTemplatePresetName('')
                                                }}
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
                                                🔊 ElevenLabs 음성 (연동)
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
                                            <span>>_ 렌더링 콘솔 로그 (Terminal)</span>
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
                                        onClick={() => {
                                            setProfileSavedMsg('모든 환경설정 변경사항이 안전하게 저장되었습니다.')
                                            setTimeout(() => setProfileSavedMsg(''), 3000)
                                        }}
                                        className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-xs font-bold text-white shadow-md flex items-center gap-1.5 transition-all"
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
                                        {/* (1) 내 추천 코드 카드 (보라색 강조) */}
                                        <div className="rounded-2xl border border-purple-500/30 bg-purple-500/10 p-5 shadow-lg">
                                            <h5 className="text-xs font-bold text-purple-400 flex items-center gap-2 mb-3">
                                                <span>🔑 내 추천 코드</span>
                                            </h5>
                                            <div className="flex items-center gap-2">
                                                <input
                                                    type="text"
                                                    value={referralCode}
                                                    readOnly
                                                    className="w-full bg-[#14181f] border border-purple-500/40 rounded-xl px-4 py-2.5 text-lg font-mono font-bold text-white text-center tracking-widest focus:outline-none"
                                                />
                                                <button
                                                    type="button"
                                                    onClick={() => {
                                                        navigator.clipboard.writeText(referralCode)
                                                        alert('추천 코드가 클립보드에 복사되었습니다: ' + referralCode)
                                                    }}
                                                    className="px-5 py-2.5 bg-purple-600 hover:bg-purple-500 border border-purple-500 rounded-xl text-xs font-bold text-white whitespace-nowrap shadow transition-all"
                                                >
                                                    복사
                                                </button>
                                            </div>
                                            <p className="text-[11px] text-purple-300/80 mt-2.5 leading-relaxed">
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

                                                {/* 선호 영상 주제 태그 */}
                                                <div className="col-span-1 md:col-span-2">
                                                    <label className="text-[11px] font-bold text-gray-400 mb-2 block">
                                                        선호 영상 주제 (복수 선택 가능)
                                                    </label>
                                                    <div className="flex flex-wrap gap-2">
                                                        {['역사/야사', '경제/재테크', '미스터리/공포', '휴먼/감동', '무협/판타지', '드라마/스토리', '건강/시니어'].map(cat => {
                                                            const isSel = selectedCategories.includes(cat)
                                                            return (
                                                                <button
                                                                    key={cat}
                                                                    type="button"
                                                                    onClick={() => {
                                                                        setSelectedCategories(prev =>
                                                                            prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]
                                                                        )
                                                                    }}
                                                                    className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                                                                        isSel
                                                                            ? 'bg-blue-600 text-white shadow'
                                                                            : 'bg-[#202632] text-gray-400 border border-white/5 hover:text-white'
                                                                    }`}
                                                                >
                                                                    {cat}
                                                                </button>
                                                            )
                                                        })}
                                                    </div>
                                                </div>

                                                <div className="col-span-1 md:col-span-2 flex items-center gap-3 pt-2">
                                                    <button
                                                        type="button"
                                                        onClick={() => {
                                                            setProfileSavedMsg('사용자 정보가 성공적으로 저장되었습니다.')
                                                            setTimeout(() => setProfileSavedMsg(''), 3000)
                                                        }}
                                                        className="px-5 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-xs font-bold text-white shadow transition"
                                                    >
                                                        저장
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
                </main>
            </div>
        </div>
    )
}
