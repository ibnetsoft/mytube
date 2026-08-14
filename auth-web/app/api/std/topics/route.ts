import { NextResponse } from 'next/server'
import { requireStdUser } from '@/lib/stdWeb'
import { getStdRecommendedTopics } from '@/lib/stdRecommendations'

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const { searchParams } = new URL(req.url)
    const limit = Math.max(1, Math.min(50, Number(searchParams.get('limit') || 20)))
    const refresh = ['1', 'true', 'yes'].includes(String(searchParams.get('refresh') || '').toLowerCase())
    const filterDuration = String(searchParams.get('filter_duration') || '')
    const filters = new Set(filterDuration.split(',').map((item) => item.trim()).filter(Boolean))

    try {
        const result = await getStdRecommendedTopics({
            email: auth.requester.email,
            profile: auth.requester.profile,
            limit,
            refresh,
            filters: {
                ignore_duration: filters.has('duration_ignore'),
                ignore_language: filters.has('language_ignore'),
                ignore_category: filters.has('category_ignore'),
            },
        })
        return NextResponse.json({ success: true, topics: result.topics, cached: result.cached })
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error.message || 'Failed to load STD topics' }, { status: 500 })
    }
}
