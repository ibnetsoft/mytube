
'use client'

import { useState } from 'react'
import { useLanguage } from '@/lib/LanguageContext'
import { Language } from '@/lib/translations'
import { ChevronDown, Globe } from 'lucide-react'

const languages: { code: Language; name: string; flag: string }[] = [
    { code: 'ko', name: '한국어', flag: '🇰🇷' },
    { code: 'en', name: 'English', flag: '🇺🇸' },
    { code: 'vi', name: 'Tiếng Việt', flag: '🇻🇳' },
    { code: 'es', name: 'Español', flag: '🇪🇸' },
    { code: 'th', name: 'ภาษาไทย', flag: '🇹🇭' },
    { code: 'id', name: 'Bahasa Indonesia', flag: '🇮🇩' },
    { code: 'fr', name: 'Français', flag: '🇫🇷' },
    { code: 'ru', name: 'Русский', flag: '🇷🇺' },
    { code: 'pt', name: 'Português (Brasil)', flag: '🇧🇷' },
]

export default function LanguageSelector() {
    const { language, setLanguage } = useLanguage()
    const [isOpen, setIsOpen] = useState(false)

    const currentLang = languages.find(l => l.code === language) || languages[0]

    return (
        <div className="relative inline-block text-left">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="flex items-center gap-2 px-3 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-full transition-all text-sm font-medium text-white/80"
            >
                <Globe size={14} className="text-blue-400" />
                <span>{currentLang.flag}</span>
                <span className="hidden sm:inline">{currentLang.name}</span>
                <ChevronDown size={14} className={`transition-transform duration-300 ${isOpen ? 'rotate-180' : ''}`} />
            </button>

            {isOpen && (
                <>
                    <div
                        className="fixed inset-0 z-40"
                        onClick={() => setIsOpen(false)}
                    />
                    <div className="absolute right-0 mt-2 w-48 bg-gray-900 border border-white/10 rounded-2xl shadow-2xl z-50 overflow-hidden backdrop-blur-xl animate-in fade-in zoom-in duration-200 origin-top-right">
                        <div className="py-2 max-h-[400px] overflow-y-auto custom-scrollbar">
                            {languages.map((lang) => (
                                <button
                                    key={lang.code}
                                    onClick={() => {
                                        setLanguage(lang.code)
                                        setIsOpen(false)
                                    }}
                                    className={`w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors hover:bg-white/5 ${language === lang.code ? 'text-blue-400 bg-blue-500/5' : 'text-gray-300'
                                        }`}
                                >
                                    <span className="text-lg leading-none">{lang.flag}</span>
                                    <span className="flex-1">{lang.name}</span>
                                    {language === lang.code && (
                                        <div className="w-1.5 h-1.5 rounded-full bg-blue-400 shadow-[0_0_8px_rgba(96,165,250,0.6)]" />
                                    )}
                                </button>
                            ))}
                        </div>
                    </div>
                </>
            )}
        </div>
    )
}
