
'use client'

import React, { createContext, useContext, useState, useEffect } from 'react';
import { Language, Translation, translations } from './translations';

interface LanguageContextType {
    language: Language;
    setLanguage: (lang: Language) => void;
    t: Translation;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
    const [language, setLanguageState] = useState<Language>('ko');

    useEffect(() => {
        const savedLang = localStorage.getItem('pica_lang') as Language;
        if (savedLang && translations[savedLang]) {
            setLanguageState(savedLang);
        } else {
            // Auto-detect browser language
            const browserLang = navigator.language.split('-')[0] as Language;
            if (translations[browserLang]) {
                setLanguageState(browserLang);
            }
        }
    }, []);

    const setLanguage = (lang: Language) => {
        setLanguageState(lang);
        localStorage.setItem('pica_lang', lang);
    };

    const t = translations[language];

    return (
        <LanguageContext.Provider value={{ language, setLanguage, t }}>
            {children}
        </LanguageContext.Provider>
    );
}

export function useLanguage() {
    const context = useContext(LanguageContext);
    if (context === undefined) {
        throw new Error('useLanguage must be used within a LanguageProvider');
    }
    return context;
}
