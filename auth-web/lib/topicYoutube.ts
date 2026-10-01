export type TopicYoutubeVideo = {
    id: string; title: string; channel: string; publishedAt: string;
    thumbnail: string; url: string; views: string | null; tags: string[];
}
export type TopicYoutubeOptions = { query: string; language: string; order: string; period: string }
export class TopicYoutubeError extends Error {
    constructor(message: string, public status = 502) { super(message) }
}

export function parseTopicYoutubeOptions(params: URLSearchParams): TopicYoutubeOptions {
    const query = (params.get('q') || '').trim()
    const language = params.get('language') || 'ko'
    const order = params.get('order') || 'relevance'
    const period = params.get('period') || 'all'
    if (query.length > 120 || !['ko', 'ja', 'en', 'es'].includes(language)
        || !['relevance', 'date', 'viewCount'].includes(order) || !['all', 'day', 'week', 'month'].includes(period)) {
        throw new TopicYoutubeError('검색어와 검색 조건을 확인하세요.', 400)
    }
    return { query, language, order, period }
}

const stopwords = new Set('the and for with this that from video youtube shorts official full episode 이야기 영상 유튜브 조회수 구독 좋아요 입니다 합니다 그리고 오늘 정말 있는 없는 되는 から まで です ます する した して ない この その'.split(' '))

export function extractTopicYoutubeKeywords(videos: TopicYoutubeVideo[], language: string) {
    const segmenter = new Intl.Segmenter(language, { granularity: 'word' })
    const counts = new Map<string, { text: string; count: number }>()
    for (const video of videos) {
        const words = [...segmenter.segment(video.title)].filter(part => part.isWordLike).map(part => part.segment)
        const seen = new Set<string>()
        for (const raw of [...words, ...video.tags]) {
            const text = raw.replace(/^#+/, '').trim()
            const key = text.toLocaleLowerCase(language)
            if (text.length < 2 || text.length > 24 || /^\d+$/.test(text) || stopwords.has(key) || seen.has(key)) continue
            seen.add(key)
            const existing = counts.get(key)
            if (existing) existing.count++
            else counts.set(key, { text, count: 1 })
        }
    }
    return [...counts.values()].sort((a, b) => b.count - a.count || a.text.localeCompare(b.text, language)).slice(0, 30)
}

export async function fetchTopicYoutube(options: TopicYoutubeOptions, keys: string[], fetcher: typeof fetch = fetch, now = Date.now()) {
    if (!keys.length) throw new TopicYoutubeError('YouTube API 키가 설정되어 있지 않습니다. 관리자 설정을 확인하세요.', 503)
    const deadline = Date.now() + 45000
    async function get(endpoint: string, params: Record<string, string>) {
        for (const key of keys) {
            const url = `https://www.googleapis.com/youtube/v3/${endpoint}?${new URLSearchParams({ ...params, key })}`
            let res: Response
            const remaining = deadline - Date.now()
            if (remaining <= 0) throw new TopicYoutubeError('YouTube 응답이 지연되고 있습니다. 잠시 후 다시 시도하세요.')
            try { res = await fetcher(url, { next: { revalidate: 300 }, signal: AbortSignal.timeout(Math.min(12000, remaining)) }) }
            catch { throw new TopicYoutubeError('YouTube에 연결하지 못했습니다. 잠시 후 다시 시도하세요.') }
            let data: any
            try { data = await res.json() } catch { throw new TopicYoutubeError('YouTube 응답을 읽지 못했습니다.') }
            if (res.ok && !data.error) return data
            const reason = data.error?.errors?.[0]?.reason || ''
            if (['quotaExceeded', 'dailyLimitExceeded', 'keyInvalid', 'accessNotConfigured', 'ipRefererBlocked'].includes(reason)) continue
            throw new TopicYoutubeError('YouTube 검색에 실패했습니다. 검색 조건을 확인하거나 잠시 후 다시 시도하세요.')
        }
        throw new TopicYoutubeError('YouTube API 사용량 또는 키 설정을 확인해야 합니다.', 503)
    }
    const regions: Record<string, string> = { ko: 'KR', ja: 'JP', en: 'US', es: 'ES' }
    let rows: any[] = []
    if (options.query) {
        const params: Record<string, string> = { part: 'snippet', type: 'video', maxResults: '20', q: options.query,
            order: options.order, relevanceLanguage: options.language, regionCode: regions[options.language] }
        const days: Record<string, number> = { day: 1, week: 7, month: 30 }
        if (days[options.period]) params.publishedAfter = new Date(Math.floor(now / 300000) * 300000 - days[options.period] * 86400000).toISOString()
        const search = await get('search', params)
        const ids = (search.items || []).map((item: any) => item.id?.videoId).filter((id: unknown) => typeof id === 'string' && /^[\w-]{11}$/.test(id))
        if (ids.length) {
            const details = await get('videos', { part: 'snippet,statistics', id: ids.join(',') })
            const byId = new Map((details.items || []).map((row: any) => [row.id, row]))
            rows = ids.map((id: string) => byId.get(id)).filter(Boolean)
        }
    } else {
        const popular = await get('videos', { part: 'snippet,statistics', chart: 'mostPopular', regionCode: regions[options.language], maxResults: '20' })
        rows = popular.items || []
    }
    const videos: TopicYoutubeVideo[] = rows.filter(row => /^[\w-]{11}$/.test(row.id)).map(row => ({
        id: row.id, title: String(row.snippet?.title || ''), channel: String(row.snippet?.channelTitle || ''),
        publishedAt: String(row.snippet?.publishedAt || ''), thumbnail: `https://i.ytimg.com/vi/${row.id}/mqdefault.jpg`,
        url: `https://www.youtube.com/watch?v=${row.id}`, views: row.statistics?.viewCount ?? null,
        tags: Array.isArray(row.snippet?.tags) ? row.snippet.tags.filter((tag: unknown) => typeof tag === 'string') : [],
    }))
    return { videos, keywords: extractTopicYoutubeKeywords(videos, options.language), source: options.query ? 'search' : 'popular' }
}
