import { NextResponse } from 'next/server'
import { requireStdUser, isPreparedStdTopic, normalizeTopicSummary } from '@/lib/stdWeb'
import { getStdRecommendedTopics } from '@/lib/stdRecommendations'
import { supabaseAdmin } from '@/lib/supabaseAdmin'

export const dynamic = 'force-dynamic'

const ROUTE_REVISION = 'std-topics-final-eligibility-guard-2026-09-06'

function isUnclaimedPendingTopic(topic: any): boolean {
    const assignee = String(topic?.assigned_employee_email || '').trim()
    const assignedAt = topic?.assigned_at
    const hasAssignedAt = assignedAt !== null && assignedAt !== undefined && String(assignedAt).trim().length > 0
    return String(topic?.status || '') === 'pending' && !hasAssignedAt && assignee.length === 0
}

function topicMatchesPreferredCategory(topic: any, preferredCategories: Set<string>): boolean {
    return preferredCategories.size === 0 || preferredCategories.has(String(topic?.category_id || ''))
}

function preferredCategorySet(profile: any): Set<string> {
    return new Set(
        (Array.isArray(profile?.preferred_category_ids) ? profile.preferred_category_ids : [])
            .map((id: any) => String(id || '').trim())
            .filter(Boolean)
    )
}

function normalizeDirectTopic(topic: any) {
    const summary = normalizeTopicSummary(topic)
    const duration = Number(topic?.duration_minutes || topic?.recommended_duration_minutes || topic?.assigned_duration_minutes || summary.assigned_duration_minutes || 0) || null
    const payout = Number(topic?.estimated_payout || summary.estimated_payout || 0) || 0
    return {
        ...summary,
        duration_minutes: duration,
        recommended_duration_minutes: duration,
        assigned_duration_minutes: duration || summary.assigned_duration_minutes,
        estimated_payout: payout,
        estimated_payout_usdt: payout,
        adjusted_payout: payout,
        adjusted_payout_usdt: payout,
    }
}

async function filterLiveEligibleTopics(topics: any[]) {
    const ids = Array.from(new Set((topics || []).map((topic: any) => topic?.id).filter(Boolean)))
    if (!ids.length) return []
    const { data } = await supabaseAdmin
        .from('topics_queue')
        .select('id,status,assigned_at,assigned_employee_email')
        .in('id', ids)
    const eligibleIds = new Set((data || []).filter(isUnclaimedPendingTopic).map((topic: any) => String(topic.id)))
    return topics.filter((topic: any) => eligibleIds.has(String(topic?.id)))
}

async function inspectEligibilityDebug(topics: any[], limit: number) {
    const ids = Array.from(new Set((topics || []).map((topic: any) => topic?.id).filter(Boolean)))
    const liveRows = ids.length
        ? (await supabaseAdmin
            .from('topics_queue')
            .select('id,status,assigned_at,assigned_employee_email,pregenerated_script_status,pregenerated_structure_status,total_scenes,recommended_duration_minutes,assigned_duration_minutes,estimated_payout')
            .in('id', ids)).data || []
        : []
    const { data: candidates } = await supabaseAdmin
        .from('topics_queue')
        .select('id,status,assigned_at,assigned_employee_email,pregenerated_script_status,pregenerated_structure_status,total_scenes,recommended_duration_minutes,assigned_duration_minutes,estimated_payout,created_at')
        .eq('status', 'pending')
        .is('assigned_at', null)
        .or('assigned_employee_email.is.null,assigned_employee_email.eq.')
        .not('generated_title', 'is', null)
        .order('created_at', { ascending: false })
        .limit(limit)
    return {
        returned_ids: topics.map((topic: any) => topic?.id),
        live_rows: liveRows,
        direct_candidate_rows: candidates || [],
    }
}

async function loadDirectPreparedTopics(limit: number, profile: any, filters: Record<string, boolean>) {
    const { data, error } = await supabaseAdmin
        .from('topics_queue')
        .select('*, categories(*)')
        .eq('status', 'pending')
        .is('assigned_at', null)
        .or('assigned_employee_email.is.null,assigned_employee_email.eq.')
        .not('generated_title', 'is', null)
        .order('created_at', { ascending: false })
        .limit(300)
    if (error) throw error

    const preferredCategories = filters.ignore_category ? new Set<string>() : preferredCategorySet(profile)
    return (data || [])
        .filter(isUnclaimedPendingTopic)
        .filter(isPreparedStdTopic)
        .filter((topic: any) => filters.ignore_category || topicMatchesPreferredCategory(topic, preferredCategories))
        .slice(0, limit)
        .map(normalizeDirectTopic)
}

export async function GET(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const { searchParams } = new URL(req.url)
    const limit = Math.max(1, Math.min(50, Number(searchParams.get('limit') || 20)))
    const refresh = ['1', 'true', 'yes'].includes(String(searchParams.get('refresh') || '').toLowerCase())
    const filterDuration = String(searchParams.get('filter_duration') || '')
    const filters = new Set(filterDuration.split(',').map((item) => item.trim()).filter(Boolean))
    const routeFilters = {
        ignore_duration: filters.has('duration_ignore'),
        ignore_language: filters.has('language_ignore'),
        ignore_category: filters.has('category_ignore'),
    }

    try {
        if (refresh) {
            const directTopics = await loadDirectPreparedTopics(limit, auth.requester.profile, routeFilters)
            if (directTopics.length > 0) {
                const debug = searchParams.get('debug') === 'eligibility'
                    ? await inspectEligibilityDebug(directTopics, 20)
                    : undefined
                return NextResponse.json({ success: true, topics: directTopics, cached: false, revision: ROUTE_REVISION, debug })
            }
        }

        const result = await getStdRecommendedTopics({
            email: auth.requester.email,
            profile: auth.requester.profile,
            limit,
            refresh,
            filters: routeFilters,
        })
        let topics = await filterLiveEligibleTopics(result.topics)
        if (topics.length < 1 && refresh) {
            topics = await loadDirectPreparedTopics(limit, auth.requester.profile, routeFilters)
        }
        const debug = searchParams.get('debug') === 'eligibility'
            ? await inspectEligibilityDebug(result.topics, 20)
            : undefined
        return NextResponse.json({ success: true, topics, cached: result.cached, revision: ROUTE_REVISION, debug })
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error.message || 'Failed to load STD topics' }, { status: 500 })
    }
}
