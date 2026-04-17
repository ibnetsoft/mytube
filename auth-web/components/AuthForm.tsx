
'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { supabase } from '../lib/supabaseClient';
import { useLanguage } from '@/lib/LanguageContext';
import LanguageSelector from './LanguageSelector';

export default function AuthForm() {
    const router = useRouter();
    const { t } = useLanguage();
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

    useEffect(() => {
        setMounted(true);
        const { data: { subscription } } = supabase.auth.onAuthStateChange((event) => {
            if (event === 'SIGNED_IN') {
                router.replace('/dashboard');
            }
        });

        return () => subscription.unsubscribe();
    }, [router]);

    if (!mounted) return null;

    const handleGoogleLogin = async () => {
        try {
            const { error } = await supabase.auth.signInWithOAuth({
                provider: 'google',
                options: {
                    redirectTo: `${window.location.origin}/dashboard`
                }
            });
            if (error) throw error;
        } catch (error: any) {
            setMessage({ type: 'error', text: error.message });
        }
    };

    const handleAuth = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setMessage(null);

        try {
            if (isSignUp) {
                // Validation
                if (password !== passwordConfirm) {
                    throw new Error(t.passwordConfirm + '이 일치하지 않습니다.');
                }
                if (!fullName || !nationality || !contact) {
                    throw new Error('모든 필수 정보를 입력해주세요.');
                }

                const { error } = await supabase.auth.signUp({
                    email,
                    password,
                    options: {
                        data: {
                            full_name: fullName,
                            nationality: nationality,
                            contact: contact,
                            referrer: referrer
                        },
                        emailRedirectTo: `${window.location.origin}/dashboard`
                    }
                });

                if (error) throw error;
                setMessage({ type: 'success', text: '회원가입 확인 메일이 발송되었습니다. 이메일을 확인해주세요!' });
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
            <div className="absolute -top-12 right-0">
                <LanguageSelector />
            </div>

            <div className="p-8 bg-black/40 backdrop-blur-2xl rounded-[2.5rem] shadow-2xl border border-white/10 relative overflow-hidden transition-all duration-500">
                {/* Decorative gradients */}
                <div className="absolute -top-24 -left-24 w-48 h-48 bg-blue-500/10 blur-[100px] rounded-full" />
                <div className="absolute -bottom-24 -right-24 w-48 h-48 bg-purple-500/10 blur-[100px] rounded-full" />

                <h1 className="text-4xl font-black text-center mb-2 bg-gradient-to-r from-blue-400 via-indigo-400 to-purple-400 bg-clip-text text-transparent italic tracking-tighter">
                    {t.loginTitle}
                </h1>
                <h2 className="text-lg font-medium text-center text-white/60 mb-8 tracking-wide uppercase text-[10px]">
                    {isSignUp ? t.signup : t.loginSubtitle}
                </h2>

                {/* Social Login */}
                <div className="space-y-3 mb-8">
                    <button
                        onClick={handleGoogleLogin}
                        className="w-full flex items-center justify-center gap-3 px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white hover:bg-white/10 transition-all font-bold text-sm shadow-lg active:scale-[0.98]"
                    >
                        <img src="https://www.google.com/favicon.ico" className="w-4 h-4" alt="Google" />
                        Sign in with Google
                    </button>
                    {/* Github removed as per request */}
                </div>

                <div className="relative flex items-center py-4 mb-4">
                    <div className="flex-grow border-t border-white/10"></div>
                    <span className="flex-shrink mx-4 text-white/20 text-[10px] uppercase tracking-widest font-bold">OR</span>
                    <div className="flex-grow border-t border-white/10"></div>
                </div>

                <form onSubmit={handleAuth} className="space-y-4">
                    <div>
                        <label className="text-xs font-bold text-gray-400 mb-1.5 ml-1 block uppercase tracking-wider">
                            Email Address
                        </label>
                        <input
                            type="email"
                            required
                            placeholder="Your email address"
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
                                        {t.fullName}
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
                                        {t.nationality}
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
                                    {t.contact}
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
                        </>
                    )}

                    <div className={isSignUp ? "grid grid-cols-2 gap-4" : "space-y-4"}>
                        <div>
                            <label className="text-xs font-bold text-gray-400 mb-1.5 ml-1 block uppercase tracking-wider">
                                {isSignUp ? t.password : "Password"}
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
                                    {t.passwordConfirm}
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
                                {t.referrer}
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
                        {loading ? t.loading : (isSignUp ? t.signup : t.signin)}
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
                        {isSignUp ? t.alreadyHaveAccount : t.dontHaveAccount}
                    </button>
                </div>
            </div>
        </div>
    );
}
