'use client'
import { useEffect, useRef, useState } from 'react'
import { topicUiText } from '@/lib/topicUiText'
import type { TopicYoutubeVideo } from '@/lib/topicYoutube'

export default function TopicYoutubeExplorer({ headers, disabled, onSelect, locale = 'ko' }: {
    headers: Record<string, string>; locale?: string; disabled: boolean; onSelect: (video: TopicYoutubeVideo) => void
}) {
    const ui = (text: string) => topicUiText(locale, text)
    const [query, setQuery] = useState('')
    const [language, setLanguage] = useState(locale)
    const [order, setOrder] = useState('relevance')
    const [period, setPeriod] = useState('all')
    const [age, setAge] = useState('all')
    const ageLabels: Record<string, string> = { all: '전체 연령', '10s': '10대', '20s': '20대', '30s': '30대', '40s': '40대', '50s': '50대', '60plus': '60대 이상' }
    const [videos, setVideos] = useState<TopicYoutubeVideo[]>([])
    const [keywords, setKeywords] = useState<{ text: string; count: number }[]>([])
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState('')
    const [resultLabel, setResultLabel] = useState('')
    const [selected, setSelected] = useState('')
    const controller = useRef<AbortController | null>(null)
    useEffect(() => () => controller.current?.abort(), [])
    useEffect(() => {
        controller.current?.abort()
        setLanguage(locale); setVideos([]); setKeywords([]); setResultLabel(''); setError(''); setBusy(false)
    }, [locale])
    const input = 'rounded-lg border border-white/15 bg-[#11141a] p-2.5 text-sm text-gray-100'
    async function search(term: string) {
        controller.current?.abort()
        const active = new AbortController(); controller.current = active
        setBusy(true); setError('')
        const params = new URLSearchParams({ q: term, language, order, period, age })
        try {
            const res = await fetch(`/api/std/topic-youtube?${params}`, { headers, signal: active.signal })
            const data = await res.json()
            if (active.signal.aborted) return
            if (!res.ok) throw new Error(data.error || '검색 실패')
            setVideos(data.videos); setKeywords(data.keywords)
            const region = { ko: '한국', ja: '일본', en: '미국', es: '스페인', vi: '베트남', th: '태국' }[language]
            const label = term ? `“${term}” ${ui('검색 결과')}` : `${ui(region || '')} ${ui(age === 'all' ? '인기 영상' : '연령 관련 영상')}`
            setResultLabel(age === 'all' ? label : `${label} · ${ui(ageLabels[age])}`)
        } catch (e) {
            if (!active.signal.aborted) setError(e instanceof Error ? e.message : '검색 실패')
        } finally { if (controller.current === active) setBusy(false) }
    }
    return <section className="rounded-xl border border-white/10 bg-[#191e27] p-5 space-y-4" aria-label={ui('YouTube 참고 영상 탐색')}>
        <div><h2 className="text-lg font-semibold">{ui('YouTube 참고 영상 찾기')}</h2><p className="mt-1 text-sm text-gray-400">{ui('키워드로 검색하거나 인기 영상에서 키워드를 골라보세요. 선택한 영상은 아래 토픽의 참고 URL에 들어갑니다.')}</p></div>
        <form onSubmit={event => { event.preventDefault(); if (query.trim()) void search(query.trim()) }}>
            <fieldset disabled={disabled || busy} className="space-y-3">
                <div className="flex gap-2"><input aria-label={ui('YouTube 검색 키워드')} maxLength={120} value={query} onChange={event => setQuery(event.target.value)} placeholder={ui('검색할 키워드 입력')} className={`${input} min-w-0 flex-1`} /><button disabled={!query.trim()} className="rounded-lg bg-indigo-500 px-4 text-sm font-semibold disabled:opacity-40">{ui('검색')}</button></div>
                <div className="flex flex-wrap items-center gap-2">
                    <select aria-label={ui('검색 언어')} value={language} onChange={event => setLanguage(event.target.value)} className={input}><option value="ko">{ui('한국어 · 한국')}</option><option value="ja">{ui('일본어 · 일본')}</option><option value="en">{ui('영어 · 미국')}</option><option value="es">{ui('스페인어 · 스페인')}</option><option value="vi">{ui('베트남어 · 베트남')}</option><option value="th">{ui('태국어 · 태국')}</option></select>
                    <select aria-label={ui('검색 정렬')} value={order} onChange={event => setOrder(event.target.value)} className={input}><option value="relevance">{ui('관련도순')}</option><option value="date">{ui('최신순')}</option><option value="viewCount">{ui('조회수순')}</option></select>
                    <select aria-label={ui('검색 기간')} value={period} onChange={event => setPeriod(event.target.value)} className={input}><option value="all">{ui('전체 기간')}</option><option value="day">{ui('최근 하루')}</option><option value="week">{ui('최근 일주일')}</option><option value="month">{ui('최근 30일')}</option></select>
                    <select aria-label={ui('검색 연령대')} value={age} onChange={event => setAge(event.target.value)} className={input}>{Object.entries(ageLabels).map(([value, label]) => <option key={value} value={value}>{ui(label)}</option>)}</select>
                    <button type="button" onClick={() => void search('')} className="rounded-lg border border-indigo-400/40 px-3 py-2.5 text-sm text-indigo-300">{age === 'all' ? ui('인기 영상·키워드 불러오기') : ui('연령 관련 영상·키워드 불러오기')}</button>
                </div>
                <p className="text-xs text-gray-500">{ui('기간과 정렬은 키워드 검색에 적용됩니다. 인기 영상은 선택한 국가 기준입니다. 연령대 선택은 연령 관련 키워드를 검색어에 추가하며, 실제 시청자 연령 통계로 필터링하지는 않습니다.')}</p>
            </fieldset>
        </form>
        {busy && <p role="status" className="text-sm text-indigo-300">{ui('YouTube 영상을 불러오는 중…')}</p>}
        {error && <p role="alert" className="text-sm text-red-300">{ui(error)}</p>}
        {resultLabel && <div className="space-y-3">
            <div><h3 className="text-sm font-semibold">{ui('키워드 클라우드')} · {resultLabel}</h3><p className="mt-1 text-xs text-gray-400">{ui('영상 제목·태그에서 추출했습니다. 여러 영상에 등장할수록 크게 표시됩니다. 키워드를 누르면 검색합니다.')}</p></div>
            <div className="flex flex-wrap items-center gap-2">{keywords.map(keyword => <button key={keyword.text} type="button" disabled={busy || disabled} onClick={() => { setQuery(keyword.text); void search(keyword.text) }} title={`${keyword.count} ${ui('개 영상에 등장')}`} style={{ fontSize: `${12 + Math.min(keyword.count - 1, 6) * 2}px` }} className="rounded-full border border-indigo-400/25 bg-indigo-500/10 px-3 py-1.5 text-indigo-200 hover:bg-indigo-500/25 disabled:opacity-40">{keyword.text}</button>)}{!keywords.length && <p className="text-sm text-gray-500">{ui('추출할 키워드가 없습니다.')}</p>}</div>
            <p className="text-sm text-gray-400">{resultLabel} · {videos.length}{ui('개')}{!videos.length && ' · ' + ui('다른 검색어나 기간으로 검색해보세요.')}</p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{videos.map(video => <article key={video.id} className="overflow-hidden rounded-lg border border-white/10 bg-[#11141a]">
                <a href={video.url} target="_blank" rel="noopener noreferrer" className="block"><img src={video.thumbnail} alt={`${video.title} ${ui('썸네일')}`} loading="lazy" className="aspect-video w-full object-cover" /></a>
                <div className="space-y-2 p-3"><a href={video.url} target="_blank" rel="noopener noreferrer" className="line-clamp-2 text-sm font-medium hover:text-indigo-300">{video.title}</a><p className="truncate text-xs text-gray-400">{video.channel}</p><p className="text-xs text-gray-500">{video.views == null ? ui('조회수 정보 없음') : `${ui('조회수')} ${Number(video.views).toLocaleString(locale)}${ui('회')}`} · {video.publishedAt ? video.publishedAt.slice(0, 10) : ui('게시일 정보 없음')}</p>
                    <button type="button" disabled={disabled || busy} onClick={() => { onSelect(video); setSelected(video.id) }} className="w-full rounded-md bg-indigo-500/20 py-2 text-sm text-indigo-200 disabled:opacity-40">{selected === video.id ? ui('✓ 참고 영상 선택됨') : ui('참고 영상으로 선택')}</button>
                </div>
            </article>)}</div>
        </div>}
    </section>
}
