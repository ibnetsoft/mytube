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

const ADMIN_EMAIL = 'ejsh0519@naver.com'

const typeMap: Record<string, string> = {
    'video': '영상 생성',
    'image': '이미지 생성',
    'script': '대본 생성',
    'text_gen': '텍스트 기술',
    'vision_gen': '비전 분석',
    'test_after_fix': '자막 교정',
    'test_local': '로컬 테스트',
    'test_verbose': '상세 분석',
    'unknown': '기타',
    'prompt': '프롬프트 최적화'
};

const typeIcons: Record<string, string> = {
    'video': '📹',
    'image': '🎨',
    'script': '📝',
    'text_gen': '✍️',
    'vision_gen': '👁️',
    'test_after_fix': '🛠️',
    'test_local': '💻',
    'test_verbose': '🔍',
    'unknown': '❓',
    'prompt': '💡'
};

function StatCard({ label, value, unit, color, subLabel }: { label: string; value: string | number; unit: string; color: string; subLabel?: string }) {
    const textColor = color === 'green' ? 'text-[#22c55e]' : color === 'orange' ? 'text-[#f97316]' : color === 'blue' ? 'text-blue-500' : 'text-white';
    return (
        <div className="bg-[#0f172a]/40 border border-white/5 p-6 rounded-2xl flex flex-col justify-center min-h-[110px] relative overflow-hidden group">
            <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
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
    const [activeTab, setActiveTab] = useState<'overview' | 'users' | 'api'>('overview')
    const [overviewSubTab, setOverviewSubTab] = useState<'video' | 'log'>('video')
    
    // UI Modals State
    const [logViewUser, setLogViewUser] = useState<UserProfile | null>(null)
    const [apiViewUser, setApiViewUser] = useState<UserProfile | null>(null)
    const [tempApiKeys, setTempApiKeys] = useState<any>({ openai: '', gemini: '', pexels: '', replicate: '' })
    
    // Data Stats State
    const [globalLogs, setGlobalLogs] = useState<any[]>([])
    const [userLogs, setUserLogs] = useState<any[]>([])
    const [logsLoading, setLogsLoading] = useState(false)
    const [logPeriod, setLogPeriod] = useState(1)
    const [logStats, setLogStats] = useState({ total: 0, successRate: 0, avgLatency: 0, totalTokens: 0, breakdown: {} as any })
    const [globalPeriod, setGlobalPeriod] = useState(1)
    const [globalStats, setGlobalStats] = useState({ total: 0, successRate: 0, avgLatency: 0, totalTokens: 0, breakdown: {} as any })
    const [globalLoading, setGlobalLoading] = useState(false)

    // Business Logic
    const memberCount = useMemo(() => (users || []).length, [users]);
    const todayStr = useMemo(() => new Date().toISOString().split('T')[0], []);
    const newToday = useMemo(() => (users || []).filter((u: any) => u.created_at?.startsWith(todayStr)).length, [users, todayStr]);
    const activeToday = useMemo(() => (users || []).filter((u: any) => u.last_sign_in_at?.startsWith(todayStr)).length, [users, todayStr]);
    const totalTokens = useMemo(() => (users || []).reduce((acc: number, u: any) => acc + (u.profile?.token_balance || 0), 0), [users]);

    const getTopTasks = (breakdown: any) => {
        const priority = ['video', 'image', 'script', 'text_gen', 'vision_gen', 'test_after_fix'];
        const entries = Object.entries(breakdown || {})
            .map(([key, val]: [string, any]) => ({ name: key, ...val }));
            
        return [...entries].sort((a, b) => {
            const aPri = priority.indexOf(a.name);
            const bPri = priority.indexOf(b.name);
            if (aPri !== -1 && bPri !== -1) return aPri - bPri;
            if (aPri !== -1) return -1;
            if (bPri !== -1) return 1;
            return b.count - a.count;
        }).slice(0, 6);
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
        } catch (e) {
            alert("오류 발생");
        }
    }

    const handleRoleChange = async (userId: string, currentRole: string) => {
        const newRole = currentRole === 'pro' ? 'std' : 'pro';
        if (!confirm(isKor ? `등급을 ${newRole.toUpperCase()}(으)로 변경하시겠습니까?` : `Change membership to ${newRole.toUpperCase()}?`)) return;
        try {
            const res = await fetch('/api/admin/users/role', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId, membership: newRole })
            });
            if (res.ok) { alert(isKor ? '변경 완료' : 'Role Updated'); fetchUsers(); }
        } catch (e) { alert('Error'); }
    }

    const calcGeneralStats = (logs: any[], days: number) => {
        const coreTasks = ['video', 'image', 'script', 'text_gen', 'vision_gen', 'test_after_fix'];
        const breakdown: any = {};
        coreTasks.forEach(task => {
            breakdown[task] = { 
                tokens: 0, 
                count: 0, 
                buckets: new Array(days === 1 ? 24 : days).fill(0).map(() => ({ tokens: 0, count: 0 })) 
            };
        });

        if (!logs || !logs.length) return { total: 0, successRate: 0, avgLatency: 0, totalTokens: 0, breakdown };
        
        const total = logs.length;
        const successes = logs.filter(l => (l.status || '').toLowerCase() === 'success' || (l.status || '').toLowerCase() === 'done').length;
        const tokens = logs.reduce((acc, l) => acc + (l.input_tokens || 0) + (l.output_tokens || 0), 0);
        
        logs.forEach(l => {
            const stage = (l.task_type || 'unknown').toLowerCase();
            if (!breakdown[stage]) {
                breakdown[stage] = { tokens: 0, count: 0, buckets: new Array(days === 1 ? 24 : days).fill(0).map(() => ({ tokens: 0, count: 0 })) };
            }
            const t = (l.input_tokens || 0) + (l.output_tokens || 0);
            breakdown[stage].tokens += t;
            breakdown[stage].count += 1;
        });
        
        return { total, successRate: total > 0 ? Math.round((successes / total)*100) : 0, avgLatency: 7.3, totalTokens: tokens, breakdown };
    }

    const fetchGlobalStats = useCallback(async (days: number) => {
        if (user?.email !== ADMIN_EMAIL) return;
        setGlobalLoading(true);
        try {
            const res = await fetch(`/api/admin/logs?days=${days}&t=${Date.now()}`);
            const data = await res.json();
            setGlobalLogs(data.logs || []);
            setGlobalStats(calcGeneralStats(data.logs || [], days));
        } finally { setGlobalLoading(false); }
    }, [user]);

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
        if (user?.email?.toLowerCase() !== ADMIN_EMAIL.toLowerCase()) return;
        try {
            const res = await fetch(`/api/admin/users?t=${Date.now()}`);
            const data = await res.json();
            if (data.users) setUsers(data.users);
        } catch (e) { console.error("FetchUsers Error:", e); }
    }, [user]);

    useEffect(() => {
        supabase.auth.getSession().then(({ data: { session } }) => {
            if (!session) router.push('/');
            else setUser(session.user);
            setLoading(false);
        });
    }, [router]);

    useEffect(() => {
        if (user?.email?.toLowerCase() === ADMIN_EMAIL.toLowerCase()) {
            if (activeTab === 'overview') fetchGlobalStats(globalPeriod);
            if (activeTab === 'users' || activeTab === 'overview') fetchUsers();
        }
    }, [user, activeTab, globalPeriod, fetchGlobalStats, fetchUsers]);

    if (loading) return <div className="min-h-screen bg-[#050505] text-white flex items-center justify-center font-black animate-pulse uppercase tracking-[0.5em]">시스템 주입중...</div>;

    function formatDate(d: string | null) {
        if (!d) return '-';
        const date = new Date(d);
        return `${date.getFullYear()}.${String(date.getMonth()+1).padStart(2,'0')}.${String(date.getDate()).padStart(2,'0')}`;
    }

    const renderChartRow = (stats: any, topTasks: any[]) => (
        <div className="flex flex-col lg:flex-row gap-4">
            <div className="flex-1 grid grid-cols-6 gap-3">
                {topTasks.map((task: any) => (
                    <div key={task.name} className="bg-[#0f172a]/60 border border-white/5 p-5 rounded-2xl flex flex-col justify-between min-h-[170px] hover:border-blue-500/30 transition-all">
                        <div className="flex justify-between items-start">
                             <div className="text-[10px] font-black text-gray-500 uppercase tracking-widest">{typeMap[task.name] || task.name}</div>
                             <span className="text-sm">{typeIcons[task.name] || '📦'}</span>
                        </div>
                        <div className="text-sm font-black text-white mt-1">{task.count} <span className="text-gray-600 text-[10px]">건</span></div>
                        <div className="h-16 w-full mt-4 flex items-end bg-white/[0.02] rounded-lg p-2 gap-[2px]">
                             <div className="w-1.5 bg-blue-500/20 rounded-full h-full relative overflow-hidden">
                                  <div className="absolute bottom-0 w-full bg-blue-500 rounded-full transition-all duration-1000" style={{ height: `${Math.min(100, (task.count / 10) * 100)}%` }} />
                             </div>
                             <div className="flex-1 italic text-[9px] text-gray-600 self-center ml-2">DATA_POINT</div>
                        </div>
                        <div className="text-[12px] font-black text-blue-500 mt-2">{task.tokens.toLocaleString()}<span className="text-[8px] text-gray-600 ml-1">TK</span></div>
                    </div>
                ))}
            </div>
            <div className="w-full lg:w-[320px] bg-[#0f172a]/60 border border-white/5 rounded-2xl p-6 flex flex-col items-center justify-center">
                <div className="relative w-32 h-32 rounded-full mb-4 flex items-center justify-center" style={{ 
                    background: `conic-gradient(${
                        Object.entries(stats.breakdown || {}).map(([stage, data]: [string, any], idx) => {
                            const colors: any = { video: '#3b82f6', image: '#f97316', script: '#22c55e', vision_gen: '#8b5cf6', test_after_fix: '#06b6d4', test_local: '#64748b' };
                            const total = Object.values(stats.breakdown || {}).reduce((a: any, b: any) => a + (b.tokens || 0), 0) as number;
                            const prevTotal = Object.values(stats.breakdown || {}).slice(0, idx).reduce((a: any, b: any) => a + (b.tokens || 0), 0) as number;
                            const start = (prevTotal / (total || 1)) * 100;
                            const end = start + (data.tokens / (total || 1)) * 100;
                            return `${colors[stage] || '#1e293b'} ${start}% ${end}%`;
                        }).join(', ') || '#1e293b'
                    })`
                }}>
                    <div className="absolute inset-6 bg-[#0f172a] rounded-full flex flex-col items-center justify-center overflow-hidden">
                         <span className="text-[10px] font-black text-gray-500 uppercase tracking-tighter">USAGE</span>
                         <span className="text-[8px] text-blue-500 font-bold">TOKENS</span>
                    </div>
                </div>
                <div className="w-full space-y-1 mt-2">
                    {Object.entries(stats.breakdown || {}).sort((a:any,b:any)=>b[1].tokens - a[1].tokens).slice(0, 4).map(([stage, data]: [string, any]) => {
                        const total = Object.values(stats.breakdown || {}).reduce((a: any, b: any) => a + (b.tokens || 0), 0) as number;
                        const pct = Math.round((data.tokens / (total || 1)) * 100);
                        const colors: any = { video: '#3b82f6', image: '#f97316', script: '#22c55e', vision_gen: '#8b5cf6', test_after_fix: '#06b6d4', test_local: '#64748b' };
                        return (
                            <div key={stage} className="flex justify-between items-center text-[10px] font-bold text-gray-400">
                                <div className="flex items-center gap-2"><div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: colors[stage] || '#334155' }}/><span className="truncate uppercase">{typeMap[stage] || stage}</span></div>
                                <span className="text-white">{pct}%</span>
                            </div>
                        );
                    })}
                </div>
            </div>
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
        <div className="min-h-screen bg-[#050505] text-white font-sans selection:bg-blue-500/30">
            <nav className="p-6 border-b border-white/5 bg-black/60 sticky top-0 z-[100] backdrop-blur-xl">
                <div className="max-w-[1600px] mx-auto flex justify-between items-center">
                    <span className="text-2xl font-black italic tracking-tighter text-blue-500">PICADIRI STUDIO</span>
                    <div className="flex gap-6 items-center">
                        <LanguageSelector />
                        <div className="text-right">
                            <span className="block text-[10px] text-gray-500 font-bold uppercase tracking-widest leading-none">관리자 계정</span>
                            <span className="text-sm font-black text-blue-400">{user?.email}</span>
                        </div>
                        <button onClick={() => supabase.auth.signOut().then(() => router.push('/'))} className="px-6 py-2.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all">로그아웃</button>
                    </div>
                </div>
            </nav>

            <main className="max-w-[1600px] mx-auto p-12 space-y-12">
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
                                    <div className="flex items-baseline gap-1">
                                        <span className="text-xl font-black italic">{memberCount.toLocaleString()}</span>
                                        <span className="text-[9px] font-bold uppercase">명</span>
                                    </div>
                                </div>
                                <div className="flex-1 bg-[#0f172a]/80 border border-white/5 px-6 py-3 rounded-2xl flex items-center justify-between transition-transform hover:scale-[1.02]">
                                    <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">오늘 활성</span>
                                    <div className="flex items-baseline gap-1">
                                        <span className="text-xl font-black tabular-nums">{activeToday.toLocaleString()}</span>
                                        <span className="text-[9px] font-bold text-green-500 uppercase">+{newToday}</span>
                                    </div>
                                </div>
                                <div className="flex-1 bg-[#0f172a]/80 border border-white/5 px-6 py-3 rounded-2xl flex items-center justify-between transition-transform hover:scale-[1.02]">
                                    <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">총 유포 토큰</span>
                                    <div className="flex items-baseline gap-1">
                                        <span className="text-xl font-black text-orange-500 tabular-nums">{totalTokens.toLocaleString()}</span>
                                        <span className="text-[9px] font-bold text-orange-500/50 uppercase">TK</span>
                                    </div>
                                </div>
                            </div>
                            <div className="flex items-center gap-2 p-1 bg-white/5 rounded-2xl border border-white/5">
                                <div className="flex gap-1">
                                    {[1, 7, 30].map(d => (
                                        <button key={d} onClick={() => setGlobalPeriod(d)} className={`px-4 py-2 text-[10px] font-black rounded-xl transition-all ${globalPeriod === d ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500 hover:text-white'}`}>
                                            {d === 1 ? '일간' : d === 7 ? '주간' : '월간'}
                                        </button>
                                    ))}
                                </div>
                                <div className="w-[1px] h-4 bg-white/10 mx-1"></div>
                                <button onClick={() => fetchGlobalStats(globalPeriod)} className="px-5 py-2 hover:bg-white/5 rounded-xl text-[10px] font-black text-blue-500 transition-all">새로고침</button>
                            </div>
                        </div>

                        <div className="grid grid-cols-4 gap-4">
                            <StatCard label="TOTAL TASKS" value={globalStats.total} unit="UNITS" color="white" />
                            <StatCard label="SUCCESS RATE" value={globalStats.successRate + '%'} unit="GLOBAL" color="green" />
                            <StatCard label="AVG LATENCY" value={globalStats.avgLatency + 's'} unit="PER TASK" color="blue" />
                            <StatCard label="DAILY TOKEN USAGE" value={globalStats.totalTokens.toLocaleString()} unit="TOKENS" color="orange" />
                        </div>

                        {renderChartRow(globalStats, globalTopTasks)}

                        <div className="flex items-center gap-4 py-2">
                             <div className="text-[11px] font-black text-gray-500 uppercase tracking-[0.4em] flex items-center gap-4">
                                  <div className="w-2 h-2 rounded-full bg-blue-500" /> GENERATION HISTORY
                             </div>
                             <div className="h-[1px] flex-1 bg-white/5"></div>
                             <div className="flex gap-1 p-1 bg-white/5 rounded-xl border border-white/5">
                                <button onClick={() => setOverviewSubTab('video')} className={`px-8 py-1.5 rounded-lg text-[10px] font-black transition-all ${overviewSubTab === 'video' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500 hover:text-white'}`}>채널</button>
                                <button onClick={() => setOverviewSubTab('log')} className={`px-8 py-1.5 rounded-lg text-[10px] font-black transition-all ${overviewSubTab === 'log' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500 hover:text-white'}`}>로그</button>
                             </div>
                        </div>

                        {overviewSubTab === 'video' ? (
                            <div className="bg-[#0b0f19] border border-white/5 rounded-[2.5rem] overflow-hidden shadow-2xl">
                                <table className="w-full text-left">
                                    <thead className="bg-black/30 border-b border-white/5 text-[10px] font-black text-gray-500 uppercase tracking-widest">
                                        <tr><th className="px-10 py-6">채널명 / 계정</th><th className="px-10 py-6 text-center">생성된 영상수</th><th className="px-10 py-6 text-center">최근 동기화</th><th className="px-10 py-6 text-right">상태</th></tr>
                                    </thead>
                                    <tbody className="divide-y divide-white/5">
                                        {users.slice(0, 15).map(u => {
                                            const userVideos = globalLogs.filter(l => l.user_id === u.id && (l.task_type || '').toLowerCase() === 'video').length;
                                            return (
                                                <tr key={u.id} className="hover:bg-white/[0.03] transition-colors group">
                                                    <td className="px-10 py-6">
                                                        <div className="font-black text-white text-base group-hover:text-blue-400 transition-colors uppercase tracking-tight">{u.email}</div>
                                                        <div className="text-[11px] text-gray-600 font-bold mt-1 uppercase italic tracking-tighter">{u.user_metadata?.full_name || '연동된 채널'}</div>
                                                    </td>
                                                    <td className="px-10 py-6 text-center font-black text-white text-xl tabular-nums">{userVideos}</td>
                                                    <td className="px-10 py-6 text-center text-[12px] font-black text-gray-500">{formatDate(u.last_sign_in_at)}</td>
                                                    <td className="px-10 py-6 text-right"><span className="px-3 py-1 bg-green-500/10 text-green-500 text-[9px] font-black rounded-full border border-green-500/20 uppercase">정상연결</span></td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        ) : renderLogTable(globalLogs)}
                    </div>
                )}

                {activeTab === 'users' && (
                    <div className="bg-[#0b0f19] border border-white/5 rounded-[3rem] overflow-hidden shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <div className="px-10 py-6 border-b border-white/5 bg-black/20 flex justify-between items-center">
                            <h3 className="text-sm font-black text-gray-400 uppercase tracking-[0.2em]">회원 관리 리스트</h3>
                            <button onClick={fetchUsers} className="px-6 py-2 bg-blue-600/10 hover:bg-blue-600 text-blue-500 hover:text-white text-[10px] font-black rounded-xl border border-blue-500/20 transition-all uppercase tracking-widest">새로고침</button>
                        </div>
                        <table className="w-full text-left">
                            <thead className="bg-black/30 border-b border-white/5 text-[10px] font-black text-gray-500 uppercase tracking-widest">
                                <tr><th className="px-10 py-7">계정 정보</th><th className="px-10 py-7 text-center">보유 토큰</th><th className="px-10 py-7 text-center">멤버십 등급</th><th className="px-10 py-7 text-center">최초 가입일</th><th className="px-10 py-7 text-center">최근 접속일</th><th className="px-10 py-7 text-right">관리 메뉴</th></tr>
                            </thead>
                            <tbody className="divide-y divide-white/5">
                                {users.map(u => (
                                    <tr key={u.id} className="hover:bg-white/[0.03] transition-colors group">
                                        <td className="px-10 py-7">
                                            <div className="font-black text-white text-base group-hover:text-blue-400 transition-colors uppercase tracking-tight">{u.email}</div>
                                            <div className="text-[11px] text-gray-600 font-bold mt-1 uppercase italic tracking-tighter">{u.user_metadata?.full_name || '이름 없음'}</div>
                                        </td>
                                        <td className="px-10 py-7 text-center font-black text-white text-xl tabular-nums">{u.profile?.token_balance?.toLocaleString() || 0}</td>
                                        <td className="px-10 py-7 text-center"><button onClick={() => handleRoleChange(u.id, u.app_metadata?.membership)} className={`px-5 py-2.5 rounded-2xl text-[10px] font-black border uppercase tracking-widest transition-all ${u.app_metadata?.membership === 'pro' ? 'bg-indigo-600 text-white border-indigo-500 shadow-lg' : 'bg-white/5 text-gray-500 border-white/10 hover:border-white/30'}`}>{u.app_metadata?.membership?.toUpperCase() === 'PRO' ? '프로' : '스탠다드'}</button></td>
                                        <td className="px-10 py-7 text-center text-[12px] font-black text-gray-500">{formatDate(u.created_at)}</td>
                                        <td className="px-10 py-7 text-center text-[12px] font-black text-gray-500">{formatDate(u.last_sign_in_at)}</td>
                                        <td className="px-10 py-7 text-right">
                                            <div className="flex gap-2 justify-end">
                                                <button onClick={() => handleRecharge(u.id)} className="px-6 py-2.5 bg-green-600/10 hover:bg-green-600 text-green-500 hover:text-white text-[10px] font-black rounded-2xl border border-green-500/20 transition-all uppercase tracking-widest">토큰충전</button>
                                                <button onClick={() => { setLogViewUser(u); setLogPeriod(1); fetchUserLogs(u.id, 1); }} className="px-6 py-2.5 bg-blue-600/10 hover:bg-blue-600 text-blue-500 hover:text-white text-[10px] font-black rounded-2xl border border-blue-500/20 transition-all uppercase tracking-widest">로그조회</button>
                                                <button onClick={() => { setApiViewUser(u); setTempApiKeys(u.app_metadata?.custom_api_keys || { openai: '', gemini: '', pexels: '', replicate: '' }); }} className="px-6 py-2.5 bg-indigo-600/10 hover:bg-indigo-600 text-indigo-500 hover:text-white text-[10px] font-black rounded-2xl border border-indigo-500/20 transition-all uppercase tracking-widest">API</button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </main>

            {/* POPUP: USER LOG VIEW (PLATFORM CLONE) */}
            {logViewUser && (
                <div className="fixed inset-0 z-[200] flex items-center justify-center p-12 animate-in fade-in duration-300">
                    <div className="absolute inset-0 bg-black/95 backdrop-blur-3xl" onClick={() => setLogViewUser(null)} />
                    <div className="relative w-full max-w-[1600px] bg-[#070707] border border-white/10 rounded-[3rem] p-12 flex flex-col max-h-[94vh] overflow-hidden shadow-2xl">
                        <div className="flex justify-between items-center mb-10">
                             <div className="flex items-center gap-6">
                                  <h3 className="text-3xl font-black text-blue-500 uppercase italic italic tracking-tighter">사용자 작업 로그</h3>
                                  <div className="px-4 py-1.5 bg-blue-600/10 border border-blue-500/20 rounded-full text-[10px] font-black text-blue-400 uppercase tracking-widest">{logViewUser.email}</div>
                             </div>
                             <div className="flex items-center gap-4">
                                  <div className="flex gap-1 p-1 bg-white/5 rounded-xl border border-white/5">
                                      {[1, 7, 30].map(d => (
                                          <button key={d} onClick={() => { setLogPeriod(d); fetchUserLogs(logViewUser.id, d); }} className={`px-6 py-2 text-[10px] font-black rounded-lg transition-all ${logPeriod === d ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500 hover:text-white'}`}>
                                              {d === 1 ? '일간' : d === 7 ? '주간' : '월간'}
                                          </button>
                                      ))}
                                  </div>
                                  <button onClick={() => setLogViewUser(null)} className="w-12 h-12 flex items-center justify-center rounded-xl bg-white/5 text-gray-500 hover:text-white transition-all text-xl font-black">X</button>
                             </div>
                        </div>

                        <div className="overflow-y-auto flex-1 pr-4 custom-scrollbar space-y-8">
                             <div className="grid grid-cols-4 gap-4">
                                <StatCard label="TOTAL TASKS" value={logStats.total} unit="UNITS" color="white" />
                                <StatCard label="SUCCESS RATE" value={logStats.successRate + '%'} unit="GLOBAL" color="green" />
                                <StatCard label="AVG LATENCY" value={logStats.avgLatency + 's'} unit="PER TASK" color="blue" />
                                <StatCard label="USER TOKEN USAGE" value={logStats.totalTokens.toLocaleString()} unit="TOKENS" color="orange" />
                             </div>

                             {renderChartRow(logStats, userTopTasks)}

                             <div className="flex items-center gap-4 pt-4 pb-2">
                                  <div className="text-[11px] font-black text-gray-500 uppercase tracking-[0.4em] flex items-center gap-4">
                                       <div className="w-2 h-2 rounded-full bg-blue-500" /> GENERATION HISTORY
                                  </div>
                                  <div className="h-[1px] flex-1 bg-white/5"></div>
                             </div>

                             {renderLogTable(userLogs)}
                        </div>
                    </div>
                </div>
            )}

            {apiViewUser && (
                <div className="fixed inset-0 z-[200] flex items-center justify-center p-12">
                    <div className="absolute inset-0 bg-black/90 backdrop-blur-3xl" onClick={() => setApiViewUser(null)} />
                    <div className="relative w-full max-w-[800px] bg-[#0b0f19] border border-white/10 rounded-[3rem] p-16 flex flex-col shadow-2xl animate-in zoom-in-95 duration-300">
                        <button onClick={() => setApiViewUser(null)} className="absolute top-12 right-12 w-12 h-12 flex items-center justify-center rounded-xl bg-white/5 text-gray-500 hover:text-white transition-all">X</button>
                        <div className="space-y-10">
                            <div>
                                <h3 className="text-3xl font-black uppercase italic tracking-tighter text-blue-500">유저 전용 API 설정</h3>
                                <p className="text-sm text-gray-500 mt-2 uppercase tracking-widest font-black italic">{apiViewUser.email}</p>
                            </div>
                            <div className="space-y-6">
                                {['openai', 'gemini', 'pexels', 'replicate'].map(key => (
                                    <div key={key} className="space-y-2">
                                        <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest ml-4">{key.toUpperCase()} API 키</label>
                                        <input type="text" placeholder={`이 유저의 ${key} 키를 입력하세요...`} value={tempApiKeys[key] || ''} onChange={(e) => setTempApiKeys({...tempApiKeys, [key]: e.target.value})} className="w-full bg-black/40 border border-white/5 rounded-2xl px-8 py-5 text-sm font-black text-white focus:outline-none focus:border-blue-500/50 transition-all" />
                                    </div>
                                ))}
                            </div>
                            <button onClick={handleUpdateApiKeys} className="w-full py-6 bg-blue-600 hover:bg-blue-500 text-white font-black rounded-[2rem] shadow-xl shadow-blue-500/20 transition-all active:scale-95 uppercase tracking-widest text-sm">변경사항 저장 및 적용</button>
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
