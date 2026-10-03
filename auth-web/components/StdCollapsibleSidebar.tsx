'use client'

import { useEffect, useId, useState, type ReactNode } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

const COPY = {
    ko: { collapse: '사이드바 접기', expand: '사이드바 펼치기' },
    th: { collapse: 'ยุบแถบด้านข้าง', expand: 'ขยายแถบด้านข้าง' },
    en: { collapse: 'Collapse sidebar', expand: 'Expand sidebar' },
    vi: { collapse: 'Thu gọn thanh bên', expand: 'Mở rộng thanh bên' },
}

export default function StdCollapsibleSidebar({ children, locale }: { children: ReactNode; locale: string }) {
    const [collapsed, setCollapsed] = useState(false)
    const sidebarId = useId()
    const copy = COPY[locale as keyof typeof COPY] || COPY.en
    const label = collapsed ? copy.expand : copy.collapse

    useEffect(() => {
        try {
            setCollapsed(localStorage.getItem('std_sidebar_collapsed') === '1')
        } catch {}
    }, [])

    const toggle = () => {
        const next = !collapsed
        setCollapsed(next)
        try {
            localStorage.setItem('std_sidebar_collapsed', next ? '1' : '0')
        } catch {}
    }

    return (
        <div className={`relative hidden h-full shrink-0 bg-[#161a22] transition-[width] duration-150 motion-reduce:transition-none md:flex ${collapsed ? 'w-4' : 'w-56'}`}>
            <aside id={sidebarId} className={`h-full w-56 min-w-0 shrink-0 flex-col border-r border-white/10 bg-[#161a22] ${collapsed ? 'hidden' : 'flex'}`}>
                {children}
            </aside>
            <button
                type="button"
                onClick={toggle}
                aria-expanded={!collapsed}
                aria-controls={sidebarId}
                aria-label={label}
                title={label}
                className="absolute -right-3 top-3 z-40 flex h-9 w-6 items-center justify-center rounded-md border border-white/15 bg-[#202632] text-gray-300 shadow-md hover:bg-[#2b3545] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
            >
                {collapsed ? <ChevronRight size={16} aria-hidden="true" /> : <ChevronLeft size={16} aria-hidden="true" />}
            </button>
        </div>
    )
}
