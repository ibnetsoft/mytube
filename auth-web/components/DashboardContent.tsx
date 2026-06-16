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

const SUPER_ADMIN_EMAIL = 'ejsh0519@naver.com'

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
    'video': '📹',
    'image': '🎨',
    'script': '📝',
    'text_gen': '✍️',
    'vision_gen': '👁️',
    'motion_guide': '⚙️',
    'character_extraction': '👤',
    'test_after_fix': '🛠️',
    'test_local': '💻',
    'test_verbose': '🔍',
    'unknown': '❓',
    'prompt': '💡'
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
    const [activeTab, setActiveTab] = useState<'topics' | 'overview' | 'users' | 'api' | 'render-queue' | 'styles'>('topics')
    const [renderQueue, setRenderQueue] = useState<any[]>([])
    const [queueLoading, setQueueLoading] = useState(false)
    const [overviewSubTab, setOverviewSubTab] = useState<'video' | 'log'>('video')

    // 카테고리 & AI 주제 자판기 상태
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
    const [generatingCatId, setGeneratingCatId] = useState<number | null>(null)
    const [generatedTopicsByCat, setGeneratedTopicsByCat] = useState<Record<number, string[]>>({})
    const [topicQueueCategoryFilter, setTopicQueueCategoryFilter] = useState<string>('all')
    
    // 카테고리 리스트 롱폼/숏폼 탭 구분
    const [categoryListTab, setCategoryListTab] = useState<'longform' | 'shorts'>('longform')

    // 카테고리 수정 모달 상태
    const [editCategory, setEditCategory] = useState<any | null>(null)
    const [editCatForm, setEditCatForm] = useState({
        name: '',
        keywords: '',
        benchmark_channel_url: '',
        assigned_employee_email: '',
        default_script_style: 'default',
        default_image_style: 'realistic',
        video_type: 'longform'
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

    // 시스템 전역 API 키 및 구글 드라이브 설정
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
        const amountStr = prompt(isKor ? '충전할 토큰량을 입력하세요' : 'Enter token amount to recharge', '50000');
        if (!amountStr) return;
        const parsedAmount = parseInt(amountStr);
        if (isNaN(parsedAmount) || parsedAmount <= 0) {
            alert(isKor ? '올바른 숫자를 입력해주세요.' : 'Please enter a valid number.');
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
                alert(isKor ? `충전 완료! ${parsedAmount.toLocaleString()} 토큰 추가됨` : `Recharge Success! +${parsedAmount.toLocaleString()} tokens`);
                // 낙관적 업데이트 — fetchUsers() 사용 시 Supabase 캐시로 stale 반환
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
        if (!apiViewUser) return;
        try {
            const res = await fetch('/api/admin/users/api-keys', {
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
                // [FIX] 서버에서 반환된 최신 유저 정보로 즉시 교체하여 동기화 지연 방지
                const updatedUser = data.user;
                if (updatedUser) {
                    setUsers(prev => prev.map(u => u.id === updatedUser.id ? {
                        ...u,
                        user_metadata: updatedUser.user_metadata
                    } : u));
                }
                
                alert(isKor ? "채널 정보가 성공적으로 업데이트되었습니다." : "Channel info updated successfully.");
                setChannelViewUser(null);
                // fetchUsers()를 호출하지 않고 로컬 상태를 우선시함 (Race Condition 해결)
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

    const handleRoleChange = async (userId: string, currentRole: string) => {
        const newRole = currentRole === 'pro' ? 'std' : 'pro';
        if (!confirm(isKor ? `등급을 ${newRole === 'pro' ? '프로' : '스탠다드'}(으)로 변경하시겠습니까?` : `Change membership to ${newRole === 'pro' ? 'PRO' : 'STANDARD'}?`)) return;
        try {
            const res = await fetch('/api/admin/users/role', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId, membership: newRole })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                // 낙관적 업데이트만 사용 (fetchUsers 시 Supabase 캐시로 인해 역행됨)
                setUsers(prev => prev.map(u =>
                    u.id === userId ? { ...u, app_metadata: { ...u.app_metadata, membership: newRole } } : u
                ));
                alert(isKor ? `${newRole === 'pro' ? '💎 프로' : '👤 스탠다드'}로 변경되었습니다.` : 'Role Updated');
            } else {
                alert('변경 실패: ' + (data.error || '서버 오류'));
            }
        } catch (e) { alert('서버 통신 오류'); }
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
            const res = await fetch('/api/admin/users/admin-role', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId, isAdmin: !currentIsAdmin })
            });
            if (res.ok) { alert('완료되었습니다.'); fetchUsers(); }
        } catch (e) { alert('오류가 발생했습니다.'); }
    }

    const handlePublishVideo = async (requestId: string) => {
        if (!confirm(isKor ? '이 영상을 유튜브에서 공개(Public)로 전환하시겠습니까?' : 'Would you like to switch this video to Public on YouTube?')) return;
        try {
            const res = await fetch('/api/admin/publishing', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ requestId, status: 'to_be_published' })
            });
            if (res.ok) {
                alert(isKor ? '전환 요청 완료! 잠시 후 유튜브에 반영됩니다.' : 'Request Complete! Will reflect on YouTube shortly.');
                fetchPublishingRequests();
            } else {
                alert('요청 실패');
            }
        } catch (e) { alert('오류 발생'); }
    }

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
        if (!confirm(isKor ? '이 작업을 대시보드 대기열에서 삭제하시겠습니까?' : 'Delete this render task from the queue?')) return;
        try {
            const res = await fetch(`/api/admin/render-queue?id=${id}`, { method: 'DELETE' });
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
            alert('필수 입력 항목을 채워주세요.')
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
            const res = await fetch(`/api/admin/style-presets?id=${id}`, {
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
        if (!newCatName || !newCatEmployee) {
            alert('카테고리명과 담당 직원 이메일은 필수입니다.')
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
                    video_type: newCatVideoType
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
                fetchCategories()
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
        if (!confirm('정말 이 카테고리를 삭제하시겠습니까? 관련 데이터도 함께 삭제될 수 있습니다.')) return
        try {
            const res = await fetch(`/api/admin/categories?id=${id}`, {
                method: 'DELETE'
            })
            const data = await res.json()
            if (data.success) {
                fetchCategories()
                fetchTopics()
            } else {
                alert('삭제 실패: ' + data.error)
            }
        } catch (err) {
            console.error(err)
        }
    }

    const handleSaveCategory = async () => {
        if (!editCategory) return
        if (!editCatForm.name || !editCatForm.assigned_employee_email) {
            alert('카테고리명과 담당 직원 이메일은 필수입니다.')
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
                alert('성공적으로 수정되었습니다.')
                setEditCategory(null)
                fetchCategories()
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
                alert(`AI가 새로운 세부 영상 주제 ${data.count}개를 성공적으로 생성하여 큐에 추가했습니다!`)
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
            else setUser(session.user);
            setLoading(false);
        });
    }, [router]);

    // 초기 데이터 로딩용 단일 Effect
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

    // 기간 변경 시에만 별도 호출
    useEffect(() => {
        if (isAdmin && !loading) {
            fetchGlobalStats(globalPeriod);
        }
    }, [globalPeriod]);

    if (loading) return <div className="min-h-screen bg-[#050505] text-white flex items-center justify-center font-black animate-pulse uppercase tracking-[0.5em]">관리자 인증 중...</div>;
    if (!isAdmin) return <div className="min-h-screen bg-[#050505] text-red-500 flex items-center justify-center font-black">접근 권한이 없습니다.</div>;

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
                        <span className="text-sm group-hover:scale-110 transition-transform">{typeIcons[task.name] || '📦'}</span>
                    </div>
                    <div>
                        <div className="text-lg font-black text-white mt-1 tabular-nums">{task.count} <span className="text-gray-600 text-[10px]">건</span></div>
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
                        <th className="px-10 py-5 text-right text-orange-500">AI 토큰 소모량</th>
                        <th className="px-10 py-5 text-right text-blue-500">남은 토큰 총량</th>
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
                            <span className="block text-[10px] text-gray-500 font-bold uppercase tracking-widest leading-none">{isSuperAdmin ? '최고 관리자' : '부관리자'}</span>
                            <span className="text-sm font-black text-blue-400">{user?.email}</span>
                        </div>
                        <button onClick={() => supabase.auth.signOut().then(() => router.push('/'))} className="px-6 py-2.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all">로그아웃</button>
                    </div>
                </div>
            </nav>

            <main className="max-w-[1600px] mx-auto px-6 py-8 space-y-12">
                <div className="flex items-center justify-between">
                    <h2 className="text-4xl font-black uppercase tracking-tighter">관리자 대시보드</h2>
                    <div className="flex gap-2 p-1.5 bg-white/5 rounded-2xl border border-white/5 shadow-2xl">
                        {['topics', 'overview', 'users', 'api', 'render-queue', 'styles'].map(tab => (
                            <button key={tab} onClick={() => setActiveTab(tab as any)} className={`px-10 py-3.5 rounded-xl text-[11px] font-black transition-all uppercase tracking-[0.1em] ${activeTab === tab ? 'bg-blue-600 text-white shadow-xl' : 'text-gray-500 hover:text-white'}`}>
                                {tab === 'topics' ? '주제배당' : tab === 'overview' ? '개요' : tab === 'users' ? '유저 관리' : tab === 'api' ? '시스템 API' : tab === 'render-queue' ? '🎬 렌더링 큐' : '🎨 스타일 세팅'}
                            </button>
                        ))}
                    </div>
                </div>

                {activeTab === 'topics' && (
                    <div className="space-y-8 animate-in fade-in duration-300">
                        {/* 1. 카테고리 추가 폼 */}
                        <div className="bg-[#0f172a]/60 rounded-[2.5rem] border border-white/10 p-8 shadow-2xl">
                            <h2 className="font-black text-xl tracking-tight mb-6 flex items-center gap-2">
                                ➕ 새 카테고리 및 직원 매핑 추가
                            </h2>
                            <form onSubmit={handleCreateCategory} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">카테고리명 *</label>
                                    <input 
                                        type="text" 
                                        required
                                        placeholder="예: 세계 미스터리"
                                        value={newCatName}
                                        onChange={e => setNewCatName(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">담당 직원 이메일 *</label>
                                    <select
                                        required
                                        value={newCatEmployee}
                                        onChange={e => setNewCatEmployee(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50 cursor-pointer"
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
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">주요 리서치 키워드</label>
                                    <input 
                                        type="text" 
                                        placeholder="쉼표로 구분 (예: 버뮤다 삼각지대, 미해결 사건)"
                                        value={newCatKeywords}
                                        onChange={e => setNewCatKeywords(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">벤치마킹할 유튜브 채널 URL</label>
                                    <input 
                                        type="url" 
                                        placeholder="예: https://www.youtube.com/@BenchmarkChannel"
                                        value={newCatChannel}
                                        onChange={e => setNewCatChannel(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">기본 대본 스타일 *</label>
                                    <select
                                        required
                                        value={newCatScriptStyle}
                                        onChange={e => setNewCatScriptStyle(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50 cursor-pointer"
                                    >
                                        <option value="default" className="bg-[#111] text-white">기본 설정 (선명하고 자연스럽게)</option>
                                        <option value="story" className="bg-[#111] text-white">옛날 이야기 (구연동화 톤)</option>
                                        <option value="senior_story" className="bg-[#111] text-white">시니어 이야기 (회상/감성 톤)</option>
                                        <option value="news" className="bg-[#111] text-white">뉴스 (정보전달 톤)</option>
                                        <option value="mystery_thriller" className="bg-[#111] text-white">미스터리 스릴러 (긴장감 톤)</option>
                                        <option value="nursery_rhyme" className="bg-[#111] text-white">전래동요풍 (어린이 구연 톤)</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">기본 이미지 화풍 *</label>
                                    <select
                                        required
                                        value={newCatImageStyle}
                                        onChange={e => setNewCatImageStyle(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50 cursor-pointer"
                                    >
                                        <option value="realistic" className="bg-[#111] text-white">실사 (Photorealistic)</option>
                                        <option value="ghibli" className="bg-[#111] text-white">지브리 감성 일러스트 (Ghibli)</option>
                                        <option value="anime" className="bg-[#111] text-white">일본 애니메이션풍 (Anime)</option>
                                        <option value="cinematic" className="bg-[#111] text-white">영화 스틸컷 느낌 (Cinematic)</option>
                                        <option value="cartoon" className="bg-[#111] text-white">2D 카툰 일러스트 (Cartoon)</option>
                                        <option value="nursery_rhyme" className="bg-[#111] text-white">3D 동화/애니 (Nursery/Pixar)</option>
                                        <option value="역사/동양철/다큐" className="bg-[#111] text-white">전통 동양화/수묵화 (Ink Wash)</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">영상 포맷 (형식) *</label>
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
                                            <span>가로형 (Longform)</span>
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
                                            <span>세로형 (Shorts)</span>
                                        </label>
                                    </div>
                                </div>
                                <div className="md:col-span-3 mt-4 flex justify-end">
                                    <button 
                                        type="submit"
                                        className="px-8 py-3 bg-blue-600 hover:bg-blue-500 text-white font-black rounded-xl transition-all shadow-lg active:scale-95"
                                    >
                                        🚀 등록 및 초기 주제 생성
                                    </button>
                                </div>
                            </form>
                        </div>

                        {/* 2. 등록된 카테고리 및 매핑 리스트 */}
                        <div className="bg-[#0f172a]/60 rounded-[2.5rem] border border-white/10 overflow-hidden shadow-2xl p-8">
                            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
                                <h2 className="font-black text-xl tracking-tight">📂 내 카테고리 현황</h2>
                                <div className="flex p-1 bg-black/40 rounded-xl border border-white/10">
                                    <button 
                                        onClick={() => setCategoryListTab('longform')}
                                        className={`px-6 py-2 rounded-lg text-xs font-black transition-all ${categoryListTab === 'longform' ? 'bg-blue-600 text-white shadow' : 'text-gray-500 hover:text-white'}`}
                                    >
                                        가로형 (Longform)
                                    </button>
                                    <button 
                                        onClick={() => setCategoryListTab('shorts')}
                                        className={`px-6 py-2 rounded-lg text-xs font-black transition-all ${categoryListTab === 'shorts' ? 'bg-blue-600 text-white shadow' : 'text-gray-500 hover:text-white'}`}
                                    >
                                        세로형 (Shorts)
                                    </button>
                                </div>
                            </div>

                            {categoriesLoading ? (
                                <div className="text-center py-20 text-gray-500 text-sm">카테고리 로딩 중...</div>
                            ) : categories.filter(c => (c.video_type || 'longform') === categoryListTab).length === 0 ? (
                                <div className="text-center py-20 text-gray-500 text-sm italic">해당 포맷에 등록된 카테고리가 없습니다.</div>
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
                                                                        video_type: cat.video_type || 'longform'
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
                                                    </div>
                                                    <div className="space-y-2 text-xs text-gray-400 mb-6">
                                                        <p>👤 <strong className="text-gray-200">담당 직원:</strong> {cat.assigned_employee_email}</p>
                                                        <p>🔑 <strong className="text-gray-200">키워드:</strong> {cat.keywords || '(없음)'}</p>
                                                        <p className="truncate">📺 <strong className="text-gray-200">채널:</strong> <a href={cat.benchmark_channel_url} target="_blank" rel="noreferrer" className="text-blue-400 underline">{cat.benchmark_channel_url || '(없음)'}</a></p>
                                                        <p>📝 <strong className="text-gray-200">대본 스타일:</strong> {cat.default_script_style || '기본'}</p>
                                                        <p>🎨 <strong className="text-gray-200">화풍:</strong> {cat.default_image_style || '실사'}</p>
                                                        <p>🎬 <strong className="text-gray-200">영상 포맷:</strong> {cat.video_type === 'shorts' ? '세로형 (Shorts)' : '가로형 (Longform)'}</p>
                                                    </div>
                                                    
                                                    {/* 주제 대기열 카운트 */}
                                                    <div className="flex gap-3 text-[11px] font-black tracking-wider uppercase mb-6">
                                                        <span className="px-3 py-1 bg-yellow-500/10 text-yellow-500 border border-yellow-500/20 rounded-lg">대기주제: {pendingTopics.length}개</span>
                                                        <span className="px-3 py-1 bg-green-500/10 text-green-500 border border-green-500/20 rounded-lg">완료주제: {completedTopics.length}개</span>
                                                    </div>
                                                </div>

                                                <button 
                                                    disabled={generatingCatId === cat.id}
                                                    onClick={() => handleTriggerAiTopics(cat.id)}
                                                    className="w-full py-2.5 bg-blue-600/20 hover:bg-blue-600 border border-blue-500/20 hover:border-transparent text-blue-400 hover:text-white rounded-xl text-xs font-black tracking-wider transition-all disabled:bg-gray-800 disabled:text-gray-500 disabled:cursor-not-allowed uppercase"
                                                >
                                                    {generatingCatId === cat.id ? '🤖 AI 주제 분석 발굴 중...' : '🔮 AI 주제 자판기 생성 (10개)'}
                                                </button>

                                                {previewTopics.length > 0 && (
                                                    <div className="mt-4 rounded-2xl border border-blue-500/20 bg-blue-950/20 p-4">
                                                        <div className="mb-3 flex items-center justify-between gap-2">
                                                            <p className="text-[11px] font-black text-blue-300">
                                                                {isFreshPreview ? '방금 생성된 주제 10개' : '대기 중 주제 미리보기'}
                                                            </p>
                                                            <span className="text-[10px] font-bold text-gray-500">{previewTopics.length}개</span>
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

                        {/* 3. 전체 주제 대기열 큐 모니터링 */}
                        {(() => {
                            const getTopicAssignee = (item: any) => item.categories?.assigned_employee_email || item.assigned_employee_email;
                            const isWorkingTopic = (item: any) => item.status === 'assigned';
                            const isQueueVisibleTopic = (item: any) => item.status === 'pending' || item.status === 'assigned';
                            const queueCategories = [...categories].sort((a, b) => {
                                const aActive = topics.filter(t => String(t.category_id) === String(a.id) && isQueueVisibleTopic(t)).length;
                                const bActive = topics.filter(t => String(t.category_id) === String(b.id) && isQueueVisibleTopic(t)).length;
                                if (bActive !== aActive) return bActive - aActive;
                                return String(a.name || '').localeCompare(String(b.name || ''), 'ko');
                            });
                            const filteredTopics = topicQueueCategoryFilter === 'all'
                                ? topics.filter(isQueueVisibleTopic)
                                : topics.filter(t => String(t.category_id) === topicQueueCategoryFilter && isQueueVisibleTopic(t));
                            const selectedCategory = topicQueueCategoryFilter === 'all'
                                ? null
                                : categories.find(cat => String(cat.id) === topicQueueCategoryFilter);

                            return (
                        <div className="bg-[#0f172a]/60 rounded-[2.5rem] border border-white/10 overflow-hidden shadow-2xl">
                            <div className="p-8 border-b border-white/10 bg-black/20">
                                <div className="flex flex-col xl:flex-row xl:items-start xl:justify-between gap-5">
                                    <div className="min-w-0">
                                        <h2 className="font-black text-xl tracking-tight">
                                            📋 실시간 전체 주제 대기열 큐 (Topics Queue)
                                        </h2>
                                        <p className="mt-2 text-xs font-bold text-gray-500">
                                            {selectedCategory ? `${selectedCategory.name} 카테고리만 표시 중` : '전체 카테고리의 대기열을 표시 중'}
                                        </p>
                                    </div>
                                    <span className="shrink-0 bg-yellow-500/20 text-yellow-500 text-[11px] px-3 py-1 rounded-full font-black">
                                        {selectedCategory ? '선택 표시건수' : '총 표시건수'}: {filteredTopics.length}개
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
                                        전체 <span className="ml-1 text-[10px] opacity-70">{topics.filter(isQueueVisibleTopic).length}</span>
                                    </button>
                                    {queueCategories.map(cat => {
                                        const activeCount = topics.filter(t => String(t.category_id) === String(cat.id) && isQueueVisibleTopic(t)).length;
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
                                            <th className="px-10 py-6">배정된 직원 이메일</th>
                                            <th className="px-10 py-6 text-center">배당 상태</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-white/5 font-medium">
                                        {filteredTopics.map((item) => (
                                            <tr key={item.id} className="hover:bg-white/[0.03] transition-colors h-16 text-xs">
                                                <td className="px-10 py-6 text-gray-300 font-bold">
                                                    {item.categories?.name || '기본'}
                                                </td>
                                                <td className="px-10 py-6 text-white font-bold max-w-sm truncate">
                                                    <div className="flex items-center gap-2">
                                                        <span className="truncate">{item.topic}</span>
                                                        {item.is_auto_generated && (
                                                            <span className="bg-purple-500/10 text-purple-400 px-1.5 py-0.5 rounded border border-purple-500/20 font-black text-[8px] tracking-tight shrink-0">
                                                                🤖 AUTO
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
                                                        {item.status === 'pending' ? '대기 중' : isWorkingTopic(item) ? '작업 중' : '제작 완료'}
                                                    </span>
                                                </td>
                                            </tr>
                                        ))}
                                        {filteredTopics.length === 0 && (
                                            <tr>
                                                <td colSpan={4} className="px-10 py-20 text-center text-gray-600 font-black uppercase tracking-widest text-xs italic">
                                                    {selectedCategory ? '선택한 카테고리에 등록된 주제가 없습니다.' : '대기열에 등록된 주제가 없습니다. 카테고리를 먼저 생성해주세요.'}
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
                                    <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">총 유포 토큰</span>
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
                                <StatCard label="DAILY TOKEN USAGE" value={globalStats.totalTokens.toLocaleString()} unit="TOKENS" color="orange" />
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
                                        <h3 className="text-[10px] font-black text-blue-500 uppercase tracking-[0.4em]">승인 대기 및 등록된 영상</h3>
                                    </div>
                                    <table className="w-full text-left">
                                        <thead className="bg-black/30 border-b border-white/5 text-[10px] font-black text-gray-500 uppercase tracking-widest">
                                            <tr><th className="px-10 py-6">영상 정보 / 소유자</th><th className="px-10 py-6 text-center">유튜브 ID</th><th className="px-10 py-6 text-center">등록일시</th><th className="px-10 py-6 text-center">상태</th><th className="px-10 py-6 text-right">관리</th></tr>
                                        </thead>
                                        <tbody className="divide-y divide-white/5">
                                            {publishingRequests.length === 0 ? (
                                                <tr><td colSpan={5} className="px-10 py-20 text-center text-gray-600 font-bold uppercase tracking-widest italic">등록된 영상이 없습니다.</td></tr>
                                            ) : (
                                                publishingRequests.map(req => {
                                                    const owner = users?.find(u => u.id === req.user_id);
                                                    return (
                                                        <tr key={req.id} className="hover:bg-white/[0.03] transition-colors group">
                                                            <td className="px-10 py-6">
                                                                <div className="font-black text-white text-base group-hover:text-blue-400 transition-colors uppercase tracking-tight">{req.metadata?.title || 'Untitled Video'}</div>
                                                                <div className="text-[11px] text-gray-600 font-bold mt-1 uppercase italic tracking-tighter">{owner?.email || req.user_id || 'Unknown User'}</div>
                                                            </td>
                                                            <td className="px-10 py-6 text-center"><a href={`https://youtu.be/${req.metadata?.videoId}`} target="_blank" className="text-[11px] font-black text-blue-500 hover:underline">{req.metadata?.videoId || '-'}</a></td>
                                                            <td className="px-10 py-6 text-center text-[12px] font-black text-gray-500">{new Date(req.created_at).toLocaleString()}</td>
                                                            <td className="px-10 py-6 text-center"><span className={`px-3 py-1 text-[9px] font-black rounded-full border uppercase tracking-widest ${req.status === 'published' ? 'bg-green-500/10 text-green-500 border-green-500/20' : req.status === 'pending' ? 'bg-orange-500/10 text-orange-500 border-orange-500/20' : req.status === 'to_be_published' ? 'bg-blue-500/10 text-blue-500 border-blue-500/20' : 'bg-red-500/10 text-red-500 border-red-500/20'}`}>{req.status === 'pending' ? '대기 중 (비공개)' : req.status === 'to_be_published' ? '공개 전환 중' : req.status.toUpperCase()}</span></td>
                                                            <td className="px-10 py-6 text-right">{req.status === 'pending' && (<button onClick={() => handlePublishVideo(req.id)} className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-[10px] font-black rounded-2xl shadow-lg transition-all uppercase tracking-widest">공개로 전환</button>)}{req.status === 'published' && req.metadata?.driveLink && (<a href={req.metadata.driveLink} target="_blank" className="px-6 py-2.5 bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white text-[10px] font-black rounded-2xl border border-white/10 transition-all uppercase tracking-widest inline-block">백업 확인</a>)}</td>
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
                                            <tr><th className="px-10 py-6">채널명 / 계정</th><th className="px-10 py-6 text-center">생성된 영상수</th><th className="px-10 py-6 text-center">최근 동기화</th><th className="px-10 py-6 text-right">상태</th></tr>
                                        </thead>
                                        <tbody className="divide-y divide-white/5">
                                            {users.slice(0, 5).map(u => {
                                                const userVideos = globalLogs.filter(l => l.user_id === u.id && (l.task_type || '').toLowerCase() === 'video').length;
                                                return (
                                                    <tr key={u.id} className="hover:bg-white/[0.03] transition-colors group">
                                                        <td className="px-10 py-6"><div className="font-black text-white text-base group-hover:text-blue-400 transition-colors uppercase tracking-tight">{u.email}</div><div className="text-[11px] text-gray-600 font-bold mt-1 uppercase italic tracking-tighter">{u.user_metadata?.full_name || '연동된 채널'}</div></td>
                                                        <td className="px-10 py-6 text-center font-black text-white text-xl tabular-nums">{userVideos}</td>
                                                        <td className="px-10 py-6 text-center text-[12px] font-black text-gray-500">{formatDate(u.last_sign_in_at)}</td>
                                                        <td className="px-10 py-6 text-right"><span className="px-3 py-1 bg-green-500/10 text-green-500 text-[9px] font-black rounded-full border border-green-500/20 uppercase">정상연결</span></td>
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
                            <h3 className="text-sm font-black text-gray-400 uppercase tracking-[0.2em]">회원 관리 리스트</h3>
                            <button onClick={fetchUsers} className="px-6 py-2 bg-blue-600/10 hover:bg-blue-600 text-blue-500 hover:text-white text-[10px] font-black rounded-xl border border-blue-500/20 transition-all uppercase tracking-widest">새로고침</button>
                        </div>
                        <table className="w-full text-left">
                            <thead className="bg-black/30 border-b border-white/20 text-xs font-black text-gray-400 uppercase tracking-widest">
                                <tr>
                                    <th className="px-0 py-4 whitespace-nowrap">이름</th>
                                    <th className="px-0 py-4 whitespace-nowrap">이메일 / 등급</th>
                                    <th className="px-0 py-4 whitespace-nowrap">연락처</th>
                                    <th className="px-0 py-4 whitespace-nowrap">국적</th>
                                    <th className="px-0 py-4 whitespace-nowrap">추천인</th>
                                    <th className="px-0 py-4 whitespace-nowrap">채널명</th>
                                    <th className="px-0 py-4 text-center whitespace-nowrap">토큰</th>
                                    <th className="px-0 py-4 text-center whitespace-nowrap">멤버십</th>
                                    <th className="px-0 py-4 text-center whitespace-nowrap">가입일</th>
                                    <th className="px-0 py-4 text-center whitespace-nowrap">최근접속</th>
                                    <th className="px-0 py-4 text-center whitespace-nowrap">관리</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-white/20">
                                {users.map(u => (
                                    <tr key={u.id} className="hover:bg-white/[0.03] transition-colors group">
                                        {/* 이름 */}
                                        <td className="px-1 py-4">
                                            <div className="font-black text-white text-xs whitespace-nowrap">{u.user_metadata?.full_name || <span className="text-gray-600 italic">없음</span>}</div>
                                        </td>
                                        {/* 이메일 / 관리자 등급 */}
                                        <td className="px-1 py-4 max-w-[160px]">
                                            <div className="font-bold text-blue-400 text-[10px] tracking-tight truncate">{u.email?.toLowerCase()}</div>
                                            <div className="flex gap-1 mt-0.5 flex-wrap">
                                                {u.email === SUPER_ADMIN_EMAIL && <span className="px-1 py-0.5 bg-blue-600 text-[7px] font-black rounded text-white">최고관리자</span>}
                                                {u.app_metadata?.is_admin && u.email !== SUPER_ADMIN_EMAIL && <span className="px-1 py-0.5 bg-indigo-500 text-[7px] font-black rounded text-white">부관리자</span>}
                                            </div>
                                        </td>
                                        {/* 연락처 */}
                                        <td className="px-1 py-4 text-[10px] text-gray-300 font-bold whitespace-nowrap">
                                            {u.user_metadata?.contact || <span className="text-gray-700">-</span>}
                                        </td>
                                        {/* 국적 */}
                                        <td className="px-1 py-4 text-[10px] text-gray-300 font-bold whitespace-nowrap">
                                            {u.user_metadata?.nationality || <span className="text-gray-700">-</span>}
                                        </td>
                                        {/* 추천인 */}
                                        <td className="px-1 py-4 text-[10px] whitespace-nowrap">
                                            {u.user_metadata?.referrer
                                                ? <span className="text-yellow-400 font-bold">{u.user_metadata.referrer}</span>
                                                : <span className="text-gray-700">-</span>}
                                        </td>
                                        {/* 채널명 */}
                                        <td className="px-1 py-4 max-w-[110px]">
                                            {u.user_metadata?.youtube_channel
                                                ? <span className="flex items-center gap-1 text-red-400 text-[10px] font-black truncate"><span className="w-1.5 h-1.5 bg-red-500 rounded-full animate-pulse shrink-0 inline-block"></span>{u.user_metadata.youtube_channel}</span>
                                                : <span className="text-gray-700 text-xs">-</span>}
                                        </td>
                                        {/* 보유 토큰 */}
                                        <td className="px-1 py-4 text-center font-black text-white text-sm tabular-nums whitespace-nowrap">
                                            {u.profile?.token_balance?.toLocaleString() || 0}
                                        </td>
                                        {/* 멤버십 */}
                                        <td className="px-1 py-4 text-center">
                                            <button onClick={() => handleRoleChange(u.id, u.app_metadata?.membership)} className={`px-2 py-1 rounded-lg text-[8px] font-black border uppercase tracking-widest transition-all whitespace-nowrap ${u.app_metadata?.membership === 'pro' ? 'bg-indigo-600 text-white border-indigo-500 shadow-lg' : 'bg-white/5 text-gray-500 border-white/10 hover:border-white/30'}`}>
                                                {u.app_metadata?.membership?.toUpperCase() === 'PRO' ? '💎 프로' : '👤 스탠다드'}
                                            </button>
                                        </td>
                                        {/* 가입일 */}
                                        <td className="px-1 py-4 text-center text-[10px] font-bold text-gray-500 whitespace-nowrap">{formatDate(u.created_at)}</td>
                                        {/* 최근접속 */}
                                        <td className="px-1 py-4 text-center text-[10px] font-bold text-gray-500 whitespace-nowrap">{formatDate(u.last_sign_in_at)}</td>
                                        {/* 관리 메뉴 — 3x2 그리드 */}
                                        <td className="px-1 py-4">
                                            <div className="grid grid-cols-3 gap-1">
                                                {isSuperAdmin && u.email !== SUPER_ADMIN_EMAIL
                                                    ? <button onClick={() => handleAdminRoleToggle(u.id, !!u.app_metadata?.is_admin)} className={`px-1.5 py-1 rounded text-[7px] font-black border transition-all whitespace-nowrap ${u.app_metadata?.is_admin ? 'bg-indigo-600/20 text-indigo-400 border-indigo-500/30' : 'bg-white/5 text-gray-600 border-white/10'}`}>권한관리</button>
                                                    : <span />
                                                }
                                                <button onClick={() => handleRecharge(u.id)} className="px-1.5 py-1 bg-green-600/10 hover:bg-green-600 text-green-500 hover:text-white text-[7px] font-black rounded border border-green-500/20 transition-all whitespace-nowrap">토큰충전</button>
                                                <button onClick={() => { setEditInfoUser(u); setEditInfoForm({ full_name: u.user_metadata?.full_name || '', nationality: u.user_metadata?.nationality || '', contact: u.user_metadata?.contact || '' }); }} className="px-1.5 py-1 bg-yellow-600/10 hover:bg-yellow-600 text-yellow-500 hover:text-white text-[7px] font-black rounded border border-yellow-500/20 transition-all whitespace-nowrap">정보수정</button>
                                                <button onClick={() => { setLogViewUser(u); setLogPeriod(1); fetchUserLogs(u.id, 1); }} className="px-1.5 py-1 bg-blue-600/10 hover:bg-blue-600 text-blue-500 hover:text-white text-[7px] font-black rounded border border-blue-500/20 transition-all whitespace-nowrap">로그조회</button>
                                                <button onClick={() => { setChannelViewUser(u); setTempChannelInfo({ name: u.user_metadata?.youtube_channel || '', id: u.user_metadata?.youtube_channel_id || '', proxy: u.user_metadata?.youtube_channel_proxy || '' }); }} className="px-1.5 py-1 bg-purple-600/10 hover:bg-purple-600 text-purple-500 hover:text-white text-[7px] font-black rounded border border-purple-500/20 transition-all whitespace-nowrap">채널ID</button>
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
                            <h3 className="text-sm font-black text-gray-400 uppercase tracking-[0.2em]">시스템 전역 API 키</h3>
                            <p className="text-[10px] text-gray-600 mt-1">서버 공용 키 — 개인 키가 없는 유저에게 적용됩니다.</p>
                        </div>
                        <div className="p-10 space-y-6">
                            <div className="grid grid-cols-1 xl:grid-cols-2 gap-8 items-start">
                                <div className="space-y-6">
                            {([
                                { key: 'gemini', label: '✨ Gemini API Key' },
                                { key: 'youtube', label: '▶️ YouTube Data API Key' },
                                { key: 'elevenlabs', label: '🎙️ ElevenLabs API Key' },
                                { key: 'topview', label: '🛒 TopView API Key' },
                                { key: 'topview_uid', label: '🛒 TopView UID' },
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
                                        className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-gray-300 placeholder:text-gray-700"
                                    />
                                </div>
                            ))}
                                </div>

                            {/* Google Drive Queue Configuration section */}
                            <div className="space-y-4 xl:border-l xl:border-white/10 xl:pl-8">
                                <h4 className="text-xs font-black text-blue-400 uppercase tracking-widest mb-2">📁 구글 드라이브 렌더 대기열 설정</h4>
                                
                                <div className="flex items-center gap-3 bg-white/[0.02] p-4 rounded-xl border border-white/5">
                                    <input 
                                        type="checkbox" 
                                        id="use_external_render" 
                                        checked={sysKeys.use_external_render} 
                                        onChange={e => setSysKeys(prev => ({ ...prev, use_external_render: e.target.checked }))}
                                        className="w-4 h-4 rounded text-blue-500 bg-black border-white/10 cursor-pointer"
                                    />
                                    <div className="text-xs">
                                        <label htmlFor="use_external_render" className="font-bold text-gray-300 cursor-pointer">외부 렌더 대기열 사용 (Google Drive File Stream 연동)</label>
                                        <p className="text-[10px] text-gray-500 mt-0.5">활성화 시, 각 생성 단계 및 비디오 렌더 파일이 아래 설정된 구글 드라이브 경로로 동기화됩니다.</p>
                                    </div>
                                </div>

                                <div className="space-y-4">
                                    <div>
                                        <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">우선 적용 언어 경로 (활성 설정)</label>
                                        <select 
                                            value={sysKeys.drive_active_lang}
                                            onChange={e => setSysKeys(prev => ({ ...prev, drive_active_lang: e.target.value }))}
                                            className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 text-gray-300 cursor-pointer"
                                        >
                                            <option value="ko" className="bg-[#111]">한국어 (Korean OS 경로 적용)</option>
                                            <option value="en" className="bg-[#111]">영어 (English OS 경로 적용)</option>
                                            <option value="ja" className="bg-[#111]">일본어 (Japanese OS 경로 적용)</option>
                                        </select>
                                    </div>

                                    <div>
                                        <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">🇰🇷 한국어 Windows 경로 (DRIVE_PATH_KO)</label>
                                        <input 
                                            type="text" 
                                            value={sysKeys.drive_path_ko} 
                                            onChange={e => setSysKeys(prev => ({ ...prev, drive_path_ko: e.target.value }))}
                                            placeholder="G:/내 드라이브/Longform_Render_Queue"
                                            className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-gray-300"
                                        />
                                    </div>

                                    <div>
                                        <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">🇺🇸 영어 Windows 경로 (DRIVE_PATH_EN)</label>
                                        <input 
                                            type="text" 
                                            value={sysKeys.drive_path_en} 
                                            onChange={e => setSysKeys(prev => ({ ...prev, drive_path_en: e.target.value }))}
                                            placeholder="G:/My Drive/Longform_Render_Queue"
                                            className="w-full bg-black/40 border border-white/10 text-xs px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-gray-300"
                                        />
                                    </div>

                                    <div>
                                        <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2 block">🇯🇵 일본어 Windows 경로 (DRIVE_PATH_JA)</label>
                                        <input 
                                            type="text" 
                                            value={sysKeys.drive_path_ja} 
                                            onChange={e => setSysKeys(prev => ({ ...prev, drive_path_ja: e.target.value }))}
                                            placeholder="G:/マイドライブ/Longform_Render_Queue"
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
                                <p className="text-[10px] text-gray-500">API 방식 원격 렌더링에서 에셋 ZIP을 업로드할 Drive 폴더 ID입니다.</p>
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
                                <p className="text-[10px] text-gray-500">메인 PC와 원격 워커가 Drive API 인증에 사용할 OAuth 토큰 파일 경로입니다.</p>
                            </div>

                            {sysKeysSaved && <p className="text-xs text-green-400 font-bold text-center">✅ 저장 완료</p>}

                            <button
                                onClick={saveSysKeys}
                                disabled={sysKeysSaving}
                                className="w-full py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white font-black rounded-2xl transition-all text-sm mt-4"
                            >
                                {sysKeysSaving ? '저장 중...' : '💾 키 저장하기'}
                            </button>
                        </div>
                    </div>
                )}
                {activeTab === 'render-queue' && (
                    <div className="bg-[#0f172a]/20 border border-white/5 rounded-[3rem] overflow-hidden shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <div className="px-10 py-6 border-b border-white/5 bg-black/20 flex justify-between items-center">
                            <div>
                                <h3 className="text-sm font-black text-gray-400 uppercase tracking-[0.2em]">원격 비디오 렌더링 큐</h3>
                                <p className="text-[10px] text-gray-600 mt-1">GPU 서버의 실시간 비디오 인코딩 대기 및 진행 상태를 모니터링합니다.</p>
                            </div>
                            <button onClick={fetchRenderQueue} className="px-6 py-2 bg-blue-600/10 hover:bg-blue-600 text-blue-500 hover:text-white text-[10px] font-black rounded-xl border border-blue-500/20 transition-all uppercase tracking-widest">새로고침</button>
                        </div>
                        <div className="p-10">
                            {queueLoading && renderQueue.length === 0 ? (
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
                                                <th className="px-4 py-4 text-center">진행도</th>
                                                <th className="px-4 py-4">메시지</th>
                                                <th className="px-4 py-4 text-center">작업 관리</th>
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
                                                            {task.status === 'pending' ? '대기 중' : task.status === 'rendering' ? '렌더링 중' : task.status === 'completed' ? '완료' : '실패'}
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
                                                        <button onClick={() => handleDeleteQueueTask(task.id)} className="px-3 py-1.5 bg-red-600/10 hover:bg-red-600 text-red-500 hover:text-white rounded-lg border border-red-500/20 hover:border-red-600 transition-all font-black text-[10px]">삭제</button>
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
                        {/* 1. 스타일 추가/수정 폼 */}
                        <div ref={presetFormRef} className={`rounded-[2.5rem] border p-8 shadow-2xl scroll-mt-24 transition-all duration-300 ${presetId ? 'bg-blue-950/40 border-blue-500/40' : 'bg-[#0f172a]/60 border-white/10'}`}>
                            <h2 className="font-black text-xl tracking-tight mb-6 flex items-center gap-2">
                                🎨 {presetId ? '스타일 프리셋 수정' : '➕ 새 스타일 프리셋 추가'}
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
                                        <option value="image">🎨 이미지 스타일 (Image Style)</option>
                                        <option value="script">📝 대본 스타일 (Script Style)</option>
                                        <option value="thumbnail">🖼️ 썸네일 스타일 (Thumbnail Style)</option>
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
                                        placeholder="예: Điện ảnh thực tế"
                                        value={presetNameVi}
                                        onChange={e => setPresetNameVi(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">프리셋 썸네일 이미지 URL</label>
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
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">AI 추가 지시사항 (Grounded Gemini Instruction - 이미지 스타일 전용)</label>
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
                                        {isSavingPreset ? '저장 중...' : '💾 프리셋 저장'}
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
                                    🔄 새로고침
                                </button>
                            </div>
                            <div className="p-6">
                                {presetsLoading ? (
                                    <div className="text-center text-xs text-gray-500 py-10">프리셋 로딩 중...</div>
                                ) : (
                                    <div className="grid grid-cols-1 gap-8">
                                        {['image', 'script', 'thumbnail'].map(type => {
                                            const typePresets = stylePresets.filter((p: any) => p.preset_type === type);
                                            const typeLabel = type === 'image' ? '🎨 이미지 스타일' : type === 'script' ? '📝 대본 스타일' : '🖼️ 썸네일 스타일';
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
                                                                                    ✏️ 수정
                                                                                </button>
                                                                                <button
                                                                                    onClick={() => handleDeletePreset(preset.id, preset.key_code)}
                                                                                    className="p-1 hover:bg-white/5 rounded text-red-500 text-xs"
                                                                                    title="삭제"
                                                                                >
                                                                                    🗑️
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
                                                                                💡 Instruction: {preset.gemini_instruction}
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
                            <div><h3 className="text-3xl font-black uppercase italic tracking-tighter text-blue-500">유저 전용 API 설정</h3><p className="text-sm text-gray-500 mt-2 uppercase tracking-widest font-black italic">{apiViewUser.email}</p></div>
                            <div className="space-y-6">{['openai', 'gemini', 'pexels', 'replicate'].map(key => (
                                <div key={key} className="space-y-2">
                                    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest ml-4">{key.toUpperCase()} API 키</label>
                                    <input type="text" placeholder={`입력하세요...`} value={tempApiKeys[key] || ''} onChange={(e) => setTempApiKeys({...tempApiKeys, [key]: e.target.value})} className="w-full bg-black/40 border border-white/5 rounded-2xl px-8 py-5 text-sm font-black text-white focus:outline-none focus:border-blue-500/50 transition-all" />
                                </div>
                            ))}</div>
                            <button onClick={handleUpdateApiKeys} className="w-full py-6 bg-blue-600 hover:bg-blue-500 text-white font-black rounded-[2rem] shadow-xl shadow-blue-500/20 transition-all active:scale-95 uppercase tracking-widest text-sm">저장 및 적용</button>
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
                                    <p className="text-[9px] text-gray-600 ml-4 font-bold">* 해당 채널 영상 업로드 시 지정한 프록시 IP 대역을 경유하여 타겟 국가 노출 확률을 높입니다.</p>
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
                        <div className="text-white font-black text-lg mb-6">"{editCategory.name}" 설정 관리</div>
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
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">벤치마킹할 유튜브 채널 URL</label>
                                <input 
                                    type="url"
                                    value={editCatForm.benchmark_channel_url} 
                                    onChange={e => setEditCatForm(p => ({ ...p, benchmark_channel_url: e.target.value }))}
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50" 
                                    placeholder="유튜브 채널 주소" 
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">기본 대본 스타일</label>
                                <select
                                    value={editCatForm.default_script_style}
                                    onChange={e => setEditCatForm(p => ({ ...p, default_script_style: e.target.value }))}
                                    className="w-full bg-[#111] border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50 cursor-pointer"
                                >
                                    <option value="default" className="bg-[#111] text-white">기본 설정 (선명하고 자연스럽게)</option>
                                    <option value="story" className="bg-[#111] text-white">옛날 이야기 (구연동화 톤)</option>
                                    <option value="senior_story" className="bg-[#111] text-white">시니어 이야기 (회상/감성 톤)</option>
                                    <option value="news" className="bg-[#111] text-white">뉴스 (정보전달 톤)</option>
                                    <option value="mystery_thriller" className="bg-[#111] text-white">미스터리 스릴러 (긴장감 톤)</option>
                                    <option value="nursery_rhyme" className="bg-[#111] text-white">전래동요풍 (어린이 구연 톤)</option>
                                </select>
                            </div>
                            <div>
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-1">기본 이미지 화풍</label>
                                <select
                                    value={editCatForm.default_image_style}
                                    onChange={e => setEditCatForm(p => ({ ...p, default_image_style: e.target.value }))}
                                    className="w-full bg-[#111] border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500/50 cursor-pointer"
                                >
                                    <option value="realistic" className="bg-[#111] text-white">실사 (Photorealistic)</option>
                                    <option value="ghibli" className="bg-[#111] text-white">지브리 감성 일러스트 (Ghibli)</option>
                                    <option value="anime" className="bg-[#111] text-white">일본 애니메이션풍 (Anime)</option>
                                    <option value="cinematic" className="bg-[#111] text-white">영화 스틸컷 느낌 (Cinematic)</option>
                                    <option value="cartoon" className="bg-[#111] text-white">2D 카툰 일러스트 (Cartoon)</option>
                                    <option value="nursery_rhyme" className="bg-[#111] text-white">3D 동화/애니 (Nursery/Pixar)</option>
                                    <option value="역사/동양철/다큐" className="bg-[#111] text-white">전통 동양화/수묵화 (Ink Wash)</option>
                                </select>
                             </div>
                             <div>
                                 <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-2">영상 포맷 (형식) *</label>
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
                                         <span>가로형 (Longform)</span>
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
                                         <span>세로형 (Shorts)</span>
                                     </label>
                                 </div>
                             </div>
                        </div>
                        <div className="flex gap-3 mt-6">
                            <button onClick={handleSaveCategory} className="flex-1 py-3 bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-black rounded-xl transition-all uppercase tracking-widest">수정완료</button>
                            <button onClick={() => setEditCategory(null)} className="px-6 py-3 bg-white/5 hover:bg-white/10 text-gray-400 text-[11px] font-black rounded-xl transition-all">취소</button>
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
