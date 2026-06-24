'use client'

import { useEffect, useState, useCallback, useMemo, useRef } from 'react'
import { supabase } from '@/lib/supabaseClient'
import { useRouter } from 'next/navigation'
import { useLanguage } from '@/lib/LanguageContext'
import LanguageSelector from './LanguageSelector'
import LearningStatsPanel from './LearningStatsPanel'
import TenantManagement from './TenantManagement'

interface UserProfile {
    id: string
    email: string
    created_at: string
    last_sign_in_at: string | null
    user_metadata: Record<string, any>
    app_metadata: Record<string, any>
    profile?: {
        token_balance?: number
        usdt_balance?: number
        wallet_address?: string
        is_approved?: boolean
        signup_status?: string
        signup_source?: string
        full_name?: string
        contact?: string
        nationality?: string
        membership?: string
        membership_tier?: string
        preferred_category_ids?: Array<number | string>
        preferred_category_names?: string[]
        preferred_video_length?: string
        preferred_languages?: string[]
        pin_code?: string
        approved_hwid?: string
        device_hwid?: string
        persona_name?: string
        persona_style?: string
        persona_description?: string
        referral_code?: string
        referred_by?: string | null
        referral_depth?: number
        country_code?: string
        referral_country?: string
        commission_rate?: number
    }
}

interface EditInfoFormState {
    full_name: string
    nationality: string
    contact: string
    preferred_languages: string[]
    persona_name: string
    persona_style: string
    persona_description: string
}


interface WithdrawalReq {
    id: string
    user_id: string
    amount: number
    dest_address: string
    status: 'pending' | 'completed' | 'rejected'
    created_at: string
}


interface WithdrawalReq {
    id: string
    user_id: string
    amount: number
    dest_address: string
    status: 'pending' | 'completed' | 'rejected'
    created_at: string
    commission_percent?: number
    commission_usd?: number
    net_usd?: number
    tenant_key?: string
    profiles?: {
        email: string
    }
}

interface PublishingRequest {
    id: string
    user_id: string
    video_url: string
    status: 'pending' | 'approved' | 'to_be_published' | 'published' | 'failed' | 'rejected'
    metadata: any
    created_at: string
    profiles?: {
        email: string
        membership_tier: string
    }
}

interface LocalUploadChannel {
    id: number
    name: string
    handle: string
    description?: string | null
    credentials_path?: string | null
    proxy?: string | null
}

const SUPER_ADMIN_EMAIL = 'ejsh0519@naver.com'
const LOCAL_APP_ORIGINS = ['http://127.0.0.1:8001', 'http://localhost:8001']
const CONTENT_LANGUAGE_OPTIONS = [
    { value: 'ko', label: '한국어' },
    { value: 'en', label: 'English' },
    { value: 'ja', label: '日本語' },
] as const

const normalizeContentLanguage = (value: any) => CONTENT_LANGUAGE_OPTIONS.some(option => option.value === value) ? value : 'ko'
const contentLanguageLabel = (value: any) => CONTENT_LANGUAGE_OPTIONS.find(option => option.value === normalizeContentLanguage(value))?.label || '한국어'

const typeMap: Record<string, string> = {
    'video': 'VIDEO',
    'image': 'IMAGE',
    'script': 'SCRIPT',
    'text_gen': 'TEXT_GEN',
    'vision_gen': 'VISION_GEN',
    'motion_guide': 'MOTION_GUIDE',
    'character_extraction': 'CHARACTER_EXTRACTION',
    'test_after_fix': 'SUBTITLE_FIX',
    'subtitle_fix': 'SUBTITLE_FIX',
    'test_local': 'LOCAL_TEST',
    'test_verbose': 'VERBOSE',
    'unknown': 'OTHER',
    'prompt': 'PROMPT_OPT'
};

const typeIcons: Record<string, string> = {
    'video': 'VD',
    'image': 'IM',
    'script': 'SC',
    'text_gen': 'TX',
    'vision_gen': 'VS',
    'motion_guide': 'MG',
    'character_extraction': 'CH',
    'test_after_fix': 'SF',
    'subtitle_fix': 'SF',
    'test_local': 'LT',
    'test_verbose': 'VB',
    'unknown': 'UK',
    'prompt': 'PR'
};

function StatCard({ label, value, unit, color, subLabel }: { label: string; value: string | number; unit: string; color: string; subLabel?: string }) {
    const textColor = color === 'green' ? 'text-[#22c55e]' : color === 'orange' ? 'text-[#f97316]' : color === 'blue' ? 'text-blue-400' : 'text-white';
    return (
        <div className="bg-[#0f172a]/60 border border-white/20 p-6 rounded-2xl flex flex-col justify-center min-h-[110px] relative overflow-hidden group hover:border-blue-500/40 transition-all shadow-lg">
            <div className="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
                <div className={`w-12 h-12 rounded-full ${color === 'green' ? 'bg-green-500' : color === 'orange' ? 'bg-orange-500' : 'bg-blue-500'}`} />
            </div>
            <span className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-1">{label}</span>
            <div className="flex items-baseline gap-2">
                <span className={`text-3xl font-black tabular-nums ${textColor}`}>{value}</span>
                <span className="text-[10px] text-gray-500 font-bold uppercase">{unit}</span>
            </div>
            {subLabel && <div className="text-[9px] text-gray-600 font-bold mt-1 uppercase">{subLabel}</div>}
        </div>
    );
}

export default function DashboardContent() {
    const router = useRouter()
    const { language } = useLanguage()
    const isKor = language === 'ko'
    const [user, setUser] = useState<any>(null)
    const [loading, setLoading] = useState(true)
    const [users, setUsers] = useState<UserProfile[]>([])
    const [publishingRequests, setPublishingRequests] = useState<PublishingRequest[]>([])
    const [withdrawals, setWithdrawals] = useState<WithdrawalReq[]>([])
    const [publishingFilter, setPublishingFilter] = useState<'all' | 'pending' | 'processing' | 'published' | 'failed' | 'invalid'>('all')
    const [activeTab, setActiveTab] = useState<'topics' | 'overview' | 'users' | 'organization' | 'api' | 'render-queue' | 'styles' | 'withdrawals' | 'learning' | 'tenants'>('topics')
    const [authToken, setAuthToken] = useState('')
    const [referralReport, setReferralReport] = useState<any>(null)
    const [userReferralInfo, setUserReferralInfo] = useState<any>(null)
    const [referralLoading, setReferralLoading] = useState(false)
    const [referralDays, setReferralDays] = useState(30)
    const [renderQueue, setRenderQueue] = useState<any[]>([])
    const [renderQueueFilter, setRenderQueueFilter] = useState<'all' | 'intro_ready'>('all')
    const [queueLoading, setQueueLoading] = useState(false)
    const [overviewSubTab, setOverviewSubTab] = useState<'video' | 'log'>('video')

    // 카테고리 & AI 주제 자판기 상태
    const [categories, setCategories] = useState<any[]>([])
    const [topics, setTopics] = useState<any[]>([])
    const [categoriesLoading, setCategoriesLoading] = useState(false)
    const hasLoadedCategoriesRef = useRef(false)
    const [newCatName, setNewCatName] = useState('')
    const [newCatKeywords, setNewCatKeywords] = useState('')
    const [newCatChannel, setNewCatChannel] = useState('')
    const [newCatEmployee, setNewCatEmployee] = useState('')
    const [newCatScriptStyle, setNewCatScriptStyle] = useState('default')
    const [newCatImageStyle, setNewCatImageStyle] = useState('realistic')
    const [newCatLanguage, setNewCatLanguage] = useState('ko')
    const [newCatVideoType, setNewCatVideoType] = useState('longform') // 'longform' | 'shorts'
    const [newCatUploadChannelId, setNewCatUploadChannelId] = useState<number | null>(null)
    const [newCatUploadChannelName, setNewCatUploadChannelName] = useState('')
    const [newCatUploadChannelHandle, setNewCatUploadChannelHandle] = useState('')
    const [generatingCatId, setGeneratingCatId] = useState<number | null>(null)
    const [generatedTopicsByCat, setGeneratedTopicsByCat] = useState<Record<number, string[]>>({})
    const [topicActionLoadingId, setTopicActionLoadingId] = useState<string | null>(null)
    const [editingTopicId, setEditingTopicId] = useState<string | null>(null)
    const [editingTopicDraft, setEditingTopicDraft] = useState('')
    const [topicQueueCategoryFilter, setTopicQueueCategoryFilter] = useState<string>('all')
    const [topicQueueStatusFilter, setTopicQueueStatusFilter] = useState<'working' | 'pending'>('working')
    const [topicQueueEmployeeFilter, setTopicQueueEmployeeFilter] = useState<string>('all')
    const [topicStyleAssigningType, setTopicStyleAssigningType] = useState<'script' | 'image' | null>(null)

    const [showAdvanced, setShowAdvanced] = useState(false)

    // 카테고리 리스트 롱폼/쇼츠 탭 구분
    const [categoryListTab, setCategoryListTab] = useState<'longform' | 'shorts'>('longform')
    const [categoryLangTab, setCategoryLangTab] = useState<'ko' | 'ja' | 'en'>('ko')

    // 카테고리 수정 모달 상태
    const [editCategory, setEditCategory] = useState<any | null>(null)
    const [editCatForm, setEditCatForm] = useState({
        name: '',
        keywords: '',
        benchmark_channel_url: '',
        assigned_employee_email: '',
        default_script_style: 'default',
        default_image_style: 'realistic',
        language: 'ko',
        video_type: 'longform',
        upload_channel_id: null as number | null,
        upload_channel_name: '',
        upload_channel_handle: '',
    })
    const [localChannels, setLocalChannels] = useState<LocalUploadChannel[]>([])
    const [localChannelsLoading, setLocalChannelsLoading] = useState(false)
    const [channelConfigCategory, setChannelConfigCategory] = useState<any | null>(null)
    const [channelConfigForm, setChannelConfigForm] = useState({
        local_channel_id: null as number | null,
        name: '',
        handle: '',
        proxy: '',
    })
    
    // UI Modals State
    const [logViewUser, setLogViewUser] = useState<UserProfile | null>(null)
    const [apiViewUser, setApiViewUser] = useState<any>(null);
    const [channelViewUser, setChannelViewUser] = useState<any>(null);
    const [tempApiKeys, setTempApiKeys] = useState<any>({ openai: '', gemini: '', pexels: '', replicate: '' });
    const [tempChannelInfo, setTempChannelInfo] = useState<any>({ name: '', id: '', proxy: '' });
    const [editInfoUser, setEditInfoUser] = useState<any>(null);
    const [editInfoForm, setEditInfoForm] = useState<EditInfoFormState>({
        full_name: '',
        nationality: '',
        contact: '',
        preferred_languages: ['ko'],
        persona_name: '',
        persona_style: '',
        persona_description: '',
    });
    
    // Data Stats State
    const [globalLogs, setGlobalLogs] = useState<any[]>([])
    const [userLogs, setUserLogs] = useState<any[]>([])
    const [logsLoading, setLogsLoading] = useState(false)
    const [logPeriod, setLogPeriod] = useState(1)
    const [logStats, setLogStats] = useState({ total: 0, successRate: 0, avgLatency: 0, totalTokens: 0, breakdown: {} as any })
    const [globalPeriod, setGlobalPeriod] = useState(1)
    const [globalStats, setGlobalStats] = useState({ total: 0, successRate: 0, avgLatency: 0, totalTokens: 0, breakdown: {} as any })
    const [globalLoading, setGlobalLoading] = useState(false)

    // 로그 검색 및 필터링 상태
    const [logFilterTask, setLogFilterTask] = useState<string>('all')
    const [logFilterStatus, setLogFilterStatus] = useState<string>('all')
    const [logSearchPrompt, setLogSearchPrompt] = useState<string>('')

    // 시스템 전역 API 키 설정
    const [sysKeys, setSysKeys] = useState({
        gemini: '', youtube: '', claude: '', elevenlabs: '', suno: '', suno_base_url: '', music_provider: 'elevenlabs',
        music_gemini_model: 'lyria-3-pro-preview', music_gemini_base_url: '', music_gemini_project_id: '', music_gemini_location: 'global',
        topview: '', topview_uid: '',
        longform_min_duration_minutes: '15',
        longform_base_payout: '10000',
        longform_extra_minute_payout: '500',
        longform_duration_lock_enabled: 'true',
        binance_api_key: '', binance_api_secret: '',
        qa_enable_pipeline: 'true', qa_enable_technical_check: 'true', qa_enable_semantic_check: 'false',
        qa_auto_normalize_lufs: 'true', qa_hold_on_technical_fail: 'true', qa_hold_on_semantic_fail: 'true',
        qa_target_lufs: '-14', qa_lufs_tolerance: '2', qa_blackdetect_min_duration: '1.0',
        qa_min_width: '1920', qa_min_height: '1080',
        terms_ko: '', terms_en: '', terms_vi: '', terms_th: '',
        privacy_ko: '', privacy_en: '', privacy_vi: '', privacy_th: '',
        script_generation_model: 'gemini-2.5-flash',
        image_generation_model: 'gemini-3.1-flash-image-preview',
        video_generation_model: 'veo-3.1-fast-generate-preview'
    })
    const [sysKeysSaving, setSysKeysSaving] = useState(false)
    const [sysKeysSaved, setSysKeysSaved] = useState(false)
    const [legalActiveTab, setLegalActiveTab] = useState<'ko' | 'en' | 'vi' | 'th'>('ko')
    const [apiSettingsTab, setApiSettingsTab] = useState<'ai' | 'music' | 'video' | 'legal' | 'policy'>('ai')

    // Style Presets state
    const [stylePresets, setStylePresets] = useState<any[]>([])
    const [presetsLoading, setPresetsLoading] = useState(false)
    const [presetId, setPresetId] = useState<string | null>(null)
    const [presetType, setPresetType] = useState<'image' | 'script' | 'thumbnail'>('image')
    const [presetKeyCode, setPresetKeyCode] = useState('')
    const [presetNameKo, setPresetNameKo] = useState('')
    const [presetNameVi, setPresetNameVi] = useState('')
    const [presetPromptTemplate, setPresetPromptTemplate] = useState('')
    const [presetGeminiInstruction, setPresetGeminiInstruction] = useState('')
    const [presetImageUrl, setPresetImageUrl] = useState('')
    const [isSavingPreset, setIsSavingPreset] = useState(false)

    // Auth & Access
    const isSuperAdmin = user?.email === SUPER_ADMIN_EMAIL;
    const isSubAdmin = user?.app_metadata?.role === 'sub_admin';
    const isAdmin = isSuperAdmin || isSubAdmin;
    const canManageSystemSettings = isSuperAdmin;
    const canManageStyles = isSuperAdmin;
    const canManageRenderQueue = isSuperAdmin;
    const canManageTopics = isSuperAdmin;
    const canManageSensitiveUserSettings = isSuperAdmin;
    const ui = useMemo(() => {
        if (language === 'th') {
            return {
                adminDashboard: 'แดชบอร์ดผู้ดูแลระบบ',
                topics: 'จัดการคิวหัวข้อ',
                overview: 'ภาพรวม',
                users: 'จัดการผู้ใช้',
                organization: 'จัดการองค์กร',
                withdrawals: 'จัดการการถอนเงิน',
                api: 'API KEY และการตั้งค่าระบบ',
                renderQueue: 'คิวเรนเดอร์ระยะไกล',
                styles: 'ตั้งค่าสไตล์',
                learning: 'สถิติการเรียนรู้',
                superAdmin: 'ผู้ดูแลสูงสุด',
                subAdminMode: '👤 โหมดผู้ดูแลย่อย',
                logout: 'ออกจากระบบ',
                authenticating: 'กำลังตรวจสอบสิทธิ์ผู้ดูแล...',
                noPermission: 'ไม่มีสิทธิ์เข้าถึง',
                refresh: 'รีเฟรช',
                save: 'บันทึก',
                edit: 'แก้ไข',
                delete: 'ลบ',
                approve: 'อนุมัติ',
                reject: 'ปฏิเสธ',
            }
        }
        return {
            adminDashboard: '관리자 대시보드',
            topics: '주제 큐 관리',
            overview: '현황 요약',
            users: '유저 관리',
            organization: '조직 관리',
            withdrawals: '출금 관리',
            api: 'API KEY & 시스템 설정',
            renderQueue: '리모트 렌더 큐',
            styles: '스타일 세팅',
            learning: '학습 통계',
            tenants: '테넌트 관리',
            superAdmin: '최고 관리자',
            subAdminMode: '👤 부관리자 모드',
            logout: '로그아웃',
            authenticating: '관리자 인증 중...',
            noPermission: '접근 권한이 없습니다.',
            refresh: '새로고침',
            save: '저장',
            edit: '수정',
            delete: '삭제',
            approve: '승인',
            reject: '거절',
        }
    }, [language]);
    const adminFetch = useCallback(async (input: RequestInfo | URL, init: RequestInit = {}) => {
        const headers = new Headers(init.headers || {});
        if (authToken) headers.set('Authorization', `Bearer ${authToken}`);
        return fetch(input, { ...init, headers });
    }, [authToken]);

    // Derived Stats
    const memberCount = useMemo(() => (users || []).length, [users]);
    const todayStr = useMemo(() => new Date().toISOString().split('T')[0], []);
    const newToday = useMemo(() => (users || []).filter((u: any) => u.created_at?.startsWith(todayStr)).length, [users, todayStr]);
    const activeToday = useMemo(() => (users || []).filter((u: any) => u.last_sign_in_at?.startsWith(todayStr)).length, [users, todayStr]);
    const totalTokens = useMemo(() => (users || []).reduce((acc: number, u: any) => acc + (u.profile?.token_balance || 0), 0), [users]);

    const getTopTasks = (breakdown: any) => {
        const priority = ['video', 'image', 'script', 'vision_gen', 'motion_guide', 'text_gen', 'character_extraction', 'test_after_fix', 'subtitle_fix'];
        const entries = Object.entries(breakdown || {})
            .map(([key, val]: [string, any]) => ({ name: key, ...val }));
            
        return [...entries].sort((a, b) => {
            const aPri = priority.indexOf(a.name);
            const bPri = priority.indexOf(b.name);
            if (aPri !== -1 && bPri !== -1) return aPri - bPri;
            if (aPri !== -1) return -1;
            if (bPri !== -1) return 1;
            return b.count - a.count;
        }).slice(0, 7);
    };

    const globalTopTasks = useMemo(() => getTopTasks(globalStats.breakdown), [globalStats.breakdown]);
    const userTopTasks = useMemo(() => getTopTasks(logStats.breakdown), [logStats.breakdown]);

    // Admin Action Handlers
    const handleRecharge = async (userId: string) => {
        if (!canManageSensitiveUserSettings) return;
        const amountStr = prompt(isKor ? '충전할 토큰 수를 입력하세요.' : 'Enter token amount to recharge', '50000');
        if (!amountStr) return;
        const parsedAmount = parseInt(amountStr);
        if (isNaN(parsedAmount) || parsedAmount <= 0) {
            alert(isKor ? '올바른 숫자를 입력해주세요.' : 'Please enter a valid number.');
            return;
        }
        try {
            const res = await adminFetch('/api/admin/users/recharge', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId, amount: parsedAmount, description: 'Admin Manual Recharge' })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                alert(isKor ? `충전 완료! ${parsedAmount.toLocaleString()} 토큰 추가` : `Recharge Success! +${parsedAmount.toLocaleString()} tokens`);
                // 동기적 업데이트 및 fetchUsers() 사용 시 Supabase 캐시로 stale 반환
                setUsers(prev => prev.map(u => u.id === userId
                    ? { ...u, profile: { ...u.profile, token_balance: (u.profile?.token_balance || 0) + parsedAmount } }
                    : u
                ));
            } else {
                alert((isKor ? '충전 실패: ' : 'Recharge Failed: ') + (data.error || `HTTP ${res.status}`));
            }
        } catch (e: any) {
            alert((isKor ? '네트워크 오류: ' : 'Network error: ') + (e?.message || String(e)));
        }
    }

    const handleUpdateApiKeys = async () => {
        if (!canManageSensitiveUserSettings) return;
        if (!apiViewUser) return;
        try {
            const res = await adminFetch('/api/admin/users/api-keys', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId: apiViewUser.id, apiKeys: tempApiKeys })
            });
            if (res.ok) {
                alert(isKor ? "성공적으로 적용되었습니다." : "API Keys updated successfully.");
                setApiViewUser(null);
                fetchUsers();
            } else {
                alert("적용 실패");
            }
        } catch (e) { alert("오류 발생"); }
    }

    const [savingChannel, setSavingChannel] = useState(false);

    // 테넌트 관리 상태
    const [tenants, setTenants] = useState<any[]>([])
    const [tenantsLoading, setTenantsLoading] = useState(false)
    const [showCreateTenant, setShowCreateTenant] = useState(false)
    const [newTenantForm, setNewTenantForm] = useState({
        tenant_key: '',
        tenant_name: '',
        brand_name: '',
        commission_percent: 10,
        min_commission_usd: 0,
        license_tier: 'standard'
    })
    const [editingTenant, setEditingTenant] = useState<any>(null)
    const [editTenantForm, setEditTenantForm] = useState({
        commission_percent: 0,
        min_commission_usd: 0,
        brand_name: '',
        primary_color: '',
        status: 'active',
        watermark_enabled: true
    })

    const handleUpdateChannelInfo = async () => {
        if (!channelViewUser) return;
        setSavingChannel(true);
        try {
            console.log('Saving channel for user:', channelViewUser.id, tempChannelInfo);
            const res = await adminFetch('/api/admin/users/update-metadata', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    userId: channelViewUser.id, 
                    metadata: { 
                        youtube_channel: tempChannelInfo.name,
                        youtube_channel_id: tempChannelInfo.id,
                        youtube_channel_proxy: tempChannelInfo.proxy
                    } 
                })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                console.log('Save success!', data);
                // [FIX] 서버에서 반환한 최신 유저 정보로 즉시 교체하여 동기화 지연을 방지
                const updatedUser = data.user;
                if (updatedUser) {
                    setUsers(prev => prev.map(u => u.id === updatedUser.id ? {
                        ...u,
                        user_metadata: updatedUser.user_metadata
                    } : u));
                }
                
                alert(isKor ? "채널 정보가 성공적으로 업데이트되었습니다." : "Channel info updated successfully.");
                setChannelViewUser(null);
                // fetchUsers()를 호출하지 않고 로컬 상태를 우선 갱신함 (Race Condition 해결)
            } else {
                console.error('Save failed:', data.error);
                alert((isKor ? "저장 실패: " : "Save failed: ") + (data.error || "Unknown error"));
            }
        } catch (e) { 
            console.error('API Catch Error:', e);
            alert("오류 발생"); 
        } finally {
            setSavingChannel(false);
        }
    };

    const fetchLocalUploadChannels = useCallback(async () => {
        setLocalChannelsLoading(true)
        try {
            let loaded: LocalUploadChannel[] = []
            let lastError = ''

            for (const origin of LOCAL_APP_ORIGINS) {
                try {
                    const res = await fetch(`${origin}/api/channels`, { method: 'GET' })
                    if (!res.ok) {
                        lastError = `HTTP ${res.status}`
                        continue
                    }
                    loaded = await res.json()
                    if (Array.isArray(loaded)) break
                } catch (err: any) {
                    lastError = err?.message || String(err)
                }
            }

            if (!Array.isArray(loaded) || loaded.length === 0) {
                setLocalChannels(Array.isArray(loaded) ? loaded : [])
                if (lastError) {
                    console.warn('Failed to load local channels:', lastError)
                }
                return
            }

            setLocalChannels(loaded)
        } finally {
            setLocalChannelsLoading(false)
        }
    }, [adminFetch])

    const applySelectedChannelToCreateForm = (channelId: number | null) => {
        if (!channelId) {
            setNewCatUploadChannelId(null)
            setNewCatUploadChannelName('')
            setNewCatUploadChannelHandle('')
            return
        }
        const selected = localChannels.find(ch => ch.id === channelId)
        setNewCatUploadChannelId(channelId)
        setNewCatUploadChannelName(selected?.name || '')
        setNewCatUploadChannelHandle(selected?.handle || '')
    }

    const openCategoryChannelConfig = async (category: any) => {
        setChannelConfigCategory(category)
        setChannelConfigForm({
            local_channel_id: category?.upload_channel_id || null,
            name: category?.upload_channel_name || '',
            handle: category?.upload_channel_handle || '',
            proxy: '',
        })
        await fetchLocalUploadChannels()
    }

    const applyLocalChannelToCategoryForm = (channelId: number | null) => {
        if (!channelId) {
            setChannelConfigForm(prev => ({ ...prev, local_channel_id: null, name: '', handle: '' }))
            return
        }
        const selected = localChannels.find(ch => ch.id === channelId)
        setChannelConfigForm(prev => ({
            ...prev,
            local_channel_id: channelId,
            name: selected?.name || '',
            handle: selected?.handle || '',
            proxy: selected?.proxy || '',
        }))
    }

    const handleCreateOrUpdateLocalChannel = async () => {
        if (!channelConfigForm.name.trim() || !channelConfigForm.handle.trim()) {
            alert(isKor ? '채널 이름과 채널 ID(또는 핸들)를 입력해주세요.' : 'Please enter channel name and channel ID/handle.')
            return
        }

        const payload = {
            name: channelConfigForm.name.trim(),
            handle: channelConfigForm.handle.trim(),
            description: `Managed by Admin (${channelConfigForm.name.trim()})`,
            proxy: channelConfigForm.proxy.trim() || null,
        }

        let saved = false
        let lastError = ''
        for (const origin of LOCAL_APP_ORIGINS) {
            try {
                const res = await fetch(`${origin}/api/channels`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                })
                if (!res.ok) {
                    lastError = `HTTP ${res.status}`
                    continue
                }
                const newId = await res.json()
                const resolved = typeof newId === 'number' ? newId : null
                setChannelConfigForm(prev => ({
                    ...prev,
                    local_channel_id: resolved,
                    name: payload.name,
                    handle: payload.handle,
                    proxy: payload.proxy || '',
                }))
                await fetchLocalUploadChannels()
                saved = true
                break
            } catch (err: any) {
                lastError = err?.message || String(err)
            }
        }

        if (!saved) {
            alert((isKor ? '로컬 채널 저장 실패: ' : 'Failed to save local channel: ') + (lastError || 'Unknown error'))
            return
        }

        alert(isKor ? '로컬 채널이 저장되었습니다.' : 'Local channel saved.')
    }

    const handleStartCategoryChannelOAuth = () => {
        if (!channelConfigForm.name.trim() || !channelConfigForm.handle.trim()) {
            alert(isKor ? '먼저 채널 이름과 채널 ID(또는 핸들)를 입력해주세요.' : 'Enter channel name and ID/handle first.')
            return
        }
        const params = new URLSearchParams({
            name: channelConfigForm.name.trim(),
            id: channelConfigForm.handle.trim(),
        })
        if (channelConfigForm.proxy.trim()) {
            params.set('proxy', channelConfigForm.proxy.trim())
        }
        const url = `${LOCAL_APP_ORIGINS[0]}/api/channels/login-by-info?${params.toString()}`
        window.open(url, '_blank', 'noopener,noreferrer,width=560,height=720')
    }

    const handleSaveCategoryChannelBinding = async () => {
        if (!channelConfigCategory) return
        const payload = {
            id: channelConfigCategory.id,
            upload_channel_id: channelConfigForm.local_channel_id,
            upload_channel_name: channelConfigForm.name.trim(),
            upload_channel_handle: channelConfigForm.handle.trim(),
        }
        try {
            const res = await adminFetch('/api/admin/categories', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            })
            const data = await res.json()
            if (!res.ok || !data.success) {
                alert((isKor ? '채널 저장 실패: ' : 'Failed to save channel: ') + (data.error || `HTTP ${res.status}`))
                return
            }
            alert(isKor ? '카테고리 업로드 채널이 저장되었습니다.' : 'Category upload channel saved.')
            setChannelConfigCategory(null)
            fetchCategories(true)
        } catch (err: any) {
            alert((isKor ? '채널 저장 오류: ' : 'Failed to save channel: ') + (err?.message || String(err)))
        }
    }

    const handleRoleChange = async (userId: string, currentRole: string) => {
        if (!canManageSensitiveUserSettings) return;
        const newRole = currentRole === 'pro' ? 'std' : 'pro';
        if (!confirm(isKor ? `등급을 ${newRole === 'pro' ? '프로' : '스탠다드'}로 변경하시겠습니까?` : `Change membership to ${newRole === 'pro' ? 'PRO' : 'STANDARD'}?`)) return;
        try {
            const res = await adminFetch('/api/admin/users/role', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId, membership: newRole })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                // 동기적 업데이트만 사용 (fetchUsers 호출 시 Supabase 캐시로 인해 지연 가능)
                setUsers(prev => prev.map(u =>
                    u.id === userId ? { ...u, app_metadata: { ...u.app_metadata, membership: newRole } } : u
                ));
                alert(isKor ? `${newRole === 'pro' ? 'PRO' : '스탠다드'}로 변경되었습니다.` : 'Role Updated');
            } else {
                alert('변경 실패: ' + (data.error || '서버 오류'));
            }
        } catch (e) { alert('서버 통신 오류'); }
    }

    const handleApprovalChange = async (userId: string, approved: boolean) => {
        if (!confirm(approved ? '이 사용자를 승인할까요?' : '이 사용자를 승인 대기 상태로 돌릴까요?')) return;
        try {
            const res = await adminFetch('/api/admin/users/approval', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId, approved })
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.error || 'approval update failed');
            }
            setUsers(prev => prev.map(u => u.id === userId
                ? {
                    ...u,
                    profile: {
                        ...u.profile,
                        is_approved: approved,
                        signup_status: approved ? 'approved' : 'pending'
                    }
                }
                : u
            ));
        } catch (e: any) {
            alert('승인 상태 변경 실패: ' + (e?.message || String(e)));
        }
    }

    const handleSaveUserInfo = async () => {
        if (!editInfoUser) return;
        try {
            const res = await adminFetch('/api/admin/users/update-metadata', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    userId: editInfoUser.id,
                    metadata: {
                        ...(editInfoForm.full_name  && { full_name:   editInfoForm.full_name }),
                        ...(editInfoForm.nationality && { nationality: editInfoForm.nationality }),
                        ...(editInfoForm.contact    && { contact:     editInfoForm.contact }),
                        preferred_languages: editInfoForm.preferred_languages?.length ? editInfoForm.preferred_languages : ['ko'],
                        persona_name: editInfoForm.persona_name || '',
                        persona_style: editInfoForm.persona_style || '',
                        persona_description: editInfoForm.persona_description || ''
                    }
                })
            });
            const data = await res.json();
            if (data.success) {
                setUsers(prev => prev.map(u => u.id === editInfoUser.id
                    ? {
                        ...u,
                        user_metadata: { ...u.user_metadata, ...editInfoForm },
                        profile: {
                            ...u.profile,
                            preferred_languages: editInfoForm.preferred_languages?.length ? editInfoForm.preferred_languages : ['ko'],
                            persona_name: editInfoForm.persona_name || '',
                            persona_style: editInfoForm.persona_style || '',
                            persona_description: editInfoForm.persona_description || ''
                        }
                      }
                    : u
                ));
                setEditInfoUser(null);
                alert('저장되었습니다.');
            } else {
                alert('저장 실패: ' + (data.error || '서버 오류'));
            }
        } catch (e) { alert('서버 오류'); }
    };

    const handleAdminRoleToggle = async (userId: string, currentIsAdmin: boolean) => {
        if (!isSuperAdmin) return;
        const action = currentIsAdmin ? '해제' : '지정';
        if (!confirm(`해당 유저를 부관리자로 ${action}하시겠습니까?`)) return;
        try {
            const res = await adminFetch('/api/admin/users/admin-role', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId, isAdmin: !currentIsAdmin })
            });
            if (res.ok) { alert('완료되었습니다.'); fetchUsers(); }
        } catch (e) { alert('오류가 발생했습니다.'); }
    }

    const handleSuperadminToggle = async (userId: string, currentIsSuperadmin: boolean | undefined) => {
        if (!isSuperAdmin) return;
        const action = currentIsSuperadmin ? '해제' : '지정';
        if (!confirm(`해당 유저를 슈퍼어드민으로 ${action}하시겠습니까?`)) return;
        try {
            const res = await adminFetch('/api/admin/users/superadmin', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId, isSuperAdmin: !currentIsSuperadmin })
            });
            if (res.ok) {
                alert('완료되었습니다.');
                fetchUsers();
            } else {
                alert('실패: ' + (await res.text()));
            }
        } catch (e) {
            alert('오류가 발생했습니다.');
        }
    }

    const handlePublishVideo = async (requestId: string) => {
        if (!confirm(isKor ? '이 영상을 유튜브에서 공개(Public)로 전환하시겠습니까?' : 'Would you like to switch this video to Public on YouTube?')) return;
        try {
            const res = await adminFetch('/api/admin/publishing', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ requestId, status: 'approved' })
            });
            if (res.ok) {
                alert(isKor ? '전환 요청 완료! 잠시 후 유튜브에 반영됩니다.' : 'Request Complete! Will reflect on YouTube shortly.');
                fetchPublishingRequests();
            } else {
                alert('요청 실패');
            }
        } catch (e) { alert('오류 발생'); }
    }

    const renderPublishingActionPanel = (req: PublishingRequest) => {
        const meta = req.metadata || {}
        const quickLinks = [
            { label: 'YouTube', href: meta.youtube_url || (meta.videoId ? `https://youtu.be/${meta.videoId}` : null), tone: 'blue' },
            { label: 'Drive', href: meta.drive_folder_link, tone: 'gray' },
            { label: 'Thumb', href: meta.drive_thumbnail_link, tone: 'gray' },
            { label: 'JSON', href: meta.drive_metadata_link, tone: 'gray' },
        ].filter(item => item.href)

        const toneClass = (tone: string) =>
            tone === 'blue'
                ? 'bg-blue-600/20 text-blue-300 border-blue-500/20 hover:bg-blue-600/30'
                : 'bg-white/5 text-gray-300 border-white/10 hover:bg-white/10 hover:text-white'

        return (
            <div className="max-w-[280px] w-full rounded-2xl border border-white/10 bg-black/20 px-3 py-3">
                <div className="text-[9px] font-black uppercase tracking-[0.28em] text-gray-500 text-left mb-2">
                    {isKor ? '빠른 바로가기' : 'Quick Access'}
                </div>
                <div className="mb-3 space-y-1 text-left">
                    {meta.project_id && (
                        <div className="text-[10px] font-black text-gray-300">
                            PROJECT ID <span className="ml-1 font-mono text-white">{meta.project_id}</span>
                        </div>
                    )}
                    {meta.app_mode && (
                        <div className="text-[10px] font-black text-gray-500">
                            MODE <span className="ml-1 font-mono text-gray-300">{meta.app_mode}</span>
                        </div>
                    )}
                    {meta.drive_video_file_id && (
                        <div className="text-[10px] font-black text-gray-500 break-all">
                            VIDEO FILE <span className="ml-1 font-mono text-gray-300">{meta.drive_video_file_id}</span>
                        </div>
                    )}
                    {meta.drive_thumbnail_file_id && (
                        <div className="text-[10px] font-black text-gray-500 break-all">
                            THUMB FILE <span className="ml-1 font-mono text-gray-300">{meta.drive_thumbnail_file_id}</span>
                        </div>
                    )}
                    {meta.drive_metadata_file_id && (
                        <div className="text-[10px] font-black text-gray-500 break-all">
                            META FILE <span className="ml-1 font-mono text-gray-300">{meta.drive_metadata_file_id}</span>
                        </div>
                    )}
                    {meta.track_count ? (
                        <div className="text-[10px] font-black text-gray-500">
                            TRACKS <span className="ml-1 font-mono text-gray-300">{meta.track_count}</span>
                        </div>
                    ) : null}
                    {meta.total_duration_seconds ? (
                        <div className="text-[10px] font-black text-gray-500">
                            TOTAL MIN <span className="ml-1 font-mono text-gray-300">{Math.round(Number(meta.total_duration_seconds || 0) / 60)}</span>
                        </div>
                    ) : null}
                </div>
                <div className="mb-3 flex justify-end">
                    {isSuperAdmin && req.status === 'pending' && !req.metadata?.is_invalid_request && (
                        <button
                            onClick={() => handlePublishVideo(req.id)}
                            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-[10px] font-black rounded-xl shadow-lg transition-all uppercase tracking-widest"
                        >
                            {isKor ? '발행 시작' : 'Publish'}
                        </button>
                    )}
                    {req.status === 'pending' && req.metadata?.is_invalid_request && (
                        <span className="px-4 py-2 bg-red-500/10 text-red-300 text-[10px] font-black rounded-xl border border-red-500/20 inline-block uppercase tracking-widest">
                            PROJECT ID MISSING
                        </span>
                    )}
                    {req.status === 'published' && req.metadata?.drive_folder_link && (
                        <a
                            href={req.metadata.drive_folder_link}
                            target="_blank"
                            rel="noreferrer"
                            className="px-4 py-2 bg-white/5 hover:bg-white/10 text-gray-300 hover:text-white text-[10px] font-black rounded-xl border border-white/10 transition-all uppercase tracking-widest inline-block"
                        >
                            {isKor ? '백업 확인' : 'Backup'}
                        </a>
                    )}
                </div>
                {quickLinks.length > 0 ? (
                    <div className="flex flex-wrap gap-2 justify-end">
                        {quickLinks.map(item => (
                            <a
                                key={`${req.id}-${item.label}-quick`}
                                href={item.href}
                                target="_blank"
                                rel="noreferrer"
                                className={`px-3 py-1.5 text-[10px] font-black rounded-xl border transition-all ${toneClass(item.tone)}`}
                            >
                                {item.label}
                            </a>
                        ))}
                    </div>
                ) : (
                    <div className="text-[10px] font-bold text-gray-600 text-left">{isKor ? '연결된 자산이 없습니다.' : 'No linked assets'}</div>
                )}
            </div>
        )
    }

    const getPublishingStatusMeta = (req: PublishingRequest) => {
        if (req.metadata?.is_invalid_request) return { label: 'INVALID', className: 'bg-red-500/15 text-red-400 border-red-500/30 font-black' }
        if (req.status === 'published') return { label: isKor ? '✓ 업로드 완료' : '✓ Published', className: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30 font-black' }
        if (req.status === 'approved' || req.status === 'to_be_published') return { label: isKor ? '⚡ 발행 진행 중' : '⚡ Publishing', className: 'bg-blue-500/15 text-blue-400 border-blue-500/30 font-black animate-pulse' }
        if (req.status === 'failed') return { label: isKor ? '❌ 업로드 실패' : '❌ Failed', className: 'bg-red-500/15 text-red-400 border-red-500/30 font-black' }
        if (req.status === 'rejected') return { label: isKor ? '🚫 제외됨' : '🚫 Rejected', className: 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30 font-black' }
        return { label: isKor ? '⏳ 대기중' : '⏳ Pending', className: 'bg-orange-500/15 text-orange-400 border-orange-500/30 font-black' }
    }

    const publishingSummary = useMemo(() => {
        return publishingRequests.reduce((acc, req) => {
            acc.total += 1
            if (req.metadata?.is_invalid_request) acc.invalid += 1
            else if (req.status === 'published') acc.published += 1
            else if (req.status === 'approved' || req.status === 'to_be_published') acc.processing += 1
            else if (req.status === 'failed') acc.failed += 1
            else acc.pending += 1
            return acc
        }, { total: 0, pending: 0, processing: 0, published: 0, failed: 0, invalid: 0 })
    }, [publishingRequests])

    const filteredPublishingRequests = useMemo(() => {
        if (publishingFilter === 'all') return publishingRequests
        if (publishingFilter === 'invalid') return publishingRequests.filter(req => Boolean(req.metadata?.is_invalid_request))
        if (publishingFilter === 'processing') return publishingRequests.filter(req => req.status === 'approved' || req.status === 'to_be_published')
        return publishingRequests.filter(req => req.status === publishingFilter)
    }, [publishingRequests, publishingFilter])

    const calcGeneralStats = (logs: any[], days: number) => {
        const coreTasks = ['video', 'image', 'script', 'text_gen', 'vision_gen', 'subtitle_fix'];
        const breakdown: any = {};
        let totalThinkingTokens = 0;
        coreTasks.forEach(task => {
            breakdown[task] = { tokens: 0, count: 0, buckets: new Array(days === 1 ? 24 : days).fill(0).map(() => ({ tokens: 0, count: 0 })) };
        });
        if (!logs || !logs.length) return { total: 0, successRate: 0, avgLatency: 0, totalTokens: 0, totalThinkingTokens: 0, breakdown };
        const total = logs.length;
        const successes = logs.filter(l => (l.task_type !== 'RECHARGE' && ((l.status || '').toLowerCase() === 'success' || (l.status || '').toLowerCase() === 'done'))).length;
        const tokens = logs.reduce((acc, l) => acc + (l.task_type === 'RECHARGE' ? 0 : (l.input_tokens || 0) + (l.output_tokens || 0) + (l.thinking_tokens || 0)), 0);
        logs.forEach(l => {
            if (l.task_type === 'RECHARGE') return;
            let stage = (l.task_type || 'unknown').toLowerCase();
            if (stage === 'test_after_fix') {
                stage = 'subtitle_fix';
            }
            if (!breakdown[stage]) breakdown[stage] = { tokens: 0, count: 0, buckets: new Array(days === 1 ? 24 : days).fill(0).map(() => ({ tokens: 0, count: 0 })) };
            const t = (l.input_tokens || 0) + (l.output_tokens || 0) + (l.thinking_tokens || 0);
            breakdown[stage].tokens += t;
            breakdown[stage].count += 1;
            totalThinkingTokens += (l.thinking_tokens || 0);
        });
        const avgLat = total > 0 ? parseFloat((logs.reduce((acc, l) => acc + (l.elapsed_time || 0), 0) / total).toFixed(1)) : 0;
        return { total, successRate: total > 0 ? Math.round((successes / total)*100) : 0, avgLatency: avgLat, totalTokens: tokens, totalThinkingTokens, breakdown };
    }

    const fetchGlobalStats = useCallback(async (days: number) => {
        if (!isAdmin) return;
        setGlobalLoading(true);
        try {
            const res = await adminFetch(`/api/admin/logs?days=${days}&t=${Date.now()}`);
            const data = await res.json();
            setGlobalLogs(data.logs || []);
            setGlobalStats(calcGeneralStats(data.logs || [], days));
        } finally { setGlobalLoading(false); }
    }, [isAdmin, adminFetch]);

    
    const fetchWithdrawals = useCallback(async () => {
        try {
            const res = await adminFetch(`/api/admin/withdrawals?t=${Date.now()}`);
            const data = await res.json();
            if (data.withdrawals) {
                setWithdrawals(data.withdrawals);
            }
        } catch (e) {
            console.error("fetchWithdrawals error:", e);
        }
    }, [adminFetch]);

    const updateWithdrawalStatus = async (id: string, newStatus: 'completed' | 'rejected') => {
        const actionText = newStatus === 'completed' ? '완료' : '거절';
        if (!confirm(`정말로 이 출금 요청을 ${actionText} 처리하시겠습니까?`)) return
        
        try {
            const res = await adminFetch('/api/admin/withdrawals', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id, status: newStatus })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                alert('출금 상태가 업데이트 되었습니다.')
                fetchWithdrawals()
            } else {
                alert('상태 업데이트 실패: ' + (data.error || '알 수 없는 오류'))
            }
        } catch (e) {
            console.error("updateWithdrawalStatus error:", e);
            alert('오류가 발생했습니다.')
        }
    }

        const fetchPublishingRequests = useCallback(async () => {
        if (!isAdmin) return;
        try {
            const res = await adminFetch(`/api/admin/publishing?t=${Date.now()}`);
            const data = await res.json();
            if (data.requests) setPublishingRequests(data.requests);
        } catch (e) {}
    }, [isAdmin, adminFetch]);

    const fetchUserLogs = async (userId: string, days: number) => {
        setLogsLoading(true);
        try {
            const res = await adminFetch(`/api/admin/users/${userId}/logs?days=${days}&t=${Date.now()}`);
            const data = await res.json();
            setUserLogs(data.logs || []);
            setLogStats(calcGeneralStats(data.logs || [], days));
        } finally { setLogsLoading(false); }
    }

    const fetchUsers = useCallback(async () => {
        if (!isAdmin) return;
        try {
            const res = await adminFetch(`/api/admin/users?t=${Date.now()}`);
            const data = await res.json();
            if (data.users) setUsers(data.users);
        } catch (e) { console.error("FetchUsers Error:", e); }
    }, [isAdmin, adminFetch]);

    const fetchReferralReport = useCallback(async (days: number = referralDays) => {
        if (!isAdmin) return;
        setReferralLoading(true);
        try {
            const res = await adminFetch(`/api/admin/referrals?days=${days}&t=${Date.now()}`);
            const data = await res.json();
            if (res.ok) setReferralReport(data);
        } catch (e) {
            console.error('fetchReferralReport error:', e);
        } finally {
            setReferralLoading(false);
        }
    }, [isAdmin, adminFetch, referralDays]);

    const copyReferralCode = async (code: string) => {
        if (!code) return;
        const link = `${window.location.origin}/?ref=${code}`;
        await navigator.clipboard?.writeText(link);
        alert(isKor ? '추천 링크가 복사되었습니다.' : 'Referral link copied.');
    }

    const handleCountryManagerUpdate = async (profile: any) => {
        if (!isSuperAdmin) return;
        const country = prompt('관리 국가 코드(예: VN, KR)', profile.referral_country || profile.country_code || 'KR');
        if (!country) return;
        const rateText = prompt('국가 책임자 커미션율(%)', String(profile.commission_rate || 1));
        if (rateText === null) return;
        const res = await adminFetch('/api/admin/referrals', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                userId: profile.id,
                country_code: country,
                referral_country: country,
                commission_rate: Number(rateText) || 0,
                make_country_manager: true,
            })
        });
        const data = await res.json();
        if (!res.ok || !data.success) {
            alert('국가 책임자 지정 실패: ' + (data.error || `HTTP ${res.status}`));
            return;
        }
        alert('국가 책임자로 지정되었습니다.');
        fetchReferralReport(referralDays);
        fetchUsers();
    }

    const buildReferralTreeRows = (profiles: any[]) => {
        const byId = new Map((profiles || []).map(profile => [String(profile.id), profile]));
        const depthOf = (profile: any) => {
            let depth = Number(profile?.referral_depth || 0);
            let parentId = profile?.referred_by ? String(profile.referred_by) : '';
            let guard = 0;
            while (parentId && byId.has(parentId) && guard < 10) {
                depth += 1;
                parentId = byId.get(parentId)?.referred_by ? String(byId.get(parentId).referred_by) : '';
                guard += 1;
            }
            return Math.min(depth, 8);
        };
        return [...(profiles || [])].sort((a, b) => depthOf(a) - depthOf(b) || String(a.email || '').localeCompare(String(b.email || '')));
    }

    const fetchSysKeys = useCallback(async () => {
        if (!canManageSystemSettings) return;
        try {
            const res = await adminFetch('/api/admin/settings/global');
            if (!res.ok) return;
            const data = await res.json();
            setSysKeys({
                gemini: data.gemini || '',
                youtube: data.youtube || '',
                elevenlabs: data.elevenlabs || '',
                suno: data.suno || '',
                suno_base_url: data.suno_base_url || '',
                music_provider: data.music_provider || 'elevenlabs',
                music_gemini_model: data.music_gemini_model || 'lyria-3-pro-preview',
                music_gemini_base_url: data.music_gemini_base_url || '',
                music_gemini_project_id: data.music_gemini_project_id || '',
                music_gemini_location: data.music_gemini_location || 'global',
                topview: data.topview || '',
                topview_uid: data.topview_uid || '',
                longform_min_duration_minutes: data.longform_min_duration_minutes || '15',
                longform_base_payout: data.longform_base_payout || '10000',
                longform_extra_minute_payout: data.longform_extra_minute_payout || '500',
                longform_duration_lock_enabled: data.longform_duration_lock_enabled || 'true',
                binance_api_key: data.binance_api_key || '',
                binance_api_secret: data.binance_api_secret || '',
                qa_enable_pipeline: data.qa_enable_pipeline || 'true',
                qa_enable_technical_check: data.qa_enable_technical_check || 'true',
                qa_enable_semantic_check: data.qa_enable_semantic_check || 'false',
                qa_auto_normalize_lufs: data.qa_auto_normalize_lufs || 'true',
                qa_hold_on_technical_fail: data.qa_hold_on_technical_fail || 'true',
                qa_hold_on_semantic_fail: data.qa_hold_on_semantic_fail || 'true',
                qa_target_lufs: data.qa_target_lufs || '-14',
                qa_lufs_tolerance: data.qa_lufs_tolerance || '2',
                qa_blackdetect_min_duration: data.qa_blackdetect_min_duration || '1.0',
                qa_min_width: data.qa_min_width || '1920',
                qa_min_height: data.qa_min_height || '1080',
                terms_ko: data.terms_ko || '',
                terms_en: data.terms_en || '',
                terms_vi: data.terms_vi || '',
                terms_th: data.terms_th || '',
                privacy_ko: data.privacy_ko || '',
                privacy_en: data.privacy_en || '',
                privacy_vi: data.privacy_vi || '',
                privacy_th: data.privacy_th || ''
            });
        } catch (e) { console.error('fetchSysKeys error:', e); }
    }, [canManageSystemSettings, adminFetch]);

    const saveSysKeys = async () => {
        setSysKeysSaving(true); setSysKeysSaved(false);
        try {
            const res = await adminFetch('/api/admin/settings/global', {
                method: 'POST', 
                headers: { 'Content-Type': 'application/json' }, 
                body: JSON.stringify({ ...sysKeys }) 
            });
            if (res.ok) setSysKeysSaved(true);
        } catch (e) { console.error('saveSysKeys error:', e); }
        finally { setSysKeysSaving(false); }
    };

    const fetchRenderQueue = useCallback(async () => {
        if (!isAdmin) return;
        setQueueLoading(true);
        try {
            const res = await adminFetch(`/api/admin/render-queue?t=${Date.now()}`);
            const data = await res.json();
            if (data.success && data.queue) setRenderQueue(data.queue);
        } catch (e) {
            console.error("fetchRenderQueue error:", e);
        } finally {
            setQueueLoading(false);
        }
    }, [isAdmin, adminFetch]);

    const handleDeleteQueueTask = async (id: string) => {
        if (!confirm(isKor ? '이 작업을 대기열에서 삭제하시겠습니까?' : 'Delete this render task from the queue?')) return;
        try {
            const res = await adminFetch(`/api/admin/render-queue?id=${id}`, { method: 'DELETE' });
            const data = await res.json();
            if (data.success) {
                alert(isKor ? '삭제되었습니다.' : 'Deleted successfully');
                fetchRenderQueue();
            } else {
                alert('삭제 실패: ' + (data.error || '오류'));
            }
        } catch (e) {
            alert('오류 발생');
        }
    };

    const fetchCategories = useCallback(async (background = false) => {
        const shouldShowBlockingLoader = !hasLoadedCategoriesRef.current && !background
        try {
            if (shouldShowBlockingLoader) setCategoriesLoading(true)
            const res = await adminFetch('/api/admin/categories')
            const data = await res.json()
            if (data.categories) {
                setCategories(data.categories)
                hasLoadedCategoriesRef.current = true
            }
        } catch (e) {
            console.error("Failed to load categories:", e)
        } finally {
            if (shouldShowBlockingLoader) setCategoriesLoading(false)
        }
    }, [adminFetch])

    const fetchTopics = useCallback(async () => {
        try {
            const res = await adminFetch('/api/admin/topics-queue')
            const data = await res.json()
            if (data.topics) setTopics(data.topics)
        } catch (e) {
            console.error("Failed to load topics:", e)
        }
    }, [adminFetch])

    const fetchStylePresets = async () => {
        try {
            setPresetsLoading(true)
            const res = await adminFetch('/api/admin/style-presets')
            const data = await res.json()
            if (data.presets) setStylePresets(data.presets)
        } catch (e) {
            console.error("Failed to load style presets:", e)
        } finally {
            setPresetsLoading(false)
        }
    }

    const handleSavePreset = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!presetType || !presetKeyCode || !presetNameKo || !presetPromptTemplate) {
            alert('필수 입력 항목을 채워주세요.')
            return
        }
        try {
            setIsSavingPreset(true)
            const res = await adminFetch('/api/admin/style-presets', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    id: presetId || undefined,
                    preset_type: presetType,
                    key_code: presetKeyCode.trim().toLowerCase(),
                    display_name_ko: presetNameKo,
                    display_name_vi: presetNameVi,
                    prompt_template: presetPromptTemplate,
                    gemini_instruction: presetGeminiInstruction,
                    image_url: presetImageUrl
                })
            })
            const data = await res.json()
            if (data.success) {
                alert('스타일 프리셋이 저장되었습니다.')
                setPresetId(null)
                setPresetKeyCode('')
                setPresetNameKo('')
                setPresetNameVi('')
                setPresetPromptTemplate('')
                setPresetGeminiInstruction('')
                setPresetImageUrl('')
                fetchStylePresets()
            } else {
                alert('저장 실패: ' + (data.error || '알 수 없는 오류'))
            }
        } catch (e: any) {
            alert('저장 오류: ' + e.message)
        } finally {
            setIsSavingPreset(false)
        }
    }

    const presetFormRef = useRef<HTMLDivElement>(null)

    const handleEditPreset = (preset: any) => {
        setPresetId(preset.id)
        setPresetType(preset.preset_type)
        setPresetKeyCode(preset.key_code)
        setPresetNameKo(preset.display_name_ko)
        setPresetNameVi(preset.display_name_vi || '')
        setPresetPromptTemplate(preset.prompt_template)
        setPresetGeminiInstruction(preset.gemini_instruction || '')
        setPresetImageUrl(preset.image_url || '')
        // 폼으로 자동 스크롤
        setTimeout(() => {
            presetFormRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }, 50)
    }

    const handleDeletePreset = async (id: string, keyCode: string) => {
        if (!confirm(`"${keyCode}" 스타일 프리셋을 삭제하시겠습니까?`)) return
        try {
            const res = await adminFetch(`/api/admin/style-presets?id=${id}`, {
                method: 'DELETE'
            })
            const data = await res.json()
            if (data.success) {
                alert('성공적으로 삭제되었습니다.')
                fetchStylePresets()
            } else {
                alert('삭제 실패: ' + (data.error || '알 수 없는 오류'))
            }
        } catch (e: any) {
            alert('삭제 오류: ' + e.message)
        }
    }

    const handleCreateCategory = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!canManageTopics) return
        if (!newCatName) {
            alert('카테고리명은 필수입니다.')
            return
        }
        try {
            const res = await adminFetch('/api/admin/categories', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: newCatName,
                    keywords: newCatKeywords,
                    benchmark_channel_url: newCatChannel,
                    assigned_employee_email: newCatEmployee || null,
                    default_script_style: newCatScriptStyle || 'default',
                    default_image_style: newCatImageStyle || 'realistic',
                    language: normalizeContentLanguage(newCatLanguage),
                    video_type: newCatVideoType,
                    upload_channel_id: newCatUploadChannelId,
                    upload_channel_name: newCatUploadChannelName,
                    upload_channel_handle: newCatUploadChannelHandle,
                })
            })
            const data = await res.json()
            if (data.success) {
                setNewCatName('')
                setNewCatKeywords('')
                setNewCatChannel('')
                setNewCatEmployee('')
                setNewCatScriptStyle('default')
                setNewCatImageStyle('realistic')
                setNewCatLanguage('ko')
                setNewCatVideoType('longform')
                setNewCatUploadChannelId(null)
                setNewCatUploadChannelName('')
                setNewCatUploadChannelHandle('')
                fetchCategories(true)
                fetchTopics()
                alert('카테고리가 성공적으로 등록되었으며, 기본 샘플 주제 3개가 적재되었습니다.')
            } else {
                alert('카테고리 등록 실패: ' + data.error)
            }
        } catch (err) {
            console.error(err)
            alert('서버 등록 에러 발생')
        }
    }

    const handleDeleteCategory = async (id: number) => {
        if (!canManageTopics) return
        if (!confirm('정말 이 카테고리를 삭제하시겠습니까? 관련된 데이터도 함께 삭제됩니다.')) return
        try {
            const res = await adminFetch(`/api/admin/categories?id=${id}`, {
                method: 'DELETE'
            })
            const data = await res.json()
            if (data.success) {
                fetchCategories(true)
                fetchTopics()
            } else {
                alert('삭제 실패: ' + data.error)
            }
        } catch (err) {
            console.error(err)
        }
    }

    const handleSaveCategory = async () => {
        if (!canManageTopics) return
        if (!editCategory) return
        if (!editCatForm.name || !editCatForm.assigned_employee_email) {
            alert('카테고리명과 해당 직원 이메일은 필수입니다.')
            return
        }
        try {
            const res = await adminFetch('/api/admin/categories', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    id: editCategory.id,
                    ...editCatForm
                })
            })
            const data = await res.json()
            if (data.success) {
                alert('성공적으로 수정되었습니다.')
                setEditCategory(null)
                fetchCategories(true)
                fetchTopics()
            } else {
                alert('수정 실패: ' + data.error)
            }
        } catch (err) {
            console.error(err)
            alert('서버 수정 에러 발생')
        }
    }

    const handleTriggerAiTopics = async (catId: number) => {
        if (!canManageTopics) return
        setGeneratingCatId(catId)
        try {
            const res = await adminFetch('/api/admin/topics-queue', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ categoryId: catId })
            })
            const data = await res.json()
            if (data.success) {
                const generatedTopics = Array.isArray(data.topics) ? data.topics.map((topic: any) => typeof topic === 'string' ? topic : (topic?.topic || '')).slice(0, 10) : []
                setGeneratedTopicsByCat(prev => ({ ...prev, [catId]: generatedTopics }))
                fetchTopics()
                alert(`AI가 새로운 영상 주제 ${data.count}개를 성공적으로 생성하여 큐에 추가했습니다!`)
            } else {
                alert('AI 생성 실패: ' + data.error)
            }
        } catch (err) {
            console.error(err)
            alert('AI 생성 요청 오류')
        } finally {
            setGeneratingCatId(null)
        }
    }

    const startEditingTopic = (topicItem: any) => {
        if (!canManageTopics) return
        const currentTopic = String(topicItem?.topic || '').trim()
        if (!topicItem?.id || !currentTopic) return
        setEditingTopicId(String(topicItem.id))
        setEditingTopicDraft(currentTopic)
    }

    const cancelEditingTopic = () => {
        setEditingTopicId(null)
        setEditingTopicDraft('')
    }

    const handleTopicEditorKeyDown = async (
        e: React.KeyboardEvent<HTMLInputElement>,
        topicItem: any
    ) => {
        if (e.key === 'Escape') {
            e.preventDefault()
            cancelEditingTopic()
            return
        }

        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            if (topicActionLoadingId === String(topicItem?.id)) return
            await handleEditTopic(topicItem)
        }
    }

    const handleEditTopic = async (topicItem: any) => {
        if (!canManageTopics) return
        const currentTopic = String(topicItem?.topic || '').trim()
        if (!topicItem?.id || !currentTopic) return

        const trimmed = editingTopicDraft.trim()
        if (!trimmed) {
            alert('주제는 비워둘 수 없습니다.')
            return
        }

        if (trimmed === currentTopic) return

        setTopicActionLoadingId(String(topicItem.id))
        try {
            const res = await adminFetch('/api/admin/topics-queue', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: topicItem.id, topic: trimmed })
            })
            const data = await res.json()
            if (!res.ok || !data.success) {
                alert('주제 수정 실패: ' + (data.error || `HTTP ${res.status}`))
                return
            }

            setTopics(prev => prev.map(item => item.id === topicItem.id ? { ...item, topic: trimmed } : item))
            setGeneratedTopicsByCat(prev => {
                const list = prev[topicItem.category_id]
                if (!Array.isArray(list) || list.length === 0) return prev
                return {
                    ...prev,
                    [topicItem.category_id]: list.map(text => text === currentTopic ? trimmed : text)
                }
            })
            cancelEditingTopic()
        } catch (err: any) {
            alert('주제 수정 오류: ' + (err?.message || String(err)))
        } finally {
            setTopicActionLoadingId(null)
        }
    }

    const handleDeleteTopic = async (topicItem: any) => {
        if (!canManageTopics) return
        if (!topicItem?.id) return
        if (!confirm('이 대기중 주제를 삭제할까요?')) return

        setTopicActionLoadingId(String(topicItem.id))
        try {
            const res = await adminFetch(`/api/admin/topics-queue?id=${topicItem.id}`, {
                method: 'DELETE'
            })
            const data = await res.json()
            if (!res.ok || !data.success) {
                alert('주제 삭제 실패: ' + (data.error || `HTTP ${res.status}`))
                return
            }

            setTopics(prev => prev.filter(item => item.id !== topicItem.id))
            setGeneratedTopicsByCat(prev => {
                const list = prev[topicItem.category_id]
                if (!Array.isArray(list) || list.length === 0) return prev
                return {
                    ...prev,
                    [topicItem.category_id]: list.filter(text => text !== topicItem.topic)
                }
            })
            if (editingTopicId === String(topicItem.id)) {
                cancelEditingTopic()
            }
        } catch (err: any) {
            alert('주제 삭제 오류: ' + (err?.message || String(err)))
        } finally {
            setTopicActionLoadingId(null)
        }
    }

    const handleDeleteTopicsByYears = async (categoryId: number, years: string[] = ['2024', '2025']) => {
        if (!canManageTopics) return
        const label = years.join(', ')
        if (!confirm(`이 카테고리의 대기중 주제 중 ${label} 연도가 들어간 항목을 일괄 삭제할까요?`)) return

        setTopicActionLoadingId(`cleanup-${categoryId}`)
        try {
            const params = new URLSearchParams({
                categoryId: String(categoryId),
                years: years.join(','),
            })
            const res = await adminFetch(`/api/admin/topics-queue?${params.toString()}`, {
                method: 'DELETE'
            })
            const data = await res.json()
            if (!res.ok || !data.success) {
                alert('연도 주제 정리 실패: ' + (data.error || `HTTP ${res.status}`))
                return
            }

            const deletedIdSet = new Set((data.deletedIds || []).map((id: any) => String(id)))
            setTopics(prev => prev.filter(item => !deletedIdSet.has(String(item.id))))

            if (editingTopicId && deletedIdSet.has(editingTopicId)) {
                cancelEditingTopic()
            }

            alert(`${data.deletedCount || 0}개의 오래된 연도 대기주제를 삭제했습니다.`)
        } catch (err: any) {
            alert('연도 주제 정리 오류: ' + (err?.message || String(err)))
        } finally {
            setTopicActionLoadingId(null)
        }
    }

    const handleAssignTopicStyles = async (targetType: 'script' | 'image') => {
        if (!canManageTopics) return
        const label = targetType === 'script' ? '대본 스타일' : '이미지 스타일'
        const categoryLabel = topicQueueCategoryFilter === 'all' ? '전체 카테고리' : '선택한 카테고리'
        if (!confirm(`${categoryLabel}의 대기중 주제에 ${label}을 AI로 재배정할까요?`)) return

        setTopicStyleAssigningType(targetType)
        try {
            const res = await adminFetch('/api/admin/topics-queue', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    targetType,
                    categoryId: topicQueueCategoryFilter,
                    limit: 100,
                })
            })
            const data = await res.json()
            if (!res.ok || !data.success) {
                alert(`${label} 자동배정 실패: ` + (data.error || `HTTP ${res.status}`))
                return
            }

            const styleField = targetType === 'script' ? 'assigned_script_style' : 'assigned_image_style'
            const updateMap = new Map((data.updates || []).map((item: any) => [String(item.id), item.style]))
            setTopics(prev => prev.map(item => {
                const nextStyle = updateMap.get(String(item.id))
                return nextStyle ? { ...item, [styleField]: nextStyle } : item
            }))
            alert(`${label} 자동배정 완료: ${data.updatedCount || 0}개 주제`)
        } catch (err: any) {
            alert(`${label} 자동배정 오류: ` + (err?.message || String(err)))
        } finally {
            setTopicStyleAssigningType(null)
        }
    }


    useEffect(() => {
        if (activeTab === 'withdrawals') {
            fetchWithdrawals();
        }
    }, [activeTab, fetchWithdrawals]);

    useEffect(() => {
        if (activeTab === 'render-queue') {
            fetchRenderQueue();
            const interval = setInterval(fetchRenderQueue, 3000); // 3초 간격 실시간 갱신
            return () => clearInterval(interval);
        }
    }, [activeTab, fetchRenderQueue]);

    useEffect(() => {
        supabase.auth.getSession().then(({ data: { session } }) => {
            if (!session) router.push('/');
            else {
                setUser(session.user);
                setAuthToken(session.access_token || '');
            }
            setLoading(false);
        });
    }, [router]);

    useEffect(() => {
        if (!user || isAdmin || !authToken) return;
        adminFetch('/api/referrals')
            .then(res => res.ok ? res.json() : null)
            .then(data => { if (data) setUserReferralInfo(data); })
            .catch(err => console.error('user referral fetch error:', err));
    }, [user, isAdmin, authToken, adminFetch]);

    // 초기 데이터 로딩을 위한 Effect
    useEffect(() => {
        if (isAdmin && !loading) {
            fetchUsers();
            fetchReferralReport(referralDays);
            fetchGlobalStats(globalPeriod);
            fetchPublishingRequests();
            if (canManageSystemSettings) fetchSysKeys();
            fetchCategories();
            fetchTopics();
            if (canManageStyles) fetchStylePresets();
        }
    }, [isAdmin, loading, globalPeriod, referralDays, fetchUsers, fetchReferralReport, fetchGlobalStats, fetchPublishingRequests, fetchSysKeys, fetchCategories, fetchTopics, fetchStylePresets, canManageSystemSettings, canManageStyles]);

    // 기간 변경 시에만 별도 호출
    useEffect(() => {
        if (isAdmin && !loading) {
            fetchGlobalStats(globalPeriod);
        }
    }, [globalPeriod]);

    if (loading) return <div className="min-h-screen bg-[#050505] text-white flex items-center justify-center font-black animate-pulse uppercase tracking-[0.5em]">{ui.authenticating}</div>;
    if (!isAdmin) return (
        <div className="min-h-screen bg-[#050505] text-white flex items-center justify-center p-6">
            <div className="max-w-2xl w-full rounded-[2.5rem] border border-white/10 bg-[#0f172a]/70 p-8 shadow-2xl">
                <div className="mb-6 flex items-center justify-between gap-4">
                    <div>
                        <h1 className="text-3xl font-black tracking-tight">{language === 'th' ? 'รหัสแนะนำของฉัน' : '내 추천 코드'}</h1>
                        <p className="mt-2 text-xs font-bold text-gray-500">{language === 'th' ? 'แชร์ลิงก์แนะนำและตรวจสอบผลงานผู้ใช้ที่คุณแนะนำโดยตรง' : '추천 링크를 공유하고 직속 추천인 성과를 확인하세요.'}</p>
                    </div>
                    <button onClick={() => supabase.auth.signOut().then(() => router.push('/'))} className="rounded-xl border border-white/10 bg-white/5 px-5 py-2 text-[10px] font-black text-gray-300 hover:bg-white/10">{ui.logout}</button>
                </div>
                <div className="rounded-2xl border border-cyan-500/20 bg-cyan-500/10 p-6">
                    <div className="text-[10px] font-black uppercase tracking-widest text-cyan-300">Referral Code</div>
                    <div className="mt-2 flex items-center gap-3">
                        <span className="text-4xl font-black text-white tracking-widest">{userReferralInfo?.profile?.referral_code || '준비 중'}</span>
                        {userReferralInfo?.profile?.referral_code && (
                            <button onClick={() => copyReferralCode(userReferralInfo.profile.referral_code)} className="rounded-xl bg-cyan-500 px-4 py-2 text-[10px] font-black text-white">{language === 'th' ? 'คัดลอก' : '복사'}</button>
                        )}
                    </div>
                    <div className="mt-3 text-xs font-bold text-cyan-100/70 break-all">{userReferralInfo?.summary?.referralLink || ''}</div>
                </div>
                <div className="mt-6 grid grid-cols-3 gap-4">
                    <StatCard label={language === 'th' ? 'ผู้ใช้ที่แนะนำ' : '추천 유저'} value={userReferralInfo?.summary?.directCount || 0} unit={language === 'th' ? 'คน' : '명'} color="blue" />
                    <StatCard label={language === 'th' ? 'การใช้โทเค็นของทีม' : '하위 토큰 사용'} value={(userReferralInfo?.summary?.referralTokenUsage || 0).toLocaleString()} unit="TK" color="orange" />
                    <StatCard label={language === 'th' ? 'ค่าคอมมิชชันโดยประมาณ' : '예상 커미션'} value={(userReferralInfo?.summary?.estimatedCommissionTokens || 0).toLocaleString()} unit="TK" color="green" />
                </div>
                <div className="mt-6 rounded-2xl border border-white/10 bg-black/20 p-5">
                    <h2 className="text-xs font-black uppercase tracking-widest text-gray-400">직속 하위자</h2>
                    <div className="mt-4 space-y-2">
                        {(userReferralInfo?.directReferrals || []).map((item: any) => (
                            <div key={item.id} className="flex items-center justify-between rounded-xl bg-white/5 px-4 py-3 text-xs font-bold text-gray-300">
                                <span>{item.email || item.id}</span>
                                <span className="text-gray-500">{formatDate(item.created_at)}</span>
                            </div>
                        ))}
                        {(!userReferralInfo?.directReferrals || userReferralInfo.directReferrals.length === 0) && <div className="py-8 text-center text-xs font-black text-gray-600">아직 추천한 유저가 없습니다.</div>}
                    </div>
                </div>
            </div>
        </div>
    );

    function formatDate(d: string | null) {
        if (!d) return '-';
        const date = new Date(d);
        return `${date.getFullYear()}.${String(date.getMonth()+1).padStart(2,'0')}.${String(date.getDate()).padStart(2,'0')}`;
    }

    const renderDonutChart = (stats: any) => {
        const colors: Record<string, string> = {
            video: '#f97316',
            image: '#3b82f6',
            script: '#22c55e',
            vision_gen: '#a855f7',
            motion_guide: '#6366f1',
            text_gen: '#06b6d4',
            character_extraction: '#94a3b8',
        }
        const entries = Object.entries(stats.breakdown || {})
        const totalTokensValue = entries.reduce((acc: number, [, value]: any) => acc + (value.tokens || 0), 0)
        let runningPct = 0
        const gradientStops = entries
            .sort((a: any, b: any) => (b[1]?.tokens || 0) - (a[1]?.tokens || 0))
            .map(([stage, value]: [string, any]) => {
                const nextPct = runningPct + (((value?.tokens || 0) / (totalTokensValue || 1)) * 100)
                const stop = `${colors[stage] || '#334155'} ${runningPct}% ${nextPct}%`
                runningPct = nextPct
                return stop
            })
            .join(', ')

        return (
            <div className="w-full lg:w-[320px] bg-[#0f172a]/60 border border-white/20 rounded-2xl p-6 flex flex-col items-center justify-center shadow-lg transition-all hover:border-blue-500/40">
                <div
                    className="relative w-28 h-28 rounded-full mb-4 flex items-center justify-center"
                    style={{ background: `conic-gradient(${gradientStops || '#1e293b'})` }}
                >
                    <div className="absolute inset-5 bg-[#0f172a] rounded-full flex flex-col items-center justify-center overflow-hidden text-center">
                        <span className="text-[9px] font-black text-gray-500 uppercase tracking-tighter">TOTAL</span>
                        <span className="text-[7.5px] text-blue-400 font-bold leading-none mt-0.5">
                            {(stats.totalTokens || 0).toLocaleString()} TK
                        </span>
                        {stats.totalThinkingTokens > 0 && (
                            <span className="text-[6.5px] text-purple-400 font-medium leading-none mt-0.5">
                                (Thk: {stats.totalThinkingTokens.toLocaleString()})
                            </span>
                        )}
                    </div>
                </div>
                <div className="w-full space-y-0.5 mt-1">
                    {entries
                        .sort((a: any, b: any) => (b[1]?.tokens || 0) - (a[1]?.tokens || 0))
                        .slice(0, 5)
                        .map(([stage, value]: [string, any]) => {
                            const pct = Math.round(((value?.tokens || 0) / (totalTokensValue || 1)) * 100)
                            return (
                                <div key={stage} className="flex justify-between items-center text-[9px] font-bold text-gray-400">
                                    <div className="flex items-center gap-2">
                                        <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: colors[stage] || '#334155' }} />
                                        <span className="truncate uppercase text-[8px]">{typeMap[stage] || stage}</span>
                                    </div>
                                    <span className="text-white">{pct}%</span>
                                </div>
                            )
                        })}
                </div>
            </div>
        )
    };

    const renderChartRow = (_stats: any, topTasks: any[]) => {
        return (
            <div className="grid grid-cols-7 gap-3">
                {topTasks.map((task: any) => (
                    <div key={task.name} className="bg-[#0f172a]/60 border border-white/20 p-5 rounded-2xl flex flex-col justify-between min-h-[170px] hover:border-blue-500/40 transition-all shadow-lg group">
                        <div className="flex justify-between items-start">
                            <div className="text-[10px] font-black text-gray-500 uppercase tracking-widest group-hover:text-blue-300 transition-colors">
                                {typeMap[task.name] || task.name}
                            </div>
                            <span className="text-sm group-hover:scale-110 transition-transform">{typeIcons[task.name] || 'ETC'}</span>
                        </div>
                        <div>
                            <div className="text-lg font-black text-white mt-1 tabular-nums">
                                {task.count} <span className="text-gray-600 text-[10px]">건</span>
                            </div>
                            <div className="h-14 w-full mt-3 flex items-end bg-white/[0.02] rounded-lg p-2 gap-[2px] overflow-hidden">
                                <div className={`w-1.5 rounded-full h-full relative overflow-hidden ${task.name === 'video' ? 'bg-orange-500/10' : 'bg-blue-500/10'}`}>
                                    <div
                                        className={`absolute bottom-0 w-full rounded-full transition-all duration-1000 ${task.name === 'video' ? 'bg-orange-500' : 'bg-blue-500'}`}
                                        style={{ height: `${Math.min(100, (task.count / 15) * 100)}%` }}
                                    />
                                </div>
                                <div className="flex-1 italic text-[8px] text-gray-600 self-center ml-2 truncate">ACTIVITY_STREAM</div>
                            </div>
                            <div className="text-[11px] font-black text-blue-400 mt-2 tracking-tight">
                                {task.tokens.toLocaleString()}
                                <span className="text-[8px] text-gray-600 ml-1 font-bold">TK</span>
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        );
    };

    const getFilteredLogs = (logsList: any[]) => {
        return (logsList || []).filter(log => {
            if (logFilterTask !== 'all') {
                let stage = (log.task_type || '').toLowerCase();
                if (stage === 'test_after_fix') {
                    stage = 'subtitle_fix';
                }
                if (stage !== logFilterTask) return false;
            }
            if (logFilterStatus !== 'all') {
                const status = (log.status || '').toLowerCase();
                const isSuccess = status === 'success' || status === 'done';
                if (logFilterStatus === 'success' && !isSuccess) return false;
                if (logFilterStatus === 'failed' && isSuccess) return false;
            }
            if (logSearchPrompt.trim() !== '') {
                const search = logSearchPrompt.toLowerCase();
                const promptMatch = (log.prompt_summary || '').toLowerCase().includes(search);
                const modelMatch = (log.model_id || '').toLowerCase().includes(search);
                const providerMatch = (log.provider || '').toLowerCase().includes(search);
                if (!promptMatch && !modelMatch && !providerMatch) return false;
            }
            return true;
        });
    };

    const downloadLogsCSV = (logsList: any[], filename: string) => {
        const filtered = getFilteredLogs(logsList);
        if (!filtered.length) {
            alert(isKor ? '내보낼 로그 데이터가 없습니다.' : 'No log data to export.');
            return;
        }

        const headers = ['Time', 'Task', 'Model', 'Provider', 'Prompt Summary', 'Input Tokens', 'Output Tokens', 'Thinking Tokens', 'Total Tokens', 'Balance After', 'Status'];
        const rows = filtered.map(log => {
            const time = new Date(log.created_at).toLocaleString();
            const task = typeMap[log.task_type] || log.task_type;
            const model = log.model_id || '';
            const provider = log.provider || '';
            const prompt = `"${(log.prompt_summary || '').replace(/"/g, '""')}"`;
            const input = log.input_tokens || 0;
            const output = log.output_tokens || 0;
            const thinking = log.thinking_tokens || 0;
            const total = input + output + thinking;
            const balance = log.balance_after || '';
            const status = log.status || '';
            return [time, task, model, provider, prompt, input, output, thinking, total, balance, status].join(',');
        });

        const csvContent = '\uFEFF' + [headers.join(','), ...rows].join('\n');
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.setAttribute('href', url);
        link.setAttribute('download', `${filename}_${new Date().toISOString().slice(0, 10)}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    const renderLogTable = (logsList: any[], isGlobal: boolean = false) => {
        const filtered = getFilteredLogs(logsList);
        return (
            <div className="space-y-6">
                <div className="flex flex-wrap items-center justify-between gap-4 bg-[#0f172a]/60 border border-white/10 p-6 rounded-[2rem] shadow-lg">
                    <div className="flex flex-wrap items-center gap-3">
                        <div className="relative">
                            <input
                                type="text"
                                placeholder={isKor ? "프롬프트 / 모델 / 엔진 검색..." : "Search prompt/model/engine..."}
                                value={logSearchPrompt}
                                onChange={e => setLogSearchPrompt(e.target.value)}
                                className="bg-black/40 border border-white/10 rounded-xl px-4 py-2.5 text-xs text-white focus:outline-none focus:border-blue-500/50 w-[240px]"
                            />
                            {logSearchPrompt && (
                                <button 
                                    onClick={() => setLogSearchPrompt('')} 
                                    className="absolute right-3.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white text-xs font-bold"
                                >
                                    ✕
                                </button>
                            )}
                        </div>

                        <select
                            value={logFilterTask}
                            onChange={e => setLogFilterTask(e.target.value)}
                            className="bg-black/40 border border-white/10 rounded-xl px-3 py-2.5 text-xs text-white focus:outline-none focus:border-blue-500/50 cursor-pointer"
                        >
                            <option value="all" className="bg-[#111]">{isKor ? "모든 작업유형" : "All Tasks"}</option>
                            <option value="video" className="bg-[#111]">VIDEO</option>
                            <option value="image" className="bg-[#111]">IMAGE</option>
                            <option value="script" className="bg-[#111]">SCRIPT</option>
                            <option value="text_gen" className="bg-[#111]">TEXT_GEN</option>
                            <option value="vision_gen" className="bg-[#111]">VISION_GEN</option>
                            <option value="subtitle_fix" className="bg-[#111]">SUBTITLE_FIX</option>
                            <option value="motion_guide" className="bg-[#111]">MOTION_GUIDE</option>
                        </select>

                        <select
                            value={logFilterStatus}
                            onChange={e => setLogFilterStatus(e.target.value)}
                            className="bg-black/40 border border-white/10 rounded-xl px-3 py-2.5 text-xs text-white focus:outline-none focus:border-blue-500/50 cursor-pointer"
                        >
                            <option value="all" className="bg-[#111]">{isKor ? "모든 상태" : "All Status"}</option>
                            <option value="success" className="bg-[#111]">{isKor ? "성공 (SUCCESS)" : "SUCCESS"}</option>
                            <option value="failed" className="bg-[#111]">{isKor ? "실패 (FAILED)" : "FAILED"}</option>
                        </select>
                    </div>

                    <div className="flex items-center gap-3">
                        <span className="text-[11px] font-bold text-gray-500">
                            {isKor ? `검색 결과: ${filtered.length}건` : `Filtered: ${filtered.length} rows`}
                        </span>
                        <button
                            onClick={() => downloadLogsCSV(logsList, isGlobal ? 'global_logs' : 'user_logs')}
                            className="px-4 py-2 bg-blue-600/20 hover:bg-blue-600 border border-blue-500/20 hover:border-transparent text-blue-400 hover:text-white text-xs font-black rounded-xl transition-all flex items-center gap-1.5"
                        >
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                            </svg>
                            {isKor ? "CSV 다운로드" : "Export CSV"}
                        </button>
                    </div>
                </div>

                <div className="bg-[#0f172a]/40 border border-white/5 rounded-[2rem] overflow-hidden overflow-x-auto shadow-2xl">
                    <table className="w-full text-left min-w-[1000px]">
                        <thead className="bg-black/20 border-b border-white/5 text-[10px] font-black text-gray-500 uppercase tracking-widest">
                            <tr>
                                <th className="px-10 py-5">TIME</th>
                                <th className="px-10 py-5">TASK</th>
                                <th className="px-10 py-5">MODEL & PROVIDER</th>
                                <th className="px-10 py-5">PROMPT SUMMARY</th>
                                <th className="px-10 py-5 text-right text-orange-500">AI 토큰 사용량</th>
                                <th className="px-10 py-5 text-right text-blue-500">현재 토큰 잔액</th>
                                <th className="px-10 py-5 text-center">STATUS</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                            {filtered.length === 0 ? (
                                <tr>
                                    <td colSpan={7} className="px-10 py-20 text-center text-gray-600 font-bold uppercase tracking-widest italic text-xs">
                                        {isKor ? "일치하는 로그 내역이 없습니다." : "No matching logs found."}
                                    </td>
                                </tr>
                            ) : (
                                filtered.map((log: any) => (
                                    <tr key={log.id} className="hover:bg-white/[0.03] transition-colors group">
                                        <td className="px-10 py-5">
                                            <div className="font-black text-white text-[13px]">{new Date(log.created_at).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit' })}</div>
                                            <div className="text-[10px] text-gray-600 font-bold">{new Date(log.created_at).toLocaleDateString([], { month: '2-digit', day: '2-digit' }).replace('/', '.')}</div>
                                        </td>
                                        <td className="px-10 py-5"><div className="flex items-center gap-3"><div className={`w-1.5 h-1.5 rounded-full ${log.status === 'success' ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.5)]' : 'bg-red-500'}`} /><span className="text-[11px] font-black text-white uppercase tracking-widest">{typeMap[log.task_type] || log.task_type}</span></div></td>
                                        <td className="px-10 py-5"><div className="text-[10px] font-black text-white uppercase italic">{log.model_id}</div><div className="text-[8px] text-gray-600 font-bold uppercase">{log.provider || 'AI_ENGINE'}</div></td>
                                        <td className="px-10 py-5 max-w-[400px] text-gray-500 italic text-[11px] truncate group-hover:text-gray-300 transition-colors">&quot;{log.prompt_summary || 'No summary available'}&quot;</td>
                                        <td className="px-10 py-5 text-right font-black text-[12px]">
                                            <div className="flex flex-col items-end">
                                                <span className={log.task_type === 'RECHARGE' ? 'text-green-500' : 'text-white'}>
                                                    {log.task_type === 'RECHARGE' ? '+' : ''}{((log.input_tokens || 0) + (log.output_tokens || 0) + (log.thinking_tokens || 0)).toLocaleString()} <span className="text-gray-600 text-[10px]">TK</span>
                                                </span>
                                                {log.thinking_tokens > 0 && (
                                                    <span className="text-[8px] text-purple-400 font-semibold mt-0.5">
                                                        (Thk: {log.thinking_tokens.toLocaleString()})
                                                    </span>
                                                )}
                                            </div>
                                        </td>
                                        <td className="px-10 py-5 text-right font-black text-blue-500 text-[12px] tabular-nums">
                                            {log.balance_after ? log.balance_after.toLocaleString() : '-'}
                                        </td>
                                        <td className="px-10 py-5 text-center"><span className={`px-3 py-1 rounded-full text-[9px] font-black border uppercase tracking-widest ${log.status?.toLowerCase() === 'success' || log.status?.toLowerCase() === 'done' ? 'bg-green-500/10 text-green-500 border-green-500/20' : 'bg-red-500/10 text-red-500 border-red-500/20'}`}>{log.status?.toUpperCase() === 'SUCCESS' ? 'SUCCESS' : (log.status?.toUpperCase() || 'FAILED')}</span></td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        );
    };

    return (
        <div className="min-h-screen bg-[#000106] text-white font-sans selection:bg-blue-500/30">
            <nav className="p-6 border-b border-white/5 bg-black/60 sticky top-0 z-[100] backdrop-blur-xl">
                <div className="max-w-[1600px] mx-auto flex justify-between items-center">
                    <span className="text-2xl font-black italic tracking-tighter text-blue-500">AIR STUDIO</span>
                    <div className="flex gap-6 items-center">
                        <LanguageSelector />
                        <div className="text-right">
                            <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-black uppercase tracking-widest leading-none ${isSuperAdmin ? 'border-blue-500/30 bg-blue-500/10 text-blue-300' : 'border-indigo-500/30 bg-indigo-500/10 text-indigo-300'}`}>
                                {isSuperAdmin ? ui.superAdmin : ui.subAdminMode}
                            </span>
                            <span className="mt-1 block text-sm font-black text-blue-400">{user?.email}</span>
                        </div>
                        <button onClick={() => supabase.auth.signOut().then(() => router.push('/'))} className="px-6 py-2.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all">{ui.logout}</button>
                    </div>
                </div>
            </nav>

            <main className="max-w-[1600px] mx-auto px-6 py-8 space-y-12">
                <div className="flex items-center justify-between">
                    <h2 className="text-4xl font-black uppercase tracking-tighter">{ui.adminDashboard}</h2>
                    <div className="flex gap-2 p-1.5 bg-white/5 rounded-2xl border border-white/5 shadow-2xl">
                        {[
                            { id: 'topics', icon: '🤖', label: ui.topics, superOnly: false },
                            { id: 'overview', icon: '📊', label: ui.overview, superOnly: false },
                            { id: 'users', icon: '👥', label: ui.users, superOnly: false },
                            { id: 'organization', icon: '📊', label: ui.organization, superOnly: false },
                            { id: 'withdrawals', icon: '💰', label: ui.withdrawals, superOnly: false },
                            { id: 'api', icon: '🔌', label: ui.api, superOnly: true },
                            { id: 'render-queue', icon: '🖥️', label: ui.renderQueue, superOnly: true },
                            { id: 'learning', icon: '🧠', label: ui.learning, superOnly: true },
                            { id: 'styles', icon: '🎨', label: ui.styles, superOnly: true },
                            { id: 'tenants', icon: '🏢', label: '테넌트', superOnly: true },
                        ].map(tab => {
                            const locked = tab.superOnly && !isSuperAdmin;
                            return (
                                <button
                                    key={tab.id}
                                    type="button"
                                    disabled={locked}
                                    title={locked ? '최고 관리자 전용 기능입니다.' : undefined}
                                    onClick={() => !locked && setActiveTab(tab.id as any)}
                                    className={`px-10 py-3.5 rounded-xl text-[11px] font-black transition-all uppercase tracking-[0.1em] ${
                                        activeTab === tab.id
                                            ? 'bg-blue-600 text-white shadow-xl'
                                            : locked
                                                ? 'text-gray-700 opacity-30 cursor-not-allowed'
                                                : 'text-gray-500 hover:text-white'
                                    }`}
                                >
                                    {tab.icon} {tab.label}
                                </button>
                            )
                        })}
                    </div>
                </div>

                {activeTab === 'topics' && (
                    <div className="space-y-8 animate-in fade-in duration-300">
                        {/* 1. 카테고리 추가 */}
                        {!canManageTopics && (
                            <div className="rounded-[2rem] border border-indigo-500/20 bg-indigo-500/10 px-8 py-5 text-sm font-bold text-indigo-200">
                                👤 부관리자는 카테고리/주제 조회만 가능합니다. 생성·삭제·자동배정은 최고 관리자만 실행할 수 있습니다.
                            </div>
                        )}
                        {canManageTopics && (
                        <div className="bg-[#0f172a]/60 rounded-[2.5rem] border border-white/10 p-8 shadow-2xl">
                            <h2 className="font-black text-xl tracking-tight mb-6 flex items-center gap-2">
                                카테고리 및 직원 매핑 추가
                            </h2>
                            <form onSubmit={handleCreateCategory} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">카테고리명 *</label>
                                    <input 
                                        type="text" 
                                        required
                                        placeholder="예: 옛날이야기"
                                        value={newCatName}
                                        onChange={e => setNewCatName(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">주요 리서치 키워드</label>
                                    <input 
                                        type="text" 
                                        placeholder="예: 주식, 부동산, 금융, 재테크"
                                        value={newCatKeywords}
                                        onChange={e => setNewCatKeywords(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">벤치마킹용 유튜브 채널 URL</label>
                                    <input 
                                        type="url" 
                                        placeholder="예: https://www.youtube.com/@BenchmarkChannel"
                                        value={newCatChannel}
                                        onChange={e => setNewCatChannel(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div>
                                    <div className="flex items-center justify-between mb-1.5">
                                        <label className="text-xs font-black text-gray-400 block uppercase tracking-wider">업로드 고정 채널</label>
                                        <button
                                            type="button"
                                            onClick={fetchLocalUploadChannels}
                                            className="text-[10px] font-black text-blue-400 hover:text-blue-300"
                                        >
                                            {localChannelsLoading ? '불러오는 중...' : '로컬 채널 불러오기'}
                                        </button>
                                    </div>
                                    <select
                                        value={newCatUploadChannelId ?? ''}
                                        onChange={e => applySelectedChannelToCreateForm(e.target.value ? Number(e.target.value) : null)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50 cursor-pointer"
                                    >
                                        <option value="" className="bg-[#111] text-white">-- 고정 채널 없음 --</option>
                                        {localChannels.map(channel => (
                                            <option key={`new-cat-channel-${channel.id}`} value={channel.id} className="bg-[#111] text-white">
                                                {channel.name} {channel.credentials_path ? '[연동완료]' : '[미연동]'}
                                            </option>
                                        ))}
                                    </select>
                                    <p className="mt-2 text-[11px] text-gray-500">
                                        {newCatUploadChannelName
                                            ? `${newCatUploadChannelName} (${newCatUploadChannelHandle || 'handle ??'})`
                                            : '선택한 주제는 해당 채널로 업로드됩니다.'}
                                    </p>
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">콘텐츠 언어 *</label>
                                    <select
                                        required
                                        value={newCatLanguage}
                                        onChange={e => setNewCatLanguage(normalizeContentLanguage(e.target.value))}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50 cursor-pointer"
                                    >
                                        {CONTENT_LANGUAGE_OPTIONS.map(option => (
                                            <option key={`new-cat-language-${option.value}`} value={option.value} className="bg-[#111] text-white">
                                                {option.label}
                                            </option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">영상 형식 (필수) *</label>
                                    <div className="flex gap-4 mt-2 bg-black/40 border border-white/10 rounded-xl px-4 py-3">
                                        <label className="flex items-center gap-2 cursor-pointer text-xs font-bold">
                                            <input 
                                                type="radio" 
                                                name="video_type" 
                                                value="longform" 
                                                checked={newCatVideoType === 'longform'} 
                                                onChange={() => setNewCatVideoType('longform')}
                                                className="w-4 h-4 rounded-full text-blue-500 bg-black border-white/10"
                                            />
                                            <span>롱폼 (Longform)</span>
                                        </label>
                                        <label className="flex items-center gap-2 cursor-pointer text-xs font-bold">
                                            <input 
                                                type="radio" 
                                                name="video_type" 
                                                value="shorts" 
                                                checked={newCatVideoType === 'shorts'} 
                                                onChange={() => setNewCatVideoType('shorts')}
                                                className="w-4 h-4 rounded-full text-blue-500 bg-black border-white/10"
                                            />
                                            <span>쇼츠 (Shorts)</span>
                                        </label>
                                    </div>
                                </div>

                                <div className="md:col-span-3 flex justify-start pt-2">
                                    <button
                                        type="button"
                                        onClick={() => setShowAdvanced(!showAdvanced)}
                                        className="text-xs font-black text-gray-400 hover:text-white flex items-center gap-1.5 transition-all"
                                    >
                                        {showAdvanced ? '🔼 고급 설정 접기' : '🔽 고급 설정 (담당 직원 및 기본 스타일 수동 지정)'}
                                    </button>
                                </div>

                                {showAdvanced && (
                                    <>
                                        <div>
                                            <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">담당 직원 이메일</label>
                                            <select
                                                value={newCatEmployee}
                                                onChange={e => setNewCatEmployee(e.target.value)}
                                                className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50 cursor-pointer"
                                            >
                                                <option value="">-- AI 자동 배정 (선택 사항) --</option>
                                                {users.map(user => {
                                                    const email = user.email?.toLowerCase();
                                                    if (!email) return null;
                                                    const name = user.user_metadata?.full_name || '';
                                                    return (
                                                        <option key={user.id} value={email} className="bg-[#111] text-white">
                                                            {email} {name ? `(${name})` : ''}
                                                        </option>
                                                    );
                                                })}
                                            </select>
                                        </div>
                                        <div>
                                            <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">기본 대본 스타일</label>
                                            <select
                                                value={newCatScriptStyle}
                                                onChange={e => setNewCatScriptStyle(e.target.value)}
                                                className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50 cursor-pointer"
                                            >
                                                <option value="default" className="bg-[#111] text-white">기본 설정 (자연스럽고 선명한 스타일)</option>
                                                <option value="story" className="bg-[#111] text-white">옛날 이야기 (구연 동화)</option>
                                                <option value="senior_story" className="bg-[#111] text-white">시니어 이야기 (회상/감성)</option>
                                                <option value="news" className="bg-[#111] text-white">뉴스 (정보 전달)</option>
                                                <option value="mystery_thriller" className="bg-[#111] text-white">미스터리 스릴러 (긴장감)</option>
                                                <option value="nursery_rhyme" className="bg-[#111] text-white">어린이 동요 (귀여운 구연)</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">기본 이미지 스타일</label>
                                            <select
                                                value={newCatImageStyle}
                                                onChange={e => setNewCatImageStyle(e.target.value)}
                                                className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50 cursor-pointer"
                                            >
                                                <option value="realistic" className="bg-[#111] text-white">실사 (Photorealistic)</option>
                                                <option value="ghibli" className="bg-[#111] text-white">지브리 감성 일러스트 (Ghibli)</option>
                                                <option value="anime" className="bg-[#111] text-white">애니메이션풍 (Anime)</option>
                                                <option value="cinematic" className="bg-[#111] text-white">영화 스타일 (Cinematic)</option>
                                                <option value="cartoon" className="bg-[#111] text-white">2D 카톤 스타일 (Cartoon)</option>
                                                <option value="nursery_rhyme" className="bg-[#111] text-white">3D 동화/애니 (Nursery/Pixar)</option>
                                                <option value="ink_wash" className="bg-[#111] text-white">동양 수목화 스타일 (Ink Wash)</option>
                                            </select>
                                        </div>
                                    </>
                                )}
                                <div className="md:col-span-3 mt-4 flex justify-end items-center gap-3">
                                    <button
                                        type="button"
                                        disabled={topicStyleAssigningType !== null}
                                        onClick={() => handleAssignTopicStyles('script')}
                                        className="px-6 py-3 rounded-xl text-xs font-black border border-emerald-500/30 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500 hover:text-white transition-all disabled:opacity-50"
                                    >
                                        {topicStyleAssigningType === 'script' ? '대본 스타일 배정 중...' : '대본 스타일 자동배정'}
                                    </button>
                                    <button
                                        type="button"
                                        disabled={topicStyleAssigningType !== null}
                                        onClick={() => handleAssignTopicStyles('image')}
                                        className="px-6 py-3 rounded-xl text-xs font-black border border-purple-500/30 bg-purple-500/10 text-purple-300 hover:bg-purple-500 hover:text-white transition-all disabled:opacity-50"
                                    >
                                        {topicStyleAssigningType === 'image' ? '이미지 스타일 배정 중...' : '이미지 스타일 자동배정'}
                                    </button>
                                    <button 
                                        type="submit"
                                        className="px-8 py-3 bg-blue-600 hover:bg-blue-500 text-white font-black rounded-xl transition-all shadow-lg active:scale-95"
                                    >
                                        카테고리 등록 및 초기 주제 생성
                                    </button>
                                </div>
                            </form>
                        </div>
                        )}

                        {/* 2. 등록된 카테고리 및 매핑 리스트 */}
                        <div className="bg-[#0f172a]/60 rounded-[2.5rem] border border-white/10 overflow-hidden shadow-2xl p-8">
                            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
                                <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
                                    <h2 className="font-black text-xl tracking-tight">내 카테고리 현황</h2>
                                    <div className="flex p-1 bg-black/40 rounded-xl border border-white/10">
                                        <button 
                                            onClick={() => setCategoryLangTab('ko')}
                                            className={`px-4 py-1.5 rounded-lg text-xs font-black transition-all ${categoryLangTab === 'ko' ? 'bg-blue-600 text-white shadow' : 'text-gray-500 hover:text-white'}`}
                                        >
                                            한국
                                        </button>
                                        <button 
                                            onClick={() => setCategoryLangTab('ja')}
                                            className={`px-4 py-1.5 rounded-lg text-xs font-black transition-all ${categoryLangTab === 'ja' ? 'bg-blue-600 text-white shadow' : 'text-gray-500 hover:text-white'}`}
                                        >
                                            일본
                                        </button>
                                        <button 
                                            onClick={() => setCategoryLangTab('en')}
                                            className={`px-4 py-1.5 rounded-lg text-xs font-black transition-all ${categoryLangTab === 'en' ? 'bg-blue-600 text-white shadow' : 'text-gray-500 hover:text-white'}`}
                                        >
                                            미국
                                        </button>
                                    </div>
                                </div>
                                <div className="flex p-1 bg-black/40 rounded-xl border border-white/10">
                                    <button 
                                        onClick={() => setCategoryListTab('longform')}
                                        className={`px-6 py-2 rounded-lg text-xs font-black transition-all ${categoryListTab === 'longform' ? 'bg-blue-600 text-white shadow' : 'text-gray-500 hover:text-white'}`}
                                    >
                                        롱폼 (Longform)
                                    </button>
                                    <button 
                                        onClick={() => setCategoryListTab('shorts')}
                                        className={`px-6 py-2 rounded-lg text-xs font-black transition-all ${categoryListTab === 'shorts' ? 'bg-blue-600 text-white shadow' : 'text-gray-500 hover:text-white'}`}
                                    >
                                        쇼츠 (Shorts)
                                    </button>
                                </div>
                            </div>

                            {categoriesLoading ? (
                                <div className="text-center py-20 text-gray-500 text-sm">카테고리 로딩 중...</div>
                            ) : categories.filter(c => (c.video_type || 'longform') === categoryListTab && normalizeContentLanguage(c.language) === categoryLangTab).length === 0 ? (
                                <div className="text-center py-20 text-gray-500 text-sm italic">해당 유형 및 언어에 등록된 카테고리가 없습니다.</div>
                            ) : (
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                    {categories.filter(c => (c.video_type || 'longform') === categoryListTab && normalizeContentLanguage(c.language) === categoryLangTab).map((cat) => {
                                        const pendingTopics = topics.filter(t => t.category_id === cat.id && t.status === 'pending');
                                        const completedTopics = topics.filter(t => t.category_id === cat.id && t.status === 'completed');
                                        const previewTopicItems = pendingTopics.slice(0, 10);
                                        const isFreshPreview = Boolean(generatedTopicsByCat[cat.id]?.length);
                                        const staleYearPendingCount = pendingTopics.filter((topicItem: any) => /2024|2025/.test(String(topicItem.topic || ''))).length;

                                        return (
                                            <div key={cat.id} className="bg-black/40 border border-white/10 rounded-3xl p-6 relative flex flex-col justify-between hover:border-blue-500/50 transition-all">
                                                <div>
                                                    <div className="flex justify-between items-start mb-4">
                                                        <h3 className="text-lg font-black text-white">{cat.name}</h3>
                                                        {canManageTopics && (
                                                        <div className="flex gap-2">
                                                        <button 
                                                                onClick={() => {
                                                                    setEditCategory(cat);
                                                                    setEditCatForm({
                                                                        name: cat.name || '',
                                                                        keywords: cat.keywords || '',
                                                                        benchmark_channel_url: cat.benchmark_channel_url || '',
                                                                        assigned_employee_email: cat.assigned_employee_email || '',
                                                                        default_script_style: cat.default_script_style || 'default',
                                                                        default_image_style: cat.default_image_style || 'realistic',
                                                                        language: normalizeContentLanguage(cat.language),
                                                                        video_type: cat.video_type || 'longform',
                                                                        upload_channel_id: cat.upload_channel_id || null,
                                                                        upload_channel_name: cat.upload_channel_name || '',
                                                                        upload_channel_handle: cat.upload_channel_handle || '',
                                                                    });
                                                                }}
                                                                className="text-blue-400 hover:text-blue-300 text-xs transition-colors shadow-none bg-transparent p-0"
                                                            >
                                                                수정
                                                            </button>
                                                            <span className="text-gray-700">|</span>
                                                            <button 
                                                                onClick={() => handleDeleteCategory(cat.id)}
                                                                className="text-gray-500 hover:text-red-500 text-xs transition-colors shadow-none bg-transparent p-0"
                                                            >
                                                                삭제
                                                            </button>
                                                        </div>
                                                        )}
                                                    </div>
                                                    <div className="space-y-2 text-xs text-gray-400 mb-6">
                                                        <p>담당 직원: <strong className="text-gray-200">{cat.assigned_employee_email}</strong></p>
                                                        <p>키워드: <strong className="text-gray-200">{cat.keywords || '(없음)'}</strong></p>
                                                        <p className="truncate">벤치 채널: <a href={cat.benchmark_channel_url} target="_blank" rel="noreferrer" className="text-blue-400 underline">{cat.benchmark_channel_url || '(없음)'}</a></p>
                                                        <p>
                                                            업로드 채널:{' ' }
                                                            <button
                                                                type="button"
                                                                disabled={!canManageTopics}
                                                                onClick={() => canManageTopics && openCategoryChannelConfig(cat)}
                                                                className={`text-blue-400 underline hover:text-blue-300 ${!canManageTopics ? 'cursor-not-allowed opacity-50' : ''}`}
                                                            >
                                                                {cat.upload_channel_name || cat.upload_channel_handle || '미지정'}
                                                        </button>
                                                    </p>
                                                        <p>대본 스타일: <strong className="text-gray-200">{cat.default_script_style || '기본'}</strong></p>
                                                        <p>이미지 스타일: <strong className="text-gray-200">{cat.default_image_style || '실사'}</strong></p>
                                                        <p>콘텐츠 언어: <strong className="text-gray-200">{contentLanguageLabel(cat.language)}</strong></p>
                                                        <p>영상 포맷: <strong className="text-gray-200">{cat.video_type === 'shorts' ? '쇼츠 (Shorts)' : '롱폼 (Longform)'}</strong></p>
                                                    </div>
                                                     
                                                    {/* 주제 대기열 카운트 */}
                                                    <div className="flex gap-3 text-[11px] font-black tracking-wider uppercase mb-6">
                                                        <span className="px-3 py-1 bg-yellow-500/10 text-yellow-500 border border-yellow-500/20 rounded-lg">대기주제: {pendingTopics.length}개</span>
                                                        <span className="px-3 py-1 bg-green-500/10 text-green-500 border border-green-500/20 rounded-lg">완료주제: {completedTopics.length}개</span>
                                                    </div>
                                                </div>

                                                {canManageTopics && (
                                                <button
                                                    disabled={generatingCatId === cat.id}
                                                    onClick={() => handleTriggerAiTopics(cat.id)}
                                                    className="w-full py-2.5 bg-blue-600/20 hover:bg-blue-600 border border-blue-500/20 hover:border-transparent text-blue-400 hover:text-white rounded-xl text-xs font-black tracking-wider transition-all disabled:bg-gray-800 disabled:text-gray-500 disabled:cursor-not-allowed uppercase"
                                                >
                                                    {generatingCatId === cat.id ? 'AI 주제 생성 중...' : 'AI 주제 자판기 생성 (10개)'}
                                                </button>
                                                )}

                                                {previewTopicItems.length > 0 && (
                                                    <div className="mt-4 rounded-2xl border border-blue-500/20 bg-blue-950/20 p-4">
                                                        <div className="mb-3 flex items-center justify-between gap-2">
                                                            <div className="flex items-center gap-2">
                                                                <p className="text-[11px] font-black text-blue-300">
                                                                    {isFreshPreview ? '방금 생성된 주제 10개' : '대기중 주제 미리보기'}
                                                                </p>
                                                                {staleYearPendingCount > 0 && (
                                                                    <span className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-[10px] font-black text-amber-300">
                                                                        2024/2025 {staleYearPendingCount}개
                                                                    </span>
                                                                )}
                                                            </div>
                                                            <div className="flex items-center gap-2">
                                                                {canManageTopics && staleYearPendingCount > 0 && (
                                                                    <button
                                                                        type="button"
                                                                        disabled={topicActionLoadingId === `cleanup-${cat.id}`}
                                                                        onClick={() => handleDeleteTopicsByYears(cat.id)}
                                                                        className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-1 text-[10px] font-black text-red-300 hover:bg-red-500/20 disabled:opacity-50"
                                                                    >
                                                                        2024/2025 삭제
                                                                    </button>
                                                                )}
                                                                <span className="text-[10px] font-bold text-gray-500">{previewTopicItems.length}개</span>
                                                            </div>
                                                        </div>
                                                        <ol className="space-y-2 text-[11px] leading-relaxed text-gray-200">
                                                            {previewTopicItems.map((topicItem, idx) => (
                                                                <li
                                                                    key={`${cat.id}-topic-preview-${topicItem.id}`}
                                                                    className={`flex items-start gap-2 rounded-xl px-2 py-2 transition-all ${
                                                                        editingTopicId === String(topicItem.id)
                                                                            ? 'bg-blue-500/10 ring-1 ring-blue-400/40'
                                                                            : 'hover:bg-white/[0.03]'
                                                                    }`}
                                                                >
                                                                    <span className="mt-0.5 shrink-0 font-black text-blue-400">{idx + 1}.</span>
                                                                    <div className="min-w-0 flex-1">
                                                                        {editingTopicId === String(topicItem.id) ? (
                                                                            <div className="space-y-2">
                                                                                <input
                                                                                    type="text"
                                                                                    value={editingTopicDraft}
                                                                                    onChange={(e) => setEditingTopicDraft(e.target.value)}
                                                                                    onKeyDown={(e) => handleTopicEditorKeyDown(e, topicItem)}
                                                                                    autoFocus
                                                                                    className="w-full rounded-lg border border-blue-400/30 bg-black/30 px-3 py-2 text-[11px] font-medium text-white outline-none focus:border-blue-400"
                                                                                />
                                                                                <div className="flex items-center gap-2 text-[10px] font-black">
                                                                                    <button
                                                                                        type="button"
                                                                                        disabled={topicActionLoadingId === String(topicItem.id)}
                                                                                        onClick={() => handleEditTopic(topicItem)}
                                                                                        className="rounded-md bg-blue-600 px-2.5 py-1 text-white disabled:opacity-50"
                                                                                    >
                                                                                        저장
                                                                                    </button>
                                                                                    <button
                                                                                        type="button"
                                                                                        disabled={topicActionLoadingId === String(topicItem.id)}
                                                                                        onClick={cancelEditingTopic}
                                                                                        className="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-gray-300 disabled:opacity-50"
                                                                                    >
                                                                                        취소
                                                                                    </button>
                                                                                    <span className="text-[10px] font-bold text-gray-500">Enter 저장 · ESC 취소</span>
                                                                                </div>
                                                                            </div>
                                                                        ) : (
                                                                            <div className="flex items-start gap-2">
                                                                                <span className="min-w-0 flex-1 break-words">{topicItem.topic}</span>
                                                                                {canManageTopics && (
                                                                                    <div className="shrink-0 flex items-center gap-2">
                                                                                        <button
                                                                                            type="button"
                                                                                            disabled={topicActionLoadingId === String(topicItem.id)}
                                                                                            onClick={() => startEditingTopic(topicItem)}
                                                                                            className="text-[10px] font-black text-blue-300 hover:text-white disabled:opacity-50"
                                                                                        >
                                                                                            수정
                                                                                        </button>
                                                                                        <button
                                                                                            type="button"
                                                                                            disabled={topicActionLoadingId === String(topicItem.id)}
                                                                                            onClick={() => handleDeleteTopic(topicItem)}
                                                                                            className="text-[10px] font-black text-red-300 hover:text-red-200 disabled:opacity-50"
                                                                                        >
                                                                                            삭제
                                                                                        </button>
                                                                                    </div>
                                                                                )}
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                </li>
                                                            ))}
                                                        </ol>
                                                    </div>
                                                )}
                                            </div>
                                        )
                                    })}
                                </div>
                            )}
                        </div>

                        {/* 3. 전체 주제 대기열 및 모니터링 */}
                        {(() => {
                            const getTopicAssignee = (item: any) => item.categories?.assigned_employee_email || item.assigned_employee_email;
                            const isWorkingTopic = (item: any) => item.status === 'assigned';
                            const isPendingTopic = (item: any) => item.status === 'pending';
                            const isQueueVisibleTopic = (item: any) => item.status === 'pending' || item.status === 'assigned';
                            const matchesTopicQueueStatus = (item: any) => topicQueueStatusFilter === 'working' ? isWorkingTopic(item) : isPendingTopic(item);
                            const topicActualPayout = (item: any) => {
                                const parsed = Number(item?.actual_payout ?? 0);
                                return Number.isFinite(parsed) ? parsed : 0;
                            };
                            const topicVideoClipRatio = (item: any) => String(item?.video_clip_ratio || '').trim();
                            const topicSceneSummary = (item: any) => {
                                const total = Number(item?.total_scenes ?? 0) || 0;
                                const video = Number(item?.video_scenes ?? 0) || 0;
                                const image = Number(item?.image_scenes ?? 0) || 0;
                                if (total <= 0 && video <= 0 && image <= 0) return '';
                                return `SCENES ${video}V ${image}I / ${total}`;
                            };
                            const queueCategories = [...categories].sort((a, b) => {
                                const aActive = topics.filter(t => String(t.category_id) === String(a.id) && isQueueVisibleTopic(t) && matchesTopicQueueStatus(t)).length;
                                const bActive = topics.filter(t => String(t.category_id) === String(b.id) && isQueueVisibleTopic(t) && matchesTopicQueueStatus(t)).length;
                                if (bActive !== aActive) return bActive - aActive;
                                return String(a.name || '').localeCompare(String(b.name || ''), 'ko');
                            });
                            const statusFilteredTopics = topicQueueCategoryFilter === 'all'
                                ? topics.filter(t => isQueueVisibleTopic(t) && matchesTopicQueueStatus(t))
                                : topics.filter(t => String(t.category_id) === topicQueueCategoryFilter && isQueueVisibleTopic(t) && matchesTopicQueueStatus(t));
                            const availableTopicQueueEmployees = Array.from(
                                new Set(
                                    statusFilteredTopics
                                        .map(item => String(getTopicAssignee(item) || '').trim())
                                        .filter(Boolean)
                                )
                            ).sort((a, b) => a.localeCompare(b, 'en'));
                            const filteredTopics = topicQueueEmployeeFilter === 'all'
                                ? statusFilteredTopics
                                : statusFilteredTopics.filter(item => String(getTopicAssignee(item) || '').trim() === topicQueueEmployeeFilter);
                            const selectedCategory = topicQueueCategoryFilter === 'all'
                                ? null
                                : categories.find(cat => String(cat.id) === topicQueueCategoryFilter);
                            const activeStatusLabel = topicQueueStatusFilter === 'working' ? '작업중' : '대기중';

                            return (
                        <div className="bg-[#0f172a]/60 rounded-[2.5rem] border border-white/10 overflow-hidden shadow-2xl">
                            <div className="p-8 border-b border-white/10 bg-black/20">
                                <div className="flex flex-col xl:flex-row xl:items-start xl:justify-between gap-5">
                                    <div className="min-w-0">
                                        <h2 className="font-black text-xl tracking-tight">
                                            실시간 전체 주제 대기열 큐 (Topics Queue)
                                        </h2>
                                        <p className="mt-2 text-xs font-bold text-gray-500">
                                            {selectedCategory ? `${selectedCategory.name} 카테고리 · ${activeStatusLabel}만 표시 중` : `전체 카테고리 · ${activeStatusLabel}만 표시 중`}
                                        </p>
                                    </div>
                                    <div className="flex flex-wrap items-center gap-2">
                                        {[
                                            { key: 'working', label: '작업중' },
                                            { key: 'pending', label: '대기중' },
                                        ].map(item => {
                                            const count = topics.filter(topic => isQueueVisibleTopic(topic) && (item.key === 'working' ? isWorkingTopic(topic) : isPendingTopic(topic))).length;
                                            return (
                                                <button
                                                    key={`topic-status-filter-${item.key}`}
                                                    type="button"
                                                    onClick={() => setTopicQueueStatusFilter(item.key as 'working' | 'pending')}
                                                    className={`px-4 py-2 rounded-xl text-[11px] font-black border transition-all ${
                                                        topicQueueStatusFilter === item.key
                                                            ? 'bg-emerald-600 text-white border-emerald-500 shadow-lg shadow-emerald-900/20'
                                                            : 'bg-white/5 text-gray-400 border-white/10 hover:text-white hover:border-emerald-500/40'
                                                    }`}
                                                >
                                                    {item.label} <span className="ml-1 text-[10px] opacity-70">{count}</span>
                                                </button>
                                            );
                                        })}
                                        <span className="shrink-0 bg-yellow-500/20 text-yellow-500 text-[11px] px-3 py-1 rounded-full font-black">
                                            {selectedCategory ? '선택 표시건수' : '총 표시건수'}: {filteredTopics.length}개
                                        </span>
                                    </div>
                                </div>

                                <div className="mt-4 flex flex-wrap items-center gap-3">
                                    <label className="text-[11px] font-black text-gray-500">배정 직원</label>
                                    <select
                                        value={topicQueueEmployeeFilter}
                                        onChange={(e) => setTopicQueueEmployeeFilter(e.target.value)}
                                        className="min-w-[240px] rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-[11px] font-bold text-white focus:outline-none focus:border-blue-500/50"
                                    >
                                        <option value="all" className="bg-[#111] text-white">전체 직원</option>
                                        {availableTopicQueueEmployees.map(email => (
                                            <option key={`topic-queue-employee-${email}`} value={email} className="bg-[#111] text-white">
                                                {email}
                                            </option>
                                        ))}
                                    </select>
                                    <span className="text-[11px] font-bold text-gray-500">
                                        {topicQueueEmployeeFilter === 'all' ? '전체 직원 표시 중' : `${topicQueueEmployeeFilter}만 표시 중`}
                                    </span>
                                </div>

                                <div className="mt-6 flex flex-wrap gap-2">
                                    <button
                                        type="button"
                                        onClick={() => setTopicQueueCategoryFilter('all')}
                                        className={`px-4 py-2 rounded-xl text-[11px] font-black border transition-all ${
                                            topicQueueCategoryFilter === 'all'
                                                ? 'bg-blue-600 text-white border-blue-500 shadow-lg shadow-blue-900/20'
                                                : 'bg-white/5 text-gray-400 border-white/10 hover:text-white hover:border-blue-500/40'
                                        }`}
                                    >
                                        전체 <span className="ml-1 text-[10px] opacity-70">{topics.filter(t => isQueueVisibleTopic(t) && matchesTopicQueueStatus(t)).length}</span>
                                    </button>
                                    {queueCategories.map(cat => {
                                        const activeCount = topics.filter(t => String(t.category_id) === String(cat.id) && isQueueVisibleTopic(t) && matchesTopicQueueStatus(t)).length;
                                        return (
                                            <button
                                                type="button"
                                                key={`topic-queue-filter-${cat.id}`}
                                                onClick={() => setTopicQueueCategoryFilter(String(cat.id))}
                                                className={`px-4 py-2 rounded-xl text-[11px] font-black border transition-all ${
                                                    topicQueueCategoryFilter === String(cat.id)
                                                        ? 'bg-blue-600 text-white border-blue-500 shadow-lg shadow-blue-900/20'
                                                        : 'bg-white/5 text-gray-400 border-white/10 hover:text-white hover:border-blue-500/40'
                                                }`}
                                            >
                                                {cat.name} <span className="ml-1 text-[10px] opacity-70">{activeCount}</span>
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-left text-sm">
                                    <thead className="bg-black/30 border-b border-white/5 text-[10px] font-black text-gray-500 uppercase tracking-widest">
                                        <tr>
                                            <th className="px-10 py-6">카테고리</th>
                                            <th className="px-10 py-6">제안 영상 주제</th>
                                            {topicQueueStatusFilter === 'working' && (
                                                <th className="px-10 py-6">작업 진행</th>
                                            )}
                                            <th className="px-10 py-6">배정된 직원 이메일</th>
                                            <th className="px-10 py-6 text-center">배당 상태</th>
                                            <th className="px-10 py-6 text-right">관리</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-white/5 font-medium">
                                        {filteredTopics.map((item) => (
                                            <tr
                                                key={item.id}
                                                className={`transition-colors h-16 text-xs ${
                                                    editingTopicId === String(item.id)
                                                        ? 'bg-blue-500/10 ring-1 ring-inset ring-blue-400/30'
                                                        : 'hover:bg-white/[0.03]'
                                                }`}
                                            >
                                                <td className="px-10 py-6 text-gray-300 font-bold">
                                                    {item.categories?.name || '기본'}
                                                </td>
                                                <td className="px-10 py-6 text-white font-bold max-w-sm">
                                                    <div className="flex items-start gap-2">
                                                        <div className="min-w-0 flex-1">
                                                            {editingTopicId === String(item.id) ? (
                                                                <div className="space-y-2">
                                                                    <input
                                                                        type="text"
                                                                        value={editingTopicDraft}
                                                                        onChange={(e) => setEditingTopicDraft(e.target.value)}
                                                                        onKeyDown={(e) => handleTopicEditorKeyDown(e, item)}
                                                                        autoFocus
                                                                        className="w-full rounded-lg border border-blue-400/30 bg-black/30 px-3 py-2 text-[11px] font-medium text-white outline-none focus:border-blue-400"
                                                                    />
                                                                    <div className="flex items-center gap-2 text-[10px] font-black">
                                                                        <button
                                                                            type="button"
                                                                            disabled={topicActionLoadingId === String(item.id)}
                                                                            onClick={() => handleEditTopic(item)}
                                                                            className="rounded-md bg-blue-600 px-2.5 py-1 text-white disabled:opacity-50"
                                                                        >
                                                                            저장
                                                                        </button>
                                                                        <button
                                                                            type="button"
                                                                            disabled={topicActionLoadingId === String(item.id)}
                                                                            onClick={cancelEditingTopic}
                                                                            className="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-gray-300 disabled:opacity-50"
                                                                        >
                                                                            취소
                                                                        </button>
                                                                        <span className="text-[10px] font-bold text-gray-500">Enter 저장 · ESC 취소</span>
                                                                    </div>
                                                                </div>
                                                            ) : (
                                                                <div className="space-y-2">
                                                                    <span className="block truncate">{item.topic}</span>
                                                                    {(topicActualPayout(item) > 0 || topicVideoClipRatio(item) || topicSceneSummary(item)) && (
                                                                        <div className="flex flex-wrap gap-1.5">
                                                                            {topicActualPayout(item) > 0 && (
                                                                                <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-1 text-[10px] font-black text-emerald-300">
                                                                                    ACTUAL {topicActualPayout(item).toLocaleString()}
                                                                                </span>
                                                                            )}
                                                                            {topicVideoClipRatio(item) && (
                                                                                <span className="rounded-full border border-sky-500/20 bg-sky-500/10 px-2 py-1 text-[10px] font-black text-sky-300">
                                                                                    CLIP {topicVideoClipRatio(item)}
                                                                                </span>
                                                                            )}
                                                                            <span className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-1 text-[10px] font-black text-amber-300">
                                                                                LANG {contentLanguageLabel(item.language || item.categories?.language)}
                                                                            </span>
                                                                            {item.assigned_script_style && (
                                                                                <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-1 text-[10px] font-black text-emerald-300">
                                                                                    SCRIPT {item.assigned_script_style}
                                                                                </span>
                                                                            )}
                                                                            {item.assigned_image_style && (
                                                                                <span className="rounded-full border border-purple-500/20 bg-purple-500/10 px-2 py-1 text-[10px] font-black text-purple-300">
                                                                                    IMAGE {item.assigned_image_style}
                                                                                </span>
                                                                            )}
                                                                            {topicSceneSummary(item) && (
                                                                                <span className="rounded-full border border-white/10 bg-white/5 px-2 py-1 text-[10px] font-black text-gray-300">
                                                                                    {topicSceneSummary(item)}
                                                                                </span>
                                                                            )}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            )}
                                                        </div>
                                                        {item.is_auto_generated && (
                                                            <span className="bg-purple-500/10 text-purple-400 px-1.5 py-0.5 rounded border border-purple-500/20 font-black text-[8px] tracking-tight shrink-0">
                                                                AUTO
                                                            </span>
                                                        )}
                                                    </div>
                                                </td>
                                                {topicQueueStatusFilter === 'working' && (
                                                    <td className="px-10 py-6">
                                                        {Array.isArray(item.progress_payload?.completed_steps) && item.progress_payload.completed_steps.length > 0 ? (
                                                            <div className="space-y-2">
                                                                <div className="flex flex-wrap gap-1.5">
                                                                    {item.progress_payload.completed_steps.map((step: string) => (
                                                                        <span
                                                                            key={`${item.id}-step-${step}`}
                                                                            className="px-2 py-1 rounded-full text-[10px] font-black bg-green-500/10 text-green-400 border border-green-500/20"
                                                                        >
                                                                            {step}
                                                                        </span>
                                                                    ))}
                                                                </div>
                                                                <div className="text-[10px] font-bold text-emerald-300">
                                                                    현재 단계: {item.progress_payload?.current_step || '진행 중'}
                                                                </div>
                                                            </div>
                                                        ) : (
                                                            <span className="text-[11px] font-bold text-gray-500">수신 대기</span>
                                                        )}
                                                    </td>
                                                )}
                                                <td className="px-10 py-6 text-gray-400">
                                                    {getTopicAssignee(item)}
                                                </td>
                                                <td className="px-10 py-6 text-center">
                                                    <span className={`px-2.5 py-1 rounded-full text-[10px] font-black border uppercase tracking-tighter ${
                                                        item.status === 'pending' ? 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20' :
                                                        isWorkingTopic(item) ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' :
                                                        'bg-green-500/10 text-green-500 border-green-500/20'
                                                    }`}>
                                                        {item.status === 'pending' ? '대기중' : isWorkingTopic(item) ? '작업중' : '시작 완료'}
                                                    </span>
                                                </td>
                                                <td className="px-10 py-6 text-right">
                                                    {canManageTopics && item.status === 'pending' ? (
                                                        <div className="flex items-center justify-end gap-3 text-[11px] font-black">
                                                            <button
                                                                type="button"
                                                                disabled={topicActionLoadingId === String(item.id)}
                                                                onClick={() => startEditingTopic(item)}
                                                                className="text-blue-300 hover:text-white disabled:opacity-50"
                                                            >
                                                                수정
                                                            </button>
                                                            <button
                                                                type="button"
                                                                disabled={topicActionLoadingId === String(item.id)}
                                                                onClick={() => handleDeleteTopic(item)}
                                                                className="text-red-300 hover:text-red-200 disabled:opacity-50"
                                                            >
                                                                삭제
                                                            </button>
                                                        </div>
                                                    ) : (
                                                        <span className="text-[10px] font-bold text-gray-600">-</span>
                                                    )}
                                                </td>
                                            </tr>
                                        ))}
                                        {filteredTopics.length === 0 && (
                                            <tr>
                                                <td colSpan={topicQueueStatusFilter === 'working' ? 6 : 5} className="px-10 py-20 text-center text-gray-600 font-black uppercase tracking-widest text-xs italic">
                                                    {selectedCategory ? '선택한 카테고리에 등록된 주제가 없습니다.' : '대기열에 등록된 주제가 없습니다. 카테고리를 먼저 선택해 주세요.'}
                                                </td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                            );
                        })()}
                    </div>
                )}

                {activeTab === 'overview' && (
                    <div className={`space-y-6 animate-in fade-in duration-500 ${globalLoading ? 'opacity-50' : ''}`}>
                        <div className="flex items-center gap-3">
                            <div className="flex-1 flex gap-2">
                                <div className="flex-1 bg-blue-600 border border-white/10 px-6 py-3 rounded-2xl flex items-center justify-between group shadow-lg shadow-blue-900/20 text-white transition-transform hover:scale-[1.02]">
                                    <span className="text-[10px] font-black uppercase tracking-widest">전체 인원</span>
                                    <div className="flex items-baseline gap-1"><span className="text-xl font-black italic">{memberCount.toLocaleString()}</span><span className="text-[9px] font-bold uppercase">명</span></div>
                                </div>
                                <div className="flex-1 bg-[#0f172a]/80 border border-white/5 px-6 py-3 rounded-2xl flex items-center justify-between transition-transform hover:scale-[1.02]">
                                    <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">오늘 활성</span>
                                    <div className="flex items-baseline gap-1"><span className="text-xl font-black tabular-nums">{activeToday.toLocaleString()}</span><span className="text-[9px] font-bold text-green-500 uppercase">+{newToday}</span></div>
                                </div>
                                <div className="flex-1 bg-[#0f172a]/80 border border-white/5 px-6 py-3 rounded-2xl flex items-center justify-between transition-transform hover:scale-[1.02]">
                                    <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">총 보유 토큰</span>
                                    <div className="flex items-baseline gap-1"><span className="text-xl font-black text-orange-500 tabular-nums">{totalTokens.toLocaleString()}</span><span className="text-[9px] font-bold text-orange-500/50 uppercase">TK</span></div>
                                </div>
                            </div>
                            <div className="flex items-center gap-2 p-1 bg-white/5 rounded-2xl border border-white/5">
                                <div className="flex gap-1">{[1, 7, 30].map(d => (
                                    <button key={d} onClick={() => setGlobalPeriod(d)} className={`px-4 py-2 text-[10px] font-black rounded-xl transition-all ${globalPeriod === d ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500 hover:text-white'}`}>{d === 1 ? '일간' : d === 7 ? '주간' : '월간'}</button>
                                ))}</div>
                                <div className="w-[1px] h-4 bg-white/10 mx-1"></div>
                                <button onClick={() => fetchGlobalStats(globalPeriod)} className="px-5 py-2 hover:bg-white/5 rounded-xl text-[10px] font-black text-blue-500 transition-all">새로고침</button>
                            </div>
                        </div>
                        <div className="flex flex-col lg:flex-row gap-4">
                            <div className="flex-1 grid grid-cols-4 gap-4">
                                <StatCard label="TOTAL TASKS" value={globalStats.total} unit="UNITS" color="white" />
                                <StatCard label="SUCCESS RATE" value={globalStats.successRate + '%'} unit="GLOBAL" color="green" />
                                <StatCard label="AVG LATENCY" value={globalStats.avgLatency + 's'} unit="PER TASK" color="blue" />
                                <StatCard 
                                    label={isKor ? "토큰 소모량" : "TOKEN USAGE"} 
                                    value={globalStats.totalTokens.toLocaleString()} 
                                    unit="TOKENS" 
                                    color="orange" 
                                    subLabel={isKor 
                                        ? `예상 비용: 약 $${((globalStats.totalTokens || 0) * 0.00002).toFixed(2)}` 
                                        : `Est. Cost: ~$${((globalStats.totalTokens || 0) * 0.00002).toFixed(2)}`
                                    }
                                />
                            </div>
                            {renderDonutChart(globalStats)}
                        </div>
                        {renderChartRow(globalStats, globalTopTasks)}
                        <div className="flex items-center gap-4 py-2">
                             <div className="text-[11px] font-black text-gray-500 uppercase tracking-[0.4em] flex items-center gap-4"><div className="w-2 h-2 rounded-full bg-blue-500" /> GENERATION HISTORY</div>
                             <div className="h-[1px] flex-1 bg-white/5"></div>
                             <div className="flex gap-1 p-1 bg-white/5 rounded-xl border border-white/5">
                                 <button onClick={() => setOverviewSubTab('video')} className={`px-8 py-1.5 rounded-lg text-[10px] font-black transition-all ${overviewSubTab === 'video' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500 hover:text-white'}`}>채널 (영상 관리)</button>
                                <button onClick={() => setOverviewSubTab('log')} className={`px-8 py-1.5 rounded-lg text-[10px] font-black transition-all ${overviewSubTab === 'log' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500 hover:text-white'}`}>로그</button>
                             </div>
                        </div>
                        {overviewSubTab === 'video' ? (
                            <div className="space-y-12">
                                <div className="bg-[#0f172a]/20 border border-white/5 rounded-[2.5rem] overflow-hidden shadow-2xl">
                                    <div className="px-10 py-6 border-b border-white/5 bg-black/20 flex justify-between items-center">
                                        <h3 className="text-[10px] font-black text-blue-500 uppercase tracking-[0.4em]">확인 대기 및 등록된 영상</h3>
                                    </div>
                                    <div className="px-10 py-6 border-b border-white/5 bg-white/[0.02]">
                                        <div className="grid grid-cols-2 xl:grid-cols-6 gap-3">
                                            <div className="rounded-2xl border border-white/10 bg-black/20 px-4 py-3">
                                                <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">Total</div>
                                                <div className="mt-1 text-2xl font-black text-white tabular-nums">{publishingSummary.total}</div>
                                            </div>
                                            <div className="rounded-2xl border border-orange-500/20 bg-orange-500/5 px-4 py-3">
                                                <div className="text-[10px] font-black uppercase tracking-widest text-orange-300">{isKor ? '대기' : 'Pending'}</div>
                                                <div className="mt-1 text-2xl font-black text-orange-300 tabular-nums">{publishingSummary.pending}</div>
                                            </div>
                                            <div className="rounded-2xl border border-blue-500/20 bg-blue-500/5 px-4 py-3">
                                                <div className="text-[10px] font-black uppercase tracking-widest text-blue-300">{isKor ? '진행 중' : 'Publishing'}</div>
                                                <div className="mt-1 text-2xl font-black text-blue-300 tabular-nums">{publishingSummary.processing}</div>
                                            </div>
                                            <div className="rounded-2xl border border-green-500/20 bg-green-500/5 px-4 py-3">
                                                <div className="text-[10px] font-black uppercase tracking-widest text-green-300">{isKor ? '완료' : 'Published'}</div>
                                                <div className="mt-1 text-2xl font-black text-green-300 tabular-nums">{publishingSummary.published}</div>
                                            </div>
                                            <div className="rounded-2xl border border-red-500/20 bg-red-500/5 px-4 py-3">
                                                <div className="text-[10px] font-black uppercase tracking-widest text-red-300">{isKor ? '실패' : 'Failed'}</div>
                                                <div className="mt-1 text-2xl font-black text-red-300 tabular-nums">{publishingSummary.failed}</div>
                                            </div>
                                            <div className="rounded-2xl border border-zinc-500/20 bg-zinc-500/5 px-4 py-3">
                                                <div className="text-[10px] font-black uppercase tracking-widest text-zinc-300">Invalid</div>
                                                <div className="mt-1 text-2xl font-black text-zinc-300 tabular-nums">{publishingSummary.invalid}</div>
                                            </div>
                                        </div>
                                    </div>
                                    <div className="px-10 py-5 border-b border-white/5 bg-black/10 flex flex-wrap gap-2">
                                        {[
                                            { key: 'all', label: isKor ? '전체' : 'All', count: publishingSummary.total },
                                            { key: 'pending', label: isKor ? '대기' : 'Pending', count: publishingSummary.pending },
                                            { key: 'processing', label: isKor ? '진행 중' : 'Publishing', count: publishingSummary.processing },
                                            { key: 'published', label: isKor ? '완료' : 'Published', count: publishingSummary.published },
                                            { key: 'failed', label: isKor ? '업로드 실패' : 'Failed', count: publishingSummary.failed },
                                            { key: 'invalid', label: 'Invalid', count: publishingSummary.invalid },
                                        ].map(item => (
                                            <button
                                                key={item.key}
                                                onClick={() => setPublishingFilter(item.key as typeof publishingFilter)}
                                                className={`px-4 py-2 rounded-xl text-[10px] font-black border transition-all ${
                                                    publishingFilter === item.key
                                                        ? 'bg-blue-600 text-white border-blue-500 shadow-lg'
                                                        : 'bg-white/5 text-gray-400 border-white/10 hover:bg-white/10 hover:text-white'
                                                }`}
                                            >
                                                {item.label} <span className="ml-1 tabular-nums">{item.count}</span>
                                            </button>
                                        ))}
                                        <div className="ml-auto self-center text-[11px] font-bold text-gray-500">
                                            {isKor
                                                ? `현재 ${filteredPublishingRequests.length}건 표시 중`
                                                : `Showing ${filteredPublishingRequests.length} requests`}
                                        </div>
                                    </div>
                                    <table className="w-full text-left">
                                        <thead className="bg-black/30 border-b border-white/5 text-[10px] font-black text-gray-500 uppercase tracking-widest">
                                            <tr><th className="px-10 py-6">영상 정보 / 사유</th><th className="px-10 py-6 text-center">유튜브 ID</th><th className="px-10 py-6 text-center">등록일시</th><th className="px-10 py-6 text-center">상태</th><th className="px-10 py-6 text-right">관리 / Drive 자산</th></tr>
                                        </thead>
                                        <tbody className="divide-y divide-white/5">
                                            {filteredPublishingRequests.length === 0 ? (
                                                <tr><td colSpan={5} className="px-10 py-20 text-center text-gray-600 font-bold uppercase tracking-widest italic">등록된 영상이 없습니다.</td></tr>
                                            ) : (
                                                filteredPublishingRequests.map(req => {
                                                    const owner = users?.find(u => u.id === req.user_id);
                                                    const statusMeta = getPublishingStatusMeta(req);
                                                    return (
                                                        <tr key={req.id} className="hover:bg-white/[0.03] transition-colors group">
                                                            <td className="px-10 py-6 align-middle">
                                                                <div className="flex items-start gap-4">
                                                                    {req.metadata?.drive_thumbnail_preview_url ? (
                                                                        <img
                                                                            src={req.metadata.drive_thumbnail_preview_url}
                                                                            alt={req.metadata?.title || 'thumbnail'}
                                                                            className="w-28 h-16 rounded-xl object-cover border border-white/10 bg-black/20 shrink-0"
                                                                        />
                                                                    ) : (
                                                                        <div className="w-28 h-16 rounded-xl border border-dashed border-white/10 bg-black/20 shrink-0 flex items-center justify-center text-[10px] text-gray-600 font-bold">
                                                                            NO THUMB
                                                                        </div>
                                                                    )}
                                                                    <div className="min-w-0">
                                                                        <div className="font-black text-white text-base group-hover:text-blue-400 transition-colors tracking-tight break-words">{req.metadata?.title || 'Untitled Video'}</div>
                                                                        <div className="text-[11px] text-gray-600 font-bold mt-1 tracking-tight break-all">{owner?.email || req.user_id || 'Unknown User'}</div>
                                                                        {req.metadata?.description && (
                                                                            <div className="mt-2 text-[11px] leading-5 text-gray-400 line-clamp-2 break-words">
                                                                                {req.metadata.description}
                                                                            </div>
                                                                        )}
                                                                        <div className="mt-2 flex flex-wrap gap-2">
                                                                            {req.metadata?.project_id && (
                                                                                <span className="px-2 py-1 rounded-full bg-white/5 border border-white/10 text-[9px] font-black text-gray-300">
                                                                                    PID {req.metadata.project_id}
                                                                                </span>
                                                                            )}
                                                                            {req.metadata?.project_name && (
                                                                                <span className="px-2 py-1 rounded-full bg-white/5 border border-white/10 text-[9px] font-black text-gray-300">
                                                                                    프로젝트: {req.metadata.project_name}
                                                                                </span>
                                                                            )}
                                                                            {req.metadata?.topic && (
                                                                                <span className="px-2 py-1 rounded-full bg-white/5 border border-white/10 text-[9px] font-black text-gray-300">
                                                                                    주제: {req.metadata.topic}
                                                                                </span>
                                                                            )}
                                                                            {req.metadata?.has_drive_bundle && (
                                                                                <span className="px-2 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-[9px] font-black text-blue-300">
                                                                                    DRIVE BUNDLE
                                                                                </span>
                                                                            )}
                                                                            {req.metadata?.app_mode === 'longform_music' && (
                                                                                <span className="px-2 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-[9px] font-black text-emerald-300">
                                                                                    LONGFORM MUSIC
                                                                                </span>
                                                                            )}
                                                                            {req.metadata?.privacy_status && (
                                                                                <span className="px-2 py-1 rounded-full bg-white/5 border border-white/10 text-[9px] font-black text-gray-300">
                                                                                    {String(req.metadata.privacy_status).toUpperCase()}
                                                                                </span>
                                                                            )}
                                                                            {req.metadata?.track_count ? (
                                                                                <span className="px-2 py-1 rounded-full bg-white/5 border border-white/10 text-[9px] font-black text-gray-300">
                                                                                    TRACKS {req.metadata.track_count}
                                                                                </span>
                                                                            ) : null}
                                                                            <span className={`px-2 py-1 rounded-full border text-[9px] font-black whitespace-nowrap ${statusMeta.className}`}>
                                                                                {statusMeta.label}
                                                                            </span>
                                                                        </div>
                                                                        {(req.metadata?.total_duration_seconds || req.metadata?.publish_at) && (
                                                                            <div className="mt-2 flex flex-wrap gap-3 text-[10px] font-bold">
                                                                                {req.metadata?.total_duration_seconds ? (
                                                                                    <span className="text-sky-300">
                                                                                        Total: {Math.round(Number(req.metadata.total_duration_seconds || 0) / 60)} min
                                                                                    </span>
                                                                                ) : null}
                                                                                {req.metadata?.publish_at ? (
                                                                                    <span className="text-amber-300">
                                                                                        Publish At: {new Date(req.metadata.publish_at).toLocaleString()}
                                                                                    </span>
                                                                                ) : null}
                                                                            </div>
                                                                        )}
                                                                        {req.metadata?.publish_error && (
                                                                            <div className="mt-2 text-[11px] font-semibold text-red-300 break-all">
                                                                                {req.metadata.publish_error}
                                                                            </div>
                                                                        )}
                                                                        {req.metadata?.published_at && (
                                                                            <div className="mt-2 text-[10px] font-bold text-green-300">
                                                                                Published: {new Date(req.metadata.published_at).toLocaleString()}
                                                                            </div>
                                                                        )}
                                                                        {req.metadata?.failed_at && (
                                                                            <div className="mt-2 text-[10px] font-bold text-red-300">
                                                                                Failed: {new Date(req.metadata.failed_at).toLocaleString()}
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                            </td>
                                                            <td className="px-10 py-6 text-center align-middle">
                                                                {req.metadata?.youtube_url || req.metadata?.videoId ? (
                                                                    <a
                                                                        href={req.metadata?.youtube_url || `https://youtu.be/${req.metadata?.videoId}`}
                                                                        target="_blank"
                                                                        rel="noreferrer"
                                                                        className="text-[11px] font-black text-blue-500 hover:underline"
                                                                    >
                                                                        {req.metadata?.videoId || (isKor ? '열기' : 'Open')}
                                                                    </a>
                                                                ) : (
                                                                    <span className="text-[11px] font-black text-gray-600">-</span>
                                                                )}
                                                            </td>
                                                            <td className="px-10 py-6 text-center align-middle text-[12px] font-black text-gray-500">{new Date(req.created_at).toLocaleString()}</td>
                                                            <td className="px-10 py-6 text-center align-middle">
                                                                <span className={`px-3 py-1 text-[9px] font-black rounded-full border uppercase tracking-widest whitespace-nowrap ${statusMeta.className}`}>
                                                                    {statusMeta.label}
                                                                </span>
                                                            </td>
                                                            <td className="px-10 py-6 text-right align-middle space-y-3">
                                                                {renderPublishingActionPanel(req)}
                                                            </td>
                                                        </tr>
                                                    );
                                                })
                                            )}
                                        </tbody>
                                    </table>
                                </div>
                                <div className="bg-[#0f172a]/20 border border-white/5 rounded-[2.5rem] overflow-hidden shadow-2xl opacity-70">
                                    <div className="px-10 py-6 border-b border-white/5 bg-black/20"><h3 className="text-[9px] font-black text-gray-500 uppercase tracking-[0.4em]">활성 유저 채널 요약</h3></div>
                                    <table className="w-full text-left">
                                        <thead className="bg-black/30 border-b border-white/5 text-[10px] font-black text-gray-500 uppercase tracking-widest">
                                            <tr><th className="px-10 py-6">채널명 / 계정</th><th className="px-10 py-6 text-center">생성 영상수</th><th className="px-10 py-6 text-center">최근 접속일</th><th className="px-10 py-6 text-right">상태</th></tr>
                                        </thead>
                                        <tbody className="divide-y divide-white/5">
                                            {users.slice(0, 5).map(u => {
                                                const userVideos = globalLogs.filter(l => l.user_id === u.id && (l.task_type || '').toLowerCase() === 'video').length;
                                                return (
                                                    <tr key={u.id} className="hover:bg-white/[0.03] transition-colors group">
                                                        <td className="px-10 py-6 align-middle"><div className="font-black text-white text-base group-hover:text-blue-400 transition-colors uppercase tracking-tight">{u.email}</div><div className="text-[11px] text-gray-600 font-bold mt-1 uppercase italic tracking-tighter">{u.user_metadata?.full_name || '연동된 채널 없음'}</div></td>
                                                        <td className="px-10 py-6 text-center align-middle font-black text-white text-xl tabular-nums">{userVideos}</td>
                                                        <td className="px-10 py-6 text-center align-middle text-[12px] font-black text-gray-500">{formatDate(u.last_sign_in_at)}</td>
                                                        <td className="px-10 py-6 text-right align-middle"><span className="px-3 py-1 bg-green-500/10 text-green-500 text-[9px] font-black rounded-full border border-green-500/20 uppercase">정상 연결</span></td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        ) : renderLogTable(globalLogs, true)}
                    </div>
                )}

                {activeTab === 'withdrawals' && (
                    <div className="bg-[#0f172a]/20 border border-white/5 rounded-[3rem] overflow-hidden shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <div className="px-10 py-6 border-b border-white/5 bg-black/20 flex justify-between items-center">
                            <h3 className="text-sm font-black text-gray-400 uppercase tracking-[0.2em]">수당 출금 요청 리스트</h3>
                            <button onClick={fetchWithdrawals} className="px-6 py-2 bg-blue-600/10 hover:bg-blue-600 text-blue-500 hover:text-white text-sm font-black rounded-xl border border-blue-500/20 transition-all uppercase tracking-widest">새로고침</button>
                        </div>
                        <table className="w-full text-left">
                            <thead className="bg-black/30 border-b border-white/20 text-sm font-black text-gray-400 uppercase tracking-widest">
                                <tr>
                                    <th className="px-6 py-5 whitespace-nowrap">신청일자</th>
                                    <th className="px-6 py-5 whitespace-nowrap">이메일</th>
                                    <th className="px-6 py-5 whitespace-nowrap">출금 주소</th>
                                    <th className="px-6 py-5 text-right whitespace-nowrap">금액 (USDT)</th>
                                    <th className="px-6 py-5 text-right whitespace-nowrap">수수료율</th>
                                    <th className="px-6 py-5 text-right whitespace-nowrap">수수료</th>
                                    <th className="px-6 py-5 text-right whitespace-nowrap">실지급액</th>
                                    <th className="px-6 py-5 text-center whitespace-nowrap">상태</th>
                                    <th className="px-6 py-5 text-center whitespace-nowrap">액션</th>
                                    <th className="px-6 py-5 text-right whitespace-nowrap">수수료율</th>
                                    <th className="px-6 py-5 text-right whitespace-nowrap">수수료</th>
                                    <th className="px-6 py-5 text-right whitespace-nowrap">실지급액</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-white/20">
                                {withdrawals.map(w => (
                                    <tr key={w.id} className="hover:bg-white/[0.03] transition-colors group">
                                        <td className="px-6 py-5 text-sm text-gray-400">{new Date(w.created_at).toLocaleString()}</td>
                                        <td className="px-6 py-5 text-base font-bold text-blue-400">{w.profiles?.email || 'N/A'}</td>
                                        <td className="px-6 py-5 text-sm font-mono text-gray-300 max-w-[200px] truncate">{w.dest_address}</td>
                                        <td className="px-6 py-5 text-right text-base font-black text-green-400">{w.amount} USDT</td>
                                        <td className="px-6 py-5 text-right text-xs text-orange-400">
                                            {w.commission_percent ? `${w.commission_percent}%` : '-'}
                                        </td>
                                        <td className="px-6 py-5 text-right text-xs text-red-400">
                                            {w.commission_usd ? `$${w.commission_usd.toFixed(2)}` : '-'}
                                        </td>
                                        <td className="px-6 py-5 text-right text-xs text-blue-400">
                                            {w.net_usd ? `$${w.net_usd.toFixed(2)}` : '-'}
                                        </td>
                                        <td className="px-6 py-5 text-center">
                                            {w.status === 'pending' && <span className="px-3 py-1.5 bg-yellow-500/20 text-yellow-400 rounded-lg text-sm font-bold">대기중</span>}
                                            {w.status === 'completed' && <span className="px-3 py-1.5 bg-green-500/20 text-green-400 rounded-lg text-sm font-bold">완료</span>}
                                            {w.status === 'rejected' && <span className="px-3 py-1.5 bg-red-500/20 text-red-400 rounded-lg text-sm font-bold">거절</span>}
                                        </td>
                                        <td className="px-6 py-5 text-center">
                                            {w.status === 'pending' && (
                                                <div className="flex justify-center gap-2">
                                                    <button onClick={() => updateWithdrawalStatus(w.id, 'completed')} className="px-4 py-2 bg-green-600 hover:bg-green-500 text-white text-xs font-bold rounded-lg transition-colors">승인완료</button>
                                                    <button onClick={() => updateWithdrawalStatus(w.id, 'rejected')} className="px-4 py-2 bg-red-600/50 hover:bg-red-500 text-white text-xs font-bold rounded-lg transition-colors">거절</button>
                                                </div>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                                {withdrawals.length === 0 && (
                                    <tr>
                                        <td colSpan={9} className="px-6 py-10 text-center text-gray-500 text-base font-bold">출금 신청 내역이 없습니다.</td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                )}

{activeTab === 'users' && (
                    <div className="bg-[#0f172a]/20 border border-white/5 rounded-[3rem] overflow-hidden shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <div className="px-10 py-6 border-b border-white/5 bg-black/20 flex justify-between items-center">
                            <h3 className="text-sm font-black text-gray-400 uppercase tracking-[0.2em]">회원 관리 리스트</h3>
                            <button onClick={fetchUsers} className="px-6 py-2 bg-blue-600/10 hover:bg-blue-600 text-blue-500 hover:text-white text-sm font-black rounded-xl border border-blue-500/20 transition-all uppercase tracking-widest">새로고침</button>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-left table-auto">
                                <thead className="bg-black/30 border-b border-white/20 text-xs font-black text-gray-400 uppercase tracking-wider">
                                    <tr>
                                        <th className="px-3 py-4.5 whitespace-nowrap w-20">이름</th>
                                        <th className="px-3 py-4.5 whitespace-nowrap">이메일 / 등급</th>
                                        <th className="px-3 py-4.5 whitespace-nowrap">연락처</th>
                                        <th className="px-3 py-4.5 whitespace-nowrap">국적</th>
                                        <th className="px-3 py-4.5 whitespace-nowrap">선호 카테고리</th>
                                        <th className="px-3 py-4.5 whitespace-nowrap">선호 길이</th>
                                        <th className="px-3 py-4.5 whitespace-nowrap">제작 언어</th>
                                        <th className="px-3 py-4.5 whitespace-nowrap">추천인</th>
                                        <th className="px-3 py-4.5 text-center whitespace-nowrap">토큰</th>
                                        <th className="px-3 py-4.5 text-center whitespace-nowrap">멤버십</th>
                                        <th className="px-3 py-4.5 text-center whitespace-nowrap">가입 / 최근접속</th>
                                        <th className="px-3 py-4.5 text-center whitespace-nowrap">USDT 잔액</th>
                                        <th className="px-3 py-4.5 text-center whitespace-nowrap">수수료</th>
                                        <th className="px-3 py-4.5 text-center whitespace-nowrap">실지급액</th>
                                        <th className="px-3 py-4.5 text-center whitespace-nowrap">관리</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-white/10">
                                    {users.map(u => (
                                        <tr key={u.id} className="hover:bg-white/[0.03] transition-colors group">
                                            {/* 이름 */}
                                            <td className="px-3 py-3 w-20">
                                                <div className="font-black text-white text-xs whitespace-nowrap truncate w-20" title={u.user_metadata?.full_name}>{u.user_metadata?.full_name || <span className="text-gray-600 italic text-[11px]">없음</span>}</div>
                                            </td>
                                            {/* 이메일 / 관리자 등급 */}
                                            <td className="px-3 py-3 max-w-[140px]">
                                                <div className="font-bold text-blue-400 text-xs tracking-tight truncate" title={u.email}>{u.email?.toLowerCase()}</div>
                                                <div className="flex gap-1 mt-1 flex-wrap">
                                                    {u.email === SUPER_ADMIN_EMAIL && <span className="px-1.5 py-0.5 bg-blue-600 text-[9px] font-black rounded text-white">최고관리자</span>}
                                                    {u.app_metadata?.role === 'sub_admin' && u.email !== SUPER_ADMIN_EMAIL && <span className="px-1.5 py-0.5 bg-indigo-500 text-[9px] font-black rounded text-white">부관리자</span>}
                                                    <span className={`px-1.5 py-0.5 text-[9px] font-black rounded border ${u.profile?.is_approved ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20'}`}>
                                                        {u.profile?.is_approved ? '승인됨' : '승인대기'}
                                                    </span>
                                                </div>
                                            </td>
                                            {/* 연락처 */}
                                            <td className="px-3 py-3 text-xs text-gray-300 font-bold whitespace-nowrap">
                                                {u.user_metadata?.contact || <span className="text-gray-700">-</span>}
                                            </td>
                                            {/* 국적 */}
                                            <td className="px-3 py-3 text-xs text-gray-300 font-bold whitespace-nowrap">
                                                {u.user_metadata?.nationality || <span className="text-gray-700">-</span>}
                                            </td>
                                            <td className="px-3 py-3">
                                                {u.profile?.preferred_category_names?.length ? (
                                                    <div className="flex flex-wrap gap-1 max-w-[180px]">
                                                        {u.profile.preferred_category_names.slice(0, 2).map((category) => (
                                                            <span
                                                                key={`${u.id}-${category}`}
                                                                className="px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 text-[10px] font-bold"
                                                            >
                                                                {category}
                                                            </span>
                                                        ))}
                                                        {u.profile.preferred_category_names.length > 2 && (
                                                            <span className="px-1.5 py-0.5 rounded bg-white/5 text-gray-400 border border-white/10 text-[10px] font-bold">
                                                                +{u.profile.preferred_category_names.length - 2}
                                                            </span>
                                                        )}
                                                    </div>
                                                ) : (
                                                    <span className="text-gray-700">-</span>
                                                )}
                                            </td>
                                            <td className="px-3 py-3 whitespace-nowrap">
                                                {u.profile?.preferred_video_length ? (
                                                    <span className="px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-300 border border-violet-500/20 text-[10px] font-bold">
                                                        {u.profile.preferred_video_length === '15m'
                                                            ? '15m'
                                                            : u.profile.preferred_video_length === '30m'
                                                                ? '30m'
                                                                : u.profile.preferred_video_length === '60m_plus'
                                                                    ? '60m+'
                                                                    : u.profile.preferred_video_length}
                                                    </span>
                                                ) : (
                                                    <span className="text-gray-700">-</span>
                                                )}
                                            </td>
                                            <td className="px-3 py-3">
                                                <div className="flex flex-wrap gap-1 max-w-[140px]">
                                                    {(u.profile?.preferred_languages?.length ? u.profile.preferred_languages : ['ko']).map(lang => (
                                                        <span key={`${u.id}-lang-${lang}`} className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 text-[10px] font-bold">
                                                            {contentLanguageLabel(lang)}
                                                        </span>
                                                    ))}
                                                </div>
                                            </td>
                                            {/* 추천인 */}
                                            <td className="px-3 py-3 text-xs whitespace-nowrap">
                                                {u.user_metadata?.referrer
                                                    ? <span className="text-yellow-400 font-bold">{u.user_metadata.referrer}</span>
                                                    : <span className="text-gray-700">-</span>}
                                                <div className="mt-1 text-[10px] font-bold text-gray-500">
                                                    내 코드: <span className="text-cyan-300">{u.profile?.referral_code || '-'}</span>
                                                </div>
                                                <div className="text-[10px] font-bold text-gray-600">
                                                    국가: {u.profile?.referral_country || u.profile?.country_code || '-'} · Lv{u.profile?.referral_depth || 0}
                                                </div>
                                            </td>
                                            {/* 보유 토큰 */}
                                            <td className="px-3 py-3 text-center font-black text-white text-sm tabular-nums whitespace-nowrap">
                                                {u.profile?.token_balance?.toLocaleString() || 0}
                                            </td>
                                            {/* 멤버십 */}
                                            <td className="px-3 py-3 text-center">
                                                {canManageSensitiveUserSettings ? (
                                                    <button onClick={() => handleRoleChange(u.id, u.app_metadata?.membership)} className={`px-2 py-1 rounded-lg text-[10px] font-black border uppercase tracking-wider transition-all whitespace-nowrap ${u.app_metadata?.membership === 'pro' ? 'bg-indigo-600 text-white border-indigo-500 shadow-lg' : 'bg-white/5 text-gray-500 border-white/10 hover:border-white/30'}`}>
                                                        {u.app_metadata?.membership?.toUpperCase() === 'PRO' ? 'PRO' : '스탠다드'}
                                                    </button>
                                                ) : (
                                                    <span className={`px-2 py-1 rounded-lg text-[10px] font-black border uppercase tracking-wider whitespace-nowrap ${u.app_metadata?.membership === 'pro' ? 'bg-indigo-600/20 text-indigo-300 border-indigo-500/30' : 'bg-white/5 text-gray-500 border-white/10'}`}>
                                                        {u.app_metadata?.membership?.toUpperCase() === 'PRO' ? 'PRO' : '스탠다드'}
                                                    </span>
                                                )}
                                            </td>
                                            {/* 가입 / 최근접속 */}
                                            <td className="px-3 py-3 text-center whitespace-nowrap">
                                                <div className="text-[11px] font-bold text-gray-400 mb-0.5" title="가입일">{formatDate(u.created_at)}</div>
                                                <div className="text-[9px] font-bold text-gray-600" title="최근접속">{formatDate(u.last_sign_in_at)}</div>
                                            </td>
                                            {/* USDT 잔액 */}
                                            <td className="px-3 py-3 text-center font-black text-emerald-300 text-sm tabular-nums whitespace-nowrap">
                                                {Number(u.profile?.usdt_balance || 0).toLocaleString()}
                                            </td>
                                            {/* 관리 메뉴 */}
                                            <td className="px-3 py-3">
                                                <div className="flex flex-wrap items-center justify-center gap-1 max-w-[200px] mx-auto">
                                                    {isSuperAdmin && u.email !== SUPER_ADMIN_EMAIL && (
                                                        <>
                                                            <button onClick={() => handleAdminRoleToggle(u.id, u.app_metadata?.role === 'sub_admin')} className={`px-2 py-1 rounded text-[10px] font-black border transition-all whitespace-nowrap ${u.app_metadata?.role === 'sub_admin' ? 'bg-indigo-600/20 text-indigo-400 border-indigo-500/30' : 'bg-white/5 text-gray-600 border-white/10'}`}>부관리자</button>
                                                            <button onClick={() => handleSuperadminToggle(u.id, u.profile?.is_superadmin)} className={`px-2 py-1 rounded text-[10px] font-black border transition-all whitespace-nowrap ${u.profile?.is_superadmin ? 'bg-red-600/20 text-red-400 border-red-500/30' : 'bg-purple-600/10 text-purple-300 border-purple-500/20'}`}>슈퍼어드민</button>
                                                        </>
                                                    )}
                                                    <button onClick={() => handleApprovalChange(u.id, !u.profile?.is_approved)} className={`px-2 py-1 text-[10px] font-black rounded border transition-all whitespace-nowrap ${u.profile?.is_approved ? 'bg-yellow-600/10 hover:bg-yellow-600 text-yellow-500 hover:text-white border-yellow-500/20' : 'bg-emerald-600/10 hover:bg-emerald-600 text-emerald-400 hover:text-white border-emerald-500/20'}`}>
                                                        {u.profile?.is_approved ? '대기전환' : '승인'}
                                                    </button>
                                                    {canManageSensitiveUserSettings && (
                                                        <button onClick={() => handleRecharge(u.id)} className="px-2 py-1 bg-green-600/10 hover:bg-green-600 text-green-500 hover:text-white text-[10px] font-black rounded border border-green-500/20 transition-all whitespace-nowrap">토큰충전</button>
                                                    )}
                                                    <button onClick={() => { setEditInfoUser(u); setEditInfoForm({ full_name: u.user_metadata?.full_name || '', nationality: u.user_metadata?.nationality || '', contact: u.user_metadata?.contact || '', preferred_languages: u.profile?.preferred_languages?.length ? u.profile.preferred_languages : ['ko'], persona_name: u.profile?.persona_name || '', persona_style: u.profile?.persona_style || '', persona_description: u.profile?.persona_description || '' }); }} className="px-2 py-1 bg-yellow-600/10 hover:bg-yellow-600 text-yellow-500 hover:text-white text-[10px] font-black rounded border border-yellow-500/20 transition-all whitespace-nowrap">정보수정</button>
                                                    <button onClick={() => { setLogViewUser(u); setLogPeriod(1); fetchUserLogs(u.id, 1); }} className="px-2 py-1 bg-blue-600/10 hover:bg-blue-600 text-blue-500 hover:text-white text-[10px] font-black rounded border border-blue-500/20 transition-all whitespace-nowrap">로그조회</button>
                                                    {canManageSensitiveUserSettings && u.app_metadata?.membership?.toLowerCase() === 'pro' && (
                                                        <button onClick={() => { setApiViewUser(u); setTempApiKeys(u.app_metadata?.custom_api_keys || { openai: '', gemini: '', pexels: '', replicate: '' }); }} className="px-2 py-1 bg-indigo-600/10 hover:bg-indigo-600 text-indigo-500 hover:text-white text-[10px] font-black rounded border border-indigo-500/20 transition-all whitespace-nowrap">API</button>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}

                {activeTab === 'organization' && (
                    <div className="space-y-6 animate-in fade-in duration-500">
                        <div className="flex items-center justify-between gap-4">
                            <div>
                                <h3 className="text-2xl font-black tracking-tight">📊 조직 관리</h3>
                                <p className="mt-1 text-xs font-bold text-gray-500">
                                    추천인 트리, 국가 태그, 토큰 사용량 기준 커미션 예상치를 확인합니다.
                                </p>
                            </div>
                            <div className="flex items-center gap-2">
                                {[7, 30, 90].map(days => (
                                    <button
                                        key={`ref-days-${days}`}
                                        type="button"
                                        onClick={() => { setReferralDays(days); fetchReferralReport(days); }}
                                        className={`rounded-xl px-4 py-2 text-[10px] font-black border transition-all ${referralDays === days ? 'bg-blue-600 text-white border-blue-500' : 'bg-white/5 text-gray-400 border-white/10 hover:text-white'}`}
                                    >
                                        {days}일
                                    </button>
                                ))}
                                <button onClick={() => fetchReferralReport(referralDays)} className="rounded-xl border border-blue-500/20 bg-blue-600/10 px-5 py-2 text-[10px] font-black text-blue-300 hover:bg-blue-600 hover:text-white">
                                    {referralLoading ? '로딩 중...' : '새로고침'}
                                </button>
                            </div>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                            <StatCard label="ORG USERS" value={(referralReport?.summary?.users || 0).toLocaleString()} unit="명" color="white" />
                            <StatCard label="TOKEN USAGE" value={(referralReport?.summary?.totalTokenUsage || 0).toLocaleString()} unit="TK" color="orange" />
                            <StatCard label="EST. COMMISSION" value={(referralReport?.summary?.totalCommissionTokens || 0).toLocaleString()} unit="TK" color="green" />
                            <StatCard label="COUNTRIES" value={(referralReport?.summary?.countries?.length || 0).toLocaleString()} unit="EA" color="blue" />
                        </div>

                        <div className="rounded-[2.5rem] border border-white/10 bg-[#0f172a]/60 overflow-hidden shadow-2xl">
                            <div className="border-b border-white/10 bg-black/20 px-8 py-5 flex items-center justify-between">
                                <h4 className="text-xs font-black uppercase tracking-[0.3em] text-blue-400">Referral Tree</h4>
                                <span className="text-[11px] font-bold text-gray-500">
                                    Lv1 5% · Lv2 2% · 국가 책임자 별도 커미션율
                                </span>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-left text-sm">
                                    <thead className="bg-black/30 text-[10px] font-black uppercase tracking-widest text-gray-500">
                                        <tr>
                                            <th className="px-8 py-5">유저 / 트리</th>
                                            <th className="px-8 py-5">추천 코드</th>
                                            <th className="px-8 py-5">국가</th>
                                            <th className="px-8 py-5 text-right">직속</th>
                                            <th className="px-8 py-5 text-right">Lv2</th>
                                            <th className="px-8 py-5 text-right">토큰 사용량</th>
                                            <th className="px-8 py-5 text-right">예상 커미션</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-white/5">
                                        {buildReferralTreeRows(referralReport?.profiles || []).map((profile: any) => {
                                            const totalCommission = (profile.direct_commission_tokens || 0) + (profile.level2_commission_tokens || 0) + (profile.country_commission_tokens || 0)
                                            return (
                                                <tr key={profile.id} className="hover:bg-white/[0.03]">
                                                    <td className="px-8 py-5">
                                                        <div className="font-black text-white" style={{ paddingLeft: `${Math.min(Number(profile.referral_depth || 0), 6) * 18}px` }}>
                                                            {Number(profile.referral_depth || 0) > 0 && <span className="mr-2 text-gray-600">└</span>}
                                                            {profile.email || profile.id}
                                                        </div>
                                                        <div className="mt-1 text-[10px] font-bold text-gray-600">Depth {profile.referral_depth || 0}</div>
                                                    </td>
                                                    <td className="px-8 py-5">
                                                        <button onClick={() => copyReferralCode(profile.referral_code)} className="rounded-lg border border-cyan-500/20 bg-cyan-500/10 px-3 py-1 text-[11px] font-black text-cyan-300 hover:bg-cyan-500/20">
                                                            {profile.referral_code || '-'}
                                                        </button>
                                                    </td>
                                                    <td className="px-8 py-5 text-xs font-bold text-gray-300">
                                                        {profile.referral_country || profile.country_code || 'KR'}
                                                        {Number(profile.commission_rate || 0) > 0 && <span className="ml-2 rounded bg-emerald-500/10 px-2 py-1 text-[10px] text-emerald-300">국가 {profile.commission_rate}%</span>}
                                                        {isSuperAdmin && (
                                                            <button onClick={() => handleCountryManagerUpdate(profile)} className="ml-2 rounded border border-indigo-500/20 bg-indigo-500/10 px-2 py-1 text-[10px] font-black text-indigo-300 hover:bg-indigo-500/20">
                                                                책임자 지정
                                                            </button>
                                                        )}
                                                    </td>
                                                    <td className="px-8 py-5 text-right font-black text-white">{profile.direct_referrals || 0}</td>
                                                    <td className="px-8 py-5 text-right font-black text-white">{profile.level2_referrals || 0}</td>
                                                    <td className="px-8 py-5 text-right font-black text-orange-300">{Number(profile.token_usage || 0).toLocaleString()}</td>
                                                    <td className="px-8 py-5 text-right font-black text-emerald-300">{Number(totalCommission || 0).toLocaleString()} TK</td>
                                                </tr>
                                            )
                                        })}
                                        {(!referralReport?.profiles || referralReport.profiles.length === 0) && (
                                            <tr>
                                                <td colSpan={7} className="px-8 py-20 text-center text-xs font-black uppercase tracking-widest text-gray-600">
                                                    조직 데이터가 없습니다.
                                                </td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                )}

                {activeTab === 'api' && canManageSystemSettings && (
                    <div className="bg-[#0f172a]/20 border border-white/5 rounded-[3rem] overflow-hidden shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-500 max-w-7xl mx-auto">
                        {/* 헤더 */}
                        <div className="px-10 py-6 border-b border-white/5 bg-black/20 flex flex-col sm:flex-row sm:items-center gap-4">
                            <div className="flex-1">
                                <h3 className="text-sm font-black text-gray-400 uppercase tracking-[0.2em]">시스템 전역 API 키 &amp; 설정</h3>
                                <p className="text-[10px] text-gray-600 mt-1">서버 공용 키는 개인 키가 없는 유저에게 적용됩니다.</p>
                            </div>
                            {/* 서브 탭 */}
                            <div className="flex gap-1 p-1 bg-black/40 border border-white/5 rounded-2xl flex-shrink-0">
                                {([
                                    { key: 'ai',     icon: '🤖', label: 'AI 핵심' },
                                    { key: 'music',  icon: '🎵', label: '음악' },
                                    { key: 'video',  icon: '🎬', label: '영상/결제' },
                                    { key: 'legal',  icon: '📋', label: '약관' },
                                    { key: 'policy', icon: '⚙️', label: '운영정책' },
                                ] as const).map(t => (
                                    <button
                                        key={t.key}
                                        type="button"
                                        onClick={() => setApiSettingsTab(t.key)}
                                        className={`px-3 py-2 rounded-xl text-[11px] font-black transition-all whitespace-nowrap ${
                                            apiSettingsTab === t.key
                                                ? 'bg-blue-600 text-white shadow-lg'
                                                : 'text-gray-500 hover:text-white hover:bg-white/5'
                                        }`}
                                    >
                                        {t.icon} {t.label}
                                    </button>
                                ))}
                            </div>
                        </div>

                        <div className="p-8 space-y-6">

                            {/* ── 탭 1: AI 핵심 ── */}
                            {apiSettingsTab === 'ai' && (
                                <div className="space-y-5 animate-in fade-in duration-200">
                                    {/* API Keys */}
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                                        {([
                                            { key: 'gemini',  label: 'Gemini API Key',        hint: 'AI 생성 전반 (스크립트, 이미지 프롬프트, 음악 등)' },
                                            { key: 'claude',  label: 'Claude API Key',         hint: '대본 생성 전용 (Anthropic Claude)' },
                                            { key: 'youtube', label: 'YouTube Data API Key',  hint: '채널/영상 검색 및 통계 조회' },
                                        ] as { key: keyof typeof sysKeys; label: string; hint: string }[]).map(({ key, label, hint }) => (
                                            <div key={key} className="space-y-1.5">
                                                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest block">{label}</label>
                                                <p className="text-[10px] text-gray-600">{hint}</p>
                                                <input
                                                    type="password"
                                                    value={sysKeys[key] as string}
                                                    onChange={e => setSysKeys(prev => ({ ...prev, [key]: e.target.value }))}
                                                    onFocus={e => (e.target as HTMLInputElement).type = 'text'}
                                                    onBlur={e => (e.target as HTMLInputElement).type = 'password'}
                                                    placeholder={sysKeys[key] ? '••••••••••••' : '(미설정)'}
                                                    className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-gray-300 placeholder:text-gray-700"
                                                />
                                            </div>
                                        ))}
                                    </div>

                                    {/* AI Model Settings */}
                                    <div className="rounded-2xl border border-blue-500/20 bg-blue-500/5 p-5 space-y-4">
                                        <p className="text-[10px] font-black text-blue-400 uppercase tracking-widest">🤖 AI 모델 선택</p>
                                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                            {/* 대본 생성 모델 */}
                                            <div>
                                                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">대본 생성 모델</label>
                                                <select
                                                    value={sysKeys.script_generation_model}
                                                    onChange={e => setSysKeys(prev => ({ ...prev, script_generation_model: e.target.value }))}
                                                    className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 text-gray-300 cursor-pointer"
                                                >
                                                    <optgroup label="🟢 Claude (Anthropic)" className="bg-[#111]">
                                                        <option value="claude-sonnet-4-6" className="bg-[#111]">Claude Sonnet 4.6 (추천)</option>
                                                        <option value="claude-opus-4-8" className="bg-[#111]">Claude Opus 4.8 (고성능)</option>
                                                        <option value="claude-haiku-4-5-20251001" className="bg-[#111]">Claude Haiku 4.5 (빠름)</option>
                                                    </optgroup>
                                                    <optgroup label="🔵 Gemini (Google)" className="bg-[#111]">
                                                        <option value="gemini-2.5-flash" className="bg-[#111]">Gemini 2.5 Flash</option>
                                                        <option value="gemini-2.5-pro" className="bg-[#111]">Gemini 2.5 Pro</option>
                                                    </optgroup>
                                                </select>
                                                <p className="text-[9px] text-gray-600 mt-1">대본 생성, 기획, 분석에 사용</p>
                                            </div>

                                            {/* 이미지 생성 모델 */}
                                            <div>
                                                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">이미지 생성 모델</label>
                                                <select
                                                    value={sysKeys.image_generation_model}
                                                    onChange={e => setSysKeys(prev => ({ ...prev, image_generation_model: e.target.value }))}
                                                    className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-purple-500/50 text-gray-300 cursor-pointer"
                                                >
                                                    <optgroup label="🔵 Gemini (Google)" className="bg-[#111]">
                                                        <option value="gemini-3.1-flash-image-preview" className="bg-[#111]">Gemini 3.1 Flash Image (기본)</option>
                                                        <option value="imagen-4" className="bg-[#111]">Imagen 4</option>
                                                        <option value="imagen-3" className="bg-[#111]">Imagen 3</option>
                                                    </optgroup>
                                                    <optgroup label="🟣 Replicate" className="bg-[#111]">
                                                        <option value="black-forest-labs/flux-dev" className="bg-[#111]">Flux Dev</option>
                                                        <option value="stability-ai/stable-diffusion-xl" className="bg-[#111]">SDXL</option>
                                                    </optgroup>
                                                </select>
                                                <p className="text-[9px] text-gray-600 mt-1">씬 이미지 생성에 사용</p>
                                            </div>

                                            {/* 영상 생성 모델 */}
                                            <div>
                                                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">영상 생성 모델</label>
                                                <select
                                                    value={sysKeys.video_generation_model}
                                                    onChange={e => setSysKeys(prev => ({ ...prev, video_generation_model: e.target.value }))}
                                                    className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/50 text-gray-300 cursor-pointer"
                                                >
                                                    <optgroup label="🔵 Veo (Google)" className="bg-[#111]">
                                                        <option value="veo-3.1-fast-generate-preview" className="bg-[#111]">Veo 3.1 Fast Preview (기본)</option>
                                                        <option value="veo-3.0-generate" className="bg-[#111]">Veo 3.0</option>
                                                    </optgroup>
                                                    <optgroup label="🟣 Wan (Replicate)" className="bg-[#111]">
                                                        <option value="wan-2.1" className="bg-[#111]">Wan 2.1</option>
                                                        <option value="wan-1.3" className="bg-[#111]">Wan 1.3</option>
                                                    </optgroup>
                                                </select>
                                                <p className="text-[9px] text-gray-600 mt-1">영상 생성에 사용</p>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Model Info */}
                                    <div className="rounded-2xl border border-cyan-500/20 bg-cyan-500/5 p-4">
                                        <p className="text-[10px] font-black text-cyan-400 uppercase tracking-widest mb-2">📌 모델 정보</p>
                                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-[10px] text-gray-400">
                                            <div className="bg-black/20 rounded-lg p-2">
                                                <div className="font-bold text-white mb-1">Claude Sonnet 4.6</div>
                                                <div>뛰어난 대본 작성 능력</div>
                                            </div>
                                            <div className="bg-black/20 rounded-lg p-2">
                                                <div className="font-bold text-white mb-1">Gemini 2.5 Flash</div>
                                                <div>빠르고 효율적인 생성</div>
                                            </div>
                                            <div className="bg-black/20 rounded-lg p-2">
                                                <div className="font-bold text-white mb-1">Veo 3.1 Fast</div>
                                                <div>고품질 영상 생성</div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* ── 탭 2: 음악 ── */}
                            {apiSettingsTab === 'music' && (
                                <div className="space-y-5 animate-in fade-in duration-200">
                                    <div>
                                        <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">Music Generation Provider</label>
                                        <select
                                            value={sysKeys.music_provider}
                                            onChange={e => setSysKeys(prev => ({ ...prev, music_provider: e.target.value }))}
                                            className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-purple-500/50 text-gray-300 cursor-pointer"
                                        >
                                            <option value="elevenlabs" className="bg-[#111]">ElevenLabs (Default)</option>
                                            <option value="suno" className="bg-[#111]">Suno API</option>
                                            <option value="gemini" className="bg-[#111]">Gemini / Lyria</option>
                                        </select>
                                    </div>

                                    {/* ElevenLabs */}
                                    <div className="rounded-2xl border border-white/10 bg-black/20 p-4 space-y-3">
                                        <p className="text-[10px] font-black text-purple-400 uppercase tracking-widest">🎙️ ElevenLabs</p>
                                        <div>
                                            <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">ElevenLabs API Key</label>
                                            <input
                                                type="password"
                                                value={sysKeys.elevenlabs}
                                                onChange={e => setSysKeys(prev => ({ ...prev, elevenlabs: e.target.value }))}
                                                onFocus={e => (e.target as HTMLInputElement).type = 'text'}
                                                onBlur={e => (e.target as HTMLInputElement).type = 'password'}
                                                placeholder={sysKeys.elevenlabs ? '••••••••••••' : '(미설정)'}
                                                className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-purple-500/50 font-mono text-gray-300 placeholder:text-gray-700"
                                            />
                                        </div>
                                    </div>

                                    {/* Suno */}
                                    <div className="rounded-2xl border border-white/10 bg-black/20 p-4 space-y-3">
                                        <p className="text-[10px] font-black text-orange-400 uppercase tracking-widest">🎸 Suno</p>
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                            <div>
                                                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">Suno API Key</label>
                                                <input
                                                    type="password"
                                                    value={sysKeys.suno}
                                                    onChange={e => setSysKeys(prev => ({ ...prev, suno: e.target.value }))}
                                                    onFocus={e => (e.target as HTMLInputElement).type = 'text'}
                                                    onBlur={e => (e.target as HTMLInputElement).type = 'password'}
                                                    placeholder={sysKeys.suno ? '••••••••••••' : '(미설정)'}
                                                    className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-orange-500/50 font-mono text-gray-300 placeholder:text-gray-700"
                                                />
                                            </div>
                                            <div>
                                                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">Suno API Base URL</label>
                                                <input
                                                    type="text"
                                                    value={sysKeys.suno_base_url}
                                                    onChange={e => setSysKeys(prev => ({ ...prev, suno_base_url: e.target.value }))}
                                                    placeholder="https://your-suno-provider.example.com/api/generate"
                                                    className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-orange-500/50 font-mono text-gray-300 placeholder:text-gray-700"
                                                />
                                            </div>
                                        </div>
                                    </div>

                                    {/* Gemini Lyria */}
                                    <div className="rounded-2xl border border-white/10 bg-black/20 p-4 space-y-3">
                                        <p className="text-[10px] font-black text-blue-400 uppercase tracking-widest">✨ Gemini / Lyria</p>
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                            <div>
                                                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">Gemini Music Model</label>
                                                <select
                                                    value={sysKeys.music_gemini_model}
                                                    onChange={e => setSysKeys(prev => ({ ...prev, music_gemini_model: e.target.value }))}
                                                    className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 text-gray-300 cursor-pointer"
                                                >
                                                    <option value="lyria-3-pro-preview" className="bg-[#111]">Lyria 3 Pro Preview</option>
                                                    <option value="lyria-3-clip-preview" className="bg-[#111]">Lyria 3 Clip Preview</option>
                                                    <option value="lyria-002" className="bg-[#111]">Lyria 2 Legacy</option>
                                                </select>
                                            </div>
                                            <div>
                                                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">Gemini Location</label>
                                                <input
                                                    type="text"
                                                    value={sysKeys.music_gemini_location}
                                                    onChange={e => setSysKeys(prev => ({ ...prev, music_gemini_location: e.target.value }))}
                                                    placeholder="global"
                                                    className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-gray-300 placeholder:text-gray-700"
                                                />
                                            </div>
                                            <div>
                                                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">Gemini Project ID</label>
                                                <input
                                                    type="text"
                                                    value={sysKeys.music_gemini_project_id}
                                                    onChange={e => setSysKeys(prev => ({ ...prev, music_gemini_project_id: e.target.value }))}
                                                    placeholder="google-cloud-project-id"
                                                    className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-gray-300 placeholder:text-gray-700"
                                                />
                                            </div>
                                            <div>
                                                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">Gemini Music Base URL</label>
                                                <input
                                                    type="text"
                                                    value={sysKeys.music_gemini_base_url}
                                                    onChange={e => setSysKeys(prev => ({ ...prev, music_gemini_base_url: e.target.value }))}
                                                    placeholder="optional custom endpoint; supports {project_id}, {location}, {model}"
                                                    className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-gray-300 placeholder:text-gray-700"
                                                />
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* ── 탭 3: 영상/결제 ── */}
                            {apiSettingsTab === 'video' && (
                                <div className="space-y-5 animate-in fade-in duration-200">
                                    <div className="rounded-2xl border border-white/10 bg-black/20 p-4 space-y-4">
                                        <p className="text-[10px] font-black text-emerald-400 uppercase tracking-widest">🎬 TopView (영상 자동 업로드)</p>
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                            {([
                                                { key: 'topview',     label: 'TopView API Key' },
                                                { key: 'topview_uid', label: 'TopView UID' },
                                            ] as { key: keyof typeof sysKeys; label: string }[]).map(({ key, label }) => (
                                                <div key={key}>
                                                    <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">{label}</label>
                                                    <input
                                                        type="password"
                                                        value={sysKeys[key] as string}
                                                        onChange={e => setSysKeys(prev => ({ ...prev, [key]: e.target.value }))}
                                                        onFocus={e => (e.target as HTMLInputElement).type = 'text'}
                                                        onBlur={e => (e.target as HTMLInputElement).type = 'password'}
                                                        placeholder={sysKeys[key] ? '••••••••••••' : '(미설정)'}
                                                        className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/50 font-mono text-gray-300 placeholder:text-gray-700"
                                                    />
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                    <div className="rounded-2xl border border-yellow-500/20 bg-yellow-500/5 p-4 space-y-4">
                                        <p className="text-[10px] font-black text-yellow-400 uppercase tracking-widest">💰 Binance (출금 자동화)</p>
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                            {([
                                                { key: 'binance_api_key',    label: 'Binance API Key' },
                                                { key: 'binance_api_secret', label: 'Binance API Secret' },
                                            ] as { key: keyof typeof sysKeys; label: string }[]).map(({ key, label }) => (
                                                <div key={key}>
                                                    <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">{label}</label>
                                                    <input
                                                        type="password"
                                                        value={sysKeys[key] as string}
                                                        onChange={e => setSysKeys(prev => ({ ...prev, [key]: e.target.value }))}
                                                        onFocus={e => (e.target as HTMLInputElement).type = 'text'}
                                                        onBlur={e => (e.target as HTMLInputElement).type = 'password'}
                                                        placeholder={sysKeys[key] ? '••••••••••••' : '(미설정)'}
                                                        className="w-full bg-black/40 border border-yellow-500/20 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-yellow-500/50 font-mono text-gray-300 placeholder:text-gray-700"
                                                    />
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* ── 탭 4: 약관 ── */}
                            {apiSettingsTab === 'legal' && (
                                <div className="space-y-5 animate-in fade-in duration-200">
                                    <div className="flex justify-between items-center">
                                        <div>
                                            <h4 className="text-xs font-black text-blue-400 uppercase tracking-widest">가입 약관 및 개인정보처리방침</h4>
                                            <p className="text-[10px] text-gray-500 mt-1">회원가입 신청 화면에 실시간으로 반영됩니다.</p>
                                        </div>
                                        <div className="flex gap-1.5 p-1 bg-black/30 border border-white/5 rounded-xl">
                                            {([
                                                { key: 'ko', label: '🇰🇷 KO' },
                                                { key: 'en', label: '🇺🇸 EN' },
                                                { key: 'vi', label: '🇻🇳 VI' },
                                                { key: 'th', label: '🇹🇭 TH' }
                                            ] as const).map(l => (
                                                <button
                                                    key={l.key}
                                                    type="button"
                                                    onClick={() => setLegalActiveTab(l.key)}
                                                    className={`px-3 py-1.5 rounded-lg text-[10px] font-black transition-all ${legalActiveTab === l.key ? 'bg-blue-600 text-white shadow-md' : 'text-gray-500 hover:text-white'}`}
                                                >
                                                    {l.label}
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                        <div>
                                            <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">
                                                서비스 이용약관 ({legalActiveTab.toUpperCase()})
                                            </label>
                                            <textarea
                                                value={
                                                    legalActiveTab === 'ko' ? sysKeys.terms_ko :
                                                    legalActiveTab === 'en' ? sysKeys.terms_en :
                                                    legalActiveTab === 'th' ? sysKeys.terms_th :
                                                    sysKeys.terms_vi
                                                }
                                                onChange={e => setSysKeys(prev => {
                                                    if (legalActiveTab === 'ko') return { ...prev, terms_ko: e.target.value };
                                                    if (legalActiveTab === 'en') return { ...prev, terms_en: e.target.value };
                                                    if (legalActiveTab === 'th') return { ...prev, terms_th: e.target.value };
                                                    return { ...prev, terms_vi: e.target.value };
                                                })}
                                                rows={12}
                                                placeholder={`${legalActiveTab.toUpperCase()} 이용약관 내용을 입력하세요.`}
                                                className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 text-gray-300 placeholder:text-gray-700 resize-y font-sans leading-relaxed"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">
                                                개인정보처리방침 ({legalActiveTab.toUpperCase()})
                                            </label>
                                            <textarea
                                                value={
                                                    legalActiveTab === 'ko' ? sysKeys.privacy_ko :
                                                    legalActiveTab === 'en' ? sysKeys.privacy_en :
                                                    legalActiveTab === 'th' ? sysKeys.privacy_th :
                                                    sysKeys.privacy_vi
                                                }
                                                onChange={e => setSysKeys(prev => {
                                                    if (legalActiveTab === 'ko') return { ...prev, privacy_ko: e.target.value };
                                                    if (legalActiveTab === 'en') return { ...prev, privacy_en: e.target.value };
                                                    if (legalActiveTab === 'th') return { ...prev, privacy_th: e.target.value };
                                                    return { ...prev, privacy_vi: e.target.value };
                                                })}
                                                rows={12}
                                                placeholder={`${legalActiveTab.toUpperCase()} 개인정보처리방침 내용을 입력하세요.`}
                                                className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 text-gray-300 placeholder:text-gray-700 resize-y font-sans leading-relaxed"
                                            />
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* ── 탭 5: 운영정책 ── */}
                            {apiSettingsTab === 'policy' && (
                                <div className="space-y-5 animate-in fade-in duration-200">
                                    <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-5 space-y-4">
                                        <div>
                                            <h4 className="text-xs font-black text-emerald-300 uppercase tracking-widest">Longform Work Policy</h4>
                                            <p className="text-[10px] text-gray-500 mt-1">롱폼 직원 작업시간 잠금과 예상 수당 계산 기준입니다.</p>
                                        </div>
                                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                            <div>
                                                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">최소 영상 길이(분)</label>
                                                <input
                                                    type="number"
                                                    min="15"
                                                    value={sysKeys.longform_min_duration_minutes}
                                                    onChange={e => setSysKeys(prev => ({ ...prev, longform_min_duration_minutes: e.target.value }))}
                                                    className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/50 text-gray-300"
                                                />
                                            </div>
                                            <div>
                                                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">기본 수당 (USDT)</label>
                                                <input
                                                    type="number"
                                                    min="0"
                                                    value={sysKeys.longform_base_payout}
                                                    onChange={e => setSysKeys(prev => ({ ...prev, longform_base_payout: e.target.value }))}
                                                    className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/50 text-gray-300"
                                                />
                                            </div>
                                            <div>
                                                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">추가 1분당 수당 (USDT)</label>
                                                <input
                                                    type="number"
                                                    min="0"
                                                    value={sysKeys.longform_extra_minute_payout}
                                                    onChange={e => setSysKeys(prev => ({ ...prev, longform_extra_minute_payout: e.target.value }))}
                                                    className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/50 text-gray-300"
                                                />
                                            </div>
                                        </div>
                                        <label className="flex items-center gap-3 text-xs font-bold text-gray-300">
                                            <input
                                                type="checkbox"
                                                checked={String(sysKeys.longform_duration_lock_enabled) !== 'false'}
                                                onChange={e => setSysKeys(prev => ({ ...prev, longform_duration_lock_enabled: String(e.target.checked) }))}
                                                className="w-4 h-4 rounded text-emerald-500 bg-black border-white/10 cursor-pointer"
                                            />
                                            롱폼 배정시간을 직원 화면에서 수정 불가로 고정
                                        </label>
                                    </div>

                                    <div className="rounded-2xl border border-purple-500/20 bg-purple-500/5 p-5 space-y-4">
                                        <div>
                                            <h4 className="text-xs font-black text-purple-300 uppercase tracking-widest">Upload QA Policy</h4>
                                            <p className="text-[10px] text-gray-500 mt-1">렌더링 PC의 업로드 전 기술 검사/AI 검사/업로드 보류 기준을 중앙에서 제어합니다.</p>
                                        </div>
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                            {[
                                                ['qa_enable_pipeline', 'QA 파이프라인 전체 활성화'],
                                                ['qa_enable_technical_check', 'Stage 1 기술 검사 활성화'],
                                                ['qa_enable_semantic_check', 'Stage 2 AI 정밀 검사 활성화'],
                                                ['qa_auto_normalize_lufs', 'LUFS 자동 보정 적용'],
                                                ['qa_hold_on_technical_fail', '기술 스펙 미달 시 자동 업로드 보류'],
                                                ['qa_hold_on_semantic_fail', 'AI 검사 실패 시 자동 업로드 보류'],
                                            ].map(([key, label]) => (
                                                <label key={key} className="flex items-center gap-3 text-xs font-bold text-gray-300 rounded-xl border border-white/10 bg-black/20 px-4 py-3">
                                                    <input
                                                        type="checkbox"
                                                        checked={String((sysKeys as any)[key]) !== 'false'}
                                                        onChange={e => setSysKeys(prev => ({ ...prev, [key]: String(e.target.checked) }))}
                                                        className="w-4 h-4 rounded text-purple-500 bg-black border-white/10 cursor-pointer"
                                                    />
                                                    {label}
                                                </label>
                                            ))}
                                        </div>
                                        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                                            {[
                                                ['qa_target_lufs', '목표 LUFS', '0.5', ''],
                                                ['qa_lufs_tolerance', 'LUFS 허용오차', '0.5', '0'],
                                                ['qa_blackdetect_min_duration', '검은화면 기준(초)', '0.1', '0.1'],
                                                ['qa_min_width', '최소 가로', '1', '1'],
                                                ['qa_min_height', '최소 세로', '1', '1'],
                                            ].map(([key, label, step, min]) => (
                                                <div key={key}>
                                                    <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">{label}</label>
                                                    <input
                                                        type="number"
                                                        step={step}
                                                        min={min || undefined}
                                                        value={(sysKeys as any)[key]}
                                                        onChange={e => setSysKeys(prev => ({ ...prev, [key]: e.target.value }))}
                                                        className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-purple-500/50 text-gray-300"
                                                    />
                                                </div>
                                            ))}
                                        </div>
                                        <div className="rounded-xl border border-yellow-500/20 bg-yellow-500/10 px-4 py-3 text-[10px] text-yellow-200">
                                            기술/AI 검사 실패 시 자동 업로드만 보류됩니다. 렌더링 PC는 이 값을 Supabase global_settings에서 가져와 적용합니다.
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* 저장 버튼 */}
                            {sysKeysSaved && <p className="text-xs text-green-400 font-bold text-center">✓ 저장 완료</p>}
                            <button
                                onClick={saveSysKeys}
                                disabled={sysKeysSaving}
                                className="w-full py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white font-black rounded-2xl transition-all text-sm"
                            >
                                {sysKeysSaving ? '저장 중...' : '변경사항 저장'}
                            </button>
                        </div>
                    </div>
                )}
                {activeTab === 'render-queue' && canManageRenderQueue && (
                    <div className="bg-[#0f172a]/20 border border-white/5 rounded-[3rem] overflow-hidden shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <div className="px-10 py-6 border-b border-white/5 bg-black/20 flex justify-between items-center">
                            <div>
                                <h3 className="text-sm font-black text-gray-400 uppercase tracking-[0.2em]">원격 비디오 렌더링 큐</h3>
                                <p className="text-[10px] text-gray-600 mt-1">GPU 서버의 실시간 비디오 렌더 대기 및 진행 상태를 모니터링합니다.</p>
                            </div>
                            <button onClick={fetchRenderQueue} className="px-6 py-2 bg-blue-600/10 hover:bg-blue-600 text-blue-500 hover:text-white text-[10px] font-black rounded-xl border border-blue-500/20 transition-all uppercase tracking-widest">새로고침</button>
                        </div>
                        <div className="p-10">
                            <div className="mb-4 flex items-center gap-2">
                                <button
                                    onClick={() => setRenderQueueFilter('all')}
                                    className={`px-4 py-2 rounded-xl border text-[10px] font-black uppercase tracking-widest transition-all ${
                                        renderQueueFilter === 'all'
                                            ? 'bg-blue-600 text-white border-blue-500'
                                            : 'bg-blue-600/10 text-blue-500 border-blue-500/20'
                                    }`}
                                >
                                    ALL
                                </button>
                                <button
                                    onClick={() => setRenderQueueFilter('intro_ready')}
                                    className={`px-4 py-2 rounded-xl border text-[10px] font-black uppercase tracking-widest transition-all ${
                                        renderQueueFilter === 'intro_ready'
                                            ? 'bg-emerald-600 text-white border-emerald-500'
                                            : 'bg-emerald-600/10 text-emerald-400 border-emerald-500/20'
                                    }`}
                                >
                                    INTRO READY
                                </button>
                            </div>
                            {queueLoading && (renderQueueFilter === 'intro_ready'
                                ? renderQueue.filter((task: any) => Boolean(task?.metadata?.intro_video_ready)).length === 0
                                : renderQueue.length === 0) ? (
                                <div className="text-center text-xs text-gray-500 py-10">대기열 조회 중...</div>
                            ) : renderQueue.length === 0 ? (
                                <div className="text-center text-xs text-gray-500 py-10">현재 대기 또는 실행 중인 렌더링 작업이 없습니다.</div>
                            ) : (
                                <div className="overflow-x-auto">
                                    <table className="w-full text-left">
                                        <thead className="bg-black/30 border-b border-white/20 text-xs font-black text-gray-400 uppercase tracking-widest">
                                            <tr>
                                                <th className="px-4 py-4">생성일</th>
                                                <th className="px-4 py-4">사용자</th>
                                                <th className="px-4 py-4">프로젝트</th>
                                                <th className="px-4 py-4">진행 상태</th>
                                                <th className="px-4 py-4 text-center">진행률</th>
                                                <th className="px-4 py-4">메시지</th>
                                                <th className="px-4 py-4 text-center">작업 관리</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-white/10 text-xs font-medium text-gray-300">
                                            {(renderQueueFilter === 'intro_ready'
                                                ? renderQueue.filter((task: any) => Boolean(task?.metadata?.intro_video_ready))
                                                : renderQueue
                                            ).map((task: any) => {
                                                const meta = task.metadata || {}
                                                const totalMinutes = meta.total_duration_seconds
                                                    ? Math.round(Number(meta.total_duration_seconds || 0) / 60)
                                                    : null
                                                return (
                                                <tr key={task.id} className="hover:bg-white/[0.02] transition-colors">
                                                    <td className="px-4 py-4 whitespace-nowrap">
                                                        <div>{new Date(task.created_at).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}</div>
                                                        <div className="text-[10px] text-gray-500 mt-0.5">{new Date(task.created_at).toLocaleDateString()}</div>
                                                    </td>
                                                    <td className="px-4 py-4 whitespace-nowrap text-blue-400 font-bold">{task.email}</td>
                                                    <td className="px-4 py-4 font-bold text-white max-w-[260px]" title={meta.title || task.project_name}>
                                                        <div className="truncate">
                                                            {meta.title || task.project_name} <span className="text-[10px] text-gray-500 font-mono">({task.project_id})</span>
                                                        </div>
                                                        <div className="mt-2 flex flex-wrap gap-1.5">
                                                            {meta.is_music_queue && (
                                                                <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-[9px] font-black text-emerald-300">
                                                                    MUSIC QUEUE
                                                                </span>
                                                            )}
                                                            {meta.app_mode === 'longform_music' && (
                                                                <span className="px-2 py-0.5 rounded-full bg-teal-500/10 border border-teal-500/20 text-[9px] font-black text-teal-300">
                                                                    LONGFORM MUSIC
                                                                </span>
                                                            )}
                                                            {meta.track_count ? (
                                                                <span className="px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-[9px] font-black text-gray-300">
                                                                    TRACKS {meta.track_count}
                                                                </span>
                                                            ) : null}
                                                            {meta.intro_video_ready != null ? (
                                                                <span className={`px-2 py-0.5 rounded-full border text-[9px] font-black ${meta.intro_video_ready ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300' : 'bg-white/5 border-white/10 text-gray-500'}`}>
                                                                    INTRO VIDEO {meta.intro_video_ready ? 'READY' : 'PENDING'}
                                                                </span>
                                                            ) : null}
                                                            {meta.intro_bgm_ready != null ? (
                                                                <span className={`px-2 py-0.5 rounded-full border text-[9px] font-black ${meta.intro_bgm_ready ? 'bg-violet-500/10 border-violet-500/20 text-violet-300' : 'bg-white/5 border-white/10 text-gray-500'}`}>
                                                                    INTRO BGM {meta.intro_bgm_ready ? 'READY' : 'PENDING'}
                                                                </span>
                                                            ) : null}
                                                            <span className="px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-[9px] font-black text-gray-400">
                                                                INTRO OPTIONAL
                                                            </span>
                                                            {totalMinutes ? (
                                                                <span className="px-2 py-0.5 rounded-full bg-sky-500/10 border border-sky-500/20 text-[9px] font-black text-sky-300">
                                                                    Total: {totalMinutes} min
                                                                </span>
                                                            ) : null}
                                                        </div>
                                                    </td>
                                                    <td className="px-4 py-4 whitespace-nowrap">
                                                        <span className={`px-2.5 py-1 rounded-full text-[9px] font-black uppercase tracking-widest border ${
                                                            task.status === 'completed' ? 'bg-green-500/10 text-green-500 border-green-500/20' :
                                                            task.status === 'rendering' ? 'bg-blue-500/10 text-blue-500 border-blue-500/20 animate-pulse' :
                                                            task.status === 'pending' ? 'bg-orange-500/10 text-orange-500 border-orange-500/20' :
                                                            'bg-red-500/10 text-red-500 border-red-500/20'
                                                        }`}>
                                                            {task.status === 'pending' ? '대기중' : task.status === 'rendering' ? '렌더링중' : task.status === 'completed' ? '완료' : '실패'}
                                                        </span>
                                                        {meta.admin_publish_status ? (
                                                            <div className="mt-2 text-[9px] font-black uppercase tracking-widest text-amber-300">
                                                                Publish Ready: {String(meta.admin_publish_status).replace(/_/g, ' ')}
                                                            </div>
                                                        ) : null}
                                                        {meta.admin_publish_ready != null ? (
                                                            <div className={`mt-1 text-[9px] font-black uppercase tracking-widest ${String(meta.admin_publish_ready) === '1' || meta.admin_publish_ready === true ? 'text-emerald-300' : 'text-gray-500'}`}>
                                                                {String(meta.admin_publish_ready) === '1' || meta.admin_publish_ready === true ? 'Admin Publish Ready' : 'Admin Publish Pending'}
                                                            </div>
                                                        ) : null}
                                                        {meta.intro_mode ? (
                                                            <div className="mt-1 text-[9px] font-black uppercase tracking-widest text-gray-500">
                                                                Intro Mode: {String(meta.intro_mode).replace(/_/g, ' ')}
                                                            </div>
                                                        ) : null}
                                                        {meta.intro_bgm_usage ? (
                                                            <div className="mt-1 text-[9px] font-black uppercase tracking-widest text-gray-500">
                                                                Intro BGM: {String(meta.intro_bgm_usage).replace(/_/g, ' ')}
                                                            </div>
                                                        ) : null}
                                                        {(meta.intro_video_prompt_ready != null || meta.intro_bgm_prompt_ready != null) ? (
                                                            <div className="mt-1 text-[9px] font-black uppercase tracking-widest text-gray-500">
                                                                Prompt Pack: {meta.intro_video_prompt_ready ? 'Video' : 'NoVideo'} / {meta.intro_bgm_prompt_ready ? 'BGM' : 'NoBGM'}
                                                            </div>
                                                        ) : null}
                                                    </td>
                                                    <td className="px-4 py-4 min-w-[150px]">
                                                        <div className="flex items-center gap-2">
                                                            <div className="flex-1 h-1.5 bg-white/5 rounded-full overflow-hidden">
                                                                <div className={`h-full rounded-full transition-all duration-500 ${
                                                                    task.status === 'completed' ? 'bg-green-500' :
                                                                    task.status === 'failed' ? 'bg-red-500' : 'bg-blue-500'
                                                                }`} style={{ width: `${task.progress || 0}%` }} />
                                                            </div>
                                                            <span className="font-bold font-mono text-[10px] w-8 text-right">{task.progress || 0}%</span>
                                                        </div>
                                                    </td>
                                                    <td className="px-4 py-4 max-w-[250px] truncate text-gray-400 italic" title={task.message}>
                                                        {task.message || '-'}
                                                    </td>
                                                    <td className="px-4 py-4 text-center whitespace-nowrap">
                                                        <button onClick={() => handleDeleteQueueTask(task.id)} className="px-3 py-1.5 bg-red-600/10 hover:bg-red-600 text-red-500 hover:text-white rounded-lg border border-red-500/20 hover:border-red-600 transition-all font-black text-[10px]">삭제</button>
                                                    </td>
                                                </tr>
                                                )
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </div>
                    </div>
                )}
                {activeTab === 'learning' && canManageSystemSettings && (
                    <LearningStatsPanel adminFetch={adminFetch} refreshLabel={ui.refresh} />
                )}

                {activeTab === 'tenants' && isSuperAdmin && (
                    <TenantManagement authToken={authToken} isSuperAdmin={isSuperAdmin} />
                )}

                {activeTab === 'styles' && canManageStyles && (
                    <div className="space-y-8 animate-in fade-in duration-300">
                        {/* 1. 스타일 추가/수정 */}
                        <div ref={presetFormRef} className={`rounded-[2.5rem] border p-8 shadow-2xl scroll-mt-24 transition-all duration-300 ${presetId ? 'bg-blue-950/40 border-blue-500/40' : 'bg-[#0f172a]/60 border-white/10'}`}>
                            <h2 className="font-black text-xl tracking-tight mb-6 flex items-center gap-2">
                                스타일 프리셋 {presetId ? '수정' : '추가'}
                            </h2>
                            <form onSubmit={handleSavePreset} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">스타일 타입 *</label>
                                    <select
                                        required
                                        value={presetType}
                                        onChange={e => setPresetType(e.target.value as any)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50 cursor-pointer"
                                    >
                                        <option value="image">이미지 스타일 (Image Style)</option>
                                        <option value="script">대본 스타일 (Script Style)</option>
                                        <option value="thumbnail">썸네일 스타일 (Thumbnail Style)</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">스타일 영문 코드명 * (예: realistic)</label>
                                    <input
                                        type="text"
                                        required
                                        placeholder="영문 소문자 및 언더바 권장"
                                        value={presetKeyCode}
                                        onChange={e => setPresetKeyCode(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">스타일 한글 표시명 *</label>
                                    <input
                                        type="text"
                                        required
                                        placeholder="예: 실사영화"
                                        value={presetNameKo}
                                        onChange={e => setPresetNameKo(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">스타일 베트남어 표시명</label>
                                    <input
                                        type="text"
                                        placeholder="예: Dien anh thuc te"
                                        value={presetNameVi}
                                        onChange={e => setPresetNameVi(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">프리뷰 썸네일 이미지 URL</label>
                                    <input
                                        type="text"
                                        placeholder="https://... 또는 /static/img/... (선택사항)"
                                        value={presetImageUrl}
                                        onChange={e => setPresetImageUrl(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div className="md:col-span-2 lg:col-span-3">
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">프롬프트 템플릿 *</label>
                                    <textarea
                                        required
                                        rows={4}
                                        placeholder="스타일에 적용할 주요 프롬프트 및 수식어를 적어주세요. 이미지 스타일의 경우 [SUBJECT] 등을 활용할 수 있습니다."
                                        value={presetPromptTemplate}
                                        onChange={e => setPresetPromptTemplate(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-xs"
                                    />
                                </div>
                                <div className="md:col-span-2 lg:col-span-3">
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">AI 추가 지시사항 (Grounded Gemini Instruction - 이미지 스타일 적용)</label>
                                    <textarea
                                        rows={3}
                                        placeholder="예: 절대 텍스트나 말풍선을 넣지 마세요."
                                        value={presetGeminiInstruction}
                                        onChange={e => setPresetGeminiInstruction(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-xs"
                                    />
                                </div>
                                <div className="md:col-span-2 lg:col-span-3 flex justify-end gap-3">
                                    {presetId && (
                                        <button
                                            type="button"
                                            onClick={() => {
                                                setPresetId(null)
                                                setPresetKeyCode('')
                                                setPresetNameKo('')
                                                setPresetNameVi('')
                                                setPresetPromptTemplate('')
                                                setPresetGeminiInstruction('')
                                                setPresetImageUrl('')
                                            }}
                                            className="px-6 py-3 rounded-xl bg-white/5 hover:bg-white/10 text-xs font-black transition-all"
                                        >
                                            취소
                                        </button>
                                    )}
                                    <button
                                        type="submit"
                                        disabled={isSavingPreset}
                                        className="px-8 py-3 rounded-xl text-xs font-black bg-blue-600 text-white shadow-lg flex items-center gap-1.5 disabled:opacity-50 hover:bg-blue-500 transition-all"
                                    >
                                        {isSavingPreset ? '저장 중...' : '프리셋 저장'}
                                    </button>
                                </div>
                            </form>
                        </div>

                        {/* 2. 스타일 프리셋 리스트 */}
                        <div className="bg-[#0f172a]/60 rounded-[2.5rem] border border-white/10 overflow-hidden shadow-2xl">
                            <div className="p-8 border-b border-white/5 bg-white/5 flex justify-between items-center">
                                <h2 className="font-black text-xl tracking-tight uppercase">스타일 템플릿 카탈로그 목록</h2>
                                <button
                                    onClick={fetchStylePresets}
                                    className="px-4 py-2 bg-white/5 hover:bg-white/10 rounded-xl text-xs font-bold transition-all flex items-center gap-2 border border-white/10"
                                >
                                    새로고침
                                </button>
                            </div>
                            <div className="p-6">
                                {presetsLoading ? (
                                    <div className="text-center text-xs text-gray-500 py-10">프리셋 로딩 중...</div>
                                ) : (
                                    <div className="grid grid-cols-1 gap-8">
                                        {['image', 'script', 'thumbnail'].map(type => {
                                            const typePresets = stylePresets.filter((p: any) => p.preset_type === type);
                                            const typeLabel = type === 'image' ? '이미지 스타일' : type === 'script' ? '대본 스타일' : '썸네일 스타일';
                                            return (
                                                <div key={type} className="border border-white/5 rounded-2xl p-6 bg-black/20">
                                                    <h3 className="text-base font-bold text-gray-300 mb-4">
                                                        {typeLabel} ({typePresets.length})
                                                    </h3>
                                                    {typePresets.length === 0 ? (
                                                        <p className="text-xs text-gray-600 italic">등록된 스타일 프리셋이 없습니다.</p>
                                                    ) : (
                                                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                                            {typePresets.map((preset: any) => (
                                                                <div key={preset.id} className="border border-white/5 bg-black/40 p-4 rounded-xl relative group hover:border-white/10 transition-all flex flex-col justify-between">
                                                                    <div>
                                                                        <div className="flex justify-between items-start mb-2">
                                                                            <div>
                                                                                <h4 className="text-sm font-bold text-white flex items-center gap-1.5">
                                                                                    {preset.display_name_ko}
                                                                                    {preset.display_name_vi && (
                                                                                        <span className="text-[10px] text-gray-500 font-normal">({preset.display_name_vi})</span>
                                                                                    )}
                                                                                </h4>
                                                                                <span className="text-[9px] font-mono text-gray-500 bg-white/5 px-1.5 py-0.5 rounded mt-1 inline-block">code: {preset.key_code}</span>
                                                                            </div>
                                                                            <div className="flex gap-1">
                                                                                <button
                                                                                    onClick={() => handleEditPreset(preset)}
                                                                                    className="px-2 py-1 bg-blue-600/20 hover:bg-blue-600 text-blue-400 hover:text-white rounded text-[10px] font-bold transition-all border border-blue-500/20"
                                                                                    title="수정"
                                                                                >
                                                                                    수정
                                                                                </button>
                                                                                <button
                                                                                    onClick={() => handleDeletePreset(preset.id, preset.key_code)}
                                                                                    className="p-1 hover:bg-white/5 rounded text-red-500 text-xs"
                                                                                    title="삭제"
                                                                                >
                                                                                    삭제
                                                                                </button>
                                                                            </div>
                                                                        </div>
                                                                        {preset.image_url && (
                                                                            <img src={preset.image_url} alt={preset.display_name_ko} className="w-24 h-24 object-cover rounded-lg mb-2.5 border border-white/5 bg-[#111]" />
                                                                        )}
                                                                        <p className="text-[10px] text-gray-400 font-mono line-clamp-3 bg-black/50 p-2 rounded border border-white/5">
                                                                            {preset.prompt_template}
                                                                        </p>
                                                                        {preset.gemini_instruction && (
                                                                            <p className="text-[9px] text-purple-400 font-mono mt-1.5">
                                                                                Instruction: {preset.gemini_instruction}
                                                                            </p>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    )}
                                                </div>
                                            )
                                        })}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                )}
            </main>

            {/* 사용자 정보 직접 수정 모달 */}
            {editInfoUser && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setEditInfoUser(null)}>
                    <div className="bg-[#0a0a0a] border border-white/10 rounded-2xl p-8 w-full max-w-md shadow-2xl" onClick={e => e.stopPropagation()}>
                        <div className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">사용자 정보 수정</div>
                        <div className="text-white font-black text-lg mb-6">{editInfoUser.email?.toLowerCase()}</div>
                        <div className="flex flex-col gap-4">
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">이름</label>
                                <input value={editInfoForm.full_name} onChange={e => setEditInfoForm(p => ({ ...p, full_name: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-yellow-500/50" placeholder="이름 입력" />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">국적</label>
                                <input value={editInfoForm.nationality} onChange={e => setEditInfoForm(p => ({ ...p, nationality: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-yellow-500/50" placeholder="국적 입력 (예: 한국)" />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">연락처</label>
                                <input value={editInfoForm.contact} onChange={e => setEditInfoForm(p => ({ ...p, contact: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-yellow-500/50" placeholder="연락처 입력" />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-2">제작 가능 언어</label>
                                <div className="grid grid-cols-3 gap-2">
                                    {CONTENT_LANGUAGE_OPTIONS.map(option => (
                                        <label key={`edit-user-language-${option.value}`} className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-[11px] font-bold text-gray-200 cursor-pointer">
                                            <input
                                                type="checkbox"
                                                checked={editInfoForm.preferred_languages.includes(option.value)}
                                                onChange={e => setEditInfoForm(p => {
                                                    const current = p.preferred_languages || []
                                                    const next = e.target.checked
                                                        ? Array.from(new Set([...current, option.value]))
                                                        : current.filter(lang => lang !== option.value)
                                                    return { ...p, preferred_languages: next.length ? next : ['ko'] }
                                                })}
                                                className="accent-yellow-400"
                                            />
                                            <span>{option.label}</span>
                                        </label>
                                    ))}
                                </div>
                            </div>
                            <div className="border-t border-white/10 my-2 pt-2">
                                <div className="text-[10px] font-black text-blue-400 uppercase tracking-wider mb-2">🤖 AI 작가 페르소나 설정</div>
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">페르소나 이름</label>
                                <input value={editInfoForm.persona_name || ''} onChange={e => setEditInfoForm(p => ({ ...p, persona_name: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-yellow-500/50" placeholder="예: 란 (유머 작가)" />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">작문 스타일 키워드 (영어 권장)</label>
                                <input value={editInfoForm.persona_style || ''} onChange={e => setEditInfoForm(p => ({ ...p, persona_style: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-yellow-500/50" placeholder="예: humorous, witty, fast-paced" />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">상세 성향 설명 (한글 가능)</label>
                                <textarea value={editInfoForm.persona_description || ''} onChange={e => setEditInfoForm(p => ({ ...p, persona_description: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-yellow-500/50 h-20 resize-none" placeholder="예: 유머러스하고 유쾌한 숏폼 스타일 대본 작가" />
                            </div>
                        </div>
                        <div className="flex gap-3 mt-6">
                            <button onClick={handleSaveUserInfo} className="flex-1 py-3 bg-yellow-500 hover:bg-yellow-400 text-black text-[11px] font-black rounded-xl transition-all uppercase tracking-widest">저장</button>
                            <button onClick={() => setEditInfoUser(null)} className="px-6 py-3 bg-white/5 hover:bg-white/10 text-gray-400 text-[11px] font-black rounded-xl transition-all">취소</button>
                        </div>
                    </div>
                </div>
            )}

            {logViewUser && (
                <div className="fixed inset-0 z-[200] flex items-center justify-center p-12 animate-in fade-in duration-300">
                    <div className="absolute inset-0 bg-black/95 backdrop-blur-3xl" onClick={() => setLogViewUser(null)} />
                    <div className="relative w-full max-w-[1600px] bg-[#000106] border border-white/10 rounded-[3rem] p-12 flex flex-col max-h-[94vh] overflow-hidden shadow-2xl">
                        <div className="flex justify-between items-center mb-10">
                             <div className="flex items-center gap-6"><h3 className="text-3xl font-black text-blue-500 uppercase italic tracking-tighter">사용자 작업 로그</h3><div className="px-4 py-1.5 bg-blue-600/10 border border-blue-500/20 rounded-full text-[10px] font-black text-blue-400 uppercase tracking-widest">{logViewUser.email}</div></div>
                             <div className="flex items-center gap-4">
                                  <div className="flex gap-1 p-1 bg-white/5 rounded-xl border border-white/5">{[1, 7, 30].map(d => (
                                      <button key={d} onClick={() => { setLogPeriod(d); fetchUserLogs(logViewUser.id, d); }} className={`px-6 py-2 text-[10px] font-black rounded-lg transition-all ${logPeriod === d ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500 hover:text-white'}`}>{d === 1 ? '일간' : d === 7 ? '주간' : '월간'}</button>
                                  ))}</div>
                                  <button onClick={() => setLogViewUser(null)} className="w-12 h-12 flex items-center justify-center rounded-xl bg-white/5 text-gray-500 hover:text-white transition-all text-xl font-black">X</button>
                             </div>
                        </div>
                        <div className="overflow-y-auto flex-1 pr-4 custom-scrollbar space-y-8">
                             <div className="flex flex-col lg:flex-row gap-4">
                                <div className="flex-1 grid grid-cols-4 gap-4">
                                    <StatCard label="TOTAL TASKS" value={logStats.total} unit="UNITS" color="white" />
                                    <StatCard label="SUCCESS RATE" value={logStats.successRate + '%'} unit="GLOBAL" color="green" />
                                    <StatCard label="AVG LATENCY" value={logStats.avgLatency + 's'} unit="PER TASK" color="blue" />
                                    <StatCard 
                                        label="TOKEN USAGE" 
                                        value={logStats.totalTokens.toLocaleString()} 
                                        unit="TOKENS" 
                                        color="orange" 
                                        subLabel={isKor 
                                            ? `예상 비용: 약 $${((logStats.totalTokens || 0) * 0.00002).toFixed(2)}` 
                                            : `Est. Cost: ~$${((logStats.totalTokens || 0) * 0.00002).toFixed(2)}`
                                        }
                                    />
                                </div>
                                {renderDonutChart(logStats)}
                             </div>
                             {renderChartRow(logStats, userTopTasks)}
                             {renderLogTable(userLogs, false)}
                        </div>
                    </div>
                </div>
            )}

            {apiViewUser && (
                <div className="fixed inset-0 z-[200] flex items-center justify-center p-12">
                    <div className="absolute inset-0 bg-black/90 backdrop-blur-3xl" onClick={() => setApiViewUser(null)} />
                    <div className="relative w-full max-w-[800px] bg-[#000106] border border-white/10 rounded-[3rem] p-16 flex flex-col shadow-2xl animate-in zoom-in-95 duration-300">
                        <button onClick={() => setApiViewUser(null)} className="absolute top-12 right-12 w-12 h-12 flex items-center justify-center rounded-xl bg-white/5 text-gray-500 hover:text-white transition-all">X</button>
                        <div className="space-y-10">
                            <div><h3 className="text-3xl font-black uppercase italic tracking-tighter text-blue-500">유저 전용 API 설정</h3><p className="text-sm text-gray-500 mt-2 uppercase tracking-widest font-black italic">{apiViewUser.email}</p></div>
                            <div className="space-y-6">{['openai', 'gemini', 'pexels', 'replicate'].map(key => (
                                <div key={key} className="space-y-2">
                                    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest ml-4">{key.toUpperCase()} API 키</label>
                                    <input type="text" placeholder={`발급받은 키를 입력하세요..`} value={tempApiKeys[key] || ''} onChange={(e) => setTempApiKeys({...tempApiKeys, [key]: e.target.value})} className="w-full bg-black/40 border border-white/5 rounded-2xl px-8 py-5 text-sm font-black text-white focus:outline-none focus:border-blue-500/50 transition-all" />
                                </div>
                            ))}</div>
                            <button onClick={handleUpdateApiKeys} className="w-full py-6 bg-blue-600 hover:bg-blue-500 text-white font-black rounded-[2rem] shadow-xl shadow-blue-500/20 transition-all active:scale-95 uppercase tracking-widest text-sm">저장 및 적용</button>
                        </div>
                    </div>
                </div>
            )}

            {channelViewUser && (
                <div className="fixed inset-0 z-[200] flems-center justify-center p-12">
                    <div className="absolute inset-0 bg-black/90 backdrop-blur-3xl" onClick={() => setChannelViewUser(null)} />
                    <div className="relative w-full max-w-[800px] bg-[#000106] border border-white/10 rounded-[3rem] p-16 flex flex-col shadow-2xl animate-in zoom-in-95 duration-300">
                        <button onClick={() => setChannelViewUser(null)} className="absolute top-12 right-12 w-12 h-12 flex items-center justify-center rounded-xl bg-white/5 text-gray-500 hover:text-white transition-all">X</button>
                        <div className="space-y-10">
                            <div><h3 className="text-3xl font-black uppercase italic tracking-tighter text-purple-500">유튜브 채널 연동 관리</h3><p className="text-sm text-gray-500 mt-2 uppercase tracking-widest font-black italic">{channelViewUser.email}</p></div>
                            <div className="space-y-8">
                                <div className="space-y-2">
                                    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest ml-4">채널 이름 (표시용)</label>
                                    <input type="text" placeholder="예: 피카디리 스튜디오" value={tempChannelInfo.name} onChange={(e) => setTempChannelInfo({...tempChannelInfo, name: e.target.value})} className="w-full bg-black/40 border border-white/5 rounded-2xl px-8 py-5 text-sm font-black text-white focus:outline-none focus:border-purple-500/50 transition-all" />
                                </div>
                                <div className="space-y-2">
                                    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest ml-4">유튜브 채널 ID</label>
                                    <input type="text" placeholder="예: UCxxxxxxxxxxxx" value={tempChannelInfo.id} onChange={(e) => setTempChannelInfo({...tempChannelInfo, id: e.target.value})} className="w-full bg-black/40 border border-white/5 rounded-2xl px-8 py-5 text-sm font-black text-white focus:outline-none focus:border-purple-500/50 transition-all" />
                                    
                                </div>
                                <div className="space-y-2">
                                    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest ml-4">국가 우회용 고정 IP 프록시 (선택)</label>
                                    <input type="text" placeholder="예: http://username:password@ip:port" value={tempChannelInfo.proxy || ''} onChange={(e) => setTempChannelInfo({...tempChannelInfo, proxy: e.target.value})} className="w-full bg-black/40 border border-white/5 rounded-2xl px-8 py-5 text-sm font-black text-white focus:outline-none focus:border-purple-500/50 transition-all font-mono" />
                                    <p className="text-[9px] text-gray-600 ml-4 font-bold">* 해당 채널 영상 업로드는 지정한 프록시 IP 설정을 경유하여 국가별 노출 안정성을 높입니다.</p>
                                </div>
                            </div>
                            <div className="flex gap-4">
                                <button 
                                    onClick={handleUpdateChannelInfo} 
                                    disabled={savingChannel}
                                    className={`flex-1 py-6 font-black rounded-[2rem] shadow-xl transition-all active:scale-95 uppercase tracking-widest text-xs ${savingChannel ? 'bg-gray-800 text-gray-500 cursor-not-allowed' : 'bg-purple-600 hover:bg-purple-500 text-white'}`}
                                >
                                    {savingChannel ? (isKor ? '저장 중...' : 'Saving...') : (isKor ? '텍스트 정보 저장' : 'Save Text Info')}
                                </button>
                                
                                <button 
                                    onClick={() => {
                                        if (!tempChannelInfo.name || !tempChannelInfo.id) {
                                            alert(isKor ? "채널 이름과 ID를 모두 입력해주세요." : "Please enter both channel name and ID.");
                                            return;
                                        }
                                        
                                        // window.open을 사용하여 CORS 우회 및 즉각적인 피드백 제공
                                        const url = `http://127.0.0.1:8001/api/channels/login-by-info?name=${encodeURIComponent(tempChannelInfo.name)}&id=${encodeURIComponent(tempChannelInfo.id)}&proxy=${encodeURIComponent(tempChannelInfo.proxy || '')}`;
                                        window.open(url, '_blank', 'width=600,height=700');
                                        
                                        // 메타데이터 정보 저장은 별도로 수행
                                        handleUpdateChannelInfo();
                                    }}
                                    className="px-8 py-6 bg-white text-black font-black rounded-[2rem] shadow-xl hover:bg-gray-100 transition-all active:scale-95 flex items-center justify-center gap-2 text-xs"
                                >
                                    <svg className="w-4 h-4" viewBox="0 0 24 24">
                                        <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                                        <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                                        <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" />
                                        <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                                    </svg>
                                    {isKor ? '구글 연동하기' : 'Connect Google'}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* 카테고리 정보 수정 모달 */}
            {editCategory && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setEditCategory(null)}>
                    <div className="bg-[#0a0a0a] border border-white/10 rounded-2xl p-8 w-full max-w-lg shadow-2xl" onClick={e => e.stopPropagation()}>
                        <div className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">카테고리 수정</div>
                        <div className="text-white font-black text-lg mb-6">&quot;{editCategory.name}&quot; 설정 관리</div>
                        <div className="flex flex-col gap-4 text-xs">
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">카테고리명 *</label>
                                <input 
                                    type="text"
                                    value={editCatForm.name} 
                                    onChange={e => setEditCatForm(p => ({ ...p, name: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50" 
                                    placeholder="카테고리명 입력" 
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">담당 직원 이메일 *</label>
                                <select
                                    value={editCatForm.assigned_employee_email}
                                    onChange={e => setEditCatForm(p => ({ ...p, assigned_employee_email: e.target.value }))}
                                    className="w-full bg-[#111] border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50 cursor-pointer"
                                >
                                    <option value="">-- 직원을 선택하세요 --</option>
                                    {users.map(user => {
                                        const email = user.email?.toLowerCase();
                                        if (!email) return null;
                                        const name = user.user_metadata?.full_name || '';
                                        return (
                                            <option key={user.id} value={email} className="bg-[#111] text-white">
                                                {email} {name ? `(${name})` : ''}
                                            </option>
                                        );
                                    })}
                                </select>
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">주요 리서치 키워드</label>
                                <input 
                                    type="text"
                                    value={editCatForm.keywords} 
                                    onChange={e => setEditCatForm(p => ({ ...p, keywords: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50" 
                                    placeholder="쉼표로 구분" 
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">벤치마킹 유튜브 채널 URL</label>
                                <input 
                                    type="url"
                                    value={editCatForm.benchmark_channel_url} 
                                    onChange={e => setEditCatForm(p => ({ ...p, benchmark_channel_url: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50" 
                                    placeholder="유튜브 채널 주소" 
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">콘텐츠 언어</label>
                                <select
                                    value={editCatForm.language}
                                    onChange={e => setEditCatForm(p => ({ ...p, language: normalizeContentLanguage(e.target.value) }))}
                                    className="w-full bg-[#111] border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50 cursor-pointer"
                                >
                                    {CONTENT_LANGUAGE_OPTIONS.map(option => (
                                        <option key={`edit-cat-language-${option.value}`} value={option.value} className="bg-[#111] text-white">
                                            {option.label}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">기본 대본 스타일</label>
                                <select
                                    value={editCatForm.default_script_style}
                                    onChange={e => setEditCatForm(p => ({ ...p, default_script_style: e.target.value }))}
                                    className="w-full bg-[#111] border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50 cursor-pointer"
                                >
                                    <option value="default" className="bg-[#111] text-white">기본 설정 (자연스럽고 선명한 스타일)</option>
                                    <option value="story" className="bg-[#111] text-white">예난 이야기 (구연 동화)</option>
                                    <option value="senior_story" className="bg-[#111] text-white">시니어 이야기 (회상/감성)</option>
                                    <option value="news" className="bg-[#111] text-white">뉴스 (정보 전달)</option>
                                    <option value="mystery_thriller" className="bg-[#111] text-white">미스터리 스릴러 (긴장감)</option>
                                    <option value="nursery_rhyme" className="bg-[#111] text-white">어린이 동요 (귀여운 구연)</option>
                                </select>
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">기본 이미지 스타일</label>
                                <select
                                    value={editCatForm.default_image_style}
                                    onChange={e => setEditCatForm(p => ({ ...p, default_image_style: e.target.value }))}
                                    className="w-full bg-[#111] border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50 cursor-pointer"
                                >
                                    <option value="realistic" className="bg-[#111] text-white">실사 (Photorealistic)</option>
                                    <option value="ghibli" className="bg-[#111] text-white">지브리 감성 일러스트 (Ghibli)</option>
                                    <option value="anime" className="bg-[#111] text-white">애니메이션풍 (Anime)</option>
                                    <option value="cinematic" className="bg-[#111] text-white">영화 스타일 (Cinematic)</option>
                                    <option value="cartoon" className="bg-[#111] text-white">2D 카톤 스타일 (Cartoon)</option>
                                    <option value="nursery_rhyme" className="bg-[#111] text-white">3D 동화/애니 (Nursery/Pixar)</option>
                                    <option value="ink_wash" className="bg-[#111] text-white">동양 수목화 스타일 (Ink Wash)</option>
                                </select>
                             </div>
                             <div>
                                 <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-2">영상 형식 (필수) *</label>
                                 <div className="flex gap-6 items-center">
                                     <label className="flex items-center gap-2 cursor-pointer text-white font-black">
                                         <input 
                                             type="radio" 
                                             name="edit_video_type" 
                                             value="longform" 
                                             checked={editCatForm.video_type === 'longform'} 
                                             onChange={() => setEditCatForm(p => ({ ...p, video_type: 'longform' }))}
                                             className="w-4 h-4 accent-blue-500 cursor-pointer"
                                         />
                                          <span>롯폼 (Longform)</span>
                                     </label>
                                     <label className="flex items-center gap-2 cursor-pointer text-white font-black">
                                         <input 
                                             type="radio" 
                                             name="edit_video_type" 
                                             value="shorts" 
                                             checked={editCatForm.video_type === 'shorts'} 
                                             onChange={() => setEditCatForm(p => ({ ...p, video_type: 'shorts' }))}
                                             className="w-4 h-4 accent-blue-500 cursor-pointer"
                                         />
                                          <span>쇼츠 (Shorts)</span>
                                     </label>
                                 </div>
                             </div>
                             <div className="rounded-xl border border-white/10 bg-white/5 px-4 py-3">
                                 <div className="flex items-center justify-between gap-3">
                                     <div>
                                         <div className="text-[10px] text-gray-500 font-black uppercase tracking-widest">업로드 고정 채널</div>
                                         <div className="mt-1 text-sm font-black text-white">
                                             {editCatForm.upload_channel_name || editCatForm.upload_channel_handle || '설정 안됨'}
                                         </div>
                                         {editCatForm.upload_channel_handle && (
                                             <div className="text-[11px] text-gray-500 mt-1">{editCatForm.upload_channel_handle}</div>
                                         )}
                                     </div>
                                     <button
                                         type="button"
                                         onClick={() => openCategoryChannelConfig({ id: editCategory.id, ...editCatForm })}
                                         className="px-4 py-2 bg-blue-600/15 hover:bg-blue-600 text-blue-300 hover:text-white text-[10px] font-black rounded-xl border border-blue-500/20 transition-all"
                                     >
                                         채널 설정
                                     </button>
                                 </div>
                             </div>
                        </div>
                        <div className="flex gap-3 mt-6">
                            <button onClick={handleSaveCategory} className="flex-1 py-3 bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-black rounded-xl transition-all uppercase tracking-widest">수정완료</button>
                            <button onClick={() => setEditCategory(null)} className="px-6 py-3 bg-white/5 hover:bg-white/10 text-gray-400 text-[11px] font-black rounded-xl transition-all">痍⑥냼</button>
                        </div>
                    </div>
                </div>
            )}

            {channelConfigCategory && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-[70] flex items-center justify-center p-4" onClick={() => setChannelConfigCategory(null)}>
                    <div className="bg-[#0a0a0a] border border-white/10 rounded-2xl p-8 w-full max-w-xl shadow-2xl" onClick={e => e.stopPropagation()}>
                        <div className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">업로드 채널 설정</div>
                        <div className="text-white font-black text-lg mb-2">&quot;{channelConfigCategory.name}&quot; 업로드 채널 연결</div>
                        <p className="text-[12px] text-gray-500 mb-6">이 카테고리에서 생성되는 영상은 여기에서 지정한 채널로만 업로드됩니다.</p>

                        <div className="space-y-4 text-xs">
                            <div>
                                <div className="flex items-center justify-between mb-1.5">
                                    <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest">로컬 채널 목록</label>
                                    <button
                                        type="button"
                                        onClick={fetchLocalUploadChannels}
                                        className="text-[10px] font-black text-blue-400 hover:text-blue-300"
                                    >
                                        {localChannelsLoading ? '불러오는 중...' : '새로고침'}
                                    </button>
                                </div>
                                <select
                                    value={channelConfigForm.local_channel_id ?? ''}
                                    onChange={e => applyLocalChannelToCategoryForm(e.target.value ? Number(e.target.value) : null)}
                                    className="w-full bg-[#111] border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50 cursor-pointer"
                                >
                                    <option value="">-- 로컬 채널 선택 --</option>
                                    {localChannels.map(channel => (
                                        <option key={`config-local-channel-${channel.id}`} value={channel.id} className="bg-[#111] text-white">
                                            {channel.name} ({channel.handle}) {channel.credentials_path ? '[연동완료]' : '[미연동]'}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                    <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">채널 이름</label>
                                <input
                                    type="text"
                                    value={channelConfigForm.name}
                                    onChange={e => setChannelConfigForm(prev => ({ ...prev, name: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50"
                                    placeholder="예: 옛날이야기 연구소"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">유튜브 채널 ID 또는 핸들</label>
                                <input
                                    type="text"
                                    value={channelConfigForm.handle}
                                    onChange={e => setChannelConfigForm(prev => ({ ...prev, handle: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50"
                                    placeholder="예: UCxxxx 또는 @channelhandle"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">프록시 (선택)</label>
                                <input
                                    type="text"
                                    value={channelConfigForm.proxy}
                                    onChange={e => setChannelConfigForm(prev => ({ ...prev, proxy: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50"
                                    placeholder="예: socks5://127.0.0.1:1080"
                                />
                            </div>

                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                                <button type="button" onClick={handleCreateOrUpdateLocalChannel} className="py-3 bg-white/5 hover:bg-white/10 text-white text-[11px] font-black rounded-xl border border-white/10 transition-all">
                                    로컬 채널 저장
                                </button>
                                <button type="button" onClick={handleStartCategoryChannelOAuth} className="py-3 bg-purple-600/15 hover:bg-purple-600 text-purple-300 hover:text-white text-[11px] font-black rounded-xl border border-purple-500/20 transition-all">
                                    Google OAuth 연동
                                </button>
                                <button type="button" onClick={handleSaveCategoryChannelBinding} className="py-3 bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-black rounded-xl transition-all">
                                    카테고리에 저장
                                </button>
                            </div>

                            <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3 text-[11px] text-gray-400 leading-5">
                                1. 로컬 채널을 선택하거나 새로 저장하고<br />
                                2. 필요하면 Google OAuth 연동을 눌러 인증한 뒤<br />
                                3. 마지막으로 카테고리에 저장하면 이 주제는 해당 채널로 고정됩니다.
                            </div>
                        </div>

                        <div className="flex justify-end mt-6">
                            <button onClick={() => setChannelConfigCategory(null)} className="px-6 py-3 bg-white/5 hover:bg-white/10 text-gray-400 text-[11px] font-black rounded-xl transition-all">닫기</button>
                        </div>
                    </div>
                </div>
            )}
            
            <style jsx global>{`
                .custom-scrollbar::-webkit-scrollbar { width: 4px; }
                .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(55,130,246,0.3); border-radius: 10px; }
            `}</style>
        </div>
    )
}
