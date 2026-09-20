'use client'

import { useState, useRef, useEffect } from 'react'
import { Volume2, Volume1, VolumeX, ChevronUp, ChevronDown, RotateCcw } from 'lucide-react'

interface SubtitleVolumePickerProps {
    volume?: number
    onChange: (nextVolume: number, allSpeaker?: boolean) => void | Promise<void>
    speakerName?: string
    disabled?: boolean
    title?: string
}

export default function SubtitleVolumePicker({
    volume = 100,
    onChange,
    speakerName,
    disabled = false,
    title = '대사 볼륨 조절'
}: SubtitleVolumePickerProps) {
    const [isOpen, setIsOpen] = useState(false)
    const [currentVolume, setCurrentVolume] = useState(volume)
    const [applyAllSpeaker, setApplyAllSpeaker] = useState(false)
    const popoverRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        setCurrentVolume(volume)
    }, [volume])

    // 외부 클릭 시 닫기
    useEffect(() => {
        if (!isOpen) return
        const handleClickOutside = (e: MouseEvent) => {
            if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
                setIsOpen(false)
            }
        }
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') setIsOpen(false)
        }
        document.addEventListener('mousedown', handleClickOutside)
        document.addEventListener('keydown', handleKeyDown)
        return () => {
            document.removeEventListener('mousedown', handleClickOutside)
            document.removeEventListener('keydown', handleKeyDown)
        }
    }, [isOpen])

    const handleVolumeChange = (next: number) => {
        const clamped = Math.max(0, Math.min(200, Math.round(next)))
        setCurrentVolume(clamped)
        void onChange(clamped, applyAllSpeaker)
    }

    const isCustom = currentVolume !== 100

    const getVolumeIcon = () => {
        if (currentVolume === 0) return <VolumeX size={13} className="shrink-0" />
        if (currentVolume < 100) return <Volume1 size={13} className="shrink-0" />
        return <Volume2 size={13} className="shrink-0" />
    }

    return (
        <div className="relative inline-flex shrink-0" ref={popoverRef} onClick={e => e.stopPropagation()}>
            {/* 마이크 버튼 옆 볼륨 아이콘 버튼 */}
            <button
                type="button"
                disabled={disabled}
                title={`${title}: ${currentVolume}%`}
                onClick={(e) => {
                    e.stopPropagation()
                    if (disabled) return
                    setIsOpen(!isOpen)
                }}
                className={`h-7 w-7 rounded-md border flex items-center justify-center transition relative ${
                    disabled
                        ? 'cursor-not-allowed border-white/5 bg-[#10141b] text-gray-600 opacity-45'
                        : isCustom
                        ? currentVolume > 100
                            ? 'bg-cyan-500/20 border-cyan-400/60 text-cyan-200 hover:bg-cyan-500/30 shadow-sm'
                            : 'bg-amber-500/15 border-amber-400/50 text-amber-200 hover:bg-amber-500/25'
                        : 'bg-[#10141b] border-white/10 text-gray-400 hover:text-white hover:bg-[#202632] hover:border-cyan-400/50'
                }`}
            >
                {getVolumeIcon()}
                {isCustom && (
                    <span className={`absolute -top-1 -right-1 w-2 h-2 rounded-full ${currentVolume > 100 ? 'bg-cyan-400' : 'bg-amber-400'}`} />
                )}
            </button>

            {/* 볼륨 팝오버 슬라이더 */}
            {isOpen && (
                <div
                    className="absolute left-0 top-full mt-1.5 z-[120] w-60 p-3.5 rounded-xl border border-white/20 bg-[#161b24] text-gray-100 shadow-2xl animate-in fade-in zoom-in-95 duration-150 [color-scheme:dark]"
                    onClick={e => e.stopPropagation()}
                >
                    {/* 상단 헤더 */}
                    <div className="flex items-center justify-between border-b border-white/10 pb-2 mb-3">
                        <div className="flex items-center gap-1.5">
                            <Volume2 size={14} className="text-cyan-400" />
                            <span className="text-xs font-bold text-white">대사 볼륨</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                            <span className={`px-2 py-0.5 text-xs font-mono font-bold rounded ${
                                isCustom
                                    ? currentVolume > 100 ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30' : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                                    : 'bg-white/10 text-gray-300'
                            }`}>
                                {currentVolume}%
                            </span>
                            {isCustom && (
                                <button
                                    type="button"
                                    onClick={() => handleVolumeChange(100)}
                                    className="text-gray-400 hover:text-white p-0.5 rounded transition"
                                    title="100% 기본값으로 초기화"
                                >
                                    <RotateCcw size={12} />
                                </button>
                            )}
                        </div>
                    </div>

                    {/* 상하 조절 버튼 및 슬라이더 */}
                    <div className="space-y-2.5">
                        <div className="flex items-center justify-between text-[11px] text-gray-400">
                            <span>0% (음소거)</span>
                            <span className="text-gray-300 font-bold">100% (기본)</span>
                            <span>200% (2배)</span>
                        </div>

                        <div className="flex items-center gap-2">
                            {/* 아래로(-5%) 버튼 */}
                            <button
                                type="button"
                                onClick={() => handleVolumeChange(currentVolume - 5)}
                                disabled={currentVolume <= 0}
                                className="h-7 w-7 rounded bg-white/5 hover:bg-white/10 border border-white/10 flex items-center justify-center text-gray-300 hover:text-white disabled:opacity-30 transition"
                                title="5% 작게"
                            >
                                <ChevronDown size={14} />
                            </button>

                            {/* 슬라이더 바 */}
                            <input
                                type="range"
                                min="0"
                                max="200"
                                step="5"
                                value={currentVolume}
                                onChange={(e) => handleVolumeChange(Number(e.target.value))}
                                className="flex-1 h-2 bg-black/40 rounded-lg appearance-none cursor-pointer accent-cyan-400 focus:outline-none"
                            />

                            {/* 위로(+5%) 버튼 */}
                            <button
                                type="button"
                                onClick={() => handleVolumeChange(currentVolume + 5)}
                                disabled={currentVolume >= 200}
                                className="h-7 w-7 rounded bg-white/5 hover:bg-white/10 border border-white/10 flex items-center justify-center text-gray-300 hover:text-white disabled:opacity-30 transition"
                                title="5% 크게"
                            >
                                <ChevronUp size={14} />
                            </button>
                        </div>
                    </div>

                    {/* 빠른 프리셋 버튼 */}
                    <div className="grid grid-cols-4 gap-1 pt-2">
                        {[
                            { label: '80%', val: 80, hint: '차분하게' },
                            { label: '100%', val: 100, hint: '기본' },
                            { label: '120%', val: 120, hint: '또렷하게' },
                            { label: '140%', val: 140, hint: '크게' }
                        ].map((preset) => (
                            <button
                                key={preset.val}
                                type="button"
                                onClick={() => handleVolumeChange(preset.val)}
                                className={`py-1 rounded text-[10px] font-bold border transition ${
                                    currentVolume === preset.val
                                        ? 'border-cyan-400 bg-cyan-500/20 text-cyan-200 shadow-sm'
                                        : 'border-white/10 bg-white/5 text-gray-400 hover:text-white hover:bg-white/10'
                                }`}
                                title={preset.hint}
                            >
                                {preset.label}
                            </button>
                        ))}
                    </div>

                    {/* 화자 전체 대사 일괄 적용 체크박스 */}
                    {speakerName && (
                        <div className="pt-2.5 mt-2.5 border-t border-white/10">
                            <label className="flex items-center gap-2 cursor-pointer select-none text-left">
                                <input
                                    type="checkbox"
                                    checked={applyAllSpeaker}
                                    onChange={(e) => {
                                        setApplyAllSpeaker(e.target.checked)
                                        if (e.target.checked) {
                                            void onChange(currentVolume, true)
                                        }
                                    }}
                                    className="w-3.5 h-3.5 rounded accent-cyan-500 cursor-pointer"
                                />
                                <span className="text-[10px] text-gray-300 leading-tight">
                                    <strong className="text-cyan-300">{speakerName}</strong>의 모든 대사에 적용
                                </span>
                            </label>
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}
