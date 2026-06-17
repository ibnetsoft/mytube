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
        token_balance: number
    }
}

interface PublishingRequest {
    id: string
    user_id: string
    video_url: string
    status: 'pending' | 'to_be_published' | 'published' | 'failed' | 'rejected'
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
    'video': '?벞',
    'image': '?렓',
    'script': '?뱷',
    'text_gen': '?랃툘',
    'vision_gen': '?몓截?,
    'motion_guide': '?숋툘',
    'character_extraction': '?뫀',
    'test_after_fix': '?썱截?,
    'test_local': '?뮲',
    'test_verbose': '?뵇',
    'unknown': '??,
    'prompt': '?뮕'
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
    const [publishingFilter, setPublishingFilter] = useState<'all' | 'pending' | 'processing' | 'published' | 'failed' | 'invalid'>('all')
    const [activeTab, setActiveTab] = useState<'topics' | 'overview' | 'users' | 'api' | 'render-queue' | 'styles'>('topics')
    const [renderQueue, setRenderQueue] = useState<any[]>([])
    const [queueLoading, setQueueLoading] = useState(false)
    const [overviewSubTab, setOverviewSubTab] = useState<'video' | 'log'>('video')

    // 移댄뀒怨좊━ & AI 二쇱젣 ?먰뙋湲??곹깭
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
    const [topicQueueCategoryFilter, setTopicQueueCategoryFilter] = useState<string>('all')
    const [topicQueueStatusFilter, setTopicQueueStatusFilter] = useState<'working' | 'pending'>('working')
    const [topicQueueEmployeeFilter, setTopicQueueEmployeeFilter] = useState<string>('all')
    
    // 移댄뀒怨좊━ 由ъ뒪??濡깊뤌/?륂뤌 ??援щ텇
    const [categoryListTab, setCategoryListTab] = useState<'longform' | 'shorts'>('longform')

    // 移댄뀒怨좊━ ?섏젙 紐⑤떖 ?곹깭
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
    const [editInfoForm, setEditInfoForm] = useState({ full_name: '', nationality: '', contact: '' });
    
    // Data Stats State
    const [globalLogs, setGlobalLogs] = useState<any[]>([])
    const [userLogs, setUserLogs] = useState<any[]>([])
    const [logsLoading, setLogsLoading] = useState(false)
    const [logPeriod, setLogPeriod] = useState(1)
    const [logStats, setLogStats] = useState({ total: 0, successRate: 0, avgLatency: 0, totalTokens: 0, breakdown: {} as any })
    const [globalPeriod, setGlobalPeriod] = useState(1)
    const [globalStats, setGlobalStats] = useState({ total: 0, successRate: 0, avgLatency: 0, totalTokens: 0, breakdown: {} as any })
    const [globalLoading, setGlobalLoading] = useState(false)

    // ?쒖뒪???꾩뿭 API ??諛?援ш? ?쒕씪?대툕 ?ㅼ젙
    const [sysKeys, setSysKeys] = useState({ 
        gemini: '', youtube: '', elevenlabs: '', topview: '', topview_uid: '',
        use_external_render: false, drive_path_ko: '', drive_path_en: '', drive_path_ja: '', drive_active_lang: 'ko',
        remote_render_drive_folder_id: '',
        remote_render_google_token_path: ''
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
        const amountStr = prompt(isKor ? '異⑹쟾???좏겙?됱쓣 ?낅젰?섏꽭?? : 'Enter token amount to recharge', '50000');
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
                alert(isKor ? `異⑹쟾 ?꾨즺! ${parsedAmount.toLocaleString()} ?좏겙 異붽??? : `Recharge Success! +${parsedAmount.toLocaleString()} tokens`);
                // ?숆????낅뜲?댄듃 ??fetchUsers() ?ъ슜 ??Supabase 罹먯떆濡?stale 諛섑솚
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
                // [FIX] ?쒕쾭?먯꽌 諛섑솚??理쒖떊 ?좎? ?뺣낫濡?利됱떆 援먯껜?섏뿬 ?숆린??吏??諛⑹?
                const updatedUser = data.user;
                if (updatedUser) {
                    setUsers(prev => prev.map(u => u.id === updatedUser.id ? {
                        ...u,
                        user_metadata: updatedUser.user_metadata
                    } : u));
                }
                
                alert(isKor ? "梨꾨꼸 ?뺣낫媛 ?깃났?곸쑝濡??낅뜲?댄듃?섏뿀?듬땲??" : "Channel info updated successfully.");
                setChannelViewUser(null);
                // fetchUsers()瑜??몄텧?섏? ?딄퀬 濡쒖뺄 ?곹깭瑜??곗꽑?쒗븿 (Race Condition ?닿껐)
            } else {
                console.error('Save failed:', data.error);
                alert((isKor ? "????ㅽ뙣: " : "Save failed: ") + (data.error || "Unknown error"));
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
            alert((isKor ? '濡쒖뺄 梨꾨꼸 ????ㅽ뙣: ' : 'Failed to save local channel: ') + (lastError || 'Unknown error'))
            return
        }

        alert(isKor ? '濡쒖뺄 梨꾨꼸????λ릺?덉뒿?덈떎.' : 'Local channel saved.')
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
                alert((isKor ? '梨꾨꼸 ????ㅽ뙣: ' : 'Failed to save channel: ') + (data.error || `HTTP ${res.status}`))
                return
            }
            alert(isKor ? '移댄뀒怨좊━ ?낅줈??梨꾨꼸????λ릺?덉뒿?덈떎.' : 'Category upload channel saved.')
            setChannelConfigCategory(null)
            fetchCategories()
        } catch (err: any) {
            alert((isKor ? '梨꾨꼸 ????ㅻ쪟: ' : 'Failed to save channel: ') + (err?.message || String(err)))
        }
    }

    const handleRoleChange = async (userId: string, currentRole: string) => {
        const newRole = currentRole === 'pro' ? 'std' : 'pro';
        if (!confirm(isKor ? `?깃툒??${newRole === 'pro' ? '?꾨줈' : '?ㅽ깲?ㅻ뱶'}(??濡?蹂寃쏀븯?쒓쿋?듬땲源?` : `Change membership to ${newRole === 'pro' ? 'PRO' : 'STANDARD'}?`)) return;
        try {
            const res = await fetch('/api/admin/users/role', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId, membership: newRole })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                // ?숆????낅뜲?댄듃留??ъ슜 (fetchUsers ??Supabase 罹먯떆濡??명빐 ??뻾??
                setUsers(prev => prev.map(u =>
                    u.id === userId ? { ...u, app_metadata: { ...u.app_metadata, membership: newRole } } : u
                ));
                alert(isKor ? `${newRole === 'pro' ? '?뭿 ?꾨줈' : '?뫀 ?ㅽ깲?ㅻ뱶'}濡?蹂寃쎈릺?덉뒿?덈떎.` : 'Role Updated');
            } else {
                alert('蹂寃??ㅽ뙣: ' + (data.error || '?쒕쾭 ?ㅻ쪟'));
            }
        } catch (e) { alert('?쒕쾭 ?듭떊 ?ㅻ쪟'); }
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
                    }
                })
            });
            const data = await res.json();
            if (data.success) {
                setUsers(prev => prev.map(u => u.id === editInfoUser.id
                    ? { ...u, user_metadata: { ...u.user_metadata, ...editInfoForm } }
                    : u
                ));
                setEditInfoUser(null);
                alert('??λ릺?덉뒿?덈떎.');
            } else {
                alert('????ㅽ뙣: ' + (data.error || '?쒕쾭 ?ㅻ쪟'));
            }
        } catch (e) { alert('?쒕쾭 ?ㅻ쪟'); }
    };

    const handleAdminRoleToggle = async (userId: string, currentIsAdmin: boolean) => {
        if (!isSuperAdmin) return;
        const action = currentIsAdmin ? '?댁젣' : '吏??;
        if (!confirm(`?대떦 ?좎?瑜?遺愿由ъ옄濡?${action}?섏떆寃좎뒿?덇퉴?`)) return;
        try {
            const res = await fetch('/api/admin/users/admin-role', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId, isAdmin: !currentIsAdmin })
            });
            if (res.ok) { alert('?꾨즺?섏뿀?듬땲??'); fetchUsers(); }
        } catch (e) { alert('?ㅻ쪟媛 諛쒖깮?덉뒿?덈떎.'); }
    }

    const handlePublishVideo = async (requestId: string) => {
        if (!confirm(isKor ? '???곸긽???좏뒠釉뚯뿉??怨듦컻(Public)濡??꾪솚?섏떆寃좎뒿?덇퉴?' : 'Would you like to switch this video to Public on YouTube?')) return;
        try {
            const res = await fetch('/api/admin/publishing', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ requestId, status: 'to_be_published' })
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
                    {isKor ? '鍮좊Ⅸ 諛붾줈媛湲? : 'Quick Access'}
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
                    <div className="text-[10px] font-bold text-gray-600 text-left">{isKor ? '?곌껐???먯궛???놁뒿?덈떎.' : 'No linked assets'}</div>
                )}
            </div>
        )
    }

    const getPublishingStatusMeta = (req: PublishingRequest) => {
        if (req.metadata?.is_invalid_request) return { label: 'INVALID', className: 'bg-red-500/10 text-red-400 border-red-500/20' }
        if (req.status === 'published') return { label: isKor ? '?낅줈???꾨즺' : 'Published', className: 'bg-green-500/10 text-green-400 border-green-500/20' }
        if (req.status === 'to_be_published') return { label: isKor ? '?낅줈??吏꾪뻾 以? : 'Publishing', className: 'bg-blue-500/10 text-blue-400 border-blue-500/20' }
        if (req.status === 'failed') return { label: isKor ? '?낅줈???ㅽ뙣' : 'Failed', className: 'bg-red-500/10 text-red-400 border-red-500/20' }
        if (req.status === 'rejected') return { label: isKor ? '?쒖쇅?? : 'Rejected', className: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20' }
        return { label: isKor ? '?湲?以? : 'Pending', className: 'bg-orange-500/10 text-orange-400 border-orange-500/20' }
    }

    const publishingSummary = useMemo(() => {
        return publishingRequests.reduce((acc, req) => {
            acc.total += 1
            if (req.metadata?.is_invalid_request) acc.invalid += 1
            else if (req.status === 'published') acc.published += 1
            else if (req.status === 'to_be_published') acc.processing += 1
            else if (req.status === 'failed') acc.failed += 1
            else acc.pending += 1
            return acc
        }, { total: 0, pending: 0, processing: 0, published: 0, failed: 0, invalid: 0 })
    }, [publishingRequests])

    const filteredPublishingRequests = useMemo(() => {
        if (publishingFilter === 'all') return publishingRequests
        if (publishingFilter === 'invalid') return publishingRequests.filter(req => Boolean(req.metadata?.is_invalid_request))
        if (publishingFilter === 'processing') return publishingRequests.filter(req => req.status === 'to_be_published')
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
                topview: data.topview || '',
                topview_uid: data.topview_uid || '',
                use_external_render: data.use_external_render === 'true' || data.use_external_render === true,
                drive_path_ko: data.drive_path_ko || '',
                drive_path_en: data.drive_path_en || '',
                drive_path_ja: data.drive_path_ja || '',
                drive_active_lang: data.drive_active_lang || 'ko',
                remote_render_drive_folder_id: data.remote_render_drive_folder_id || '',
                remote_render_google_token_path: data.remote_render_google_token_path || ''
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
        if (!confirm(isKor ? '???묒뾽????쒕낫???湲곗뿴?먯꽌 ??젣?섏떆寃좎뒿?덇퉴?' : 'Delete this render task from the queue?')) return;
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
                alert('?ㅽ????꾨━?뗭씠 ??λ릺?덉뒿?덈떎.')
                setPresetId(null)
                setPresetKeyCode('')
                setPresetNameKo('')
                setPresetNameVi('')
                setPresetPromptTemplate('')
                setPresetGeminiInstruction('')
                setPresetImageUrl('')
                fetchStylePresets()
            } else {
                alert('????ㅽ뙣: ' + (data.error || '?????녿뒗 ?ㅻ쪟'))
            }
        } catch (e: any) {
            alert('????ㅻ쪟: ' + e.message)
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
        // ?쇱쑝濡??먮룞 ?ㅽ겕濡?
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
                alert('移댄뀒怨좊━媛 ?깃났?곸쑝濡??깅줉?섏뿀?쇰ŉ, 湲곕낯 ?섑뵆 二쇱젣 3媛쒓? ?곸옱?섏뿀?듬땲??')
            } else {
                alert('移댄뀒怨좊━ ?깅줉 ?ㅽ뙣: ' + data.error)
            }
        } catch (err) {
            console.error(err)
            alert('?쒕쾭 ?깅줉 ?먮윭 諛쒖깮')
        }
    }

    const handleDeleteCategory = async (id: number) => {
        if (!confirm('?뺣쭚 ??移댄뀒怨좊━瑜???젣?섏떆寃좎뒿?덇퉴? 愿???곗씠?곕룄 ?④퍡 ??젣?????덉뒿?덈떎.')) return
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
                alert(`AI媛 ?덈줈???몃? ?곸긽 二쇱젣 ${data.count}媛쒕? ?깃났?곸쑝濡??앹꽦?섏뿬 ?먯뿉 異붽??덉뒿?덈떎!`)
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

    useEffect(() => {
        if (activeTab === 'render-queue') {
            fetchRenderQueue();
            const interval = setInterval(fetchRenderQueue, 3000); // 3珥?媛꾧꺽 ?ㅼ떆媛?媛깆떊
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

    // 珥덇린 ?곗씠??濡쒕뵫???⑥씪 Effect
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

    // 湲곌컙 蹂寃??쒖뿉留?蹂꾨룄 ?몄텧
    useEffect(() => {
        if (isAdmin && !loading) {
            fetchGlobalStats(globalPeriod);
        }
    }, [globalPeriod]);

    if (loading) return <div className="min-h-screen bg-[#050505] text-white flex items-center justify-center font-black animate-pulse uppercase tracking-[0.5em]">愿由ъ옄 ?몄쬆 以?..</div>;
    if (!isAdmin) return <div className="min-h-screen bg-[#050505] text-red-500 flex items-center justify-center font-black">?묎렐 沅뚰븳???놁뒿?덈떎.</div>;

    function formatDate(d: string | null) {
        if (!d) return '-';
        const date = new Date(d);
        return `${date.getFullYear()}.${String(date.getMonth()+1).padStart(2,'0')}.${String(date.getDate()).padStart(2,'0')}`;
    }

    const renderDonutChart = (stats: any) => (
        <div className="w-full lg:w-[320px] bg-[#0f172a]/60 border border-white/20 rounded-2xl p-6 flex flex-col items-center justify-center shadow-lg transition-all hover:border-blue-500/40">
            <div className="relative w-28 h-28 rounded-full mb-4 flex items-center justify-center" 
                style={{ background: `conic-gradient(${Object.entries(stats.breakdown || {}).sort((a:any, b:any) => {
                    const priority = ['video', 'image', 'script', 'vision_gen', 'motion_guide', 'text_gen', 'character_extraction'];
                    return priority.indexOf(a[0]) - priority.indexOf(b[0]);
                }).map(([stage, data]: [string, any], idx, arr) => { 
                    const colors: any = { video: '#f97316', image: '#3b82f6', script: '#22c55e', vision_gen: '#a855f7', motion_guide: '#6366f1', text_gen: '#06b6d4', character_extraction: '#94a3b8' }; 
                    const total = Object.values(stats.breakdown || {}).reduce((a: any, b: any) => a + (b.tokens || 0), 0) as number; 
                    const prevTotal = arr.slice(0, idx).reduce((a: any, b: any) => a + (b[1].tokens || 0), 0) as number; 
                    const start = (prevTotal / (total || 1)) * 100; 
                    const end = start + (data.tokens / (total || 1)) * 100; 
                    return `${colors[stage] || '#334155'} ${start}% ${end}%`; 
                }).join(', ') || '#1e293b'})` }}>
                <div className="absolute inset-5 bg-[#0f172a] rounded-full flex flex-col items-center justify-center overflow-hidden text-center">
                    <span className="text-[9px] font-black text-gray-500 uppercase tracking-tighter">TOTAL</span>
                    <span className="text-[7.5px] text-blue-400 font-bold leading-none mt-0.5">{(stats.totalTokens || 0).toLocaleString()} TK</span>
                    {stats.totalThinkingTokens > 0 && (
                        <span className="text-[6.5px] text-purple-400 font-medium leading-none mt-0.5">(Thk: {stats.totalThinkingTokens.toLocaleString()})</span>
                    )}
                </div>
            </div>
            <div className="w-full space-y-0.5 mt-1">
                {Object.entries(stats.breakdown || {}).sort((a:any,b:any)=>b[1].tokens - a[1].tokens).slice(0, 5).map(([stage, data]: [string, any]) => {
                    const total = Object.values(stats.breakdown || {}).reduce((a: any, b: any) => a + (b.tokens || 0), 0) as number;
                    const pct = Math.round((data.tokens / (total || 1)) * 100);
                    const colors: any = { video: '#f97316', image: '#3b82f6', script: '#22c55e', vision_gen: '#a855f7', motion_guide: '#6366f1', text_gen: '#06b6d4', character_extraction: '#94a3b8' };
                    return (
                        <div key={stage} className="flex justify-between items-center text-[9px] font-bold text-gray-400">
                            <div className="flex items-center gap-2"><div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: colors[stage] || '#334155' }}/><span className="truncate uppercase text-[8px]">{typeMap[stage] || stage}</span></div>
                            <span className="text-white">{pct}%</span>
                        </div>
                    );
                })}
            </div>
        </div>
    );

    const renderChartRow = (stats: any, topTasks: any[]) => (
        <div className="grid grid-cols-7 gap-3">
            {topTasks.map((task: any) => (
                <div key={task.name} className="bg-[#0f172a]/60 border border-white/20 p-5 rounded-2xl flex flex-col justify-between min-h-[170px] hover:border-blue-500/40 transition-all shadow-lg group">
                    <div className="flex justify-between items-start">
                        <div className="text-[10px] font-black text-gray-500 uppercase tracking-widest group-hover:text-blue-300 transition-colors">{typeMap[task.name] || task.name}</div>
                        <span className="text-sm group-hover:scale-110 transition-transform">{typeIcons[task.name] || '?벀'}</span>
                    </div>
                    <div>
                        <div className="text-lg font-black text-white mt-1 tabular-nums">{task.count} <span className="text-gray-600 text-[10px]">嫄?/span></div>
                        <div className="h-14 w-full mt-3 flex items-end bg-white/[0.02] rounded-lg p-2 gap-[2px] overflow-hidden">
                            <div className={`w-1.5 rounded-full h-full relative overflow-hidden ${task.name === 'video' ? 'bg-orange-500/10' : 'bg-blue-500/10'}`}>
                                <div className={`absolute bottom-0 w-full rounded-full transition-all duration-1000 ${task.name === 'video' ? 'bg-orange-500' : 'bg-blue-500'}`} style={{ height: `${Math.min(100, (task.count / 15) * 100)}%` }} />
                            </div>
                            <div className="flex-1 italic text-[8px] text-gray-600 self-center ml-2 truncate">ACTIVITY_STREAM</div>
                        </div>
                        <div className="text-[11px] font-black text-blue-400 mt-2 tracking-tight">{task.tokens.toLocaleString()}<span className="text-[8px] text-gray-600 ml-1 font-bold">TK</span></div>
                    </div>
                </div>
            ))}
        </div>
    );

    const renderLogTable = (logs: any[]) => (
        <div className="bg-[#0f172a]/40 border border-white/5 rounded-[2rem] overflow-hidden overflow-x-auto shadow-2xl">
            <table className="w-full text-left min-w-[1000px]">
                <thead className="bg-black/20 border-b border-white/5 text-[10px] font-black text-gray-500 uppercase tracking-widest">
                    <tr>
                        <th className="px-10 py-5">TIME</th>
                        <th className="px-10 py-5">TASK</th>
                        <th className="px-10 py-5">MODEL & PROVIDER</th>
                        <th className="px-10 py-5">PROMPT SUMMARY</th>
                        <th className="px-10 py-5 text-right text-orange-500">AI ?좏겙 ?뚮え??/th>
                        <th className="px-10 py-5 text-right text-blue-500">?⑥? ?좏겙 珥앸웾</th>
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
                            <td className="px-10 py-5 max-w-[400px] text-gray-500 italic text-[11px] truncate group-hover:text-gray-300 transition-colors">"{log.prompt_summary || 'No summary available'}"</td>
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
                            <span className="block text-[10px] text-gray-500 font-bold uppercase tracking-widest leading-none">{isSuperAdmin ? '理쒓퀬 愿由ъ옄' : '遺愿由ъ옄'}</span>
                            <span className="text-sm font-black text-blue-400">{user?.email}</span>
                        </div>
                        <button onClick={() => supabase.auth.signOut().then(() => router.push('/'))} className="px-6 py-2.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all">濡쒓렇?꾩썐</button>
                    </div>
                </div>
            </nav>

            <main className="max-w-[1600px] mx-auto px-6 py-8 space-y-12">
                <div className="flex items-center justify-between">
                    <h2 className="text-4xl font-black uppercase tracking-tighter">愿由ъ옄 ??쒕낫??/h2>
                    <div className="flex gap-2 p-1.5 bg-white/5 rounded-2xl border border-white/5 shadow-2xl">
                        {['topics', 'overview', 'users', 'api', 'render-queue', 'styles'].map(tab => (
                            <button key={tab} onClick={() => setActiveTab(tab as any)} className={`px-10 py-3.5 rounded-xl text-[11px] font-black transition-all uppercase tracking-[0.1em] ${activeTab === tab ? 'bg-blue-600 text-white shadow-xl' : 'text-gray-500 hover:text-white'}`}>
                                {tab === 'topics' ? '二쇱젣諛곕떦' : tab === 'overview' ? '媛쒖슂' : tab === 'users' ? '?좎? 愿由? : tab === 'api' ? '?쒖뒪??API' : tab === 'render-queue' ? '?렗 ?뚮뜑留??? : '?렓 ?ㅽ????명똿'}
                            </button>
                        ))}
                    </div>
                </div>

                {activeTab === 'topics' && (
                    <div className="space-y-8 animate-in fade-in duration-300">
                        {/* 1. 移댄뀒怨좊━ 異붽? ??*/}
                        <div className="bg-[#0f172a]/60 rounded-[2.5rem] border border-white/10 p-8 shadow-2xl">
                            <h2 className="font-black text-xl tracking-tight mb-6 flex items-center gap-2">
                                ????移댄뀒怨좊━ 諛?吏곸썝 留ㅽ븨 異붽?
                            </h2>
                            <form onSubmit={handleCreateCategory} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">移댄뀒怨좊━紐?*</label>
                                    <input 
                                        type="text" 
                                        required
                                        placeholder="?? ?멸퀎 誘몄뒪?곕━"
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
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">二쇱슂 由ъ꽌移??ㅼ썙??/label>
                                    <input 
                                        type="text" 
                                        placeholder="?쇳몴濡?援щ텇 (?? 踰꾨????쇨컖吏?, 誘명빐寃??ш굔)"
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
                                                {channel.name} {channel.credentials_path ? '쨌 ?곕룞?꾨즺' : '쨌 誘몄뿰??}
                                            </option>
                                        ))}
                                    </select>
                                    <p className="mt-2 text-[11px] text-gray-500">
                                        {newCatUploadChannelName
                                            ? `${newCatUploadChannelName} (${newCatUploadChannelHandle || 'handle ?놁쓬'})`
                                            : '?좏깮??二쇱젣????긽 ??梨꾨꼸濡??낅줈?쒕맗?덈떎.'}
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
                                        <option value="default" className="bg-[#111] text-white">湲곕낯 ?ㅼ젙 (?좊챸?섍퀬 ?먯뿰?ㅻ읇寃?</option>
                                        <option value="story" className="bg-[#111] text-white">?쏅궇 ?댁빞湲?(援ъ뿰?숉솕 ??</option>
                                        <option value="senior_story" className="bg-[#111] text-white">?쒕땲???댁빞湲?(?뚯긽/媛먯꽦 ??</option>
                                        <option value="news" className="bg-[#111] text-white">?댁뒪 (?뺣낫?꾨떖 ??</option>
                                        <option value="mystery_thriller" className="bg-[#111] text-white">誘몄뒪?곕━ ?ㅻ┫??(湲댁옣媛???</option>
                                        <option value="nursery_rhyme" className="bg-[#111] text-white">?꾨옒?숈슂??(?대┛??援ъ뿰 ??</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">湲곕낯 ?대?吏 ?뷀뭾 *</label>
                                    <select
                                        required
                                        value={newCatImageStyle}
                                        onChange={e => setNewCatImageStyle(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50 cursor-pointer"
                                    >
                                        <option value="realistic" className="bg-[#111] text-white">?ㅼ궗 (Photorealistic)</option>
                                        <option value="ghibli" className="bg-[#111] text-white">吏釉뚮━ 媛먯꽦 ?쇰윭?ㅽ듃 (Ghibli)</option>
                                        <option value="anime" className="bg-[#111] text-white">?쇰낯 ?좊땲硫붿씠?섑뭾 (Anime)</option>
                                        <option value="cinematic" className="bg-[#111] text-white">?곹솕 ?ㅽ떥而??먮굦 (Cinematic)</option>
                                        <option value="cartoon" className="bg-[#111] text-white">2D 移댄댆 ?쇰윭?ㅽ듃 (Cartoon)</option>
                                        <option value="nursery_rhyme" className="bg-[#111] text-white">3D ?숉솕/?좊땲 (Nursery/Pixar)</option>
                                        <option value="??궗/?숈뼇泥??ㅽ걧" className="bg-[#111] text-white">?꾪넻 ?숈뼇???섎У??(Ink Wash)</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">?곸긽 ?щ㎎ (?뺤떇) *</label>
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
                                            <span>媛濡쒗삎 (Longform)</span>
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
                                            <span>?몃줈??(Shorts)</span>
                                        </label>
                                    </div>
                                </div>
                                <div className="md:col-span-3 mt-4 flex justify-end">
                                    <button 
                                        type="submit"
                                        className="px-8 py-3 bg-blue-600 hover:bg-blue-500 text-white font-black rounded-xl transition-all shadow-lg active:scale-95"
                                    >
                                        ?? ?깅줉 諛?珥덇린 二쇱젣 ?앹꽦
                                    </button>
                                </div>
                            </form>
                        </div>

                        {/* 2. ?깅줉??移댄뀒怨좊━ 諛?留ㅽ븨 由ъ뒪??*/}
                        <div className="bg-[#0f172a]/60 rounded-[2.5rem] border border-white/10 overflow-hidden shadow-2xl p-8">
                            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
                                <h2 className="font-black text-xl tracking-tight">?뱛 ??移댄뀒怨좊━ ?꾪솴</h2>
                                <div className="flex p-1 bg-black/40 rounded-xl border border-white/10">
                                    <button 
                                        onClick={() => setCategoryListTab('longform')}
                                        className={`px-6 py-2 rounded-lg text-xs font-black transition-all ${categoryListTab === 'longform' ? 'bg-blue-600 text-white shadow' : 'text-gray-500 hover:text-white'}`}
                                    >
                                        媛濡쒗삎 (Longform)
                                    </button>
                                    <button 
                                        onClick={() => setCategoryListTab('shorts')}
                                        className={`px-6 py-2 rounded-lg text-xs font-black transition-all ${categoryListTab === 'shorts' ? 'bg-blue-600 text-white shadow' : 'text-gray-500 hover:text-white'}`}
                                    >
                                        ?몃줈??(Shorts)
                                    </button>
                                </div>
                            </div>

                            {categoriesLoading ? (
                                <div className="text-center py-20 text-gray-500 text-sm">移댄뀒怨좊━ 濡쒕뵫 以?..</div>
                            ) : categories.filter(c => (c.video_type || 'longform') === categoryListTab).length === 0 ? (
                                <div className="text-center py-20 text-gray-500 text-sm italic">?대떦 ?щ㎎???깅줉??移댄뀒怨좊━媛 ?놁뒿?덈떎.</div>
                            ) : (
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                    {categories.filter(c => (c.video_type || 'longform') === categoryListTab).map((cat) => {
                                        const pendingTopics = topics.filter(t => t.category_id === cat.id && t.status === 'pending');
                                        const completedTopics = topics.filter(t => t.category_id === cat.id && t.status === 'completed');
                                        const previewTopics = generatedTopicsByCat[cat.id]?.length
                                            ? generatedTopicsByCat[cat.id]
                                            : pendingTopics.slice(0, 10).map(t => t.topic);
                                        const isFreshPreview = Boolean(generatedTopicsByCat[cat.id]?.length);

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
                                                        <p>?뫀 <strong className="text-gray-200">?대떦 吏곸썝:</strong> {cat.assigned_employee_email}</p>
                                                        <p>?뵎 <strong className="text-gray-200">?ㅼ썙??</strong> {cat.keywords || '(?놁쓬)'}</p>
                                                        <p className="truncate">?벟 <strong className="text-gray-200">踰ㅼ튂 梨꾨꼸:</strong> <a href={cat.benchmark_channel_url} target="_blank" rel="noreferrer" className="text-blue-400 underline">{cat.benchmark_channel_url || '(?놁쓬)'}</a></p>
                                                        <p>
                                                            ?? <strong className="text-gray-200">?낅줈??梨꾨꼸:</strong>{' '}
                                                            <button
                                                                type="button"
                                                                onClick={() => openCategoryChannelConfig(cat)}
                                                                className="text-blue-400 underline hover:text-blue-300"
                                                            >
                                                                {cat.upload_channel_name || cat.upload_channel_handle || '?대┃?댁꽌 ?ㅼ젙'}
                                                            </button>
                                                        </p>
                                                        <p>?뱷 <strong className="text-gray-200">?蹂??ㅽ???</strong> {cat.default_script_style || '湲곕낯'}</p>
                                                        <p>?렓 <strong className="text-gray-200">?뷀뭾:</strong> {cat.default_image_style || '?ㅼ궗'}</p>
                                                        <p>?렗 <strong className="text-gray-200">?곸긽 ?щ㎎:</strong> {cat.video_type === 'shorts' ? '?몃줈??(Shorts)' : '媛濡쒗삎 (Longform)'}</p>
                                                    </div>
                                                    
                                                    {/* 二쇱젣 ?湲곗뿴 移댁슫??*/}
                                                    <div className="flex gap-3 text-[11px] font-black tracking-wider uppercase mb-6">
                                                        <span className="px-3 py-1 bg-yellow-500/10 text-yellow-500 border border-yellow-500/20 rounded-lg">?湲곗＜?? {pendingTopics.length}媛?/span>
                                                        <span className="px-3 py-1 bg-green-500/10 text-green-500 border border-green-500/20 rounded-lg">?꾨즺二쇱젣: {completedTopics.length}媛?/span>
                                                    </div>
                                                </div>

                                                <button 
                                                    disabled={generatingCatId === cat.id}
                                                    onClick={() => handleTriggerAiTopics(cat.id)}
                                                    className="w-full py-2.5 bg-blue-600/20 hover:bg-blue-600 border border-blue-500/20 hover:border-transparent text-blue-400 hover:text-white rounded-xl text-xs font-black tracking-wider transition-all disabled:bg-gray-800 disabled:text-gray-500 disabled:cursor-not-allowed uppercase"
                                                >
                                                    {generatingCatId === cat.id ? '?쨼 AI 二쇱젣 遺꾩꽍 諛쒓뎬 以?..' : '?뵰 AI 二쇱젣 ?먰뙋湲??앹꽦 (10媛?'}
                                                </button>

                                                {previewTopics.length > 0 && (
                                                    <div className="mt-4 rounded-2xl border border-blue-500/20 bg-blue-950/20 p-4">
                                                        <div className="mb-3 flex items-center justify-between gap-2">
                                                            <p className="text-[11px] font-black text-blue-300">
                                                                {isFreshPreview ? '諛⑷툑 ?앹꽦??二쇱젣 10媛? : '?湲?以?二쇱젣 誘몃━蹂닿린'}
                                                            </p>
                                                            <span className="text-[10px] font-bold text-gray-500">{previewTopics.length}媛?/span>
                                                        </div>
                                                        <ol className="space-y-2 text-[11px] leading-relaxed text-gray-200">
                                                            {previewTopics.slice(0, 10).map((topic, idx) => (
                                                                <li key={`${cat.id}-topic-preview-${idx}`} className="flex gap-2">
                                                                    <span className="shrink-0 font-black text-blue-400">{idx + 1}.</span>
                                                                    <span className="break-words">{topic}</span>
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

                        {/* 3. ?꾩껜 二쇱젣 ?湲곗뿴 ??紐⑤땲?곕쭅 */}
                        {(() => {
                            const getTopicAssignee = (item: any) => item.categories?.assigned_employee_email || item.assigned_employee_email;
                            const isWorkingTopic = (item: any) => item.status === 'assigned';
                            const isPendingTopic = (item: any) => item.status === 'pending';
                            const isQueueVisibleTopic = (item: any) => item.status === 'pending' || item.status === 'assigned';
                            const matchesTopicQueueStatus = (item: any) => topicQueueStatusFilter === 'working' ? isWorkingTopic(item) : isPendingTopic(item);
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
                                            ?뱥 ?ㅼ떆媛??꾩껜 二쇱젣 ?湲곗뿴 ??(Topics Queue)
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
                                            <th className="px-10 py-6">移댄뀒怨좊━</th>
                                            <th className="px-10 py-6">?쒖븞 ?곸긽 二쇱젣</th>
                                            <th className="px-10 py-6">諛곗젙??吏곸썝 ?대찓??/th>
                                            <th className="px-10 py-6 text-center">諛곕떦 ?곹깭</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-white/5 font-medium">
                                        {filteredTopics.map((item) => (
                                            <tr key={item.id} className="hover:bg-white/[0.03] transition-colors h-16 text-xs">
                                                <td className="px-10 py-6 text-gray-300 font-bold">
                                                    {item.categories?.name || '湲곕낯'}
                                                </td>
                                                <td className="px-10 py-6 text-white font-bold max-w-sm truncate">
                                                    <div className="flex items-center gap-2">
                                                        <span className="truncate">{item.topic}</span>
                                                        {item.is_auto_generated && (
                                                            <span className="bg-purple-500/10 text-purple-400 px-1.5 py-0.5 rounded border border-purple-500/20 font-black text-[8px] tracking-tight shrink-0">
                                                                ?쨼 AUTO
                                                            </span>
                                                        )}
                                                    </div>
                                                </td>
                                                <td className="px-10 py-6 text-gray-400">
                                                    {getTopicAssignee(item)}
                                                </td>
                                                <td className="px-10 py-6 text-center">
                                                    <span className={`px-2.5 py-1 rounded-full text-[10px] font-black border uppercase tracking-tighter ${
                                                        item.status === 'pending' ? 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20' :
                                                        isWorkingTopic(item) ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' :
                                                        'bg-green-500/10 text-green-500 border-green-500/20'
                                                    }`}>
                                                        {item.status === 'pending' ? '?湲?以? : isWorkingTopic(item) ? '?묒뾽 以? : '?쒖옉 ?꾨즺'}
                                                    </span>
                                                </td>
                                            </tr>
                                        ))}
                                        {filteredTopics.length === 0 && (
                                            <tr>
                                                <td colSpan={4} className="px-10 py-20 text-center text-gray-600 font-black uppercase tracking-widest text-xs italic">
                                                    {selectedCategory ? '?좏깮??移댄뀒怨좊━???깅줉??二쇱젣媛 ?놁뒿?덈떎.' : '?湲곗뿴???깅줉??二쇱젣媛 ?놁뒿?덈떎. 移댄뀒怨좊━瑜?癒쇱? ?앹꽦?댁＜?몄슂.'}
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
                                    <div className="flex items-baseline gap-1"><span className="text-xl font-black italic">{memberCount.toLocaleString()}</span><span className="text-[9px] font-bold uppercase">紐?/span></div>
                                </div>
                                <div className="flex-1 bg-[#0f172a]/80 border border-white/5 px-6 py-3 rounded-2xl flex items-center justify-between transition-transform hover:scale-[1.02]">
                                    <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">?ㅻ뒛 ?쒖꽦</span>
                                    <div className="flex items-baseline gap-1"><span className="text-xl font-black tabular-nums">{activeToday.toLocaleString()}</span><span className="text-[9px] font-bold text-green-500 uppercase">+{newToday}</span></div>
                                </div>
                                <div className="flex-1 bg-[#0f172a]/80 border border-white/5 px-6 py-3 rounded-2xl flex items-center justify-between transition-transform hover:scale-[1.02]">
                                    <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">珥??좏룷 ?좏겙</span>
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
                                <button onClick={() => setOverviewSubTab('video')} className={`px-8 py-1.5 rounded-lg text-[10px] font-black transition-all ${overviewSubTab === 'video' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500 hover:text-white'}`}>梨꾨꼸 (?곸긽 愿由?</button>
                                <button onClick={() => setOverviewSubTab('log')} className={`px-8 py-1.5 rounded-lg text-[10px] font-black transition-all ${overviewSubTab === 'log' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500 hover:text-white'}`}>濡쒓렇</button>
                             </div>
                        </div>
                        {overviewSubTab === 'video' ? (
                            <div className="space-y-12">
                                <div className="bg-[#0f172a]/20 border border-white/5 rounded-[2.5rem] overflow-hidden shadow-2xl">
                                    <div className="px-10 py-6 border-b border-white/5 bg-black/20 flex justify-between items-center">
                                        <h3 className="text-[10px] font-black text-blue-500 uppercase tracking-[0.4em]">?뱀씤 ?湲?諛??깅줉???곸긽</h3>
                                    </div>
                                    <div className="px-10 py-6 border-b border-white/5 bg-white/[0.02]">
                                        <div className="grid grid-cols-2 xl:grid-cols-6 gap-3">
                                            <div className="rounded-2xl border border-white/10 bg-black/20 px-4 py-3">
                                                <div className="text-[10px] font-black uppercase tracking-widest text-gray-500">Total</div>
                                                <div className="mt-1 text-2xl font-black text-white tabular-nums">{publishingSummary.total}</div>
                                            </div>
                                            <div className="rounded-2xl border border-orange-500/20 bg-orange-500/5 px-4 py-3">
                                                <div className="text-[10px] font-black uppercase tracking-widest text-orange-300">{isKor ? '?湲? : 'Pending'}</div>
                                                <div className="mt-1 text-2xl font-black text-orange-300 tabular-nums">{publishingSummary.pending}</div>
                                            </div>
                                            <div className="rounded-2xl border border-blue-500/20 bg-blue-500/5 px-4 py-3">
                                                <div className="text-[10px] font-black uppercase tracking-widest text-blue-300">{isKor ? '吏꾪뻾 以? : 'Publishing'}</div>
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
                                            { key: 'pending', label: isKor ? '?湲? : 'Pending', count: publishingSummary.pending },
                                            { key: 'processing', label: isKor ? '吏꾪뻾 以? : 'Publishing', count: publishingSummary.processing },
                                            { key: 'published', label: isKor ? '?꾨즺' : 'Published', count: publishingSummary.published },
                                            { key: 'failed', label: isKor ? '?ㅽ뙣' : 'Failed', count: publishingSummary.failed },
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
                                                ? `?꾩옱 ${filteredPublishingRequests.length}嫄??쒖떆 以?
                                                : `Showing ${filteredPublishingRequests.length} requests`}
                                        </div>
                                    </div>
                                    <table className="w-full text-left">
                                        <thead className="bg-black/30 border-b border-white/5 text-[10px] font-black text-gray-500 uppercase tracking-widest">
                                            <tr><th className="px-10 py-6">?곸긽 ?뺣낫 / ?뚯쑀??/th><th className="px-10 py-6 text-center">?좏뒠釉?ID</th><th className="px-10 py-6 text-center">?깅줉?쇱떆</th><th className="px-10 py-6 text-center">?곹깭</th><th className="px-10 py-6 text-right">愿由?/ Drive ?먯궛</th></tr>
                                        </thead>
                                        <tbody className="divide-y divide-white/5">
                                            {filteredPublishingRequests.length === 0 ? (
                                                <tr><td colSpan={5} className="px-10 py-20 text-center text-gray-600 font-bold uppercase tracking-widest italic">?깅줉???곸긽???놁뒿?덈떎.</td></tr>
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
                                                                            {req.metadata?.project_name && (
                                                                                <span className="px-2 py-1 rounded-full bg-white/5 border border-white/10 text-[9px] font-black text-gray-300">
                                                                                    ?꾨줈?앺듃: {req.metadata.project_name}
                                                                                </span>
                                                                            )}
                                                                            {req.metadata?.topic && (
                                                                                <span className="px-2 py-1 rounded-full bg-white/5 border border-white/10 text-[9px] font-black text-gray-300">
                                                                                    二쇱젣: {req.metadata.topic}
                                                                                </span>
                                                                            )}
                                                                            {req.metadata?.has_drive_bundle && (
                                                                                <span className="px-2 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-[9px] font-black text-blue-300">
                                                                                    DRIVE BUNDLE
                                                                                </span>
                                                                            )}
                                                                            <span className={`px-2 py-1 rounded-full border text-[9px] font-black ${statusMeta.className}`}>
                                                                                {statusMeta.label}
                                                                            </span>
                                                                        </div>
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
                                            <tr><th className="px-10 py-6">梨꾨꼸紐?/ 怨꾩젙</th><th className="px-10 py-6 text-center">?앹꽦???곸긽??/th><th className="px-10 py-6 text-center">理쒓렐 ?숆린??/th><th className="px-10 py-6 text-right">?곹깭</th></tr>
                                        </thead>
                                        <tbody className="divide-y divide-white/5">
                                            {users.slice(0, 5).map(u => {
                                                const userVideos = globalLogs.filter(l => l.user_id === u.id && (l.task_type || '').toLowerCase() === 'video').length;
                                                return (
                                                    <tr key={u.id} className="hover:bg-white/[0.03] transition-colors group">
                                                        <td className="px-10 py-6"><div className="font-black text-white text-base group-hover:text-blue-400 transition-colors uppercase tracking-tight">{u.email}</div><div className="text-[11px] text-gray-600 font-bold mt-1 uppercase italic tracking-tighter">{u.user_metadata?.full_name || '?곕룞??梨꾨꼸'}</div></td>
                                                        <td className="px-10 py-6 text-center font-black text-white text-xl tabular-nums">{userVideos}</td>
                                                        <td className="px-10 py-6 text-center text-[12px] font-black text-gray-500">{formatDate(u.last_sign_in_at)}</td>
                                                        <td className="px-10 py-6 text-right"><span className="px-3 py-1 bg-green-500/10 text-green-500 text-[9px] font-black rounded-full border border-green-500/20 uppercase">?뺤긽?곌껐</span></td>
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

                {activeTab === 'users' && (
                    <div className="bg-[#0f172a]/20 border border-white/5 rounded-[3rem] overflow-hidden shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <div className="px-10 py-6 border-b border-white/5 bg-black/20 flex justify-between items-center">
                            <h3 className="text-sm font-black text-gray-400 uppercase tracking-[0.2em]">?뚯썝 愿由?由ъ뒪??/h3>
                            <button onClick={fetchUsers} className="px-6 py-2 bg-blue-600/10 hover:bg-blue-600 text-blue-500 hover:text-white text-[10px] font-black rounded-xl border border-blue-500/20 transition-all uppercase tracking-widest">?덈줈怨좎묠</button>
                        </div>
                        <table className="w-full text-left">
                            <thead className="bg-black/30 border-b border-white/20 text-xs font-black text-gray-400 uppercase tracking-widest">
                                <tr>
                                    <th className="px-0 py-4 whitespace-nowrap">?대쫫</th>
                                    <th className="px-0 py-4 whitespace-nowrap">?대찓??/ ?깃툒</th>
                                    <th className="px-0 py-4 whitespace-nowrap">?곕씫泥?/th>
                                    <th className="px-0 py-4 whitespace-nowrap">援?쟻</th>
                                    <th className="px-0 py-4 whitespace-nowrap">異붿쿇??/th>
                                    <th className="px-0 py-4 whitespace-nowrap">梨꾨꼸紐?/th>
                                    <th className="px-0 py-4 text-center whitespace-nowrap">?좏겙</th>
                                    <th className="px-0 py-4 text-center whitespace-nowrap">硫ㅻ쾭??/th>
                                    <th className="px-0 py-4 text-center whitespace-nowrap">媛?낆씪</th>
                                    <th className="px-0 py-4 text-center whitespace-nowrap">理쒓렐?묒냽</th>
                                    <th className="px-0 py-4 text-center whitespace-nowrap">愿由?/th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-white/20">
                                {users.map(u => (
                                    <tr key={u.id} className="hover:bg-white/[0.03] transition-colors group">
                                        {/* ?대쫫 */}
                                        <td className="px-1 py-4">
                                            <div className="font-black text-white text-xs whitespace-nowrap">{u.user_metadata?.full_name || <span className="text-gray-600 italic">?놁쓬</span>}</div>
                                        </td>
                                        {/* ?대찓??/ 愿由ъ옄 ?깃툒 */}
                                        <td className="px-1 py-4 max-w-[160px]">
                                            <div className="font-bold text-blue-400 text-[10px] tracking-tight truncate">{u.email?.toLowerCase()}</div>
                                            <div className="flex gap-1 mt-0.5 flex-wrap">
                                                {u.email === SUPER_ADMIN_EMAIL && <span className="px-1 py-0.5 bg-blue-600 text-[7px] font-black rounded text-white">理쒓퀬愿由ъ옄</span>}
                                                {u.app_metadata?.is_admin && u.email !== SUPER_ADMIN_EMAIL && <span className="px-1 py-0.5 bg-indigo-500 text-[7px] font-black rounded text-white">遺愿由ъ옄</span>}
                                            </div>
                                        </td>
                                        {/* ?곕씫泥?*/}
                                        <td className="px-1 py-4 text-[10px] text-gray-300 font-bold whitespace-nowrap">
                                            {u.user_metadata?.contact || <span className="text-gray-700">-</span>}
                                        </td>
                                        {/* 援?쟻 */}
                                        <td className="px-1 py-4 text-[10px] text-gray-300 font-bold whitespace-nowrap">
                                            {u.user_metadata?.nationality || <span className="text-gray-700">-</span>}
                                        </td>
                                        {/* 異붿쿇??*/}
                                        <td className="px-1 py-4 text-[10px] whitespace-nowrap">
                                            {u.user_metadata?.referrer
                                                ? <span className="text-yellow-400 font-bold">{u.user_metadata.referrer}</span>
                                                : <span className="text-gray-700">-</span>}
                                        </td>
                                        {/* 梨꾨꼸紐?*/}
                                        <td className="px-1 py-4 max-w-[110px]">
                                            {u.user_metadata?.youtube_channel
                                                ? <span className="flex items-center gap-1 text-red-400 text-[10px] font-black truncate"><span className="w-1.5 h-1.5 bg-red-500 rounded-full animate-pulse shrink-0 inline-block"></span>{u.user_metadata.youtube_channel}</span>
                                                : <span className="text-gray-700 text-xs">-</span>}
                                        </td>
                                        {/* 蹂댁쑀 ?좏겙 */}
                                        <td className="px-1 py-4 text-center font-black text-white text-sm tabular-nums whitespace-nowrap">
                                            {u.profile?.token_balance?.toLocaleString() || 0}
                                        </td>
                                        {/* 硫ㅻ쾭??*/}
                                        <td className="px-1 py-4 text-center">
                                            <button onClick={() => handleRoleChange(u.id, u.app_metadata?.membership)} className={`px-2 py-1 rounded-lg text-[8px] font-black border uppercase tracking-widest transition-all whitespace-nowrap ${u.app_metadata?.membership === 'pro' ? 'bg-indigo-600 text-white border-indigo-500 shadow-lg' : 'bg-white/5 text-gray-500 border-white/10 hover:border-white/30'}`}>
                                                {u.app_metadata?.membership?.toUpperCase() === 'PRO' ? '?뭿 ?꾨줈' : '?뫀 ?ㅽ깲?ㅻ뱶'}
                                            </button>
                                        </td>
                                        {/* 媛?낆씪 */}
                                        <td className="px-1 py-4 text-center text-[10px] font-bold text-gray-500 whitespace-nowrap">{formatDate(u.created_at)}</td>
                                        {/* 理쒓렐?묒냽 */}
                                        <td className="px-1 py-4 text-center text-[10px] font-bold text-gray-500 whitespace-nowrap">{formatDate(u.last_sign_in_at)}</td>
                                        {/* 愿由?硫붾돱 ??3x2 洹몃━??*/}
                                        <td className="px-1 py-4">
                                            <div className="grid grid-cols-3 gap-1">
                                                {isSuperAdmin && u.email !== SUPER_ADMIN_EMAIL
                                                    ? <button onClick={() => handleAdminRoleToggle(u.id, !!u.app_metadata?.is_admin)} className={`px-1.5 py-1 rounded text-[7px] font-black border transition-all whitespace-nowrap ${u.app_metadata?.is_admin ? 'bg-indigo-600/20 text-indigo-400 border-indigo-500/30' : 'bg-white/5 text-gray-600 border-white/10'}`}>沅뚰븳愿由?/button>
                                                    : <span />
                                                }
                                                <button onClick={() => handleRecharge(u.id)} className="px-1.5 py-1 bg-green-600/10 hover:bg-green-600 text-green-500 hover:text-white text-[7px] font-black rounded border border-green-500/20 transition-all whitespace-nowrap">?좏겙異⑹쟾</button>
                                                <button onClick={() => { setEditInfoUser(u); setEditInfoForm({ full_name: u.user_metadata?.full_name || '', nationality: u.user_metadata?.nationality || '', contact: u.user_metadata?.contact || '' }); }} className="px-1.5 py-1 bg-yellow-600/10 hover:bg-yellow-600 text-yellow-500 hover:text-white text-[7px] font-black rounded border border-yellow-500/20 transition-all whitespace-nowrap">?뺣낫?섏젙</button>
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
                            <h3 className="text-sm font-black text-gray-400 uppercase tracking-[0.2em]">?쒖뒪???꾩뿭 API ??/h3>
                            <p className="text-[10px] text-gray-600 mt-1">?쒕쾭 怨듭슜 ????媛쒖씤 ?ㅺ? ?녿뒗 ?좎??먭쾶 ?곸슜?⑸땲??</p>
                        </div>
                        <div className="p-10 space-y-6">
                            <div className="grid grid-cols-1 xl:grid-cols-2 gap-8 items-start">
                                <div className="space-y-6">
                            {([
                                { key: 'gemini', label: '??Gemini API Key' },
                                { key: 'youtube', label: '?띰툘 YouTube Data API Key' },
                                { key: 'elevenlabs', label: '?럺截?ElevenLabs API Key' },
                                { key: 'topview', label: '?썟 TopView API Key' },
                                { key: 'topview_uid', label: '?썟 TopView UID' },
                            ] as { key: keyof typeof sysKeys; label: string }[]).map(({ key, label }) => (
                                <div key={key}>
                                    <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">{label}</label>
                                    <input
                                        type="password"
                                        value={sysKeys[key] as string}
                                        onChange={e => setSysKeys(prev => ({ ...prev, [key]: e.target.value }))}
                                        onFocus={e => (e.target as HTMLInputElement).type = 'text'}
                                        onBlur={e => (e.target as HTMLInputElement).type = 'password'}
                                        placeholder={sysKeys[key] ? '?™™™™™™™™™™™? : '(誘몄꽕??'}
                                        className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-gray-300 placeholder:text-gray-700"
                                    />
                                </div>
                            ))}
                                </div>

                            {/* Google Drive Queue Configuration section */}
                            <div className="space-y-4 xl:border-l xl:border-white/10 xl:pl-8">
                                <h4 className="text-xs font-black text-blue-400 uppercase tracking-widest mb-2">?뱚 援ш? ?쒕씪?대툕 ?뚮뜑 ?湲곗뿴 ?ㅼ젙</h4>
                                
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
                                        <p className="text-[10px] text-gray-500 mt-0.5">?쒖꽦???? 媛??앹꽦 ?④퀎 諛?鍮꾨뵒???뚮뜑 ?뚯씪???꾨옒 ?ㅼ젙??援ш? ?쒕씪?대툕 寃쎈줈濡??숆린?붾맗?덈떎.</p>
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
                                        <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">?눖?눟 ?쒓뎅??Windows 寃쎈줈 (DRIVE_PATH_KO)</label>
                                        <input 
                                            type="text" 
                                            value={sysKeys.drive_path_ko} 
                                            onChange={e => setSysKeys(prev => ({ ...prev, drive_path_ko: e.target.value }))}
                                            placeholder="G:/???쒕씪?대툕/Longform_Render_Queue"
                                            className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-gray-300"
                                        />
                                    </div>

                                    <div>
                                        <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">?눣?눡 ?곸뼱 Windows 寃쎈줈 (DRIVE_PATH_EN)</label>
                                        <input 
                                            type="text" 
                                            value={sysKeys.drive_path_en} 
                                            onChange={e => setSysKeys(prev => ({ ...prev, drive_path_en: e.target.value }))}
                                            placeholder="G:/My Drive/Longform_Render_Queue"
                                            className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-gray-300"
                                        />
                                    </div>

                                    <div>
                                        <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">?눓?눝 ?쇰낯??Windows 寃쎈줈 (DRIVE_PATH_JA)</label>
                                        <input 
                                            type="text" 
                                            value={sysKeys.drive_path_ja} 
                                            onChange={e => setSysKeys(prev => ({ ...prev, drive_path_ja: e.target.value }))}
                                            placeholder="G:/?욁궎?됥꺀?ㅳ깣/Longform_Render_Queue"
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
                                <p className="text-[10px] text-gray-500">API 諛⑹떇 ?먭꺽 ?뚮뜑留곸뿉???먯뀑 ZIP???낅줈?쒗븷 Drive ?대뜑 ID?낅땲??</p>
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
                                <p className="text-[10px] text-gray-500">硫붿씤 PC? ?먭꺽 ?뚯빱媛 Drive API ?몄쬆???ъ슜??OAuth ?좏겙 ?뚯씪 寃쎈줈?낅땲??</p>
                            </div>

                            {sysKeysSaved && <p className="text-xs text-green-400 font-bold text-center">??????꾨즺</p>}

                            <button
                                onClick={saveSysKeys}
                                disabled={sysKeysSaving}
                                className="w-full py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white font-black rounded-2xl transition-all text-sm mt-4"
                            >
                                {sysKeysSaving ? '???以?..' : '?뮶 ????ν븯湲?}
                            </button>
                        </div>
                    </div>
                )}
                {activeTab === 'render-queue' && (
                    <div className="bg-[#0f172a]/20 border border-white/5 rounded-[3rem] overflow-hidden shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <div className="px-10 py-6 border-b border-white/5 bg-black/20 flex justify-between items-center">
                            <div>
                                <h3 className="text-sm font-black text-gray-400 uppercase tracking-[0.2em]">?먭꺽 鍮꾨뵒???뚮뜑留???/h3>
                                <p className="text-[10px] text-gray-600 mt-1">GPU ?쒕쾭???ㅼ떆媛?鍮꾨뵒???몄퐫???湲?諛?吏꾪뻾 ?곹깭瑜?紐⑤땲?곕쭅?⑸땲??</p>
                            </div>
                            <button onClick={fetchRenderQueue} className="px-6 py-2 bg-blue-600/10 hover:bg-blue-600 text-blue-500 hover:text-white text-[10px] font-black rounded-xl border border-blue-500/20 transition-all uppercase tracking-widest">?덈줈怨좎묠</button>
                        </div>
                        <div className="p-10">
                            {queueLoading && renderQueue.length === 0 ? (
                                <div className="text-center text-xs text-gray-500 py-10">?湲곗뿴 議고쉶 以?..</div>
                            ) : renderQueue.length === 0 ? (
                                <div className="text-center text-xs text-gray-500 py-10">?꾩옱 ?湲??먮뒗 ?ㅽ뻾 以묒씤 ?뚮뜑留??묒뾽???놁뒿?덈떎.</div>
                            ) : (
                                <div className="overflow-x-auto">
                                    <table className="w-full text-left">
                                        <thead className="bg-black/30 border-b border-white/20 text-xs font-black text-gray-400 uppercase tracking-widest">
                                            <tr>
                                                <th className="px-4 py-4">?앹꽦??/th>
                                                <th className="px-4 py-4">?ъ슜??/th>
                                                <th className="px-4 py-4">?꾨줈?앺듃</th>
                                                <th className="px-4 py-4">吏꾪뻾 ?곹깭</th>
                                                <th className="px-4 py-4 text-center">吏꾪뻾??/th>
                                                <th className="px-4 py-4">硫붿떆吏</th>
                                                <th className="px-4 py-4 text-center">?묒뾽 愿由?/th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-white/10 text-xs font-medium text-gray-300">
                                            {renderQueue.map((task: any) => (
                                                <tr key={task.id} className="hover:bg-white/[0.02] transition-colors">
                                                    <td className="px-4 py-4 whitespace-nowrap">
                                                        <div>{new Date(task.created_at).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}</div>
                                                        <div className="text-[10px] text-gray-500 mt-0.5">{new Date(task.created_at).toLocaleDateString()}</div>
                                                    </td>
                                                    <td className="px-4 py-4 whitespace-nowrap text-blue-400 font-bold">{task.email}</td>
                                                    <td className="px-4 py-4 font-bold text-white max-w-[200px] truncate" title={task.project_name}>{task.project_name} <span className="text-[10px] text-gray-500 font-mono">({task.project_id})</span></td>
                                                    <td className="px-4 py-4 whitespace-nowrap">
                                                        <span className={`px-2.5 py-1 rounded-full text-[9px] font-black uppercase tracking-widest border ${
                                                            task.status === 'completed' ? 'bg-green-500/10 text-green-500 border-green-500/20' :
                                                            task.status === 'rendering' ? 'bg-blue-500/10 text-blue-500 border-blue-500/20 animate-pulse' :
                                                            task.status === 'pending' ? 'bg-orange-500/10 text-orange-500 border-orange-500/20' :
                                                            'bg-red-500/10 text-red-500 border-red-500/20'
                                                        }`}>
                                                            {task.status === 'pending' ? '?湲?以? : task.status === 'rendering' ? '?뚮뜑留?以? : task.status === 'completed' ? '?꾨즺' : '?ㅽ뙣'}
                                                        </span>
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
                                                        <button onClick={() => handleDeleteQueueTask(task.id)} className="px-3 py-1.5 bg-red-600/10 hover:bg-red-600 text-red-500 hover:text-white rounded-lg border border-red-500/20 hover:border-red-600 transition-all font-black text-[10px]">??젣</button>
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </div>
                    </div>
                )}
                {activeTab === 'styles' && (
                    <div className="space-y-8 animate-in fade-in duration-300">
                        {/* 1. ?ㅽ???異붽?/?섏젙 ??*/}
                        <div ref={presetFormRef} className={`rounded-[2.5rem] border p-8 shadow-2xl scroll-mt-24 transition-all duration-300 ${presetId ? 'bg-blue-950/40 border-blue-500/40' : 'bg-[#0f172a]/60 border-white/10'}`}>
                            <h2 className="font-black text-xl tracking-tight mb-6 flex items-center gap-2">
                                ?렓 {presetId ? '?ㅽ????꾨━???섏젙' : '?????ㅽ????꾨━??異붽?'}
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
                                        <option value="image">?렓 ?대?吏 ?ㅽ???(Image Style)</option>
                                        <option value="script">?뱷 ?蹂??ㅽ???(Script Style)</option>
                                        <option value="thumbnail">?뼹截??몃꽕???ㅽ???(Thumbnail Style)</option>
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
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">?ㅽ???踰좏듃?⑥뼱 ?쒖떆紐?/label>
                                    <input
                                        type="text"
                                        placeholder="?? 휂i沼뇆 梳즢h th沼켧 t梳?
                                        value={presetNameVi}
                                        onChange={e => setPresetNameVi(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">?꾨━???몃꽕???대?吏 URL</label>
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
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">AI 異붽? 吏?쒖궗??(Grounded Gemini Instruction - ?대?吏 ?ㅽ????꾩슜)</label>
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
                                        {isSavingPreset ? '???以?..' : '?뮶 ?꾨━?????}
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
                                    ?봽 ?덈줈怨좎묠
                                </button>
                            </div>
                            <div className="p-6">
                                {presetsLoading ? (
                                    <div className="text-center text-xs text-gray-500 py-10">?꾨━??濡쒕뵫 以?..</div>
                                ) : (
                                    <div className="grid grid-cols-1 gap-8">
                                        {['image', 'script', 'thumbnail'].map(type => {
                                            const typePresets = stylePresets.filter((p: any) => p.preset_type === type);
                                            const typeLabel = type === 'image' ? '?렓 ?대?吏 ?ㅽ??? : type === 'script' ? '?뱷 ?蹂??ㅽ??? : '?뼹截??몃꽕???ㅽ???;
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
                                                                                    ?륅툘 ?섏젙
                                                                                </button>
                                                                                <button
                                                                                    onClick={() => handleDeletePreset(preset.id, preset.key_code)}
                                                                                    className="p-1 hover:bg-white/5 rounded text-red-500 text-xs"
                                                                                    title="??젣"
                                                                                >
                                                                                    ?뿊截?
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
                                                                                ?뮕 Instruction: {preset.gemini_instruction}
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

            {/* ?ъ슜???뺣낫 吏곸젒 ?섏젙 紐⑤떖 */}
            {editInfoUser && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setEditInfoUser(null)}>
                    <div className="bg-[#0a0a0a] border border-white/10 rounded-2xl p-8 w-full max-w-md shadow-2xl" onClick={e => e.stopPropagation()}>
                        <div className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">?ъ슜???뺣낫 ?섏젙</div>
                        <div className="text-white font-black text-lg mb-6">{editInfoUser.email?.toLowerCase()}</div>
                        <div className="flex flex-col gap-4">
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">?대쫫</label>
                                <input value={editInfoForm.full_name} onChange={e => setEditInfoForm(p => ({ ...p, full_name: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-yellow-500/50" placeholder="?대쫫 ?낅젰" />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">援?쟻</label>
                                <input value={editInfoForm.nationality} onChange={e => setEditInfoForm(p => ({ ...p, nationality: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-yellow-500/50" placeholder="援?쟻 ?낅젰 (?? ?쒓뎅)" />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">?곕씫泥?/label>
                                <input value={editInfoForm.contact} onChange={e => setEditInfoForm(p => ({ ...p, contact: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-yellow-500/50" placeholder="?곕씫泥??낅젰" />
                            </div>
                        </div>
                        <div className="flex gap-3 mt-6">
                            <button onClick={handleSaveUserInfo} className="flex-1 py-3 bg-yellow-500 hover:bg-yellow-400 text-black text-[11px] font-black rounded-xl transition-all uppercase tracking-widest">???/button>
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
                             <div className="flex items-center gap-6"><h3 className="text-3xl font-black text-blue-500 uppercase italic tracking-tighter">?ъ슜???묒뾽 濡쒓렇</h3><div className="px-4 py-1.5 bg-blue-600/10 border border-blue-500/20 rounded-full text-[10px] font-black text-blue-400 uppercase tracking-widest">{logViewUser.email}</div></div>
                             <div className="flex items-center gap-4">
                                  <div className="flex gap-1 p-1 bg-white/5 rounded-xl border border-white/5">{[1, 7, 30].map(d => (
                                      <button key={d} onClick={() => { setLogPeriod(d); fetchUserLogs(logViewUser.id, d); }} className={`px-6 py-2 text-[10px] font-black rounded-lg transition-all ${logPeriod === d ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500 hover:text-white'}`}>{d === 1 ? '?쇨컙' : d === 7 ? '二쇨컙' : '?붽컙'}</button>
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
                                    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest ml-4">{key.toUpperCase()} API ??/label>
                                    <input type="text" placeholder={`?낅젰?섏꽭??..`} value={tempApiKeys[key] || ''} onChange={(e) => setTempApiKeys({...tempApiKeys, [key]: e.target.value})} className="w-full bg-black/40 border border-white/5 rounded-2xl px-8 py-5 text-sm font-black text-white focus:outline-none focus:border-blue-500/50 transition-all" />
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
                            <div><h3 className="text-3xl font-black uppercase italic tracking-tighter text-purple-500">?좏뒠釉?梨꾨꼸 ?곕룞 愿由?/h3><p className="text-sm text-gray-500 mt-2 uppercase tracking-widest font-black italic">{channelViewUser.email}</p></div>
                            <div className="space-y-8">
                                <div className="space-y-2">
                                    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest ml-4">梨꾨꼸 ?대쫫 (?쒖떆??</label>
                                    <input type="text" placeholder="?? ?쇱뭅?붾━ ?ㅽ뒠?붿삤" value={tempChannelInfo.name} onChange={(e) => setTempChannelInfo({...tempChannelInfo, name: e.target.value})} className="w-full bg-black/40 border border-white/5 rounded-2xl px-8 py-5 text-sm font-black text-white focus:outline-none focus:border-purple-500/50 transition-all" />
                                </div>
                                <div className="space-y-2">
                                    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest ml-4">?좏뒠釉?梨꾨꼸 ID</label>
                                    <input type="text" placeholder="?? UCxxxxxxxxxxxx" value={tempChannelInfo.id} onChange={(e) => setTempChannelInfo({...tempChannelInfo, id: e.target.value})} className="w-full bg-black/40 border border-white/5 rounded-2xl px-8 py-5 text-sm font-black text-white focus:outline-none focus:border-purple-500/50 transition-all" />
                                    
                                </div>
                                <div className="space-y-2">
                                    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest ml-4">援?? ?고쉶??怨좎젙 IP ?꾨줉??(?좏깮)</label>
                                    <input type="text" placeholder="?? http://username:password@ip:port" value={tempChannelInfo.proxy || ''} onChange={(e) => setTempChannelInfo({...tempChannelInfo, proxy: e.target.value})} className="w-full bg-black/40 border border-white/5 rounded-2xl px-8 py-5 text-sm font-black text-white focus:outline-none focus:border-purple-500/50 transition-all font-mono" />
                                    <p className="text-[9px] text-gray-600 ml-4 font-bold">* ?대떦 梨꾨꼸 ?곸긽 ?낅줈????吏?뺥븳 ?꾨줉??IP ???쓣 寃쎌쑀?섏뿬 ?寃?援?? ?몄텧 ?뺣쪧???믪엯?덈떎.</p>
                                </div>
                            </div>
                            <div className="flex gap-4">
                                <button 
                                    onClick={handleUpdateChannelInfo} 
                                    disabled={savingChannel}
                                    className={`flex-1 py-6 font-black rounded-[2rem] shadow-xl transition-all active:scale-95 uppercase tracking-widest text-xs ${savingChannel ? 'bg-gray-800 text-gray-500 cursor-not-allowed' : 'bg-purple-600 hover:bg-purple-500 text-white'}`}
                                >
                                    {savingChannel ? (isKor ? '???以?..' : 'Saving...') : (isKor ? '?띿뒪???뺣낫 ??? : 'Save Text Info')}
                                </button>
                                
                                <button 
                                    onClick={() => {
                                        if (!tempChannelInfo.name || !tempChannelInfo.id) {
                                            alert(isKor ? "梨꾨꼸 ?대쫫怨?ID瑜?紐⑤몢 ?낅젰?댁＜?몄슂." : "Please enter both channel name and ID.");
                                            return;
                                        }
                                        
                                        // window.open???ъ슜?섏뿬 CORS ?고쉶 諛?利됯컖?곸씤 ?쇰뱶諛??쒓났
                                        const url = `http://127.0.0.1:8001/api/channels/login-by-info?name=${encodeURIComponent(tempChannelInfo.name)}&id=${encodeURIComponent(tempChannelInfo.id)}&proxy=${encodeURIComponent(tempChannelInfo.proxy || '')}`;
                                        window.open(url, '_blank', 'width=600,height=700');
                                        
                                        // 硫뷀??곗씠???뺣낫 ??μ? 蹂꾨룄濡??섑뻾
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

            {/* 移댄뀒怨좊━ ?뺣낫 ?섏젙 紐⑤떖 */}
            {editCategory && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setEditCategory(null)}>
                    <div className="bg-[#0a0a0a] border border-white/10 rounded-2xl p-8 w-full max-w-lg shadow-2xl" onClick={e => e.stopPropagation()}>
                        <div className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">移댄뀒怨좊━ ?섏젙</div>
                        <div className="text-white font-black text-lg mb-6">"{editCategory.name}" ?ㅼ젙 愿由?/div>
                        <div className="flex flex-col gap-4 text-xs">
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">移댄뀒怨좊━紐?*</label>
                                <input 
                                    type="text"
                                    value={editCatForm.name} 
                                    onChange={e => setEditCatForm(p => ({ ...p, name: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50" 
                                    placeholder="移댄뀒怨좊━紐??낅젰" 
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">?대떦 吏곸썝 ?대찓??*</label>
                                <select
                                    value={editCatForm.assigned_employee_email}
                                    onChange={e => setEditCatForm(p => ({ ...p, assigned_employee_email: e.target.value }))}
                                    className="w-full bg-[#111] border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50 cursor-pointer"
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
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">二쇱슂 由ъ꽌移??ㅼ썙??/label>
                                <input 
                                    type="text"
                                    value={editCatForm.keywords} 
                                    onChange={e => setEditCatForm(p => ({ ...p, keywords: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50" 
                                    placeholder="?쇳몴濡?援щ텇" 
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">踰ㅼ튂留덊궧???좏뒠釉?梨꾨꼸 URL</label>
                                <input 
                                    type="url"
                                    value={editCatForm.benchmark_channel_url} 
                                    onChange={e => setEditCatForm(p => ({ ...p, benchmark_channel_url: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50" 
                                    placeholder="?좏뒠釉?梨꾨꼸 二쇱냼" 
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">湲곕낯 ?蹂??ㅽ???/label>
                                <select
                                    value={editCatForm.default_script_style}
                                    onChange={e => setEditCatForm(p => ({ ...p, default_script_style: e.target.value }))}
                                    className="w-full bg-[#111] border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50 cursor-pointer"
                                >
                                    <option value="default" className="bg-[#111] text-white">湲곕낯 ?ㅼ젙 (?좊챸?섍퀬 ?먯뿰?ㅻ읇寃?</option>
                                    <option value="story" className="bg-[#111] text-white">?쏅궇 ?댁빞湲?(援ъ뿰?숉솕 ??</option>
                                    <option value="senior_story" className="bg-[#111] text-white">?쒕땲???댁빞湲?(?뚯긽/媛먯꽦 ??</option>
                                    <option value="news" className="bg-[#111] text-white">?댁뒪 (?뺣낫?꾨떖 ??</option>
                                    <option value="mystery_thriller" className="bg-[#111] text-white">誘몄뒪?곕━ ?ㅻ┫??(湲댁옣媛???</option>
                                    <option value="nursery_rhyme" className="bg-[#111] text-white">?꾨옒?숈슂??(?대┛??援ъ뿰 ??</option>
                                </select>
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">湲곕낯 ?대?吏 ?뷀뭾</label>
                                <select
                                    value={editCatForm.default_image_style}
                                    onChange={e => setEditCatForm(p => ({ ...p, default_image_style: e.target.value }))}
                                    className="w-full bg-[#111] border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50 cursor-pointer"
                                >
                                    <option value="realistic" className="bg-[#111] text-white">?ㅼ궗 (Photorealistic)</option>
                                    <option value="ghibli" className="bg-[#111] text-white">吏釉뚮━ 媛먯꽦 ?쇰윭?ㅽ듃 (Ghibli)</option>
                                    <option value="anime" className="bg-[#111] text-white">?쇰낯 ?좊땲硫붿씠?섑뭾 (Anime)</option>
                                    <option value="cinematic" className="bg-[#111] text-white">?곹솕 ?ㅽ떥而??먮굦 (Cinematic)</option>
                                    <option value="cartoon" className="bg-[#111] text-white">2D 移댄댆 ?쇰윭?ㅽ듃 (Cartoon)</option>
                                    <option value="nursery_rhyme" className="bg-[#111] text-white">3D ?숉솕/?좊땲 (Nursery/Pixar)</option>
                                    <option value="??궗/?숈뼇泥??ㅽ걧" className="bg-[#111] text-white">?꾪넻 ?숈뼇???섎У??(Ink Wash)</option>
                                </select>
                             </div>
                             <div>
                                 <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-2">?곸긽 ?щ㎎ (?뺤떇) *</label>
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
                                         <span>媛濡쒗삎 (Longform)</span>
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
                                         <span>?몃줈??(Shorts)</span>
                                     </label>
                                 </div>
                             </div>
                             <div className="rounded-xl border border-white/10 bg-white/5 px-4 py-3">
                                 <div className="flex items-center justify-between gap-3">
                                     <div>
                                         <div className="text-[10px] text-gray-500 font-black uppercase tracking-widest">?낅줈??怨좎젙 梨꾨꼸</div>
                                         <div className="mt-1 text-sm font-black text-white">
                                             {editCatForm.upload_channel_name || editCatForm.upload_channel_handle || '?ㅼ젙 ????}
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
                                         梨꾨꼸 ?ㅼ젙
                                     </button>
                                 </div>
                             </div>
                        </div>
                        <div className="flex gap-3 mt-6">
                            <button onClick={handleSaveCategory} className="flex-1 py-3 bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-black rounded-xl transition-all uppercase tracking-widest">?섏젙?꾨즺</button>
                            <button onClick={() => setEditCategory(null)} className="px-6 py-3 bg-white/5 hover:bg-white/10 text-gray-400 text-[11px] font-black rounded-xl transition-all">痍⑥냼</button>
                        </div>
                    </div>
                </div>
            )}

            {channelConfigCategory && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-[70] flex items-center justify-center p-4" onClick={() => setChannelConfigCategory(null)}>
                    <div className="bg-[#0a0a0a] border border-white/10 rounded-2xl p-8 w-full max-w-xl shadow-2xl" onClick={e => e.stopPropagation()}>
                        <div className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">?낅줈??梨꾨꼸 ?ㅼ젙</div>
                        <div className="text-white font-black text-lg mb-2">"{channelConfigCategory.name}" ?낅줈??梨꾨꼸 ?곌껐</div>
                        <p className="text-[12px] text-gray-500 mb-6">??移댄뀒怨좊━?먯꽌 ?앹꽦?섎뒗 ?곸긽? ?ш린??吏?뺥븳 梨꾨꼸濡쒕쭔 ?낅줈?쒕맗?덈떎.</p>

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
                                            {channel.name} ({channel.handle}) {channel.credentials_path ? '쨌 ?곕룞?꾨즺' : '쨌 誘몄뿰??}
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
                                    placeholder="?? ?쏅궇?댁빞湲??곌뎄??
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
                                    濡쒖뺄 梨꾨꼸 ???                                </button>
                                <button type="button" onClick={handleStartCategoryChannelOAuth} className="py-3 bg-purple-600/15 hover:bg-purple-600 text-purple-300 hover:text-white text-[11px] font-black rounded-xl border border-purple-500/20 transition-all">
                                    Google OAuth ?곕룞
                                </button>
                                <button type="button" onClick={handleSaveCategoryChannelBinding} className="py-3 bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-black rounded-xl transition-all">
                                    移댄뀒怨좊━?????                                </button>
                            </div>

                            <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3 text-[11px] text-gray-400 leading-5">
                                1. 濡쒖뺄 梨꾨꼸???좏깮?섍굅???덈줈 ??ν븯怨?br />
                                2. ?꾩슂?섎㈃ Google OAuth ?곕룞???뚮윭 ?몄쬆????br />
                                3. 留덉?留됱쑝濡?移댄뀒怨좊━????ν븯硫???二쇱젣???대떦 梨꾨꼸濡?怨좎젙?⑸땲??
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
