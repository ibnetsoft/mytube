'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { supabase } from '../lib/supabaseClient';
import { useLanguage } from '@/lib/LanguageContext';

export default function AuthForm() {
    const router = useRouter();
    const { t, language } = useLanguage();
    const [mounted, setMounted] = useState(false);
    const [isSignUp, setIsSignUp] = useState(false);
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState<{ type: 'error' | 'success', text: string } | null>(null);

    // Form states
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [passwordConfirm, setPasswordConfirm] = useState('');
    const [fullName, setFullName] = useState('');
    const [nationality, setNationality] = useState('');
    const [contact, setContact] = useState('');
    const [referrer, setReferrer] = useState('');
    const [preferredLanguages, setPreferredLanguages] = useState<string[]>(['ko']);

    // B2B 도입 신청 모달 상태
    const [showAppModal, setShowAppModal] = useState(false);
    const [appSubmitting, setAppSubmitting] = useState(false);
    const [appSubmitted, setAppSubmitted] = useState(false);
    const [appError, setAppError] = useState<string | null>(null);
    const [appForm, setAppForm] = useState({
        company_name: '',
        brand_name: '',
        contact_name: '',
        email: '',
        phone: '',
        channel_count: 5,
        currency: 'USD',
        notes: ''
    });

    const contentLanguageOptions = [
        { value: 'ko', label: '한국어' },
        { value: 'en', label: 'English' },
        { value: 'ja', label: '日本語' },
        { value: 'th', label: 'ภาษาไทย' },
    ];

    useEffect(() => {
        setMounted(true);
        const params = new URLSearchParams(window.location.search);
        const refCode = params.get('ref') || params.get('code') || params.get('referral');
        if (refCode) {
            setReferrer(refCode.trim().toUpperCase());
            setIsSignUp(true);
        }
        if (params.get('mode') === 'signup' || params.get('mode') === 'register' || params.get('tab') === 'register') {
            setIsSignUp(true);
        }
        const { data: { subscription } } = supabase.auth.onAuthStateChange((event) => {
            if (event === 'SIGNED_IN') {
                router.replace('/dashboard');
            }
        });

        return () => subscription.unsubscribe();
    }, [router]);

    if (!mounted) return null;

    const handleAuth = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setMessage(null);

        try {
            if (isSignUp) {
                // Validation
                if (password !== passwordConfirm) {
                    throw new Error(t('auth.error.password_mismatch'));
                }
                if (!fullName || !nationality || !contact) {
                    throw new Error(t('auth.error.missing_info'));
                }
                const normalizedPreferredLanguages = preferredLanguages.length ? preferredLanguages : ['ko'];

                const { error } = await supabase.auth.signUp({
                    email,
                    password,
                    options: {
                        data: {
                            full_name: fullName,
                            nationality: nationality,
                            contact: contact,
                            referrer: referrer.trim().toUpperCase(),
                            referral_code: referrer.trim().toUpperCase(),
                            country_code: nationality.trim().slice(0, 2).toUpperCase() || 'KR',
                            preferred_languages: normalizedPreferredLanguages
                        },
                        emailRedirectTo: `${window.location.origin}/dashboard`
                    }
                });

                if (error) throw error;
                setMessage({
                    type: 'success',
                    text: t('auth.success.signup_email')
                });
            } else {
                const { error } = await supabase.auth.signInWithPassword({
                    email,
                    password,
                });
                if (error) throw error;
            }
        } catch (error: any) {
            setMessage({ type: 'error', text: error.message });
        } finally {
            setLoading(false);
        }
    };

    const handleApplicationSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setAppSubmitting(true);
        setAppError(null);

        try {
            if (!appForm.company_name || !appForm.contact_name || !appForm.email || !appForm.phone) {
                throw new Error('회사명, 담당자 성함, 이메일, 연락처는 필수입니다.');
            }

            const res = await fetch('/api/tenant-applications', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ...appForm,
                    estimated_setup_fee: 500,
                    estimated_monthly_fee: appForm.channel_count * 100
                })
            });

            const data = await res.json();
            if (!res.ok) throw new Error(data.error || '신청 접수에 실패했습니다.');

            setAppSubmitted(true);
        } catch (err: any) {
            setAppError(err.message || '오류가 발생했습니다.');
        } finally {
            setAppSubmitting(false);
        }
    };

    return (
        <div className="max-w-md w-full mx-auto relative group">
            <div className="p-5 sm:p-8 bg-black/50 backdrop-blur-2xl rounded-2xl sm:rounded-[2.5rem] shadow-2xl border border-white/10 relative overflow-hidden transition-all duration-500">
                {/* Decorative gradients */}
                <div className="absolute -top-24 -left-24 w-48 h-48 bg-blue-500/10 blur-[100px] rounded-full pointer-events-none" />
                <div className="absolute -bottom-24 -right-24 w-48 h-48 bg-purple-500/10 blur-[100px] rounded-full pointer-events-none" />

                <h1 className="text-3xl sm:text-4xl font-black text-center mb-6 sm:mb-8 bg-gradient-to-r from-blue-400 via-indigo-400 to-purple-400 bg-clip-text text-transparent italic tracking-tighter">
                    {t('auth.title')}
                </h1>
                {isSignUp && (
                    <h2 className="text-xs sm:text-sm font-semibold text-center text-blue-300/80 -mt-4 mb-6 tracking-wider uppercase">
                        {t('auth.signup')}
                    </h2>
                )}

                <form onSubmit={handleAuth} className="space-y-3.5 sm:space-y-4">
                    <div>
                        <label className="text-[11px] sm:text-xs font-bold text-gray-400 mb-1 ml-1 block uppercase tracking-wider">
                            {t('auth.label.email')}
                        </label>
                        <input
                            type="email"
                            required
                            placeholder={t('auth.placeholder.email')}
                            className="w-full px-3.5 py-2.5 sm:px-4 sm:py-3 bg-white/5 border border-white/10 rounded-xl text-white text-sm focus:ring-2 focus:ring-blue-500/50 transition-all placeholder:text-gray-600 outline-none"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                        />
                    </div>

                    {isSignUp && (
                        <>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
                                <div>
                                    <label className="text-[11px] sm:text-xs font-bold text-gray-400 mb-1 ml-1 block uppercase tracking-wider">
                                        {t('auth.full_name')}
                                    </label>
                                    <input
                                        type="text"
                                        required={isSignUp}
                                        placeholder="이름"
                                        className="w-full px-3.5 py-2.5 sm:px-4 sm:py-3 bg-white/5 border border-white/10 rounded-xl text-white text-sm focus:ring-2 focus:ring-blue-500/50 transition-all placeholder:text-gray-600 outline-none"
                                        value={fullName}
                                        onChange={(e) => setFullName(e.target.value)}
                                    />
                                </div>
                                <div>
                                    <label className="text-[11px] sm:text-xs font-bold text-gray-400 mb-1 ml-1 block uppercase tracking-wider">
                                        {t('auth.nationality')}
                                    </label>
                                    <input
                                        type="text"
                                        required={isSignUp}
                                        placeholder="국적 (예: KR)"
                                        className="w-full px-3.5 py-2.5 sm:px-4 sm:py-3 bg-white/5 border border-white/10 rounded-xl text-white text-sm focus:ring-2 focus:ring-blue-500/50 transition-all placeholder:text-gray-600 outline-none"
                                        value={nationality}
                                        onChange={(e) => setNationality(e.target.value)}
                                    />
                                </div>
                            </div>

                            <div>
                                <label className="text-[11px] sm:text-xs font-bold text-gray-400 mb-1 ml-1 block uppercase tracking-wider">
                                    {t('auth.contact')}
                                </label>
                                <input
                                    type="text"
                                    required={isSignUp}
                                    placeholder="010-0000-0000"
                                    className="w-full px-3.5 py-2.5 sm:px-4 sm:py-3 bg-white/5 border border-white/10 rounded-xl text-white text-sm focus:ring-2 focus:ring-blue-500/50 transition-all placeholder:text-gray-600 outline-none"
                                    value={contact}
                                    onChange={(e) => setContact(e.target.value)}
                                />
                            </div>

                            <div>
                                <label className="text-[11px] sm:text-xs font-bold text-gray-400 mb-1.5 ml-1 block uppercase tracking-wider">
                                    {t('auth.label.available_lang')}
                                </label>
                                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                                    {contentLanguageOptions.map(option => (
                                        <label key={`signup-language-${option.value}`} className="flex items-center justify-center sm:justify-start gap-1.5 px-2.5 py-2 rounded-xl bg-white/5 border border-white/10 text-[11px] font-bold text-gray-300 cursor-pointer hover:bg-white/10 transition-colors">
                                            <input
                                                type="checkbox"
                                                className="w-3.5 h-3.5 rounded text-blue-500 bg-black/40 border-white/20"
                                                checked={preferredLanguages.includes(option.value)}
                                                onChange={(e) => setPreferredLanguages(current => {
                                                    const next = e.target.checked
                                                        ? Array.from(new Set([...current, option.value]))
                                                        : current.filter(lang => lang !== option.value)
                                                    return next.length ? next : ['ko']
                                                })}
                                            />
                                            <span>{option.label}</span>
                                        </label>
                                    ))}
                                </div>
                            </div>
                        </>
                    )}

                    <div className={isSignUp ? "grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4" : "space-y-3 sm:space-y-4"}>
                        <div>
                            <label className="text-[11px] sm:text-xs font-bold text-gray-400 mb-1 ml-1 block uppercase tracking-wider">
                                {isSignUp ? t('auth.password') : t('auth.password')}
                            </label>
                            <input
                                type="password"
                                required
                                placeholder="비밀번호 입력"
                                className="w-full px-3.5 py-2.5 sm:px-4 sm:py-3 bg-white/5 border border-white/10 rounded-xl text-white text-sm focus:ring-2 focus:ring-blue-500/50 transition-all placeholder:text-gray-600 outline-none"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                            />
                        </div>
                        {isSignUp && (
                            <div>
                                <label className="text-[11px] sm:text-xs font-bold text-gray-400 mb-1 ml-1 block uppercase tracking-wider">
                                    {t('auth.password_confirm')}
                                </label>
                                <input
                                    type="password"
                                    required={isSignUp}
                                    placeholder="비밀번호 확인"
                                    className="w-full px-3.5 py-2.5 sm:px-4 sm:py-3 bg-white/5 border border-white/10 rounded-xl text-white text-sm focus:ring-2 focus:ring-blue-500/50 transition-all placeholder:text-gray-600 outline-none"
                                    value={passwordConfirm}
                                    onChange={(e) => setPasswordConfirm(e.target.value)}
                                />
                            </div>
                        )}
                    </div>

                    {isSignUp && (
                        <div>
                            <label className="text-[11px] sm:text-xs font-bold text-gray-400 mb-1 ml-1 block uppercase tracking-wider">
                                {t('auth.referrer')}
                            </label>
                            <input
                                type="text"
                                placeholder="추천인 코드 (선택사항)"
                                className="w-full px-3.5 py-2.5 sm:px-4 sm:py-3 bg-white/5 border border-white/10 rounded-xl text-white text-sm focus:ring-2 focus:ring-blue-500/50 transition-all placeholder:text-gray-600 outline-none"
                                value={referrer}
                                onChange={(e) => setReferrer(e.target.value)}
                            />
                        </div>
                    )}

                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full px-4 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-xl transition-all font-bold text-sm sm:text-base shadow-lg shadow-blue-900/40 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed mt-4"
                    >
                        {loading ? t('common.loading') : (isSignUp ? t('auth.signup') : t('auth.signin'))}
                    </button>
                </form>

                {message && (
                    <div className={`text-xs p-3 rounded-lg mt-4 border ${
                        message.type === 'error' 
                        ? 'bg-red-500/10 border-red-500/20 text-red-400' 
                        : 'bg-green-500/10 border-green-500/20 text-green-400'
                    }`}>
                        {message.text}
                    </div>
                )}

                <div className="mt-6 sm:mt-8 text-center text-xs sm:text-sm">
                    <button
                        onClick={() => setIsSignUp(!isSignUp)}
                        className="text-gray-400 hover:text-blue-400 transition-colors py-1 px-2"
                    >
                        {isSignUp ? t('auth.already_have_account') : t('auth.dont_have_account')}
                    </button>
                </div>

                {/* B2B 기업/스튜디오 도입 신청 배너 버튼 */}
                <div className="mt-6 pt-5 border-t border-white/10">
                    <button
                        type="button"
                        onClick={() => {
                            setAppSubmitted(false);
                            setAppError(null);
                            setShowAppModal(true);
                        }}
                        className="w-full py-3 px-4 rounded-2xl bg-gradient-to-r from-blue-600/20 via-purple-600/20 to-indigo-600/20 hover:from-blue-600/30 hover:to-indigo-600/30 border border-blue-500/30 text-blue-200 hover:text-white transition-all flex items-center justify-between group/btn shadow-lg"
                    >
                        <div className="flex items-center gap-2.5 text-left">
                            <span className="text-2xl">🏢</span>
                            <div>
                                <div className="text-xs font-black tracking-tight text-white flex items-center gap-1.5">
                                    기업 / 5개 채널 스튜디오 도입 신청
                                    <span className="text-[9px] bg-blue-500/30 text-blue-300 px-1.5 py-0.2 rounded font-bold">B2B</span>
                                </div>
                                <div className="text-[10px] text-gray-400 mt-0.5">전담 인프라 세팅비 + 최대 5개 채널 월 구독 솔루션</div>
                            </div>
                        </div>
                        <span className="text-xs font-bold text-blue-400 group-hover/btn:translate-x-1 transition-transform">신청하기 →</span>
                    </button>
                </div>

                <div className="mt-4 flex items-center justify-center gap-2 text-center text-[11px] font-semibold text-gray-500">
                    <a href="/terms" target="_blank" rel="noreferrer" className="underline underline-offset-4 hover:text-gray-300">
                        서비스 이용약관
                    </a>
                    <span aria-hidden="true">·</span>
                    <a href="/privacy" target="_blank" rel="noreferrer" className="underline underline-offset-4 hover:text-gray-300">
                        개인정보처리방침
                    </a>
                </div>
            </div>

            {/* B2B 도입 신청 팝업 모달 */}
            {showAppModal && (
                <div className="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-4 overflow-y-auto" onClick={() => setShowAppModal(false)}>
                    <div className="bg-[#0f172a] border border-blue-500/30 rounded-3xl p-6 sm:p-8 w-full max-w-lg my-8 shadow-2xl relative" onClick={e => e.stopPropagation()}>
                        <button
                            onClick={() => setShowAppModal(false)}
                            className="absolute top-6 right-6 text-gray-400 hover:text-white text-lg font-bold"
                        >
                            ✕
                        </button>

                        {appSubmitted ? (
                            <div className="text-center py-8 space-y-4">
                                <div className="w-16 h-16 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 flex items-center justify-center text-3xl mx-auto">
                                    ✓
                                </div>
                                <h3 className="text-xl font-black text-white">도입 신청이 정상 접수되었습니다!</h3>
                                <p className="text-xs text-gray-300 leading-relaxed max-w-sm mx-auto">
                                    기재해주신 연락처와 이메일(<span className="text-blue-400">{appForm.email}</span>)로 
                                    담당자가 세팅비 결제 안내 및 5개 채널 인프라 구축 일정을 신속히 안내해 드리겠습니다.
                                </p>
                                <button
                                    onClick={() => setShowAppModal(false)}
                                    className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold rounded-xl transition-all mt-4"
                                >
                                    확인 닫기
                                </button>
                            </div>
                        ) : (
                            <div>
                                <div className="mb-5">
                                    <span className="text-[10px] font-black uppercase tracking-widest text-blue-400 bg-blue-500/10 px-2.5 py-1 rounded-full border border-blue-500/20">
                                        AIR STUDIO B2B SOLUTION
                                    </span>
                                    <h2 className="text-xl font-black text-white mt-2">
                                        🏢 테넌트 도입 신청 / 가입 문의
                                    </h2>
                                    <p className="text-xs text-gray-400 mt-1">
                                        귀사만의 전용 브랜드 세팅과 최대 5개 유튜브 채널 자동 운영 솔루션을 신청하세요.
                                    </p>
                                </div>

                                {appError && (
                                    <div className="text-xs p-3 rounded-xl mb-4 bg-red-500/10 border border-red-500/20 text-red-400">
                                        {appError}
                                    </div>
                                )}

                                <form onSubmit={handleApplicationSubmit} className="space-y-3.5">
                                    <div className="grid grid-cols-2 gap-3">
                                        <div>
                                            <label className="text-[10px] font-black uppercase tracking-widest text-gray-400 block mb-1">
                                                회사 / 스튜디오명 <span className="text-red-400">*</span>
                                            </label>
                                            <input
                                                type="text"
                                                required
                                                placeholder="주식회사 ABC"
                                                value={appForm.company_name}
                                                onChange={e => setAppForm({ ...appForm, company_name: e.target.value })}
                                                className="w-full px-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-[10px] font-black uppercase tracking-widest text-gray-400 block mb-1">
                                                브랜드명
                                            </label>
                                            <input
                                                type="text"
                                                placeholder="ABC Studio"
                                                value={appForm.brand_name}
                                                onChange={e => setAppForm({ ...appForm, brand_name: e.target.value })}
                                                className="w-full px-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                                            />
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-2 gap-3">
                                        <div>
                                            <label className="text-[10px] font-black uppercase tracking-widest text-gray-400 block mb-1">
                                                담당자 성함 <span className="text-red-400">*</span>
                                            </label>
                                            <input
                                                type="text"
                                                required
                                                placeholder="홍길동 팀장"
                                                value={appForm.contact_name}
                                                onChange={e => setAppForm({ ...appForm, contact_name: e.target.value })}
                                                className="w-full px-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-[10px] font-black uppercase tracking-widest text-gray-400 block mb-1">
                                                연락처 <span className="text-red-400">*</span>
                                            </label>
                                            <input
                                                type="text"
                                                required
                                                placeholder="010-1234-5678"
                                                value={appForm.phone}
                                                onChange={e => setAppForm({ ...appForm, phone: e.target.value })}
                                                className="w-full px-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                                            />
                                        </div>
                                    </div>

                                    <div>
                                        <label className="text-[10px] font-black uppercase tracking-widest text-gray-400 block mb-1">
                                            회사 이메일 (승인 안내 수신용) <span className="text-red-400">*</span>
                                        </label>
                                        <input
                                            type="email"
                                            required
                                            placeholder="contact@company.com"
                                            value={appForm.email}
                                            onChange={e => setAppForm({ ...appForm, email: e.target.value })}
                                            className="w-full px-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                                        />
                                    </div>

                                    {/* 채널 수 선택 및 예상 견적 실시간 계산 박스 */}
                                    <div className="bg-blue-950/40 border border-blue-500/30 rounded-2xl p-4 space-y-3">
                                        <div className="flex items-center justify-between">
                                            <label className="text-xs font-black text-blue-300">
                                                운영 희망 채널 수: <span className="text-white text-sm">{appForm.channel_count}개</span>
                                            </label>
                                            <span className="text-[10px] text-purple-300 bg-purple-500/20 px-2 py-0.5 rounded-full border border-purple-500/30">
                                                최대 5개 지원
                                            </span>
                                        </div>
                                        <div className="grid grid-cols-5 gap-2">
                                            {[1, 2, 3, 4, 5].map(cnt => (
                                                <button
                                                    key={`ch-btn-${cnt}`}
                                                    type="button"
                                                    onClick={() => setAppForm({ ...appForm, channel_count: cnt })}
                                                    className={`py-2 rounded-xl text-xs font-black transition-all ${
                                                        appForm.channel_count === cnt
                                                            ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/30 border border-blue-400'
                                                            : 'bg-white/5 text-gray-400 hover:bg-white/10 border border-white/10'
                                                    }`}
                                                >
                                                    {cnt}채널
                                                </button>
                                            ))}
                                        </div>

                                        <div className="bg-black/50 border border-white/10 rounded-xl p-3 flex items-center justify-between mt-2">
                                            <div>
                                                <div className="text-[10px] text-gray-400">도입 견적 (예상)</div>
                                                <div className="text-xs text-white mt-0.5">
                                                    초기 세팅비 <span className="font-bold text-emerald-400">$500</span> + 월 <span className="font-bold text-blue-400">${appForm.channel_count * 100}</span>
                                                </div>
                                            </div>
                                            <div className="text-right text-[10px] text-gray-400">
                                                채널당 $100/월 기준
                                            </div>
                                        </div>
                                    </div>

                                    <div>
                                        <label className="text-[10px] font-black uppercase tracking-widest text-gray-400 block mb-1">
                                            기존 채널 링크 또는 문의사항
                                        </label>
                                        <textarea
                                            rows={2}
                                            placeholder="운영 중인 유튜브 채널 링크나 특별 요청사항을 적어주세요."
                                            value={appForm.notes}
                                            onChange={e => setAppForm({ ...appForm, notes: e.target.value })}
                                            className="w-full px-3.5 py-2 bg-white/5 border border-white/10 rounded-xl text-white text-xs focus:ring-2 focus:ring-blue-500 outline-none resize-none"
                                        />
                                    </div>

                                    <button
                                        type="submit"
                                        disabled={appSubmitting}
                                        className="w-full py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-bold text-xs shadow-xl shadow-blue-500/20 active:scale-[0.98] disabled:opacity-50 transition-all mt-2"
                                    >
                                        {appSubmitting ? '신청서 제출 중...' : 'B2B 도입 신청서 제출하기'}
                                    </button>
                                </form>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
