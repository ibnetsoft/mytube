import { NextResponse } from 'next/server'
import { requireStdUser } from '@/lib/stdWeb'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { fetchTopicYoutube, parseTopicYoutubeOptions, TopicYoutubeError } from '@/lib/topicYoutube'

export const dynamic = 'force-dynamic'
export const maxDuration = 60

export async function GET(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response
    try {
        const options = parseTopicYoutubeOptions(new URL(req.url).searchParams)
        const { data, error } = await supabaseAdmin.from('global_settings').select('key,value')
            .in('key', ['sys_api_youtube', 'sys_api_youtube_keys'])
        const split = (value: unknown) => String(value || '').split(/[\s,;]+/).map(key => key.trim()).filter(Boolean)
        const keys = [...new Set([...split(process.env.YOUTUBE_API_KEY), ...split(process.env.YOUTUBE_API_KEYS),
            ...(data || []).flatMap(row => split(row.value))])].slice(0, 3)
        if (error && !keys.length) throw new TopicYoutubeError('YouTube API 설정을 불러오지 못했습니다.', 503)
        return NextResponse.json(await fetchTopicYoutube(options, keys))
    } catch (error) {
        return NextResponse.json({ error: error instanceof TopicYoutubeError ? error.message : 'YouTube 검색을 처리하지 못했습니다.' },
            { status: error instanceof TopicYoutubeError ? error.status : 502 })
    }
}
