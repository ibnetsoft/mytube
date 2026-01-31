
'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Auth } from '@supabase/auth-ui-react';
import { ThemeSupa } from '@supabase/auth-ui-shared';
import { supabase } from '../lib/supabaseClient';

import { useLanguage } from '@/lib/LanguageContext';
import LanguageSelector from './LanguageSelector';

// @ts-ignore
const AuthComponent = Auth;

export default function AuthForm() {
    const router = useRouter();
    const { t } = useLanguage();
    const [mounted, setMounted] = useState(false);

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

    return (
        <div className="max-w-md w-full mx-auto relative group">
            <div className="absolute -top-12 right-0">
                <LanguageSelector />
            </div>

            <div className="p-8 bg-black/40 backdrop-blur-2xl rounded-[2.5rem] shadow-2xl border border-white/10 relative overflow-hidden">
                {/* Decorative gradients */}
                <div className="absolute -top-24 -left-24 w-48 h-48 bg-blue-500/10 blur-[100px] rounded-full" />
                <div className="absolute -bottom-24 -right-24 w-48 h-48 bg-purple-500/10 blur-[100px] rounded-full" />

                <h1 className="text-4xl font-black text-center mb-2 bg-gradient-to-r from-blue-400 via-indigo-400 to-purple-400 bg-clip-text text-transparent italic tracking-tighter">
                    {t.loginTitle}
                </h1>
                <h2 className="text-lg font-medium text-center text-white/60 mb-10 tracking-wide uppercase text-[10px]">
                    {t.loginSubtitle}
                </h2>

                <AuthComponent
                    supabaseClient={supabase}
                    localization={{
                        variables: {
                            sign_in: {
                                email_label: 'Email',
                                password_label: 'Password',
                                button_label: t.login,
                            }
                        }
                    }}
                    appearance={{
                        theme: ThemeSupa,
                        variables: {
                            default: {
                                colors: {
                                    brand: '#2563eb',
                                    brandAccent: '#3b82f6',
                                    inputText: 'white',
                                    inputBackground: 'rgba(255,255,255,0.03)',
                                    inputLabelText: '#94a3b8',
                                    inputBorder: 'rgba(255,255,255,0.1)',
                                    inputBorderHover: 'rgba(255,255,255,0.2)',
                                    inputBorderFocus: '#3b82f6',
                                },
                                space: {
                                    inputPadding: '12px 16px',
                                    buttonPadding: '12px 16px',
                                },
                                radii: {
                                    borderRadiusButton: '12px',
                                    buttonBorderRadius: '12px',
                                    inputBorderRadius: '12px',
                                },
                            },
                        },
                        className: {
                            container: 'space-y-4',
                            button: 'w-full px-4 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-all font-bold shadow-lg shadow-blue-900/40 active:scale-[0.98]',
                            input: 'w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white focus:ring-2 focus:ring-blue-500/50 transition-all placeholder:text-gray-600',
                            label: 'text-xs font-bold text-gray-400 mb-1.5 ml-1 block uppercase tracking-wider',
                            anchor: 'text-sm text-gray-500 hover:text-blue-400 transition-colors',
                            divider: 'opacity-20',
                            message: 'text-xs bg-red-500/10 border border-red-500/20 text-red-400 p-3 rounded-lg mt-4'
                        },
                    }}
                    theme="dark"
                    providers={['google', 'github']}
                    redirectTo={typeof window !== 'undefined' ? `${window.location.origin}/dashboard` : undefined}
                />
            </div>
        </div>
    );
}
