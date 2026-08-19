
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

    return (
        <div className="max-w-md w-full mx-auto relative group">
            <div className="p-8 bg-black/40 backdrop-blur-2xl rounded-[2.5rem] shadow-2xl border border-white/10 relative overflow-hidden transition-all duration-500">
                {/* Decorative gradients */}
                <div className="absolute -top-24 -left-24 w-48 h-48 bg-blue-500/10 blur-[100px] rounded-full" />
                <div className="absolute -bottom-24 -right-24 w-48 h-48 bg-purple-500/10 blur-[100px] rounded-full" />

                <h1 className="text-4xl font-black text-center mb-8 bg-gradient-to-r from-blue-400 via-indigo-400 to-purple-400 bg-clip-text text-transparent italic tracking-tighter">
                    {t('auth.title')}
                </h1>
                {isSignUp && (
                    <h2 className="text-lg font-medium text-center text-white/60 mb-8 tracking-wide uppercase text-[10px]">
                        {t('auth.signup')}
                    </h2>
                )}

                <form onSubmit={handleAuth} className="space-y-4">
                    <div>
                        <label className="text-xs font-bold text-gray-400 mb-1.5 ml-1 block uppercase tracking-wider">
                            {t('auth.label.email')}
                        </label>
                        <input
                            type="email"
                            required
                            placeholder={t('auth.placeholder.email')}
                            className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white focus:ring-2 focus:ring-blue-500/50 transition-all placeholder:text-gray-600 outline-none"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                        />
                    </div>

                    {isSignUp && (
                        <>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="text-xs font-bold text-gray-400 mb-1.5 ml-1 block uppercase tracking-wider">
                                        {t('auth.full_name')}
                                    </label>
                                    <input
                                        type="text"
                                        required={isSignUp}
                                        placeholder="Name"
                                        className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white focus:ring-2 focus:ring-blue-500/50 transition-all placeholder:text-gray-600 outline-none text-sm"
                                        value={fullName}
                                        onChange={(e) => setFullName(e.target.value)}
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-bold text-gray-400 mb-1.5 ml-1 block uppercase tracking-wider">
                                        {t('auth.nationality')}
                                    </label>
                                    <input
                                        type="text"
                                        required={isSignUp}
                                        placeholder="Country"
                                        className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white focus:ring-2 focus:ring-blue-500/50 transition-all placeholder:text-gray-600 outline-none text-sm"
                                        value={nationality}
                                        onChange={(e) => setNationality(e.target.value)}
                                    />
                                </div>
                            </div>

                            <div>
                                <label className="text-xs font-bold text-gray-400 mb-1.5 ml-1 block uppercase tracking-wider">
                                    {t('auth.contact')}
                                </label>
                                <input
                                    type="text"
                                    required={isSignUp}
                                    placeholder="Phone number"
                                    className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white focus:ring-2 focus:ring-blue-500/50 transition-all placeholder:text-gray-600 outline-none text-sm"
                                    value={contact}
                                    onChange={(e) => setContact(e.target.value)}
                                />
                            </div>

                            <div>
                                <label className="text-xs font-bold text-gray-400 mb-2 ml-1 block uppercase tracking-wider">
                                    {t('auth.label.available_lang')}
                                </label>
                                <div className="grid grid-cols-3 gap-2">
                                    {contentLanguageOptions.map(option => (
                                        <label key={`signup-language-${option.value}`} className="flex items-center gap-2 px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-[11px] font-bold text-gray-300 cursor-pointer hover:bg-white/10">
                                            <input
                                                type="checkbox"
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

                    <div className={isSignUp ? "grid grid-cols-2 gap-4" : "space-y-4"}>
                        <div>
                            <label className="text-xs font-bold text-gray-400 mb-1.5 ml-1 block uppercase tracking-wider">
                                {isSignUp ? t('auth.password') : t('auth.password')}
                            </label>
                            <input
                                type="password"
                                required
                                placeholder="Your password"
                                className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white focus:ring-2 focus:ring-blue-500/50 transition-all placeholder:text-gray-600 outline-none"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                            />
                        </div>
                        {isSignUp && (
                            <div>
                                <label className="text-xs font-bold text-gray-400 mb-1.5 ml-1 block uppercase tracking-wider">
                                    {t('auth.password_confirm')}
                                </label>
                                <input
                                    type="password"
                                    required={isSignUp}
                                    placeholder="Confirm"
                                    className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white focus:ring-2 focus:ring-blue-500/50 transition-all placeholder:text-gray-600 outline-none text-sm"
                                    value={passwordConfirm}
                                    onChange={(e) => setPasswordConfirm(e.target.value)}
                                />
                            </div>
                        )}
                    </div>

                    {isSignUp && (
                        <div>
                            <label className="text-xs font-bold text-gray-400 mb-1.5 ml-1 block uppercase tracking-wider">
                                {t('auth.referrer')}
                            </label>
                            <input
                                type="text"
                                placeholder="Optional"
                                className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white focus:ring-2 focus:ring-blue-500/50 transition-all placeholder:text-gray-600 outline-none text-sm"
                                value={referrer}
                                onChange={(e) => setReferrer(e.target.value)}
                            />
                        </div>
                    )}

                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full px-4 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-all font-bold shadow-lg shadow-blue-900/40 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed mt-4"
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

                <div className="mt-8 text-center text-sm">
                    <button
                        onClick={() => setIsSignUp(!isSignUp)}
                        className="text-gray-500 hover:text-blue-400 transition-colors"
                    >
                        {isSignUp ? t('auth.already_have_account') : t('auth.dont_have_account')}
                    </button>
                </div>
            </div>
        </div>
    );
}
