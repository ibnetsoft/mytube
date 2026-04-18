'use client'

import { useEffect, useState, useCallback, useMemo } from 'react'
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
    const [activeTab, setActiveTab] = useState<'overview' | 'users' | 'api'>('overview')
    const [overviewSubTab, setOverviewSubTab] = useState<'video' | 'log'>('video')
    
    // UI Modals State
    const [logViewUser, setLogViewUser] = useState<UserProfile | null>(null)
    const [apiViewUser, setApiViewUser] = useState<any>(null);
    const [channelViewUser, setChannelViewUser] = useState<any>(null);
    const [tempApiKeys, setTempApiKeys] = useState<any>({ openai: '', gemini: '', pexels: '', replicate: '' });
    const [tempChannelInfo, setTempChannelInfo] = useState<any>({ name: '', id: '' });
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
                fetchUsers();
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
                        youtube_channel_id: tempChannelInfo.id 
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
        coreTasks.forEach(task => {
            breakdown[task] = { tokens: 0, count: 0, buckets: new Array(days === 1 ? 24 : days).fill(0).map(() => ({ tokens: 0, count: 0 })) };
        });
        if (!logs || !logs.length) return { total: 0, successRate: 0, avgLatency: 0, totalTokens: 0, breakdown };
        const total = logs.length;
        const successes = logs.filter(l => (l.status || '').toLowerCase() === 'success' || (l.status || '').toLowerCase() === 'done').length;
        const tokens = logs.reduce((acc, l) => acc + (l.input_tokens || 0) + (l.output_tokens || 0), 0);
        logs.forEach(l => {
            const stage = (l.task_type || 'unknown').toLowerCase();
            if (!breakdown[stage]) breakdown[stage] = { tokens: 0, count: 0, buckets: new Array(days === 1 ? 24 : days).fill(0).map(() => ({ tokens: 0, count: 0 })) };
            const t = (l.input_tokens || 0) + (l.output_tokens || 0);
            breakdown[stage].tokens += t;
            breakdown[stage].count += 1;
        });
        const avgLat = total > 0 ? parseFloat((logs.reduce((acc, l) => acc + (l.elapsed_time || 0), 0) / total).toFixed(1)) : 0;
        return { total, successRate: total > 0 ? Math.round((successes / total)*100) : 0, avgLatency: avgLat, totalTokens: tokens, breakdown };
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
        }
    }, [isAdmin, loading]);

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
                <div className="absolute inset-5 bg-[#0f172a] rounded-full flex flex-col items-center justify-center overflow-hidden">
                    <span className="text-[9px] font-black text-gray-500 uppercase tracking-tighter">EXPEND</span>
                    <span className="text-[7px] text-blue-500 font-bold">TOKENS</span>
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
                    <tr><th className="px-10 py-5">TIME</th><th className="px-10 py-5">TASK</th><th className="px-10 py-5">MODEL & PROVIDER</th><th className="px-10 py-5">PROMPT SUMMARY</th><th className="px-10 py-5 text-right">TOKENS (IN/OUT)</th><th className="px-10 py-5 text-center">STATUS</th></tr>
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
                            <td className="px-10 py-5 text-right font-black text-white text-[12px]">{(log.input_tokens+log.output_tokens).toLocaleString()} <span className="text-gray-600 text-[10px]">TK</span></td>
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
                        {['overview', 'users', 'api'].map(tab => (
                            <button key={tab} onClick={() => setActiveTab(tab as any)} className={`px-10 py-3.5 rounded-xl text-[11px] font-black transition-all uppercase tracking-[0.1em] ${activeTab === tab ? 'bg-blue-600 text-white shadow-xl' : 'text-gray-500 hover:text-white'}`}>
                                {tab === 'overview' ? '개요' : tab === 'users' ? '유저 관리' : '시스템 API'}
                            </button>
                        ))}
                    </div>
                </div>

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
                                                <button onClick={() => { setChannelViewUser(u); setTempChannelInfo({ name: u.user_metadata?.youtube_channel || '', id: u.user_metadata?.youtube_channel_id || '' }); }} className="px-1.5 py-1 bg-purple-600/10 hover:bg-purple-600 text-purple-500 hover:text-white text-[7px] font-black rounded border border-purple-500/20 transition-all whitespace-nowrap">채널ID</button>
                                                <button onClick={() => { setApiViewUser(u); setTempApiKeys(u.app_metadata?.custom_api_keys || { openai: '', gemini: '', pexels: '', replicate: '' }); }} className="px-1.5 py-1 bg-indigo-600/10 hover:bg-indigo-600 text-indigo-500 hover:text-white text-[7px] font-black rounded border border-indigo-500/20 transition-all whitespace-nowrap">API</button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
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
                                    <p className="text-[10px] text-gray-600 ml-4 font-bold">* 관리자가 수동으로 연동 채널을 지정하거나 정보를 수정할 수 있습니다.</p>
                                </div>
                            </div>
                            <div className="flex gap-4">
                                <button 
                                    onClick={handleUpdateChannelInfo} 
                                    disabled={savingChannel}
                                    className={`flex-1 py-6 font-black rounded-[2rem] shadow-xl transition-all active:scale-95 uppercase tracking-widest text-sm ${savingChannel ? 'bg-gray-800 text-gray-500 cursor-not-allowed' : 'bg-purple-600 hover:bg-purple-500 text-white'}`}
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
                                        const url = `http://127.0.0.1:8000/api/channels/login-by-info?name=${encodeURIComponent(tempChannelInfo.name)}&id=${encodeURIComponent(tempChannelInfo.id)}`;
                                        window.open(url, '_blank', 'width=600,height=700');
                                        
                                        // 메타데이터 정보 저장은 별도로 수행
                                        handleUpdateChannelInfo();
                                    }}
                                    className="px-10 py-6 bg-white text-black font-black rounded-[2rem] shadow-xl hover:bg-gray-100 transition-all active:scale-95 flex items-center gap-3"
                                >
                                    <svg className="w-5 h-5" viewBox="0 0 24 24">
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
            
            <style jsx global>{`
                .custom-scrollbar::-webkit-scrollbar { width: 4px; }
                .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(55,130,246,0.3); border-radius: 10px; }
            `}</style>
        </div>
    )
}
