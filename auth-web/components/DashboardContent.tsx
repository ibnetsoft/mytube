'use client'

import { useEffect, useState, useCallback, useMemo, useRef } from 'react'
import { supabase } from '@/lib/supabaseClient'
import { useRouter } from 'next/navigation'
import { useLanguage } from '@/lib/LanguageContext'
import LanguageSelector from './LanguageSelector'

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
        pin_code?: string
        approved_hwid?: string
        device_hwid?: string
        persona_name?: string
        persona_style?: string
        persona_description?: string
    }
}

interface EditInfoFormState {
    full_name: string
    nationality: string
    contact: string
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

const typeMap: Record<string, string> = {
    'video': 'VIDEO',
    'image': 'IMAGE',
    'script': 'SCRIPT',
    'text_gen': 'TEXT_GEN',
    'vision_gen': 'VISION_GEN',
    'motion_guide': 'MOTION_GUIDE',
    'character_extraction': 'CHARACTER_EXTRACTION',
    'test_after_fix': 'SUBTITLE_FIX',
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
    const [activeTab, setActiveTab] = useState<'topics' | 'overview' | 'users' | 'api' | 'render-queue' | 'styles' | 'withdrawals'>('topics')
    const [renderQueue, setRenderQueue] = useState<any[]>([])
    const [renderQueueFilter, setRenderQueueFilter] = useState<'all' | 'intro_ready'>('all')
    const [queueLoading, setQueueLoading] = useState(false)
    const [overviewSubTab, setOverviewSubTab] = useState<'video' | 'log'>('video')

    // 燁삳똾?믤⑥쥓??& AI 雅뚯눘???癒곕솇疫??怨밴묶
    const [categories, setCategories] = useState<any[]>([])
    const [topics, setTopics] = useState<any[]>([])
    const [categoriesLoading, setCategoriesLoading] = useState(false)
    const [newCatName, setNewCatName] = useState('')
    const [newCatKeywords, setNewCatKeywords] = useState('')
    const [newCatChannel, setNewCatChannel] = useState('')
    const [newCatEmployee, setNewCatEmployee] = useState('')
    const [newCatScriptStyle, setNewCatScriptStyle] = useState('default')
    const [newCatImageStyle, setNewCatImageStyle] = useState('realistic')
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
    
    // 燁삳똾?믤⑥쥓???귐딅뮞??嚥↔퉲琉??瑜귣쨲 ???닌됲뀋
    const [categoryListTab, setCategoryListTab] = useState<'longform' | 'shorts'>('longform')

    // 燁삳똾?믤⑥쥓????륁젟 筌뤴뫀???怨밴묶
    const [editCategory, setEditCategory] = useState<any | null>(null)
    const [editCatForm, setEditCatForm] = useState({
        name: '',
        keywords: '',
        benchmark_channel_url: '',
        assigned_employee_email: '',
        default_script_style: 'default',
        default_image_style: 'realistic',
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

    // ??뽯뮞???袁⑸열 API ??獄??닌? ??뺤뵬??????쇱젟
    const [sysKeys, setSysKeys] = useState({ 
        gemini: '', youtube: '', elevenlabs: '', suno: '', suno_base_url: '', music_provider: 'elevenlabs',
        music_gemini_model: 'lyria-3-pro-preview', music_gemini_base_url: '', music_gemini_project_id: '', music_gemini_location: 'global',
        topview: '', topview_uid: '',
        use_external_render: false, drive_path_ko: '', drive_path_en: '', drive_path_ja: '', drive_active_lang: 'ko',
        remote_render_drive_folder_id: '',
        remote_render_google_token_path: '',
        longform_min_duration_minutes: '15',
        longform_base_payout: '10000',
        longform_extra_minute_payout: '500',
        longform_duration_lock_enabled: 'true'
    })
    const [sysKeysSaving, setSysKeysSaving] = useState(false)
    const [sysKeysSaved, setSysKeysSaved] = useState(false)

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
    const isAdmin = user?.app_metadata?.is_admin || isSuperAdmin;

    // Derived Stats
    const memberCount = useMemo(() => (users || []).length, [users]);
    const todayStr = useMemo(() => new Date().toISOString().split('T')[0], []);
    const newToday = useMemo(() => (users || []).filter((u: any) => u.created_at?.startsWith(todayStr)).length, [users, todayStr]);
    const activeToday = useMemo(() => (users || []).filter((u: any) => u.last_sign_in_at?.startsWith(todayStr)).length, [users, todayStr]);
    const totalTokens = useMemo(() => (users || []).reduce((acc: number, u: any) => acc + (u.profile?.token_balance || 0), 0), [users]);

    const getTopTasks = (breakdown: any) => {
        const priority = ['video', 'image', 'script', 'vision_gen', 'motion_guide', 'text_gen', 'character_extraction', 'test_after_fix'];
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
        const amountStr = prompt(isKor ? '異⑹쟾???좏겙 ?섎? ?낅젰?섏꽭??' : 'Enter token amount to recharge', '50000');
        if (!amountStr) return;
        const parsedAmount = parseInt(amountStr);
        if (isNaN(parsedAmount) || parsedAmount <= 0) {
            alert(isKor ? '?щ컮瑜??レ옄瑜??낅젰?댁＜?몄슂.' : 'Please enter a valid number.');
            return;
        }
        try {
            const res = await fetch('/api/admin/users/recharge', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId, amount: parsedAmount, description: 'Admin Manual Recharge' })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                alert(isKor ? `異⑹쟾 ?꾨즺! ${parsedAmount.toLocaleString()} ?좏겙 異붽?` : `Recharge Success! +${parsedAmount.toLocaleString()} tokens`);
                // ???????낅쑓??꾨뱜 ??fetchUsers() ??????Supabase 筌?Ŋ?녷에?stale 獄쏆꼹??
                setUsers(prev => prev.map(u => u.id === userId
                    ? { ...u, profile: { ...u.profile, token_balance: (u.profile?.token_balance || 0) + parsedAmount } }
                    : u
                ));
            } else {
                alert((isKor ? '異⑹쟾 ?ㅽ뙣: ' : 'Recharge Failed: ') + (data.error || `HTTP ${res.status}`));
            }
        } catch (e: any) {
            alert((isKor ? '?ㅽ듃?뚰겕 ?ㅻ쪟: ' : 'Network error: ') + (e?.message || String(e)));
        }
    }

    const handleUpdateApiKeys = async () => {
        if (!apiViewUser) return;
        try {
            const res = await fetch('/api/admin/users/api-keys', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId: apiViewUser.id, apiKeys: tempApiKeys })
            });
            if (res.ok) {
                alert(isKor ? "?깃났?곸쑝濡??곸슜?섏뿀?듬땲??" : "API Keys updated successfully.");
                setApiViewUser(null);
                fetchUsers();
            } else {
                alert("?곸슜 ?ㅽ뙣");
            }
        } catch (e) { alert("?ㅻ쪟 諛쒖깮"); }
    }

    const [savingChannel, setSavingChannel] = useState(false);

    const handleUpdateChannelInfo = async () => {
        if (!channelViewUser) return;
        setSavingChannel(true);
        try {
            console.log('Saving channel for user:', channelViewUser.id, tempChannelInfo);
            const res = await fetch('/api/admin/users/update-metadata', {
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
                // [FIX] ??뺤쒔?癒?퐣 獄쏆꼹???筌ㅼ뮇???醫? ?類ｋ궖嚥?筌앸맩???대Ŋ猿??뤿연 ??녿┛??筌왖??獄쎻뫗?
                const updatedUser = data.user;
                if (updatedUser) {
                    setUsers(prev => prev.map(u => u.id === updatedUser.id ? {
                        ...u,
                        user_metadata: updatedUser.user_metadata
                    } : u));
                }
                
                alert(isKor ? "筌?쑬瑗??類ｋ궖揶쎛 ?源껊궗?怨몄몵嚥???낅쑓??꾨뱜??뤿???щ빍??" : "Channel info updated successfully.");
                setChannelViewUser(null);
                // fetchUsers()???紐꾪뀱??? ??꾪?嚥≪뮇類??怨밴묶???怨쀪퐨??쀫맙 (Race Condition ??욧퍙)
            } else {
                console.error('Save failed:', data.error);
                alert((isKor ? "??????쎈솭: " : "Save failed: ") + (data.error || "Unknown error"));
            }
        } catch (e) { 
            console.error('API Catch Error:', e);
            alert("?ㅻ쪟 諛쒖깮"); 
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
    }, [])

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
            alert(isKor ? '梨꾨꼸 ?대쫫怨?梨꾨꼸 ID(?먮뒗 ?몃뱾)瑜??낅젰?댁＜?몄슂.' : 'Please enter channel name and channel ID/handle.')
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
            alert((isKor ? '嚥≪뮇類?筌?쑬瑗???????쎈솭: ' : 'Failed to save local channel: ') + (lastError || 'Unknown error'))
            return
        }

        alert(isKor ? '嚥≪뮇類?筌?쑬瑗?????貫由??됰뮸??덈뼄.' : 'Local channel saved.')
    }

    const handleStartCategoryChannelOAuth = () => {
        if (!channelConfigForm.name.trim() || !channelConfigForm.handle.trim()) {
            alert(isKor ? '癒쇱? 梨꾨꼸 ?대쫫怨?梨꾨꼸 ID(?먮뒗 ?몃뱾)瑜??낅젰?댁＜?몄슂.' : 'Enter channel name and ID/handle first.')
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
            const res = await fetch('/api/admin/categories', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            })
            const data = await res.json()
            if (!res.ok || !data.success) {
                alert((isKor ? '筌?쑬瑗???????쎈솭: ' : 'Failed to save channel: ') + (data.error || `HTTP ${res.status}`))
                return
            }
            alert(isKor ? '燁삳똾?믤⑥쥓????낆쨮??筌?쑬瑗?????貫由??됰뮸??덈뼄.' : 'Category upload channel saved.')
            setChannelConfigCategory(null)
            fetchCategories()
        } catch (err: any) {
            alert((isKor ? '筌?쑬瑗??????ㅻ쪟: ' : 'Failed to save channel: ') + (err?.message || String(err)))
        }
    }

    const handleRoleChange = async (userId: string, currentRole: string) => {
        const newRole = currentRole === 'pro' ? 'std' : 'pro';
        if (!confirm(isKor ? `?깃툒??${newRole === 'pro' ? '?袁⑥쨮' : '?ㅽ깲?ㅻ뱶'}(??嚥?癰궰野껋?釉??볦퓢??щ빍繹?` : `Change membership to ${newRole === 'pro' ? 'PRO' : 'STANDARD'}?`)) return;
        try {
            const res = await fetch('/api/admin/users/role', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId, membership: newRole })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                // ???????낅쑓??꾨뱜筌?????(fetchUsers ??Supabase 筌?Ŋ?녷에??紐낅퉸 ??六??
                setUsers(prev => prev.map(u =>
                    u.id === userId ? { ...u, app_metadata: { ...u.app_metadata, membership: newRole } } : u
                ));
                alert(isKor ? `${newRole === 'pro' ? 'PRO' : '?維 ?ㅽ깲?ㅻ뱶'}嚥?癰궰野껋럥由??됰뮸??덈뼄.` : 'Role Updated');
            } else {
                alert('癰궰野???쎈솭: ' + (data.error || '?쒕쾭 ?ㅻ쪟'));
            }
        } catch (e) { alert('?쒕쾭 ?듭떊 ?ㅻ쪟'); }
    }

    const handleApprovalChange = async (userId: string, approved: boolean) => {
        if (!confirm(approved ? '???ъ슜?먮? ?뱀씤?좉퉴??' : '???ъ슜?먮? ?뱀씤 ?湲??곹깭濡??뚮┫源뚯슂?')) return;
        try {
            const res = await fetch('/api/admin/users/approval', {
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
            alert('?뱀씤 ?곹깭 蹂寃??ㅽ뙣: ' + (e?.message || String(e)));
        }
    }

    const handleSaveUserInfo = async () => {
        if (!editInfoUser) return;
        try {
            const res = await fetch('/api/admin/users/update-metadata', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    userId: editInfoUser.id,
                    metadata: {
                        ...(editInfoForm.full_name  && { full_name:   editInfoForm.full_name }),
                        ...(editInfoForm.nationality && { nationality: editInfoForm.nationality }),
                        ...(editInfoForm.contact    && { contact:     editInfoForm.contact }),
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
                            persona_name: editInfoForm.persona_name || '',
                            persona_style: editInfoForm.persona_style || '',
                            persona_description: editInfoForm.persona_description || ''
                        }
                      }
                    : u
                ));
                setEditInfoUser(null);
                alert('???貫由??됰뮸??덈뼄.');
            } else {
                alert('??????쎈솭: ' + (data.error || '?쒕쾭 ?ㅻ쪟'));
            }
        } catch (e) { alert('?쒕쾭 ?ㅻ쪟'); }
    };

    const handleAdminRoleToggle = async (userId: string, currentIsAdmin: boolean) => {
        if (!isSuperAdmin) return;
        const action = currentIsAdmin ? 'remove' : 'grant';
        if (!confirm(`?????醫????봔?온?귐딆쁽嚥?${action}?섏떆寃좎뒿?덇퉴?`)) return;
        try {
            const res = await fetch('/api/admin/users/admin-role', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId, isAdmin: !currentIsAdmin })
            });
            if (res.ok) { alert('?꾨즺?섏뿀?듬땲??'); fetchUsers(); }
        } catch (e) { alert('?ㅻ쪟揶쎛 獄쏆뮇源??됰뮸??덈뼄.'); }
    }

    const handlePublishVideo = async (requestId: string) => {
        if (!confirm(isKor ? '???곸긽???좏뒠釉뚯뿉??怨듦컻(Public)濡??꾪솚?섏떆寃좎뒿?덇퉴?' : 'Would you like to switch this video to Public on YouTube?')) return;
        try {
            const res = await fetch('/api/admin/publishing', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ requestId, status: 'approved' })
            });
            if (res.ok) {
                alert(isKor ? '?꾪솚 ?붿껌 ?꾨즺! ?좎떆 ???좏뒠釉뚯뿉 諛섏쁺?⑸땲??' : 'Request Complete! Will reflect on YouTube shortly.');
                fetchPublishingRequests();
            } else {
                alert('?붿껌 ?ㅽ뙣');
            }
        } catch (e) { alert('?ㅻ쪟 諛쒖깮'); }
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
                    {isKor ? 'Quick Access' : 'Quick Access'}
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
                    {req.status === 'pending' && !req.metadata?.is_invalid_request && (
                        <button
                            onClick={() => handlePublishVideo(req.id)}
                            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-[10px] font-black rounded-xl shadow-lg transition-all uppercase tracking-widest"
                        >
                            {isKor ? '諛쒗뻾 ?쒖옉' : 'Publish'}
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
                            {isKor ? '諛깆뾽 ?뺤씤' : 'Backup'}
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
                    <div className="text-[10px] font-bold text-gray-600 text-left">{isKor ? '?怨뚭퍙???癒?텦????곷뮸??덈뼄.' : 'No linked assets'}</div>
                )}
            </div>
        )
    }

    const getPublishingStatusMeta = (req: PublishingRequest) => {
        if (req.metadata?.is_invalid_request) return { label: 'INVALID', className: 'bg-red-500/10 text-red-400 border-red-500/20' }
        if (req.status === 'published') return { label: isKor ? '?낅줈???꾨즺' : 'Published', className: 'bg-green-500/10 text-green-400 border-green-500/20' }
        if (req.status === 'approved' || req.status === 'to_be_published') return { label: isKor ? 'Publishing' : 'Publishing', className: 'bg-blue-500/10 text-blue-400 border-blue-500/20' }
        if (req.status === 'failed') return { label: isKor ? '?낅줈???ㅽ뙣' : 'Failed', className: 'bg-red-500/10 text-red-400 border-red-500/20' }
        if (req.status === 'rejected') return { label: isKor ? 'Rejected' : 'Rejected', className: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20' }
        return { label: isKor ? '?湲곗쨷' : 'Pending', className: 'bg-orange-500/10 text-orange-400 border-orange-500/20' }
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
        const coreTasks = ['video', 'image', 'script', 'text_gen', 'vision_gen', 'test_after_fix'];
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
            const stage = (l.task_type || 'unknown').toLowerCase();
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
            const res = await fetch(`/api/admin/logs?days=${days}&t=${Date.now()}`);
            const data = await res.json();
            setGlobalLogs(data.logs || []);
            setGlobalStats(calcGeneralStats(data.logs || [], days));
        } finally { setGlobalLoading(false); }
    }, [isAdmin]);

    
    const fetchWithdrawals = useCallback(async () => {
        const { data, error } = await supabase
            .from('withdrawals')
            .select('*')
            .order('created_at', { ascending: false })
            .limit(100)
        
        if (data && !error) {
            setWithdrawals(data)
        }
    }, [])

    const updateWithdrawalStatus = async (id: string, newStatus: 'completed' | 'rejected') => {
        if (!confirm(`?뺣쭚濡???異쒓툑 ?붿껌??${newStatus === 'completed' ? '?꾨즺' : '嫄곗젅'} 泥섎━?섏떆寃좎뒿?덇퉴?`)) return
        
        const { error } = await supabase
            .from('withdrawals')
            .update({ status: newStatus, processed_at: new Date().toISOString() })
            .eq('id', id)
            
        if (error) {
            alert('?곹깭 ?낅뜲?댄듃 ?ㅽ뙣: ' + error.message)
        } else {
            alert('異쒓툑 ?곹깭媛 ?낅뜲?댄듃 ?섏뿀?듬땲??')
            fetchWithdrawals()
        }
    }

    const fetchPublishingRequests = useCallback(async () => {
        if (!isAdmin) return;
        try {
            const res = await fetch(`/api/admin/publishing?t=${Date.now()}`);
            const data = await res.json();
            if (data.requests) setPublishingRequests(data.requests);
        } catch (e) {}
    }, [isAdmin]);

    const fetchUserLogs = async (userId: string, days: number) => {
        setLogsLoading(true);
        try {
            const res = await fetch(`/api/admin/users/${userId}/logs?days=${days}&t=${Date.now()}`);
            const data = await res.json();
            setUserLogs(data.logs || []);
            setLogStats(calcGeneralStats(data.logs || [], days));
        } finally { setLogsLoading(false); }
    }

    const fetchUsers = useCallback(async () => {
        if (!isAdmin) return;
        try {
            const res = await fetch(`/api/admin/users?t=${Date.now()}`);
            const data = await res.json();
            if (data.users) setUsers(data.users);
        } catch (e) { console.error("FetchUsers Error:", e); }
    }, [isAdmin]);

    const fetchSysKeys = useCallback(async () => {
        try {
            const res = await fetch('/api/admin/settings/global');
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
                use_external_render: data.use_external_render === 'true' || data.use_external_render === true,
                drive_path_ko: data.drive_path_ko || '',
                drive_path_en: data.drive_path_en || '',
                drive_path_ja: data.drive_path_ja || '',
                drive_active_lang: data.drive_active_lang || 'ko',
                remote_render_drive_folder_id: data.remote_render_drive_folder_id || '',
                remote_render_google_token_path: data.remote_render_google_token_path || '',
                longform_min_duration_minutes: data.longform_min_duration_minutes || '15',
                longform_base_payout: data.longform_base_payout || '10000',
                longform_extra_minute_payout: data.longform_extra_minute_payout || '500',
                longform_duration_lock_enabled: data.longform_duration_lock_enabled || 'true'
            });
        } catch (e) { console.error('fetchSysKeys error:', e); }
    }, []);

    const saveSysKeys = async () => {
        setSysKeysSaving(true); setSysKeysSaved(false);
        try {
            const res = await fetch('/api/admin/settings/global', { 
                method: 'POST', 
                headers: { 'Content-Type': 'application/json' }, 
                body: JSON.stringify({
                    ...sysKeys,
                    use_external_render: String(sysKeys.use_external_render)
                }) 
            });
            if (res.ok) setSysKeysSaved(true);
        } catch (e) { console.error('saveSysKeys error:', e); }
        finally { setSysKeysSaving(false); }
    };

    const fetchRenderQueue = useCallback(async () => {
        if (!isAdmin) return;
        setQueueLoading(true);
        try {
            const res = await fetch(`/api/admin/render-queue?t=${Date.now()}`);
            const data = await res.json();
            if (data.success && data.queue) setRenderQueue(data.queue);
        } catch (e) {
            console.error("fetchRenderQueue error:", e);
        } finally {
            setQueueLoading(false);
        }
    }, [isAdmin]);

    const handleDeleteQueueTask = async (id: string) => {
        if (!confirm(isKor ? '???묒뾽???湲곗뿴?먯꽌 ??젣?섏떆寃좎뒿?덇퉴?' : 'Delete this render task from the queue?')) return;
        try {
            const res = await fetch(`/api/admin/render-queue?id=${id}`, { method: 'DELETE' });
            const data = await res.json();
            if (data.success) {
                alert(isKor ? '??젣?섏뿀?듬땲??' : 'Deleted successfully');
                fetchRenderQueue();
            } else {
                alert('??젣 ?ㅽ뙣: ' + (data.error || '?ㅻ쪟'));
            }
        } catch (e) {
            alert('?ㅻ쪟 諛쒖깮');
        }
    };

    const fetchCategories = useCallback(async () => {
        try {
            setCategoriesLoading(true)
            const res = await fetch('/api/admin/categories')
            const data = await res.json()
            if (data.categories) setCategories(data.categories)
        } catch (e) {
            console.error("Failed to load categories:", e)
        } finally {
            setCategoriesLoading(false)
        }
    }, [])

    const fetchTopics = useCallback(async () => {
        try {
            const res = await fetch('/api/admin/topics-queue')
            const data = await res.json()
            if (data.topics) setTopics(data.topics)
        } catch (e) {
            console.error("Failed to load topics:", e)
        }
    }, [])

    const fetchStylePresets = async () => {
        try {
            setPresetsLoading(true)
            const res = await fetch('/api/admin/style-presets')
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
            alert('?꾩닔 ?낅젰 ??ぉ??梨꾩썙二쇱꽭??')
            return
        }
        try {
            setIsSavingPreset(true)
            const res = await fetch('/api/admin/style-presets', {
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
                alert('??????袁ⓥ봺???뵠 ???貫由??됰뮸??덈뼄.')
                setPresetId(null)
                setPresetKeyCode('')
                setPresetNameKo('')
                setPresetNameVi('')
                setPresetPromptTemplate('')
                setPresetGeminiInstruction('')
                setPresetImageUrl('')
                fetchStylePresets()
            } else {
                alert('??????쎈솭: ' + (data.error || '??????용뮉 ?ㅻ쪟'))
            }
        } catch (e: any) {
            alert('?????ㅻ쪟: ' + e.message)
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
        // ??깆몵嚥??癒?짗 ??쎄쾿嚥?
        setTimeout(() => {
            presetFormRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }, 50)
    }

    const handleDeletePreset = async (id: string, keyCode: string) => {
        if (!confirm(`"${keyCode}" ?ㅽ????꾨━?뗭쓣 ??젣?섏떆寃좎뒿?덇퉴?`)) return
        try {
            const res = await fetch(`/api/admin/style-presets?id=${id}`, {
                method: 'DELETE'
            })
            const data = await res.json()
            if (data.success) {
                alert('?깃났?곸쑝濡???젣?섏뿀?듬땲??')
                fetchStylePresets()
            } else {
                alert('??젣 ?ㅽ뙣: ' + (data.error || '?????녿뒗 ?ㅻ쪟'))
            }
        } catch (e: any) {
            alert('??젣 ?ㅻ쪟: ' + e.message)
        }
    }

    const handleCreateCategory = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!newCatName || !newCatEmployee) {
            alert('移댄뀒怨좊━紐낃낵 ?대떦 吏곸썝 ?대찓?쇱? ?꾩닔?낅땲??')
            return
        }
        try {
            const res = await fetch('/api/admin/categories', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: newCatName,
                    keywords: newCatKeywords,
                    benchmark_channel_url: newCatChannel,
                    assigned_employee_email: newCatEmployee,
                    default_script_style: newCatScriptStyle,
                    default_image_style: newCatImageStyle,
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
                setNewCatVideoType('longform')
                setNewCatUploadChannelId(null)
                setNewCatUploadChannelName('')
                setNewCatUploadChannelHandle('')
                fetchCategories()
                fetchTopics()
                alert('燁삳똾?믤⑥쥓?곩첎? ?源껊궗?怨몄몵嚥??源낆쨯??뤿???거? 疫꿸퀡????묐탣 雅뚯눘??3揶쏆뮄? ?怨몄삺??뤿???щ빍??')
            } else {
                alert('移댄뀒怨좊━ ?깅줉 ?ㅽ뙣: ' + data.error)
            }
        } catch (err) {
            console.error(err)
            alert('?쒕쾭 ?깅줉 ?먮윭 諛쒖깮')
        }
    }

    const handleDeleteCategory = async (id: number) => {
        if (!confirm('?뺣쭚 ??移댄뀒怨좊━瑜???젣?섏떆寃좎뒿?덇퉴? 愿?⑤맂 ?곗씠?곕룄 ?④퍡 ??젣?⑸땲??')) return
        try {
            const res = await fetch(`/api/admin/categories?id=${id}`, {
                method: 'DELETE'
            })
            const data = await res.json()
            if (data.success) {
                fetchCategories()
                fetchTopics()
            } else {
                alert('??젣 ?ㅽ뙣: ' + data.error)
            }
        } catch (err) {
            console.error(err)
        }
    }

    const handleSaveCategory = async () => {
        if (!editCategory) return
        if (!editCatForm.name || !editCatForm.assigned_employee_email) {
            alert('移댄뀒怨좊━紐낃낵 ?대떦 吏곸썝 ?대찓?쇱? ?꾩닔?낅땲??')
            return
        }
        try {
            const res = await fetch('/api/admin/categories', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    id: editCategory.id,
                    ...editCatForm
                })
            })
            const data = await res.json()
            if (data.success) {
                alert('?깃났?곸쑝濡??섏젙?섏뿀?듬땲??')
                setEditCategory(null)
                fetchCategories()
                fetchTopics()
            } else {
                alert('?섏젙 ?ㅽ뙣: ' + data.error)
            }
        } catch (err) {
            console.error(err)
            alert('?쒕쾭 ?섏젙 ?먮윭 諛쒖깮')
        }
    }

    const handleTriggerAiTopics = async (catId: number) => {
        setGeneratingCatId(catId)
        try {
            const res = await fetch('/api/admin/topics-queue', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ categoryId: catId })
            })
            const data = await res.json()
            if (data.success) {
                const generatedTopics = Array.isArray(data.topics) ? data.topics.map((topic: any) => String(topic)).slice(0, 10) : []
                setGeneratedTopicsByCat(prev => ({ ...prev, [catId]: generatedTopics }))
                fetchTopics()
                alert(`AI揶쎛 ??덉쨮???紐? ?怨멸맒 雅뚯눘??${data.count}媛쒕? ?깃났?곸쑝濡??앹꽦?섏뿬 ?먯뿉 異붽??덉뒿?덈떎!`)
            } else {
                alert('AI ?앹꽦 ?ㅽ뙣: ' + data.error)
            }
        } catch (err) {
            console.error(err)
            alert('AI ?앹꽦 ?붿껌 ?ㅻ쪟')
        } finally {
            setGeneratingCatId(null)
        }
    }

    const startEditingTopic = (topicItem: any) => {
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
        const currentTopic = String(topicItem?.topic || '').trim()
        if (!topicItem?.id || !currentTopic) return

        const trimmed = editingTopicDraft.trim()
        if (!trimmed) {
            alert('二쇱젣??鍮꾩썙?????놁뒿?덈떎.')
            return
        }

        if (trimmed === currentTopic) return

        setTopicActionLoadingId(String(topicItem.id))
        try {
            const res = await fetch('/api/admin/topics-queue', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: topicItem.id, topic: trimmed })
            })
            const data = await res.json()
            if (!res.ok || !data.success) {
                alert('二쇱젣 ?섏젙 ?ㅽ뙣: ' + (data.error || `HTTP ${res.status}`))
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
            alert('二쇱젣 ?섏젙 ?ㅻ쪟: ' + (err?.message || String(err)))
        } finally {
            setTopicActionLoadingId(null)
        }
    }

    const handleDeleteTopic = async (topicItem: any) => {
        if (!topicItem?.id) return
        if (!confirm('???湲곗쨷 二쇱젣瑜???젣?좉퉴??')) return

        setTopicActionLoadingId(String(topicItem.id))
        try {
            const res = await fetch(`/api/admin/topics-queue?id=${topicItem.id}`, {
                method: 'DELETE'
            })
            const data = await res.json()
            if (!res.ok || !data.success) {
                alert('二쇱젣 ??젣 ?ㅽ뙣: ' + (data.error || `HTTP ${res.status}`))
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
            alert('二쇱젣 ??젣 ?ㅻ쪟: ' + (err?.message || String(err)))
        } finally {
            setTopicActionLoadingId(null)
        }
    }

    const handleDeleteTopicsByYears = async (categoryId: number, years: string[] = ['2024', '2025']) => {
        const label = years.join(', ')
        if (!confirm(`??移댄뀒怨좊━???湲곗쨷 二쇱젣 以?${label} ?곕룄媛 ?ㅼ뼱媛???ぉ???쇨큵 ??젣?좉퉴??`)) return

        setTopicActionLoadingId(`cleanup-${categoryId}`)
        try {
            const params = new URLSearchParams({
                categoryId: String(categoryId),
                years: years.join(','),
            })
            const res = await fetch(`/api/admin/topics-queue?${params.toString()}`, {
                method: 'DELETE'
            })
            const data = await res.json()
            if (!res.ok || !data.success) {
                alert('?곕룄 二쇱젣 ?뺣━ ?ㅽ뙣: ' + (data.error || `HTTP ${res.status}`))
                return
            }

            const deletedIdSet = new Set((data.deletedIds || []).map((id: any) => String(id)))
            setTopics(prev => prev.filter(item => !deletedIdSet.has(String(item.id))))

            if (editingTopicId && deletedIdSet.has(editingTopicId)) {
                cancelEditingTopic()
            }

            alert(`${data.deletedCount || 0}媛쒖쓽 ?ㅻ옒???곕룄 ?湲곗＜?쒕? ??젣?덉뒿?덈떎.`)
        } catch (err: any) {
            alert('?곕룄 二쇱젣 ?뺣━ ?ㅻ쪟: ' + (err?.message || String(err)))
        } finally {
            setTopicActionLoadingId(null)
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
            const interval = setInterval(fetchRenderQueue, 3000); // 3??揶쏄쑨爰???쇰뻻揶?揶쏄퉮??
            return () => clearInterval(interval);
        }
    }, [activeTab, fetchRenderQueue]);

    useEffect(() => {
        supabase.auth.getSession().then(({ data: { session } }) => {
            if (!session) router.push('/');
            else setUser(session.user);
            setLoading(false);
        });
    }, [router]);

    // ?λ뜃由??怨쀬뵠??嚥≪뮆逾????μ뵬 Effect
    useEffect(() => {
        if (isAdmin && !loading) {
            fetchUsers();
            fetchGlobalStats(globalPeriod);
            fetchPublishingRequests();
            fetchSysKeys();
            fetchCategories();
            fetchTopics();
            fetchStylePresets();
        }
    }, [isAdmin, loading, fetchCategories, fetchTopics]);

    // 疫꿸퀗而?癰궰野???뽯퓠筌?癰귢쑬猷??紐꾪뀱
    useEffect(() => {
        if (isAdmin && !loading) {
            fetchGlobalStats(globalPeriod);
        }
    }, [globalPeriod]);

    if (loading) return <div className="min-h-screen bg-[#050505] text-white flex items-center justify-center font-black animate-pulse uppercase tracking-[0.5em]">?온?귐딆쁽 ?紐꾩쵄 餓?..</div>;
    if (!isAdmin) return <div className="min-h-screen bg-[#050505] text-red-500 flex items-center justify-center font-black">?臾롫젏 亦낅슦釉????곷뮸??덈뼄.</div>;

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
                                {task.count} <span className="text-gray-600 text-[10px]">items</span>
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

    const renderLogTable = (logs: any[]) => (
        <div className="bg-[#0f172a]/40 border border-white/5 rounded-[2rem] overflow-hidden overflow-x-auto shadow-2xl">
            <table className="w-full text-left min-w-[1000px]">
                <thead className="bg-black/20 border-b border-white/5 text-[10px] font-black text-gray-500 uppercase tracking-widest">
                    <tr>
                        <th className="px-10 py-5">TIME</th>
                        <th className="px-10 py-5">TASK</th>
                        <th className="px-10 py-5">MODEL & PROVIDER</th>
                        <th className="px-10 py-5">PROMPT SUMMARY</th>
                        <th className="px-10 py-5 text-right text-orange-500">AI Token Usage</th>
                        <th className="px-10 py-5 text-right text-blue-500">?꾩옱 ?좏겙 ?붿븸</th>
                        <th className="px-10 py-5 text-center">STATUS</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                    {(logs || []).map((log: any) => (
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
                    ))}
                </tbody>
            </table>
        </div>
    );

    return (
        <div className="min-h-screen bg-[#000106] text-white font-sans selection:bg-blue-500/30">
            <nav className="p-6 border-b border-white/5 bg-black/60 sticky top-0 z-[100] backdrop-blur-xl">
                <div className="max-w-[1600px] mx-auto flex justify-between items-center">
                    <span className="text-2xl font-black italic tracking-tighter text-blue-500">PICADIRI STUDIO</span>
                    <div className="flex gap-6 items-center">
                        <LanguageSelector />
                        <div className="text-right">
                            <span className="block text-[10px] text-gray-500 font-bold uppercase tracking-widest leading-none">
                                {isSuperAdmin ? '理쒓퀬 愿由ъ옄' : '遺愿由ъ옄'}
                            </span>
                            <span className="text-sm font-black text-blue-400">{user?.email}</span>
                        </div>
                        <button onClick={() => supabase.auth.signOut().then(() => router.push('/'))} className="px-6 py-2.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all">濡쒓렇?꾩썐</button>
                    </div>
                </div>
            </nav>

            <main className="max-w-[1600px] mx-auto px-6 py-8 space-y-12">
                <div className="flex items-center justify-between">
                    <h2 className="text-4xl font-black uppercase tracking-tighter">ADMIN DASHBOARD</h2>
                    <div className="flex gap-2 p-1.5 bg-white/5 rounded-2xl border border-white/5 shadow-2xl">
                        {(['topics', 'overview', 'users', 'withdrawals', 'api', 'render-queue', 'styles'] as const).map(tab => (
                            <button key={tab} onClick={() => setActiveTab(tab)} className={`px-10 py-3.5 rounded-xl text-[11px] font-black transition-all uppercase tracking-[0.1em] ${activeTab === tab ? 'bg-blue-600 text-white shadow-xl' : 'text-gray-500 hover:text-white'}`}>
                                {tab === 'topics'
                                    ? 'Topics'
                                    : tab === 'overview'
                                    ? 'Overview'
                                    : tab === 'users'
                                    ? 'Users'
                                    : tab === 'withdrawals'
                                    ? 'Withdrawals'
                                    : tab === 'api'
                                    ? 'System API'
                                    : tab === 'render-queue'
                                    ? 'Render Queue'
                                    : 'Style Settings'}
                            </button>
                        ))}
                    </div>
                </div>

                {activeTab === 'topics' && (
                    <div className="space-y-8 animate-in fade-in duration-300">
                        {/* 1. 移댄뀒怨좊━ 異붽? */}
                        <div className="bg-[#0f172a]/60 rounded-[2.5rem] border border-white/10 p-8 shadow-2xl">
                            <h2 className="font-black text-xl tracking-tight mb-6 flex items-center gap-2">
                                移댄뀒怨좊━ 諛?吏곸썝 留ㅽ븨 異붽?
                            </h2>
                            <form onSubmit={handleCreateCategory} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">移댄뀒怨좊━紐?*</label>
                                    <input 
                                        type="text" 
                                        required
                                        placeholder="Enter category name"
                                        value={newCatName}
                                        onChange={e => setNewCatName(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">?대떦 吏곸썝 ?대찓??*</label>
                                    <select
                                        required
                                        value={newCatEmployee}
                                        onChange={e => setNewCatEmployee(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50 cursor-pointer"
                                    >
                                        <option value="">-- 吏곸썝???좏깮?섏꽭??--</option>
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
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">Main keywords</label>
                                    <input 
                                        type="text" 
                                        placeholder="Stocks, real estate, finance, lifestyle"
                                        value={newCatKeywords}
                                        onChange={e => setNewCatKeywords(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">踰ㅼ튂留덊궧???좏뒠釉?梨꾨꼸 URL</label>
                                    <input 
                                        type="url" 
                                        placeholder="?? https://www.youtube.com/@BenchmarkChannel"
                                        value={newCatChannel}
                                        onChange={e => setNewCatChannel(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div>
                                    <div className="flex items-center justify-between mb-1.5">
                                        <label className="text-xs font-black text-gray-400 block uppercase tracking-wider">?낅줈??怨좎젙 梨꾨꼸</label>
                                        <button
                                            type="button"
                                            onClick={fetchLocalUploadChannels}
                                            className="text-[10px] font-black text-blue-400 hover:text-blue-300"
                                        >
                                            {localChannelsLoading ? '遺덈윭?ㅻ뒗 以?..' : '濡쒖뺄 梨꾨꼸 遺덈윭?ㅺ린'}
                                        </button>
                                    </div>
                                    <select
                                        value={newCatUploadChannelId ?? ''}
                                        onChange={e => applySelectedChannelToCreateForm(e.target.value ? Number(e.target.value) : null)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50 cursor-pointer"
                                    >
                                        <option value="" className="bg-[#111] text-white">-- 怨좎젙 梨꾨꼸 ?놁쓬 --</option>
                                        {localChannels.map(channel => (
                                            <option key={`new-cat-channel-${channel.id}`} value={channel.id} className="bg-[#111] text-white">
                                                {channel.name} {channel.credentials_path ? '[?곕룞?꾨즺]' : '[誘몄뿰??'}
                                            </option>
                                        ))}
                                    </select>
                                    <p className="mt-2 text-[11px] text-gray-500">
                                        {newCatUploadChannelName
                                            ? `${newCatUploadChannelName} (${newCatUploadChannelHandle || 'handle ??'})`
                                            : '?좏깮??二쇱젣???대떦 梨꾨꼸濡??낅줈?쒕맗?덈떎.'}
                                    </p>
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">湲곕낯 ?蹂??ㅽ???*</label>
                                    <select
                                        required
                                        value={newCatScriptStyle}
                                        onChange={e => setNewCatScriptStyle(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50 cursor-pointer"
                                    >
                                        <option value="default" className="bg-[#111] text-white">湲곕낯 ?ㅼ젙 (?먯뿰?ㅻ읇怨??좊챸???ㅽ???</option>
                                        <option value="story" className="bg-[#111] text-white">?쏅궇 ?댁빞湲?(援ъ뿰 ?숉솕)</option>
                                        <option value="senior_story" className="bg-[#111] text-white">?쒕땲???댁빞湲?(?뚯긽/媛먯꽦)</option>
                                        <option value="news" className="bg-[#111] text-white">?댁뒪 (?뺣낫 ?꾨떖)</option>
                                        <option value="mystery_thriller" className="bg-[#111] text-white">誘몄뒪?곕━ ?ㅻ┫??(湲댁옣媛?</option>
                                        <option value="nursery_rhyme" className="bg-[#111] text-white">?대┛???숈슂 (洹?ъ슫 援ъ뿰)</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">湲곕낯 ?대?吏 ?ㅽ???*</label>
                                    <select
                                        required
                                        value={newCatImageStyle}
                                        onChange={e => setNewCatImageStyle(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50 cursor-pointer"
                                    >
                                        <option value="realistic" className="bg-[#111] text-white">?ㅼ궗 (Photorealistic)</option>
                                        <option value="ghibli" className="bg-[#111] text-white">吏釉뚮━ 媛먯꽦 ?쇰윭?ㅽ듃 (Ghibli)</option>
                                        <option value="anime" className="bg-[#111] text-white">?좊땲硫붿씠?섑뭾 (Anime)</option>
                                        <option value="cinematic" className="bg-[#111] text-white">?곹솕 ?ㅽ???(Cinematic)</option>
                                        <option value="cartoon" className="bg-[#111] text-white">2D 移댄넠 ?ㅽ???(Cartoon)</option>
                                        <option value="nursery_rhyme" className="bg-[#111] text-white">3D ?숉솕/?좊땲 (Nursery/Pixar)</option>
                                        <option value="ink_wash" className="bg-[#111] text-white">?숈뼇 ?섎ぉ???ㅽ???(Ink Wash)</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">?곸긽 ?뺤떇 (?꾩닔) *</label>
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
                                            <span>濡깊뤌 (Longform)</span>
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
                                            <span>?쇱툩 (Shorts)</span>
                                        </label>
                                    </div>
                                </div>
                                <div className="md:col-span-3 mt-4 flex justify-end">
                                    <button 
                                        type="submit"
                                        className="px-8 py-3 bg-blue-600 hover:bg-blue-500 text-white font-black rounded-xl transition-all shadow-lg active:scale-95"
                                    >
                                        移댄뀒怨좊━ ?깅줉 諛?珥덇린 二쇱젣 ?앹꽦
                                    </button>
                                </div>
                            </form>
                        </div>

                        {/* 2. ?깅줉??移댄뀒怨좊━ 諛?留ㅽ븨 由ъ뒪??*/}
                        <div className="bg-[#0f172a]/60 rounded-[2.5rem] border border-white/10 overflow-hidden shadow-2xl p-8">
                            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
                                <h2 className="font-black text-xl tracking-tight">??移댄뀒怨좊━ ?꾪솴</h2>
                                <div className="flex p-1 bg-black/40 rounded-xl border border-white/10">
                                    <button 
                                        onClick={() => setCategoryListTab('longform')}
                                        className={`px-6 py-2 rounded-lg text-xs font-black transition-all ${categoryListTab === 'longform' ? 'bg-blue-600 text-white shadow' : 'text-gray-500 hover:text-white'}`}
                                    >
                                        濡깊뤌 (Longform)
                                    </button>
                                    <button 
                                        onClick={() => setCategoryListTab('shorts')}
                                        className={`px-6 py-2 rounded-lg text-xs font-black transition-all ${categoryListTab === 'shorts' ? 'bg-blue-600 text-white shadow' : 'text-gray-500 hover:text-white'}`}
                                    >
                                        ?쇱툩 (Shorts)
                                    </button>
                                </div>
                            </div>

                            {categoriesLoading ? (
                                <div className="text-center py-20 text-gray-500 text-sm">移댄뀒怨좊━ 濡쒕뵫 以?..</div>
                            ) : categories.filter(c => (c.video_type || 'longform') === categoryListTab).length === 0 ? (
                                <div className="text-center py-20 text-gray-500 text-sm italic">?대떦 ?좏삎???깅줉??移댄뀒怨좊━媛 ?놁뒿?덈떎.</div>
                            ) : (
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                    {categories.filter(c => (c.video_type || 'longform') === categoryListTab).map((cat) => {
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
                                                                        video_type: cat.video_type || 'longform',
                                                                        upload_channel_id: cat.upload_channel_id || null,
                                                                        upload_channel_name: cat.upload_channel_name || '',
                                                                        upload_channel_handle: cat.upload_channel_handle || '',
                                                                    });
                                                                }}
                                                                className="text-blue-400 hover:text-blue-300 text-xs transition-colors shadow-none bg-transparent p-0"
                                                            >
                                                                ?섏젙
                                                            </button>
                                                            <span className="text-gray-700">|</span>
                                                            <button 
                                                                onClick={() => handleDeleteCategory(cat.id)}
                                                                className="text-gray-500 hover:text-red-500 text-xs transition-colors shadow-none bg-transparent p-0"
                                                            >
                                                                ??젣
                                                            </button>
                                                        </div>
                                                    </div>
                                                    <div className="space-y-2 text-xs text-gray-400 mb-6">
                                                        <p>?대떦 吏곸썝: <strong className="text-gray-200">{cat.assigned_employee_email}</strong></p>
                                                        <p>?ㅼ썙?? <strong className="text-gray-200">{cat.keywords || '(?놁쓬)'}</strong></p>
                                                        <p className="truncate">踰ㅼ튂 梨꾨꼸: <a href={cat.benchmark_channel_url} target="_blank" rel="noreferrer" className="text-blue-400 underline">{cat.benchmark_channel_url || '(?놁쓬)'}</a></p>
                                                        <p>
                                                            ?낅줈??梨꾨꼸:{' ' }
                                                            <button
                                                                type="button"
                                                                onClick={() => openCategoryChannelConfig(cat)}
                                                                className="text-blue-400 underline hover:text-blue-300"
                                                            >
                                                                {cat.upload_channel_name || cat.upload_channel_handle || 'Unassigned'}
                                                        </button>
                                                    </p>
                                                        <p>?蹂??ㅽ??? <strong className="text-gray-200">{cat.default_script_style || '湲곕낯'}</strong></p>
                                                        <p>?대?吏 ?ㅽ??? <strong className="text-gray-200">{cat.default_image_style || '?ㅼ궗'}</strong></p>
                                                        <p>?곸긽 ?щ㎎: <strong className="text-gray-200">{cat.video_type === 'shorts' ? '?쇱툩 (Shorts)' : '濡깊뤌 (Longform)'}</strong></p>
                                                    </div>
                                                     
                                                    {/* 二쇱젣 ?湲곗뿴 移댁슫??*/}
                                                    <div className="flex gap-3 text-[11px] font-black tracking-wider uppercase mb-6">
                                                        <span className="px-3 py-1 bg-yellow-500/10 text-yellow-500 border border-yellow-500/20 rounded-lg">Pending {pendingTopics.length}</span>
                                                        <span className="px-3 py-1 bg-green-500/10 text-green-500 border border-green-500/20 rounded-lg">Completed {completedTopics.length}</span>
                                                    </div>
                                                </div>

                                                <button 
                                                    disabled={generatingCatId === cat.id}
                                                    onClick={() => handleTriggerAiTopics(cat.id)}
                                                    className="w-full py-2.5 bg-blue-600/20 hover:bg-blue-600 border border-blue-500/20 hover:border-transparent text-blue-400 hover:text-white rounded-xl text-xs font-black tracking-wider transition-all disabled:bg-gray-800 disabled:text-gray-500 disabled:cursor-not-allowed uppercase"
                                                >
                                                    {generatingCatId === cat.id ? 'AI 二쇱젣 ?앹꽦 以?..' : 'AI 二쇱젣 ?먰뙋湲??앹꽦 (10媛?'}
                                                </button>

                                                {previewTopicItems.length > 0 && (
                                                    <div className="mt-4 rounded-2xl border border-blue-500/20 bg-blue-950/20 p-4">
                                                        <div className="mb-3 flex items-center justify-between gap-2">
                                                            <div className="flex items-center gap-2">
                                                                <p className="text-[11px] font-black text-blue-300">
                                                                    {isFreshPreview ? 'Fresh topic preview (10)' : 'Pending topic preview'}
                                                                </p>
                                                                {staleYearPendingCount > 0 && (
                                                                    <span className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-[10px] font-black text-amber-300">
                                                                        2024/2025 {staleYearPendingCount}媛?
                                                                    </span>
                                                                )}
                                                            </div>
                                                            <div className="flex items-center gap-2">
                                                                {staleYearPendingCount > 0 && (
                                                                    <button
                                                                        type="button"
                                                                        disabled={topicActionLoadingId === `cleanup-${cat.id}`}
                                                                        onClick={() => handleDeleteTopicsByYears(cat.id)}
                                                                        className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-1 text-[10px] font-black text-red-300 hover:bg-red-500/20 disabled:opacity-50"
                                                                    >
                                                                        2024/2025 ??젣
                                                                    </button>
                                                                )}
                                                                <span className="text-[10px] font-bold text-gray-500">{previewTopicItems.length} items</span>
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
                                                                                        ???
                                                                                    </button>
                                                                                    <button
                                                                                        type="button"
                                                                                        disabled={topicActionLoadingId === String(topicItem.id)}
                                                                                        onClick={cancelEditingTopic}
                                                                                        className="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-gray-300 disabled:opacity-50"
                                                                                    >
                                                                                        痍⑥냼
                                                                                    </button>
                                                                                    <span className="text-[10px] font-bold text-gray-500">Enter ???쨌 ESC 痍⑥냼</span>
                                                                                </div>
                                                                            </div>
                                                                        ) : (
                                                                            <div className="flex items-start gap-2">
                                                                                <span className="min-w-0 flex-1 break-words">{topicItem.topic}</span>
                                                                                <div className="shrink-0 flex items-center gap-2">
                                                                                    <button
                                                                                        type="button"
                                                                                        disabled={topicActionLoadingId === String(topicItem.id)}
                                                                                        onClick={() => startEditingTopic(topicItem)}
                                                                                        className="text-[10px] font-black text-blue-300 hover:text-white disabled:opacity-50"
                                                                                    >
                                                                                        ?섏젙
                                                                                    </button>
                                                                                    <button
                                                                                        type="button"
                                                                                        disabled={topicActionLoadingId === String(topicItem.id)}
                                                                                        onClick={() => handleDeleteTopic(topicItem)}
                                                                                        className="text-[10px] font-black text-red-300 hover:text-red-200 disabled:opacity-50"
                                                                                    >
                                                                                        ??젣
                                                                                    </button>
                                                                                </div>
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

                        {/* 3. ?袁⑷퍥 雅뚯눘????疫꿸퀣肉???筌뤴뫀??怨뺤춦 */}
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
                            const activeStatusLabel = topicQueueStatusFilter === 'working' ? 'Working' : 'Pending';

                            return (
                        <div className="bg-[#0f172a]/60 rounded-[2.5rem] border border-white/10 overflow-hidden shadow-2xl">
                            <div className="p-8 border-b border-white/10 bg-black/20">
                                <div className="flex flex-col xl:flex-row xl:items-start xl:justify-between gap-5">
                                    <div className="min-w-0">
                                        <h2 className="font-black text-xl tracking-tight">
                                            Topics Queue
                                        </h2>
                                        <p className="mt-2 text-xs font-bold text-gray-500">
                                            {selectedCategory ? `${selectedCategory.name} - ${activeStatusLabel}` : `All categories - ${activeStatusLabel}`}
                                        </p>
                                    </div>
                                    <div className="flex flex-wrap items-center gap-2">
                                        {[
                                            { key: 'working', label: 'Working' },
                                            { key: 'pending', label: 'Pending' },
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
                                            {selectedCategory ? '?좏깮 ?쒖떆嫄댁닔' : '珥??쒖떆嫄댁닔'}: {filteredTopics.length}媛?
                                        </span>
                                    </div>
                                </div>

                                <div className="mt-4 flex flex-wrap items-center gap-3">
                                    <label className="text-[11px] font-black text-gray-500">諛곗젙 吏곸썝</label>
                                    <select
                                        value={topicQueueEmployeeFilter}
                                        onChange={(e) => setTopicQueueEmployeeFilter(e.target.value)}
                                        className="min-w-[240px] rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-[11px] font-bold text-white focus:outline-none focus:border-blue-500/50"
                                    >
                                        <option value="all" className="bg-[#111] text-white">?꾩껜 吏곸썝</option>
                                        {availableTopicQueueEmployees.map(email => (
                                            <option key={`topic-queue-employee-${email}`} value={email} className="bg-[#111] text-white">
                                                {email}
                                            </option>
                                        ))}
                                    </select>
                                    <span className="text-[11px] font-bold text-gray-500">
                                        {topicQueueEmployeeFilter === 'all' ? 'Showing all employees' : 'Showing selected employee'}
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
                                        ?꾩껜 <span className="ml-1 text-[10px] opacity-70">{topics.filter(t => isQueueVisibleTopic(t) && matchesTopicQueueStatus(t)).length}</span>
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
                                            <th className="px-10 py-6">移댄뀒怨좊━</th>
                                            <th className="px-10 py-6">?쒖븞 ?곸긽 二쇱젣</th>
                                            {topicQueueStatusFilter === 'working' && (
                                                <th className="px-10 py-6">?묒뾽 吏꾪뻾</th>
                                            )}
                                            <th className="px-10 py-6">Assigned worker</th>
                                            <th className="px-10 py-6 text-center">諛곕떦 ?곹깭</th>
                                            <th className="px-10 py-6 text-right">Actions</th>
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
                                                    {item.categories?.name || '湲곕낯'}
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
                                                                            ???
                                                                        </button>
                                                                        <button
                                                                            type="button"
                                                                            disabled={topicActionLoadingId === String(item.id)}
                                                                            onClick={cancelEditingTopic}
                                                                            className="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-gray-300 disabled:opacity-50"
                                                                        >
                                                                            痍⑥냼
                                                                        </button>
                                                                        <span className="text-[10px] font-bold text-gray-500">Enter ???쨌 ESC 痍⑥냼</span>
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
                                                                    Current step: {item.progress_payload?.current_step || 'In progress'}
                                                                </div>
                                                            </div>
                                                        ) : (
                                                            <span className="text-[11px] font-bold text-gray-500">Waiting</span>
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
                                                        {item.status === 'pending' ? 'Pending' : isWorkingTopic(item) ? 'Working' : 'Started'}
                                                    </span>
                                                </td>
                                                <td className="px-10 py-6 text-right">
                                                    {item.status === 'pending' ? (
                                                        <div className="flex items-center justify-end gap-3 text-[11px] font-black">
                                                            <button
                                                                type="button"
                                                                disabled={topicActionLoadingId === String(item.id)}
                                                                onClick={() => startEditingTopic(item)}
                                                                className="text-blue-300 hover:text-white disabled:opacity-50"
                                                            >
                                                                ?섏젙
                                                            </button>
                                                            <button
                                                                type="button"
                                                                disabled={topicActionLoadingId === String(item.id)}
                                                                onClick={() => handleDeleteTopic(item)}
                                                                className="text-red-300 hover:text-red-200 disabled:opacity-50"
                                                            >
                                                                ??젣
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
                                                    {selectedCategory ? '?좏깮??移댄뀒怨좊━???깅줉??二쇱젣媛 ?놁뒿?덈떎.' : '?湲곗뿴???깅줉??二쇱젣媛 ?놁뒿?덈떎. 移댄뀒怨좊━瑜?癒쇱? ?좏깮??二쇱꽭??'}
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
                                    <span className="text-[10px] font-black uppercase tracking-widest">?꾩껜 ?몄썝</span>
                                    <div className="flex items-baseline gap-1"><span className="text-xl font-black italic">{memberCount.toLocaleString()}</span><span className="text-[9px] font-bold uppercase">members</span></div>
                                </div>
                                <div className="flex-1 bg-[#0f172a]/80 border border-white/5 px-6 py-3 rounded-2xl flex items-center justify-between transition-transform hover:scale-[1.02]">
                                    <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">?ㅻ뒛 ?쒖꽦</span>
                                    <div className="flex items-baseline gap-1"><span className="text-xl font-black tabular-nums">{activeToday.toLocaleString()}</span><span className="text-[9px] font-bold text-green-500 uppercase">+{newToday}</span></div>
                                </div>
                                <div className="flex-1 bg-[#0f172a]/80 border border-white/5 px-6 py-3 rounded-2xl flex items-center justify-between transition-transform hover:scale-[1.02]">
                                    <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">珥?蹂댁쑀 ?좏겙</span>
                                    <div className="flex items-baseline gap-1"><span className="text-xl font-black text-orange-500 tabular-nums">{totalTokens.toLocaleString()}</span><span className="text-[9px] font-bold text-orange-500/50 uppercase">TK</span></div>
                                </div>
                            </div>
                            <div className="flex items-center gap-2 p-1 bg-white/5 rounded-2xl border border-white/5">
                                <div className="flex gap-1">{[1, 7, 30].map(d => (
                                    <button key={d} onClick={() => setGlobalPeriod(d)} className={`px-4 py-2 text-[10px] font-black rounded-xl transition-all ${globalPeriod === d ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500 hover:text-white'}`}>{d === 1 ? '?쇨컙' : d === 7 ? '二쇨컙' : '?붽컙'}</button>
                                ))}</div>
                                <div className="w-[1px] h-4 bg-white/10 mx-1"></div>
                                <button onClick={() => fetchGlobalStats(globalPeriod)} className="px-5 py-2 hover:bg-white/5 rounded-xl text-[10px] font-black text-blue-500 transition-all">?덈줈怨좎묠</button>
                            </div>
                        </div>
                        <div className="flex flex-col lg:flex-row gap-4">
                            <div className="flex-1 grid grid-cols-4 gap-4">
                                <StatCard label="TOTAL TASKS" value={globalStats.total} unit="UNITS" color="white" />
                                <StatCard label="SUCCESS RATE" value={globalStats.successRate + '%'} unit="GLOBAL" color="green" />
                                <StatCard label="AVG LATENCY" value={globalStats.avgLatency + 's'} unit="PER TASK" color="blue" />
                                <StatCard label="DAILY TOKEN USAGE" value={globalStats.totalTokens.toLocaleString()} unit="TOKENS" color="orange" />
                            </div>
                            {renderDonutChart(globalStats)}
                        </div>
                        {renderChartRow(globalStats, globalTopTasks)}
                        <div className="flex items-center gap-4 py-2">
                             <div className="text-[11px] font-black text-gray-500 uppercase tracking-[0.4em] flex items-center gap-4"><div className="w-2 h-2 rounded-full bg-blue-500" /> GENERATION HISTORY</div>
                             <div className="h-[1px] flex-1 bg-white/5"></div>
                             <div className="flex gap-1 p-1 bg-white/5 rounded-xl border border-white/5">
                                 <button onClick={() => setOverviewSubTab('video')} className={`px-8 py-1.5 rounded-lg text-[10px] font-black transition-all ${overviewSubTab === 'video' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500 hover:text-white'}`}>Video Queue</button>
                                 <button onClick={() => setOverviewSubTab('log')} className={`px-8 py-1.5 rounded-lg text-[10px] font-black transition-all ${overviewSubTab === 'log' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500 hover:text-white'}`}>Logs</button>
                             </div>
                        </div>
                        {overviewSubTab === 'video' ? (
                            <div className="space-y-12">
                                <div className="bg-[#0f172a]/20 border border-white/5 rounded-[2.5rem] overflow-hidden shadow-2xl">
                                    <div className="px-10 py-6 border-b border-white/5 bg-black/20 flex justify-between items-center">
                                        <h3 className="text-[10px] font-black text-blue-500 uppercase tracking-[0.4em]">?뺤씤 ?湲?諛??깅줉???곸긽</h3>
                                    </div>
                                    <div className="px-10 py-6 border-b border-white/5 bg-white/[0.02]">
                                        <div className="grid grid-cols-2 xl:grid-cols-6 gap-3">
                                            <div className="rounded-2xl border border-white/10 bg-black/20 px-4 py-3">
                                                <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">Total</div>
                                                <div className="mt-1 text-2xl font-black text-white tabular-nums">{publishingSummary.total}</div>
                                            </div>
                                            <div className="rounded-2xl border border-orange-500/20 bg-orange-500/5 px-4 py-3">
                                                <div className="text-[10px] font-black uppercase tracking-widest text-orange-300">{isKor ? 'Pending' : 'Pending'}</div>
                                                <div className="mt-1 text-2xl font-black text-orange-300 tabular-nums">{publishingSummary.pending}</div>
                                            </div>
                                            <div className="rounded-2xl border border-blue-500/20 bg-blue-500/5 px-4 py-3">
                                                <div className="text-[10px] font-black uppercase tracking-widest text-blue-300">{isKor ? 'Publishing' : 'Publishing'}</div>
                                                <div className="mt-1 text-2xl font-black text-blue-300 tabular-nums">{publishingSummary.processing}</div>
                                            </div>
                                            <div className="rounded-2xl border border-green-500/20 bg-green-500/5 px-4 py-3">
                                                <div className="text-[10px] font-black uppercase tracking-widest text-green-300">{isKor ? '?꾨즺' : 'Published'}</div>
                                                <div className="mt-1 text-2xl font-black text-green-300 tabular-nums">{publishingSummary.published}</div>
                                            </div>
                                            <div className="rounded-2xl border border-red-500/20 bg-red-500/5 px-4 py-3">
                                                <div className="text-[10px] font-black uppercase tracking-widest text-red-300">{isKor ? '?ㅽ뙣' : 'Failed'}</div>
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
                                            { key: 'all', label: isKor ? '?꾩껜' : 'All', count: publishingSummary.total },
                                            { key: 'pending', label: isKor ? 'Pending' : 'Pending', count: publishingSummary.pending },
                                            { key: 'processing', label: isKor ? 'Publishing' : 'Publishing', count: publishingSummary.processing },
                                            { key: 'published', label: isKor ? '?꾨즺' : 'Published', count: publishingSummary.published },
                                            { key: 'failed', label: isKor ? '?낅줈???ㅽ뙣' : 'Failed', count: publishingSummary.failed },
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
                                            {isKor ? `Showing ${filteredPublishingRequests.length} requests` : `Showing ${filteredPublishingRequests.length} requests`}


                                        </div>
                                    </div>
                                    <table className="w-full text-left">
                                        <thead className="bg-black/30 border-b border-white/5 text-[10px] font-black text-gray-500 uppercase tracking-widest">
                                            <tr><th className="px-10 py-6">?곸긽 ?뺣낫 / ?ъ쑀</th><th className="px-10 py-6 text-center">?좏뒠釉?ID</th><th className="px-10 py-6 text-center">?깅줉?쇱떆</th><th className="px-10 py-6 text-center">?곹깭</th><th className="px-10 py-6 text-right">愿由?/ Drive ?먯궛</th></tr>
                                        </thead>
                                        <tbody className="divide-y divide-white/5">
                                            {filteredPublishingRequests.length === 0 ? (
                                                <tr><td colSpan={5} className="px-10 py-20 text-center text-gray-600 font-bold uppercase tracking-widest italic">?源낆쨯???怨멸맒????곷뮸??덈뼄.</td></tr>
                                            ) : (
                                                filteredPublishingRequests.map(req => {
                                                    const owner = users?.find(u => u.id === req.user_id);
                                                    const statusMeta = getPublishingStatusMeta(req);
                                                    return (
                                                        <tr key={req.id} className="hover:bg-white/[0.03] transition-colors group">
                                                            <td className="px-10 py-6">
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
                                                                                    ?袁⑥쨮??븍뱜: {req.metadata.project_name}
                                                                                </span>
                                                                            )}
                                                                            {req.metadata?.topic && (
                                                                                <span className="px-2 py-1 rounded-full bg-white/5 border border-white/10 text-[9px] font-black text-gray-300">
                                                                                    雅뚯눘?? {req.metadata.topic}
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
                                                                            <span className={`px-2 py-1 rounded-full border text-[9px] font-black ${statusMeta.className}`}>
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
                                                            <td className="px-10 py-6 text-center">
                                                                {req.metadata?.youtube_url || req.metadata?.videoId ? (
                                                                    <a
                                                                        href={req.metadata?.youtube_url || `https://youtu.be/${req.metadata?.videoId}`}
                                                                        target="_blank"
                                                                        rel="noreferrer"
                                                                        className="text-[11px] font-black text-blue-500 hover:underline"
                                                                    >
                                                                        {req.metadata?.videoId || (isKor ? '?닿린' : 'Open')}
                                                                    </a>
                                                                ) : (
                                                                    <span className="text-[11px] font-black text-gray-600">-</span>
                                                                )}
                                                            </td>
                                                            <td className="px-10 py-6 text-center text-[12px] font-black text-gray-500">{new Date(req.created_at).toLocaleString()}</td>
                                                            <td className="px-10 py-6 text-center">
                                                                <span className={`px-3 py-1 text-[9px] font-black rounded-full border uppercase tracking-widest ${statusMeta.className}`}>
                                                                    {statusMeta.label}
                                                                </span>
                                                            </td>
                                                            <td className="px-10 py-6 text-right space-y-3">
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
                                    <div className="px-10 py-6 border-b border-white/5 bg-black/20"><h3 className="text-[9px] font-black text-gray-500 uppercase tracking-[0.4em]">?쒖꽦 ?좎? 梨꾨꼸 ?붿빟</h3></div>
                                    <table className="w-full text-left">
                                        <thead className="bg-black/30 border-b border-white/5 text-[10px] font-black text-gray-500 uppercase tracking-widest">
                                            <tr><th className="px-10 py-6">Channel / Account</th><th className="px-10 py-6 text-center">Generated Videos</th><th className="px-10 py-6 text-center">Last Active</th><th className="px-10 py-6 text-right">Status</th></tr>
                                        </thead>
                                        <tbody className="divide-y divide-white/5">
                                            {users.slice(0, 5).map(u => {
                                                const userVideos = globalLogs.filter(l => l.user_id === u.id && (l.task_type || '').toLowerCase() === 'video').length;
                                                return (
                                                    <tr key={u.id} className="hover:bg-white/[0.03] transition-colors group">
                                                        <td className="px-10 py-6"><div className="font-black text-white text-base group-hover:text-blue-400 transition-colors uppercase tracking-tight">{u.email}</div><div className="text-[11px] text-gray-600 font-bold mt-1 uppercase italic tracking-tighter">{u.user_metadata?.full_name || '?곕룞??梨꾨꼸 ?놁쓬'}</div></td>
                                                        <td className="px-10 py-6 text-center font-black text-white text-xl tabular-nums">{userVideos}</td>
                                                        <td className="px-10 py-6 text-center text-[12px] font-black text-gray-500">{formatDate(u.last_sign_in_at)}</td>
                                                        <td className="px-10 py-6 text-right"><span className="px-3 py-1 bg-green-500/10 text-green-500 text-[9px] font-black rounded-full border border-green-500/20 uppercase">?뺤긽 ?곌껐</span></td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        ) : renderLogTable(globalLogs)}
                    </div>
                )}

                
                {activeTab === 'withdrawals' && (
                    <div className="bg-[#0f172a]/20 border border-white/5 rounded-[3rem] overflow-hidden shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <div className="px-10 py-6 border-b border-white/5 bg-black/20 flex justify-between items-center">
                            <h3 className="text-sm font-black text-gray-400 uppercase tracking-[0.2em]">Withdrawal Requests</h3>
                            <button onClick={fetchWithdrawals} className="px-6 py-2 bg-blue-600/10 hover:bg-blue-600 text-blue-500 hover:text-white text-[10px] font-black rounded-xl border border-blue-500/20 transition-all uppercase tracking-widest">?덈줈怨좎묠</button>
                        </div>
                        <table className="w-full text-left">
                            <thead className="bg-black/30 border-b border-white/20 text-xs font-black text-gray-400 uppercase tracking-widest">
                                <tr>
                                    <th className="px-4 py-4 whitespace-nowrap">Requested At</th>
                                    <th className="px-4 py-4 whitespace-nowrap">Email</th>
                                    <th className="px-4 py-4 whitespace-nowrap">Wallet Address</th>
                                    <th className="px-4 py-4 text-right whitespace-nowrap">Amount (USDT)</th>
                                    <th className="px-4 py-4 text-center whitespace-nowrap">Status</th>
                                    <th className="px-4 py-4 text-center whitespace-nowrap">?≪뀡</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-white/20">
                                {withdrawals.map(w => (
                                    <tr key={w.id} className="hover:bg-white/[0.03] transition-colors group">
                                        <td className="px-4 py-4 text-xs text-gray-400">{new Date(w.created_at).toLocaleString()}</td>
                                        <td className="px-4 py-4 text-sm font-bold text-blue-400">{users.find(u => u.id === w.user_id)?.email || 'N/A'}</td>
                                        <td className="px-4 py-4 text-xs font-mono text-gray-300 max-w-[200px] truncate">{w.dest_address}</td>
                                        <td className="px-4 py-4 text-right text-sm font-black text-green-400">{w.amount} USDT</td>
                                        <td className="px-4 py-4 text-center">
                                            {w.status === 'pending' && <span className="px-2 py-1 bg-yellow-500/20 text-yellow-400 rounded-lg text-xs font-bold">?湲곗쨷</span>}
                                            {w.status === 'completed' && <span className="px-2 py-1 bg-green-500/20 text-green-400 rounded-lg text-xs font-bold">?꾨즺</span>}
                                            {w.status === 'rejected' && <span className="px-2 py-1 bg-red-500/20 text-red-400 rounded-lg text-xs font-bold">嫄곗젅</span>}
                                        </td>
                                        <td className="px-4 py-4 text-center">
                                            {w.status === 'pending' && (
                                                <div className="flex justify-center gap-2">
                                                    <button onClick={() => updateWithdrawalStatus(w.id, 'completed')} className="px-3 py-1 bg-green-600 hover:bg-green-500 text-white text-[10px] font-bold rounded-lg transition-colors">?뱀씤?꾨즺</button>
                                                    <button onClick={() => updateWithdrawalStatus(w.id, 'rejected')} className="px-3 py-1 bg-red-600/50 hover:bg-red-500 text-white text-[10px] font-bold rounded-lg transition-colors">嫄곗젅</button>
                                                </div>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                                {withdrawals.length === 0 && (
                                    <tr>
                                        <td colSpan={6} className="px-4 py-8 text-center text-gray-500 text-sm font-bold">異쒓툑 ?좎껌 ?댁뿭???놁뒿?덈떎.</td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                )}

                {activeTab === 'users' && (
                    <div className="bg-[#0f172a]/20 border border-white/5 rounded-[3rem] overflow-hidden shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <div className="px-10 py-6 border-b border-white/5 bg-black/20 flex justify-between items-center">
                            <h3 className="text-sm font-black text-gray-400 uppercase tracking-[0.2em]">User Management</h3>
                            <button onClick={fetchUsers} className="px-6 py-2 bg-blue-600/10 hover:bg-blue-600 text-blue-500 hover:text-white text-[10px] font-black rounded-xl border border-blue-500/20 transition-all uppercase tracking-widest">?덈줈怨좎묠</button>
                        </div>
                        <table className="w-full text-left">
                            <thead className="bg-black/30 border-b border-white/20 text-xs font-black text-gray-400 uppercase tracking-widest">
                                <tr>
                                    <th className="px-0 py-4 whitespace-nowrap">?대쫫</th>
                                    <th className="px-0 py-4 whitespace-nowrap">?대찓??/ ?깃툒</th>
                                    <th className="px-0 py-4 whitespace-nowrap">Contact</th>
                                    <th className="px-0 py-4 whitespace-nowrap">援?쟻</th>
                                    <th className="px-0 py-4 whitespace-nowrap">Referrer</th>
                                    <th className="px-0 py-4 whitespace-nowrap">Channel</th>
                                    <th className="px-0 py-4 text-center whitespace-nowrap">?좏겙</th>
                                    <th className="px-0 py-4 text-center whitespace-nowrap">Membership</th>
                                    <th className="px-0 py-4 text-center whitespace-nowrap">媛?낆씪</th>
                                    <th className="px-0 py-4 text-center whitespace-nowrap">理쒓렐?묒냽</th>
                                    <th className="px-0 py-4 text-center whitespace-nowrap">USDT ?붿븸</th>
                                    <th className="px-0 py-4 text-center whitespace-nowrap">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-white/20">
                                {users.map(u => (
                                    <tr key={u.id} className="hover:bg-white/[0.03] transition-colors group">
                                        {/* ??已?*/}
                                        <td className="px-1 py-4">
                                            <div className="font-black text-white text-xs whitespace-nowrap">{u.user_metadata?.full_name || <span className="text-gray-600 italic">??곸벉</span>}</div>
                                        </td>
                                        {/* ??李??/ ?온?귐딆쁽 ?源껎닋 */}
                                        <td className="px-1 py-4 max-w-[160px]">
                                            <div className="font-bold text-blue-400 text-[10px] tracking-tight truncate">{u.email?.toLowerCase()}</div>
                                            <div className="flex gap-1 mt-0.5 flex-wrap">
                                                {u.email === SUPER_ADMIN_EMAIL && <span className="px-1 py-0.5 bg-blue-600 text-[7px] font-black rounded text-white">筌ㅼ뮄?ф꽴??귐딆쁽</span>}
                                                {u.app_metadata?.is_admin && u.email !== SUPER_ADMIN_EMAIL && <span className="px-1 py-0.5 bg-indigo-500 text-[7px] font-black rounded text-white">?봔?온?귐딆쁽</span>}
                                                <span className={`px-1 py-0.5 text-[7px] font-black rounded border ${u.profile?.is_approved ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20'}`}>
                                                    {u.profile?.is_approved ? 'Approved' : 'Pending Approval'}
                                                </span>
                                            </div>
                                        </td>
                                        {/* ?怨뺤뵭筌?*/}
                                        <td className="px-1 py-4 text-[10px] text-gray-300 font-bold whitespace-nowrap">
                                            {u.user_metadata?.contact || <span className="text-gray-700">-</span>}
                                        </td>
                                        {/* ????*/}
                                        <td className="px-1 py-4 text-[10px] text-gray-300 font-bold whitespace-nowrap">
                                            {u.user_metadata?.nationality || <span className="text-gray-700">-</span>}
                                        </td>
                                        {/* ?곕뗄荑??*/}
                                        <td className="px-1 py-4 text-[10px] whitespace-nowrap">
                                            {u.user_metadata?.referrer
                                                ? <span className="text-yellow-400 font-bold">{u.user_metadata.referrer}</span>
                                                : <span className="text-gray-700">-</span>}
                                        </td>
                                        {/* 筌?쑬瑗몌쭗?*/}
                                        <td className="px-1 py-4 max-w-[110px]">
                                            {u.user_metadata?.youtube_channel
                                                ? <span className="flex items-center gap-1 text-red-400 text-[10px] font-black truncate"><span className="w-1.5 h-1.5 bg-red-500 rounded-full animate-pulse shrink-0 inline-block"></span>{u.user_metadata.youtube_channel}</span>
                                                : <span className="text-gray-700 text-xs">-</span>}
                                        </td>
                                        {/* 癰귣똻? ?醫뤾쿃 */}
                                        <td className="px-1 py-4 text-center font-black text-white text-sm tabular-nums whitespace-nowrap">
                                            {u.profile?.token_balance?.toLocaleString() || 0}
                                        </td>
                                        {/* 筌롢끇苡??*/}
                                        <td className="px-1 py-4 text-center">
                                            <button onClick={() => handleRoleChange(u.id, u.app_metadata?.membership)} className={`px-2 py-1 rounded-lg text-[8px] font-black border uppercase tracking-widest transition-all whitespace-nowrap ${u.app_metadata?.membership === 'pro' ? 'bg-indigo-600 text-white border-indigo-500 shadow-lg' : 'bg-white/5 text-gray-500 border-white/10 hover:border-white/30'}`}>
                                                {u.app_metadata?.membership?.toUpperCase() === 'PRO' ? 'PRO' : '?ㅽ깲?ㅻ뱶'}
                                            </button>
                                        </td>
                                        {/* 揶쎛??놁뵬 */}
                                        <td className="px-1 py-4 text-center text-[10px] font-bold text-gray-500 whitespace-nowrap">{formatDate(u.created_at)}</td>
                                        {/* 筌ㅼ뮄??臾믩꺗 */}
                                        <td className="px-1 py-4 text-center text-[10px] font-bold text-gray-500 whitespace-nowrap">{formatDate(u.last_sign_in_at)}</td>
                                        <td className="px-1 py-4 text-center font-black text-emerald-300 text-sm tabular-nums whitespace-nowrap">
                                            {Number(u.profile?.usdt_balance || 0).toLocaleString()}
                                        </td>
                                        {/* ?온??筌롫뗀????3x2 域밸챶???*/}
                                        <td className="px-1 py-4">
                                            <div className="grid grid-cols-3 gap-1">
                                                {isSuperAdmin && u.email !== SUPER_ADMIN_EMAIL
                                                    ? <button onClick={() => handleAdminRoleToggle(u.id, !!u.app_metadata?.is_admin)} className={`px-1.5 py-1 rounded text-[7px] font-black border transition-all whitespace-nowrap ${u.app_metadata?.is_admin ? 'bg-indigo-600/20 text-indigo-400 border-indigo-500/30' : 'bg-white/5 text-gray-600 border-white/10'}`}>Admin Role</button>
                                                    : <span />
                                                }
                                                <button onClick={() => handleApprovalChange(u.id, !u.profile?.is_approved)} className={`px-1.5 py-1 text-[7px] font-black rounded border transition-all whitespace-nowrap ${u.profile?.is_approved ? 'bg-yellow-600/10 hover:bg-yellow-600 text-yellow-500 hover:text-white border-yellow-500/20' : 'bg-emerald-600/10 hover:bg-emerald-600 text-emerald-400 hover:text-white border-emerald-500/20'}`}>
                                                    {u.profile?.is_approved ? 'Pending Approval' : 'Approve'}
                                                </button>
                                                <button onClick={() => handleRecharge(u.id)} className="px-1.5 py-1 bg-green-600/10 hover:bg-green-600 text-green-500 hover:text-white text-[7px] font-black rounded border border-green-500/20 transition-all whitespace-nowrap">?좏겙異⑹쟾</button>
                                                <button onClick={() => { setEditInfoUser(u); setEditInfoForm({ full_name: u.user_metadata?.full_name || '', nationality: u.user_metadata?.nationality || '', contact: u.user_metadata?.contact || '', persona_name: u.profile?.persona_name || '', persona_style: u.profile?.persona_style || '', persona_description: u.profile?.persona_description || '' }); }} className="px-1.5 py-1 bg-yellow-600/10 hover:bg-yellow-600 text-yellow-500 hover:text-white text-[7px] font-black rounded border border-yellow-500/20 transition-all whitespace-nowrap">?뺣낫?섏젙</button>
                                                <button onClick={() => { setLogViewUser(u); setLogPeriod(1); fetchUserLogs(u.id, 1); }} className="px-1.5 py-1 bg-blue-600/10 hover:bg-blue-600 text-blue-500 hover:text-white text-[7px] font-black rounded border border-blue-500/20 transition-all whitespace-nowrap">濡쒓렇議고쉶</button>
                                                <button onClick={() => { setChannelViewUser(u); setTempChannelInfo({ name: u.user_metadata?.youtube_channel || '', id: u.user_metadata?.youtube_channel_id || '', proxy: u.user_metadata?.youtube_channel_proxy || '' }); }} className="px-1.5 py-1 bg-purple-600/10 hover:bg-purple-600 text-purple-500 hover:text-white text-[7px] font-black rounded border border-purple-500/20 transition-all whitespace-nowrap">梨꾨꼸ID</button>
                                                <button onClick={() => { setApiViewUser(u); setTempApiKeys(u.app_metadata?.custom_api_keys || { openai: '', gemini: '', pexels: '', replicate: '' }); }} className="px-1.5 py-1 bg-indigo-600/10 hover:bg-indigo-600 text-indigo-500 hover:text-white text-[7px] font-black rounded border border-indigo-500/20 transition-all whitespace-nowrap">API</button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {activeTab === 'api' && (
                    <div className="bg-[#0f172a]/20 border border-white/5 rounded-[3rem] overflow-hidden shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-500 max-w-7xl mx-auto">
                        <div className="px-10 py-6 border-b border-white/5 bg-black/20">
                            <h3 className="text-sm font-black text-gray-400 uppercase tracking-[0.2em]">System API Keys</h3>
                            <p className="text-[10px] text-gray-600 mt-1">?쒕쾭 怨듭슜 ?ㅻ뒗 媛쒖씤 ?ㅺ? ?녿뒗 ?좎??먭쾶 ?곸슜?⑸땲??</p>
                        </div>
                        <div className="p-10 space-y-6">
                            <div className="grid grid-cols-1 xl:grid-cols-2 gap-8 items-start">
                                <div className="space-y-6">
                            <div>
                                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">Music Generation Provider</label>
                                <select
                                    value={sysKeys.music_provider}
                                    onChange={e => setSysKeys(prev => ({ ...prev, music_provider: e.target.value }))}
                                    className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 text-gray-300 cursor-pointer"
                                >
                                    <option value="elevenlabs" className="bg-[#111]">ElevenLabs (Default)</option>
                                    <option value="suno" className="bg-[#111]">Suno API</option>
                                    <option value="gemini" className="bg-[#111]">Gemini / Lyria</option>
                                </select>
                            </div>
                            {([
                                { key: 'gemini', label: '??Gemini API Key' },
                                { key: 'youtube', label: '??고닔 YouTube Data API Key' },
                                { key: 'elevenlabs', label: '??뷸닼?ElevenLabs API Key' },
                                { key: 'topview', label: '???TopView API Key' },
                                { key: 'topview_uid', label: '???TopView UID' },
                            ] as { key: keyof typeof sysKeys; label: string }[]).map(({ key, label }) => (
                                <div key={key}>
                                    <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">{label}</label>
                                    <input
                                        type="password"
                                        value={sysKeys[key] as string}
                                        onChange={e => setSysKeys(prev => ({ ...prev, [key]: e.target.value }))}
                                        onFocus={e => (e.target as HTMLInputElement).type = 'text'}
                                        onBlur={e => (e.target as HTMLInputElement).type = 'password'}
                                        placeholder={sysKeys[key] ? '************' : '(誘몄꽕??'}
                                        className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-gray-300 placeholder:text-gray-700"
                                    />
                                </div>
                            ))}
                            <div>
                                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">Suno API Key</label>
                                <input
                                    type="password"
                                    value={sysKeys.suno}
                                    onChange={e => setSysKeys(prev => ({ ...prev, suno: e.target.value }))}
                                    onFocus={e => (e.target as HTMLInputElement).type = 'text'}
                                    onBlur={e => (e.target as HTMLInputElement).type = 'password'}
                                    placeholder={sysKeys.suno ? '************' : '(not set)'}
                                    className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-gray-300 placeholder:text-gray-700"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">Suno API Base URL</label>
                                <input
                                    type="text"
                                    value={sysKeys.suno_base_url}
                                    onChange={e => setSysKeys(prev => ({ ...prev, suno_base_url: e.target.value }))}
                                    placeholder="https://your-suno-provider.example.com/api/generate"
                                    className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-gray-300 placeholder:text-gray-700"
                                />
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 rounded-2xl border border-white/10 bg-black/20 p-4">
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

                            {/* Google Drive Queue Configuration section */}
                            <div className="space-y-4 xl:border-l xl:border-white/10 xl:pl-8">
                                <h4 className="text-xs font-black text-blue-400 uppercase tracking-widest mb-2">Google Drive ?뚮뜑 ?湲곗뿴 ?ㅼ젙</h4>
                                
                                <div className="flex items-center gap-3 bg-white/[0.02] p-4 rounded-xl border border-white/5">
                                    <input 
                                        type="checkbox" 
                                        id="use_external_render" 
                                        checked={sysKeys.use_external_render} 
                                        onChange={e => setSysKeys(prev => ({ ...prev, use_external_render: e.target.checked }))}
                                        className="w-4 h-4 rounded text-blue-500 bg-black border-white/10 cursor-pointer"
                                    />
                                    <div className="text-xs">
                                        <label htmlFor="use_external_render" className="font-bold text-gray-300 cursor-pointer">?몃? ?뚮뜑 ?湲곗뿴 ?ъ슜 (Google Drive File Stream ?곕룞)</label>
                                        <p className="text-[10px] text-gray-500 mt-0.5">?쒖꽦?뷀븯硫??앹꽦 ?④퀎? 鍮꾨뵒???뚮뜑 ?뚯씪???꾨옒 ?ㅼ젙??援ш? ?쒕씪?대툕 寃쎈줈濡??숆린?붾맗?덈떎.</p>
                                    </div>
                                </div>

                                <div className="space-y-4">
                                    <div>
                                        <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">?곗꽑 ?곸슜 ?몄뼱 寃쎈줈 (?쒖꽦 ?ㅼ젙)</label>
                                        <select 
                                            value={sysKeys.drive_active_lang}
                                            onChange={e => setSysKeys(prev => ({ ...prev, drive_active_lang: e.target.value }))}
                                            className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 text-gray-300 cursor-pointer"
                                        >
                                            <option value="ko" className="bg-[#111]">?쒓뎅??(Korean OS 寃쎈줈 ?곸슜)</option>
                                            <option value="en" className="bg-[#111]">?곸뼱 (English OS 寃쎈줈 ?곸슜)</option>
                                            <option value="ja" className="bg-[#111]">?쇰낯??(Japanese OS 寃쎈줈 ?곸슜)</option>
                                        </select>
                                    </div>

                                    <div>
                                        <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">?쒓뎅??Windows 寃쎈줈 (DRIVE_PATH_KO)</label>
                                        <input 
                                            type="text" 
                                            value={sysKeys.drive_path_ko} 
                                            onChange={e => setSysKeys(prev => ({ ...prev, drive_path_ko: e.target.value }))}
                                            placeholder="G:/???쒕씪?대툕/Longform_Render_Queue"
                                            className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-gray-300"
                                        />
                                    </div>

                                    <div>
                                        <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">?곸뼱 Windows 寃쎈줈 (DRIVE_PATH_EN)</label>
                                        <input 
                                            type="text" 
                                            value={sysKeys.drive_path_en} 
                                            onChange={e => setSysKeys(prev => ({ ...prev, drive_path_en: e.target.value }))}
                                            placeholder="G:/My Drive/Longform_Render_Queue"
                                            className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-gray-300"
                                        />
                                    </div>

                                    <div>
                                        <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">?쇰낯??Windows 寃쎈줈 (DRIVE_PATH_JA)</label>
                                        <input 
                                            type="text" 
                                            value={sysKeys.drive_path_ja} 
                                            onChange={e => setSysKeys(prev => ({ ...prev, drive_path_ja: e.target.value }))}
                                            placeholder="G:/??곴텕??κ???녠묍/Longform_Render_Queue"
                                            className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-gray-300"
                                        />
                                    </div>
                                </div>
                            </div>
                            </div>

                            <div className="space-y-2">
                                <label className="text-[10px] font-black text-blue-300 uppercase tracking-widest block">Google Drive API Folder ID</label>
                                <input
                                    type="text"
                                    value={sysKeys.remote_render_drive_folder_id}
                                    onChange={e => setSysKeys(prev => ({ ...prev, remote_render_drive_folder_id: e.target.value }))}
                                    placeholder="Drive folder ID for remote render asset ZIPs"
                                    className="w-full bg-black/40 border border-blue-500/20 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-gray-300"
                                />
                                <p className="text-[10px] text-gray-500">API 諛⑹떇?쇰줈 ?뚮뜑 ?湲곗뿴?먯꽌 ?앹꽦??ZIP???낅줈?쒗븷 Drive ?대뜑 ID?낅땲??</p>
                            </div>

                            <div className="space-y-2">
                                <label className="text-[10px] font-black text-blue-300 uppercase tracking-widest block">Google OAuth Token Path</label>
                                <input
                                    type="text"
                                    value={sysKeys.remote_render_google_token_path}
                                    onChange={e => setSysKeys(prev => ({ ...prev, remote_render_google_token_path: e.target.value }))}
                                    placeholder="C:/path/to/token.json"
                                    className="w-full bg-black/40 border border-blue-500/20 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-gray-300"
                                />
                                <p className="text-[10px] text-gray-500">硫붿씤 PC???먭꺽 利앸챸 ?뚯씪濡?Drive API ?몄쬆???ъ슜?⑸땲?? OAuth ?좏겙 ?뚯씪 寃쎈줈?낅땲??</p>
                            </div>

                            {sysKeysSaved && <p className="text-xs text-green-400 font-bold text-center">????꾨즺</p>}

                            <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-5 space-y-4">
                                <div>
                                    <h4 className="text-xs font-black text-emerald-300 uppercase tracking-widest">Longform Work Policy</h4>
                                    <p className="text-[10px] text-gray-500 mt-1">濡깊뤌 吏곸썝 ?묒뾽?쒓컙 ?좉툑怨??덉긽 ?섎떦 怨꾩궛 湲곗??낅땲??</p>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                    <div>
                                        <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">理쒖냼 ?곸긽 湲몄씠(遺?</label>
                                        <input
                                            type="number"
                                            min="15"
                                            value={sysKeys.longform_min_duration_minutes}
                                            onChange={e => setSysKeys(prev => ({ ...prev, longform_min_duration_minutes: e.target.value }))}
                                            className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/50 text-gray-300"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">湲곕낯 ?섎떦</label>
                                        <input
                                            type="number"
                                            min="0"
                                            value={sysKeys.longform_base_payout}
                                            onChange={e => setSysKeys(prev => ({ ...prev, longform_base_payout: e.target.value }))}
                                            className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/50 text-gray-300"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">異붽? 1遺꾨떦 ?섎떦</label>
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
                                    濡깊뤌 諛곗젙?쒓컙??吏곸썝 ?붾㈃?먯꽌 ?섏젙 遺덇?濡?怨좎젙
                                </label>
                            </div>

                            <button
                                onClick={saveSysKeys}
                                disabled={sysKeysSaving}
                                className="w-full py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white font-black rounded-2xl transition-all text-sm mt-4"
                            >
                                {sysKeysSaving ? 'Saving...' : 'Save changes'}
                            </button>
                        </div>
                    </div>
                )}
                {activeTab === 'render-queue' && (
                    <div className="bg-[#0f172a]/20 border border-white/5 rounded-[3rem] overflow-hidden shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <div className="px-10 py-6 border-b border-white/5 bg-black/20 flex justify-between items-center">
                            <div>
                                <h3 className="text-sm font-black text-gray-400 uppercase tracking-[0.2em]">Remote Render Queue</h3>
                                <p className="text-[10px] text-gray-600 mt-1">GPU ?쒕쾭???ㅼ떆媛?鍮꾨뵒???뚮뜑 ?湲?諛?吏꾪뻾 ?곹깭瑜?紐⑤땲?곕쭅?⑸땲??</p>
                            </div>
                            <button onClick={fetchRenderQueue} className="px-6 py-2 bg-blue-600/10 hover:bg-blue-600 text-blue-500 hover:text-white text-[10px] font-black rounded-xl border border-blue-500/20 transition-all uppercase tracking-widest">?덈줈怨좎묠</button>
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
                                <div className="text-center text-xs text-gray-500 py-10">?湲곗뿴 議고쉶 以?..</div>
                            ) : renderQueue.length === 0 ? (
                                <div className="text-center text-xs text-gray-500 py-10">?꾩옱 ?湲??먮뒗 ?ㅽ뻾 以묒씤 ?뚮뜑留??묒뾽???놁뒿?덈떎.</div>
                            ) : (
                                <div className="overflow-x-auto">
                                    <table className="w-full text-left">
                                        <thead className="bg-black/30 border-b border-white/20 text-xs font-black text-gray-400 uppercase tracking-widest">
                                            <tr>
                                                <th className="px-4 py-4">Created</th>
                                                <th className="px-4 py-4">User</th>
                                                <th className="px-4 py-4">?꾨줈?앺듃</th>
                                                <th className="px-4 py-4">吏꾪뻾 ?곹깭</th>
                                                <th className="px-4 py-4 text-center">Progress</th>
                                                <th className="px-4 py-4">硫붿떆吏</th>
                                                <th className="px-4 py-4 text-center">Actions</th>
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
                                                            {task.status === 'pending' ? '?湲곗쨷' : task.status === 'rendering' ? '?뚮뜑留곸쨷' : task.status === 'completed' ? '?꾨즺' : '?ㅽ뙣'}
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
                                                        <button onClick={() => handleDeleteQueueTask(task.id)} className="px-3 py-1.5 bg-red-600/10 hover:bg-red-600 text-red-500 hover:text-white rounded-lg border border-red-500/20 hover:border-red-600 transition-all font-black text-[10px]">Delete</button>
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
                {activeTab === 'styles' && (
                    <div className="space-y-8 animate-in fade-in duration-300">
                        {/* 1. ?ㅽ???異붽?/?섏젙 */}
                        <div ref={presetFormRef} className={`rounded-[2.5rem] border p-8 shadow-2xl scroll-mt-24 transition-all duration-300 ${presetId ? 'bg-blue-950/40 border-blue-500/40' : 'bg-[#0f172a]/60 border-white/10'}`}>
                            <h2 className="font-black text-xl tracking-tight mb-6 flex items-center gap-2">
                                ?ㅽ????꾨━??{presetId ? '?섏젙' : '異붽?'}
                            </h2>
                            <form onSubmit={handleSavePreset} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">?ㅽ??????*</label>
                                    <select
                                        required
                                        value={presetType}
                                        onChange={e => setPresetType(e.target.value as any)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50 cursor-pointer"
                                    >
                                        <option value="image">?대?吏 ?ㅽ???(Image Style)</option>
                                        <option value="script">?蹂??ㅽ???(Script Style)</option>
                                        <option value="thumbnail">?몃꽕???ㅽ???(Thumbnail Style)</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">?ㅽ????곷Ц 肄붾뱶紐?* (?? realistic)</label>
                                    <input
                                        type="text"
                                        required
                                        placeholder="?곷Ц ?뚮Ц??諛??몃뜑諛?沅뚯옣"
                                        value={presetKeyCode}
                                        onChange={e => setPresetKeyCode(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">?ㅽ????쒓? ?쒖떆紐?*</label>
                                    <input
                                        type="text"
                                        required
                                        placeholder="?? ?ㅼ궗?곹솕"
                                        value={presetNameKo}
                                        onChange={e => setPresetNameKo(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">Style preset version</label>
                                    <input
                                        type="text"
                                        placeholder="?? Dien anh thuc te"
                                        value={presetNameVi}
                                        onChange={e => setPresetNameVi(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">?꾨━酉??몃꽕???대?吏 URL</label>
                                    <input
                                        type="text"
                                        placeholder="https://... ?먮뒗 /static/img/... (?좏깮?ы빆)"
                                        value={presetImageUrl}
                                        onChange={e => setPresetImageUrl(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div className="md:col-span-2 lg:col-span-3">
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">?꾨＼?꾪듃 ?쒗뵆由?*</label>
                                    <textarea
                                        required
                                        rows={4}
                                        placeholder="?ㅽ??쇱뿉 ?곸슜??二쇱슂 ?꾨＼?꾪듃 諛??섏떇?대? ?곸뼱二쇱꽭?? ?대?吏 ?ㅽ??쇱쓽 寃쎌슦 [SUBJECT] ?깆쓣 ?쒖슜?????덉뒿?덈떎."
                                        value={presetPromptTemplate}
                                        onChange={e => setPresetPromptTemplate(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-xs"
                                    />
                                </div>
                                <div className="md:col-span-2 lg:col-span-3">
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">AI 異붽? 吏?쒖궗??(Grounded Gemini Instruction - ?대?吏 ?ㅽ????곸슜)</label>
                                    <textarea
                                        rows={3}
                                        placeholder="?? ?덈? ?띿뒪?몃굹 留먰뭾?좎쓣 ?ｌ? 留덉꽭??"
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
                                            痍⑥냼
                                        </button>
                                    )}
                                    <button
                                        type="submit"
                                        disabled={isSavingPreset}
                                        className="px-8 py-3 rounded-xl text-xs font-black bg-blue-600 text-white shadow-lg flex items-center gap-1.5 disabled:opacity-50 hover:bg-blue-500 transition-all"
                                    >
                                        {isSavingPreset ? 'Saving...' : 'Save preset'}
                                    </button>
                                </div>
                            </form>
                        </div>

                        {/* 2. ?ㅽ????꾨━??由ъ뒪??*/}
                        <div className="bg-[#0f172a]/60 rounded-[2.5rem] border border-white/10 overflow-hidden shadow-2xl">
                            <div className="p-8 border-b border-white/5 bg-white/5 flex justify-between items-center">
                                <h2 className="font-black text-xl tracking-tight uppercase">?ㅽ????쒗뵆由?移댄깉濡쒓렇 紐⑸줉</h2>
                                <button
                                    onClick={fetchStylePresets}
                                    className="px-4 py-2 bg-white/5 hover:bg-white/10 rounded-xl text-xs font-bold transition-all flex items-center gap-2 border border-white/10"
                                >
                                    ?덈줈怨좎묠
                                </button>
                            </div>
                            <div className="p-6">
                                {presetsLoading ? (
                                    <div className="text-center text-xs text-gray-500 py-10">?꾨━??濡쒕뵫 以?..</div>
                                ) : (
                                    <div className="grid grid-cols-1 gap-8">
                                        {['image', 'script', 'thumbnail'].map(type => {
                                            const typePresets = stylePresets.filter((p: any) => p.preset_type === type);
                                            const typeLabel = type === 'image' ? 'Image style' : type === 'script' ? 'Script style' : 'Thumbnail style';
                                            return (
                                                <div key={type} className="border border-white/5 rounded-2xl p-6 bg-black/20">
                                                    <h3 className="text-base font-bold text-gray-300 mb-4">
                                                        {typeLabel} ({typePresets.length})
                                                    </h3>
                                                    {typePresets.length === 0 ? (
                                                        <p className="text-xs text-gray-600 italic">?깅줉???ㅽ????꾨━?뗭씠 ?놁뒿?덈떎.</p>
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
                                                                                    title="?섏젙"
                                                                                >
                                                                                    ?섏젙
                                                                                </button>
                                                                                <button
                                                                                    onClick={() => handleDeletePreset(preset.id, preset.key_code)}
                                                                                    className="p-1 hover:bg-white/5 rounded text-red-500 text-xs"
                                                                                    title="??젣"
                                                                                >
                                                                                    ??젣
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

            {/* ??????類ｋ궖 筌욊낯????륁젟 筌뤴뫀??*/}
            {editInfoUser && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setEditInfoUser(null)}>
                    <div className="bg-[#0a0a0a] border border-white/10 rounded-2xl p-8 w-full max-w-md shadow-2xl" onClick={e => e.stopPropagation()}>
                        <div className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">??????類ｋ궖 ??륁젟</div>
                        <div className="text-white font-black text-lg mb-6">{editInfoUser.email?.toLowerCase()}</div>
                        <div className="flex flex-col gap-4">
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">Name</label>
                                <input value={editInfoForm.full_name} onChange={e => setEditInfoForm(p => ({ ...p, full_name: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-yellow-500/50" placeholder="??已???낆젾" />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">Country</label>
                                <input value={editInfoForm.nationality} onChange={e => setEditInfoForm(p => ({ ...p, nationality: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-yellow-500/50" placeholder="援?쟻 ?낅젰 (?? ?쒓뎅)" />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">Contact</label>
                                <input value={editInfoForm.contact} onChange={e => setEditInfoForm(p => ({ ...p, contact: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-yellow-500/50" placeholder="?곕씫泥??낅젰" />
                            </div>
                            <div className="border-t border-white/10 my-2 pt-2">
                                <div className="text-[10px] font-black text-blue-400 uppercase tracking-wider mb-2">?쨼 AI ?묎? ?섎Ⅴ?뚮굹 ?ㅼ젙</div>
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">?섎Ⅴ?뚮굹 ?대쫫</label>
                                <input value={editInfoForm.persona_name || ''} onChange={e => setEditInfoForm(p => ({ ...p, persona_name: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-yellow-500/50" placeholder="?? ? (?좊㉧ ?묎?)" />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">?묐Ц ?ㅽ????ㅼ썙??(?곸뼱 沅뚯옣)</label>
                                <input value={editInfoForm.persona_style || ''} onChange={e => setEditInfoForm(p => ({ ...p, persona_style: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-yellow-500/50" placeholder="?? humorous, witty, fast-paced" />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">?곸꽭 ?깊뼢 ?ㅻ챸 (?쒓? 媛??</label>
                                <textarea value={editInfoForm.persona_description || ''} onChange={e => setEditInfoForm(p => ({ ...p, persona_description: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-yellow-500/50 h-20 resize-none" placeholder="?? ?좊㉧?ъ뒪?섍퀬 ?좎풄???륂뤌 ?ㅽ????蹂??묎?" />
                            </div>
                        </div>
                        <div className="flex gap-3 mt-6">
                            <button onClick={handleSaveUserInfo} className="flex-1 py-3 bg-yellow-500 hover:bg-yellow-400 text-black text-[11px] font-black rounded-xl transition-all uppercase tracking-widest">Save</button>
                            <button onClick={() => setEditInfoUser(null)} className="px-6 py-3 bg-white/5 hover:bg-white/10 text-gray-400 text-[11px] font-black rounded-xl transition-all">痍⑥냼</button>
                        </div>
                    </div>
                </div>
            )}

            {logViewUser && (
                <div className="fixed inset-0 z-[200] flex items-center justify-center p-12 animate-in fade-in duration-300">
                    <div className="absolute inset-0 bg-black/95 backdrop-blur-3xl" onClick={() => setLogViewUser(null)} />
                    <div className="relative w-full max-w-[1600px] bg-[#000106] border border-white/10 rounded-[3rem] p-12 flex flex-col max-h-[94vh] overflow-hidden shadow-2xl">
                        <div className="flex justify-between items-center mb-10">
                             <div className="flex items-center gap-6"><h3 className="text-3xl font-black text-blue-500 uppercase italic tracking-tighter">Usage Logs</h3><div className="px-4 py-1.5 bg-blue-600/10 border border-blue-500/20 rounded-full text-[10px] font-black text-blue-400 uppercase tracking-widest">{logViewUser.email}</div></div>
                             <div className="flex items-center gap-4">
                                  <div className="flex gap-1 p-1 bg-white/5 rounded-xl border border-white/5">{[1, 7, 30].map(d => (
                                      <button key={d} onClick={() => { setLogPeriod(d); fetchUserLogs(logViewUser.id, d); }} className={`px-6 py-2 text-[10px] font-black rounded-lg transition-all ${logPeriod === d ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500 hover:text-white'}`}>{d === 1 ? 'Today' : d === 7 ? 'Weekly' : 'Monthly'}</button>
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
                                    <StatCard label="TOKEN USAGE" value={logStats.totalTokens.toLocaleString()} unit="TOKENS" color="orange" />
                                </div>
                                {renderDonutChart(logStats)}
                             </div>
                             {renderChartRow(logStats, userTopTasks)}
                             {renderLogTable(userLogs)}
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
                            <div><h3 className="text-3xl font-black uppercase italic tracking-tighter text-blue-500">?좎? ?꾩슜 API ?ㅼ젙</h3><p className="text-sm text-gray-500 mt-2 uppercase tracking-widest font-black italic">{apiViewUser.email}</p></div>
                            <div className="space-y-6">{['openai', 'gemini', 'pexels', 'replicate'].map(key => (
                                <div key={key} className="space-y-2">
                                    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest ml-4">{key.toUpperCase()} API Key</label>
                                    <input type="text" placeholder={`??낆젾??뤾쉭??..`} value={tempApiKeys[key] || ''} onChange={(e) => setTempApiKeys({...tempApiKeys, [key]: e.target.value})} className="w-full bg-black/40 border border-white/5 rounded-2xl px-8 py-5 text-sm font-black text-white focus:outline-none focus:border-blue-500/50 transition-all" />
                                </div>
                            ))}</div>
                            <button onClick={handleUpdateApiKeys} className="w-full py-6 bg-blue-600 hover:bg-blue-500 text-white font-black rounded-[2rem] shadow-xl shadow-blue-500/20 transition-all active:scale-95 uppercase tracking-widest text-sm">???諛??곸슜</button>
                        </div>
                    </div>
                </div>
            )}

            {channelViewUser && (
                <div className="fixed inset-0 z-[200] flex items-center justify-center p-12">
                    <div className="absolute inset-0 bg-black/90 backdrop-blur-3xl" onClick={() => setChannelViewUser(null)} />
                    <div className="relative w-full max-w-[800px] bg-[#000106] border border-white/10 rounded-[3rem] p-16 flex flex-col shadow-2xl animate-in zoom-in-95 duration-300">
                        <button onClick={() => setChannelViewUser(null)} className="absolute top-12 right-12 w-12 h-12 flex items-center justify-center rounded-xl bg-white/5 text-gray-500 hover:text-white transition-all">X</button>
                        <div className="space-y-10">
                            <div><h3 className="text-3xl font-black uppercase italic tracking-tighter text-purple-500">YouTube Channel Mapping</h3><p className="text-sm text-gray-500 mt-2 uppercase tracking-widest font-black italic">{channelViewUser.email}</p></div>
                            <div className="space-y-8">
                                <div className="space-y-2">
                                    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest ml-4">筌?쑬瑗???已?(??뽯뻻??</label>
                                    <input type="text" placeholder="?? ??깅춦?遺얄봺 ??쎈뮔?遺우궎" value={tempChannelInfo.name} onChange={(e) => setTempChannelInfo({...tempChannelInfo, name: e.target.value})} className="w-full bg-black/40 border border-white/5 rounded-2xl px-8 py-5 text-sm font-black text-white focus:outline-none focus:border-purple-500/50 transition-all" />
                                </div>
                                <div className="space-y-2">
                                    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest ml-4">?醫뤿뮔??筌?쑬瑗?ID</label>
                                    <input type="text" placeholder="?? UCxxxxxxxxxxxx" value={tempChannelInfo.id} onChange={(e) => setTempChannelInfo({...tempChannelInfo, id: e.target.value})} className="w-full bg-black/40 border border-white/5 rounded-2xl px-8 py-5 text-sm font-black text-white focus:outline-none focus:border-purple-500/50 transition-all" />
                                    
                                </div>
                                <div className="space-y-2">
                                    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest ml-4">??? ?怨좎돳???⑥쥙??IP ?袁⑥쨯??(?醫뤾문)</label>
                                    <input type="text" placeholder="?? http://username:password@ip:port" value={tempChannelInfo.proxy || ''} onChange={(e) => setTempChannelInfo({...tempChannelInfo, proxy: e.target.value})} className="w-full bg-black/40 border border-white/5 rounded-2xl px-8 py-5 text-sm font-black text-white focus:outline-none focus:border-purple-500/50 transition-all font-mono" />
                                    <p className="text-[9px] text-gray-600 ml-4 font-bold">* ????筌?쑬瑗??怨멸맒 ??낆쨮????筌왖?類λ립 ?袁⑥쨯??IP ??????野껋럩???뤿연 ??野???? ?紐꾪뀱 ?類ｌぇ???誘れ뿯??덈뼄.</p>
                                </div>
                            </div>
                            <div className="flex gap-4">
                                <button 
                                    onClick={handleUpdateChannelInfo} 
                                    disabled={savingChannel}
                                    className={`flex-1 py-6 font-black rounded-[2rem] shadow-xl transition-all active:scale-95 uppercase tracking-widest text-xs ${savingChannel ? 'bg-gray-800 text-gray-500 cursor-not-allowed' : 'bg-purple-600 hover:bg-purple-500 text-white'}`}
                                >
                                    {savingChannel ? (isKor ? 'Saving...' : 'Saving...') : (isKor ? 'Save text info' : 'Save Text Info')}
                                </button>
                                
                                <button 
                                    onClick={() => {
                                        if (!tempChannelInfo.name || !tempChannelInfo.id) {
                                            alert(isKor ? "梨꾨꼸 ?대쫫怨?ID瑜?紐⑤몢 ?낅젰?댁＜?몄슂." : "Please enter both channel name and ID.");
                                            return;
                                        }
                                        
                                        // window.open???????뤿연 CORS ?怨좎돳 獄?筌앸맦而?怨몄뵥 ??곕굡獄???볥궗
                                        const url = `http://127.0.0.1:8001/api/channels/login-by-info?name=${encodeURIComponent(tempChannelInfo.name)}&id=${encodeURIComponent(tempChannelInfo.id)}&proxy=${encodeURIComponent(tempChannelInfo.proxy || '')}`;
                                        window.open(url, '_blank', 'width=600,height=700');
                                        
                                        // 筌롫???怨쀬뵠???類ｋ궖 ???關? 癰귢쑬猷꾣에???묐뻬
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
                                    {isKor ? '援ш? ?곕룞?섍린' : 'Connect Google'}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* 燁삳똾?믤⑥쥓???類ｋ궖 ??륁젟 筌뤴뫀??*/}
            {editCategory && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setEditCategory(null)}>
                    <div className="bg-[#0a0a0a] border border-white/10 rounded-2xl p-8 w-full max-w-lg shadow-2xl" onClick={e => e.stopPropagation()}>
                        <div className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">移댄뀒怨좊━ ?섏젙</div>
                        <div className="text-white font-black text-lg mb-6">&quot;{editCategory.name}&quot; category settings</div>
                        <div className="flex flex-col gap-4 text-xs">
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">燁삳똾?믤⑥쥓?곻쭗?*</label>
                                <input 
                                    type="text"
                                    value={editCatForm.name} 
                                    onChange={e => setEditCatForm(p => ({ ...p, name: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50" 
                                    placeholder="燁삳똾?믤⑥쥓?곻쭗???낆젾" 
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">????筌욊낯????李??*</label>
                                <select
                                    value={editCatForm.assigned_employee_email}
                                    onChange={e => setEditCatForm(p => ({ ...p, assigned_employee_email: e.target.value }))}
                                    className="w-full bg-[#111] border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50 cursor-pointer"
                                >
                                    <option value="">-- 筌욊낯????醫뤾문??뤾쉭??--</option>
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
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">Main keywords</label>
                                <input 
                                    type="text"
                                    value={editCatForm.keywords} 
                                    onChange={e => setEditCatForm(p => ({ ...p, keywords: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50" 
                                    placeholder="??노ご嚥??닌됲뀋" 
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">甕겹끉?귨쭕?딄때???醫뤿뮔??筌?쑬瑗?URL</label>
                                <input 
                                    type="url"
                                    value={editCatForm.benchmark_channel_url} 
                                    onChange={e => setEditCatForm(p => ({ ...p, benchmark_channel_url: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50" 
                                    placeholder="Describe the channel or target audience" 
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">Default script style</label>
                                <select
                                    value={editCatForm.default_script_style}
                                    onChange={e => setEditCatForm(p => ({ ...p, default_script_style: e.target.value }))}
                                    className="w-full bg-[#111] border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50 cursor-pointer"
                                >
                                    <option value="default" className="bg-[#111] text-white">湲곕낯 ?ㅼ젙 (?먯뿰?ㅻ읇怨??좊챸???ㅽ???</option>
                                    <option value="story" className="bg-[#111] text-white">?덈궃 ?댁빞湲?(援ъ뿰 ?숉솕)</option>
                                    <option value="senior_story" className="bg-[#111] text-white">?쒕땲???댁빞湲?(?뚯긽/媛먯꽦)</option>
                                    <option value="news" className="bg-[#111] text-white">?댁뒪 (?뺣낫 ?꾨떖)</option>
                                    <option value="mystery_thriller" className="bg-[#111] text-white">誘몄뒪?곕━ ?ㅻ┫??(湲댁옣媛?</option>
                                    <option value="nursery_rhyme" className="bg-[#111] text-white">?대┛???숈슂 (洹?ъ슫 援ъ뿰)</option>
                                </select>
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">Default image style</label>
                                <select
                                    value={editCatForm.default_image_style}
                                    onChange={e => setEditCatForm(p => ({ ...p, default_image_style: e.target.value }))}
                                    className="w-full bg-[#111] border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50 cursor-pointer"
                                >
                                    <option value="realistic" className="bg-[#111] text-white">?ㅼ궗 (Photorealistic)</option>
                                    <option value="ghibli" className="bg-[#111] text-white">吏釉뚮━ 媛먯꽦 ?쇰윭?ㅽ듃 (Ghibli)</option>
                                    <option value="anime" className="bg-[#111] text-white">?좊땲硫붿씠?섑뭾 (Anime)</option>
                                    <option value="cinematic" className="bg-[#111] text-white">?곹솕 ?ㅽ???(Cinematic)</option>
                                    <option value="cartoon" className="bg-[#111] text-white">2D 移댄넠 ?ㅽ???(Cartoon)</option>
                                    <option value="nursery_rhyme" className="bg-[#111] text-white">3D ?숉솕/?좊땲 (Nursery/Pixar)</option>
                                    <option value="ink_wash" className="bg-[#111] text-white">?숈뼇 ?섎ぉ???ㅽ???(Ink Wash)</option>
                                </select>
                             </div>
                             <div>
                                 <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-2">?곸긽 ?뺤떇 (?꾩닔) *</label>
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
                                          <span>濡?뤌 (Longform)</span>
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
                                          <span>?쇱툩 (Shorts)</span>
                                     </label>
                                 </div>
                             </div>
                             <div className="rounded-xl border border-white/10 bg-white/5 px-4 py-3">
                                 <div className="flex items-center justify-between gap-3">
                                     <div>
                                         <div className="text-[10px] text-gray-500 font-black uppercase tracking-widest">Upload Channel</div>
                                         <div className="mt-1 text-sm font-black text-white">
                                             {editCatForm.upload_channel_name || editCatForm.upload_channel_handle || '?ㅼ젙 ?덈맖'}
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
                                         筌?쑬瑗???쇱젟
                                     </button>
                                 </div>
                             </div>
                        </div>
                        <div className="flex gap-3 mt-6">
                            <button onClick={handleSaveCategory} className="flex-1 py-3 bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-black rounded-xl transition-all uppercase tracking-widest">?섏젙?꾨즺</button>
                            <button onClick={() => setEditCategory(null)} className="px-6 py-3 bg-white/5 hover:bg-white/10 text-gray-400 text-[11px] font-black rounded-xl transition-all">Close</button>
                        </div>
                    </div>
                </div>
            )}

            {channelConfigCategory && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-[70] flex items-center justify-center p-4" onClick={() => setChannelConfigCategory(null)}>
                    <div className="bg-[#0a0a0a] border border-white/10 rounded-2xl p-8 w-full max-w-xl shadow-2xl" onClick={e => e.stopPropagation()}>
                        <div className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">?낅줈??梨꾨꼸 ?ㅼ젙</div>
                        <div className="text-white font-black text-lg mb-2">&quot;{channelConfigCategory.name}&quot; ?낅줈??梨꾨꼸 ?곌껐</div>
                        <p className="text-[12px] text-gray-500 mb-6">??移댄뀒怨좊━?먯꽌 ?앹꽦?섎뒗 ?곸긽? ?ш린?먯꽌 吏?뺥븳 梨꾨꼸濡쒕쭔 ?낅줈?쒕맗?덈떎.</p>

                        <div className="space-y-4 text-xs">
                            <div>
                                <div className="flex items-center justify-between mb-1.5">
                                    <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest">濡쒖뺄 梨꾨꼸 紐⑸줉</label>
                                    <button
                                        type="button"
                                        onClick={fetchLocalUploadChannels}
                                        className="text-[10px] font-black text-blue-400 hover:text-blue-300"
                                    >
                                        {localChannelsLoading ? '遺덈윭?ㅻ뒗 以?..' : '?덈줈怨좎묠'}
                                    </button>
                                </div>
                                <select
                                    value={channelConfigForm.local_channel_id ?? ''}
                                    onChange={e => applyLocalChannelToCategoryForm(e.target.value ? Number(e.target.value) : null)}
                                    className="w-full bg-[#111] border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50 cursor-pointer"
                                >
                                    <option value="">-- 濡쒖뺄 梨꾨꼸 ?좏깮 --</option>
                                    {localChannels.map(channel => (
                                        <option key={`config-local-channel-${channel.id}`} value={channel.id} className="bg-[#111] text-white">
                                            {channel.name} ({channel.handle}) {channel.credentials_path ? '[?곕룞?꾨즺]' : '[誘몄뿰??'}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                    <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">梨꾨꼸 ?대쫫</label>
                                <input
                                    type="text"
                                    value={channelConfigForm.name}
                                    onChange={e => setChannelConfigForm(prev => ({ ...prev, name: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50"
                                    placeholder="Enter channel ID or handle"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">?좏뒠釉?梨꾨꼸 ID ?먮뒗 ?몃뱾</label>
                                <input
                                    type="text"
                                    value={channelConfigForm.handle}
                                    onChange={e => setChannelConfigForm(prev => ({ ...prev, handle: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50"
                                    placeholder="?? UCxxxx ?먮뒗 @channelhandle"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">?꾨줉??(?좏깮)</label>
                                <input
                                    type="text"
                                    value={channelConfigForm.proxy}
                                    onChange={e => setChannelConfigForm(prev => ({ ...prev, proxy: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50"
                                    placeholder="?? socks5://127.0.0.1:1080"
                                />
                            </div>

                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                                <button type="button" onClick={handleCreateOrUpdateLocalChannel} className="py-3 bg-white/5 hover:bg-white/10 text-white text-[11px] font-black rounded-xl border border-white/10 transition-all">
                                    濡쒖뺄 梨꾨꼸 ???
                                </button>
                                <button type="button" onClick={handleStartCategoryChannelOAuth} className="py-3 bg-purple-600/15 hover:bg-purple-600 text-purple-300 hover:text-white text-[11px] font-black rounded-xl border border-purple-500/20 transition-all">
                                    Google OAuth ?怨뺣짗
                                </button>
                                <button type="button" onClick={handleSaveCategoryChannelBinding} className="py-3 bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-black rounded-xl transition-all">
                                    移댄뀒怨좊━?????
                                </button>
                            </div>

                            <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3 text-[11px] text-gray-400 leading-5">
                                1. Select an existing channel or create a new one.<br />
                                2. If needed, connect Google OAuth.<br />
                                3. Save the category binding to lock this category to that channel.
                            </div>
                        </div>

                        <div className="flex justify-end mt-6">
                            <button onClick={() => setChannelConfigCategory(null)} className="px-6 py-3 bg-white/5 hover:bg-white/10 text-gray-400 text-[11px] font-black rounded-xl transition-all">?リ린</button>
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

