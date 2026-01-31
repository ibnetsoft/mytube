
'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Auth } from '@supabase/auth-ui-react';
import { ThemeSupa } from '@supabase/auth-ui-shared';
import { supabase } from '../lib/supabaseClient';

// @ts-ignore
const AuthComponent = Auth;

export default function AuthForm() {
    const router = useRouter();
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
        <div className="max-w-md w-full mx-auto p-6 bg-white/10 backdrop-blur-md rounded-xl shadow-2xl border border-white/20">
            <h2 className="text-2xl font-bold text-center text-white mb-6">로그인 / 회원가입</h2>
            <AuthComponent
                supabaseClient={supabase}
                appearance={{
                    theme: ThemeSupa,
                    variables: {
                        default: {
                            colors: {
                                brand: '#3b82f6',
                                brandAccent: '#2563eb',
                                inputText: 'white',
                                inputBackground: '#1f2937',
                                inputLabelText: '#9ca3af',
                            },
                        },
                    },
                    className: {
                        container: 'space-y-4',
                        button: 'w-full px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition',
                        input: 'w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:ring-2 focus:ring-blue-500',
                        label: 'text-sm text-gray-400 mb-1 block',
                    },
                }}
                theme="dark"
                providers={['google', 'github']}
                redirectTo="http://localhost:3000/dashboard"
            />
        </div>
    );
}
