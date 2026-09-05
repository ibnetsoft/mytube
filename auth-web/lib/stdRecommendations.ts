import { supabaseAdmin } from './supabaseAdmin'
import { isPreparedStdTopic, normalizeTopicSummary } from './stdWeb'
import {
    DEFAULT_LONGFORM_PAYOUT_TIERS_JSON,
    calculateLongformPayoutByScenes,
    capLongformPayout,
} from './stdPayoutPolicy'

const LONGFORM_POLICY_KEYS = [
    'sys_api_longform_min_duration_minutes',
    'sys_api_longform_base_payout',
    'sys_api_longform_extra_minute_payout',
    'sys_api_longform_payout_tiers',
    'sys_api_longform_duration_lock_enabled',
]

function toInt(value: any, fallback: number): number {
    const parsed = Number.parseInt(String(value ?? ''), 10)
    return Number.isFinite(parsed) ? parsed : fallback
}

function toFloat(value: any, fallback: number): number {
    const parsed = Number.parseFloat(String(value ?? ''))
    return Number.isFinite(parsed) ? parsed : fallback
}

function normalizeContentLanguage(value: any): string {
    const lang = String(value || '').trim().toLowerCase()
    return ['ko', 'en', 'ja'].includes(lang) ? lang : 'ko'
}

function durationPreferenceBucket(minutes: number | null): string {
    if (!minutes || minutes <= 0) return ''
    if (minutes <= 15) return '15m'
    if (minutes <= 30) return '30m'
    return '60m_plus'
}

function normalizePayoutUsdt(value: any): number {
    const amount = toFloat(value, 0)
    if (amount <= 0) return 0
    if (amount >= 1000) return Math.round((amount / 1000) * 10) / 10
    return Math.round(amount * 10) / 10
}

async function loadPolicy(): Promise<Record<string, any>> {
    const defaults: Record<string, any> = {
        sys_api_longform_min_duration_minutes: '15',
        sys_api_longform_base_payout: '4',
        sys_api_longform_extra_minute_payout: '0',
        sys_api_longform_payout_tiers: DEFAULT_LONGFORM_PAYOUT_TIERS_JSON,
        sys_api_longform_duration_lock_enabled: 'true',
    }
    const { data } = await supabaseAdmin
        .from('global_settings')
        .select('key,value')
        .in('key', LONGFORM_POLICY_KEYS)
    for (const row of data || []) {
        if (row?.key) defaults[row.key] = row.value
    }
    return defaults
}

async function loadBoosts(): Promise<Map<string, number>> {
    const boosts = new Map<string, number>()
    const { data } = await supabaseAdmin
        .from('category_priority_boosts')
        .select('category_id,boost_multiplier')
    for (const row of data || []) {
        if (row?.category_id != null) boosts.set(String(row.category_id), Number(row.boost_multiplier || 1))
    }
    return boosts
}

function normalizeTopicForStd(topic: any, policy: Record<string, any>, payoutMultiplier = 1) {
    const category = topic?.categories || {}
    const summary = normalizeTopicSummary(topic)
    const videoType = String(topic?.video_type || category?.video_type || 'longform').trim().toLowerCase() || 'longform'
    const minMinutes = Math.max(15, toInt(policy.sys_api_longform_min_duration_minutes, 15))
    let durationMinutes = toInt(topic?.duration_minutes || topic?.recommended_duration_minutes || topic?.assigned_duration_minutes, 0)
    if (videoType === 'longform') durationMinutes = Math.max(minMinutes, durationMinutes || minMinutes)

    const estimatedPayout = videoType === 'longform'
        ? calculateLongformPayoutByScenes(summary.scene_count || 53)
        : normalizePayoutUsdt(topic?.estimated_payout)
    const adjustedPayout = videoType === 'longform'
        ? capLongformPayout(estimatedPayout * payoutMultiplier)
        : Math.round(estimatedPayout * payoutMultiplier * 10) / 10

    return {
        ...summary,
        duration_minutes: durationMinutes || null,
        recommended_duration_minutes: durationMinutes || null,
        assigned_duration_minutes: durationMinutes || summary.assigned_duration_minutes,
        estimated_payout: estimatedPayout,
        estimated_payout_usdt: estimatedPayout,
        payout_multiplier: payoutMultiplier,
        adjusted_payout: adjustedPayout,
        adjusted_payout_usdt: adjustedPayout,
        video_type: videoType,
        language: normalizeContentLanguage(summary.language),
    }
}

function preferredCategorySet(profile: any): Set<string> {
    return new Set(
        (Array.isArray(profile?.preferred_category_ids) ? profile.preferred_category_ids : [])
            .map((id: any) => String(id || '').trim())
            .filter(Boolean)
    )
}

function topicMatchesPreferredCategory(topic: any, preferredCategories: Set<string>): boolean {
    return preferredCategories.size === 0 || preferredCategories.has(String(topic?.category_id || ''))
}

function calculateTopicScore(topic: any, profile: any, requesterEmail: string, filters: Record<string, boolean>): number {
    let score = 0
    if (String(topic?.assigned_employee_email || '').toLowerCase() === requesterEmail.toLowerCase()) score += 50

    if (!filters.ignore_language) {
        const category = topic?.categories || {}
        const topicLang = normalizeContentLanguage(topic?.language || category?.language)
        const preferredLangs = new Set(
            (Array.isArray(profile?.preferred_languages) && profile.preferred_languages.length ? profile.preferred_languages : ['ko'])
                .map(normalizeContentLanguage)
        )
        if (preferredLangs.has(topicLang)) score += 30
    }

    if (!filters.ignore_duration) {
        const prefLength = String(profile?.preferred_video_length || '')
        const duration = Number(topic?.assigned_duration_minutes || topic?.recommended_duration_minutes || 0)
        const bucket = durationPreferenceBucket(duration || null)
        if (prefLength && bucket && prefLength === bucket) score += 25
    }

    if (!filters.ignore_category) {
        const preferredCategories = new Set((profile?.preferred_category_ids || []).map((id: any) => String(id)))
        if (preferredCategories.size && preferredCategories.has(String(topic?.category_id || ''))) score += 20
    }

    if (topic?.created_at) {
        const ts = new Date(topic.created_at).getTime()
        if (Number.isFinite(ts) && Date.now() - ts < 86_400_000) score += 10
    }
    return score
}

async function cachedRecommendationTopics(email: string, limit: number, profile: any, filters: Record<string, boolean>) {
    const now = new Date().toISOString()
    const { data: cacheRows } = await supabaseAdmin
        .from('user_topic_recommendations')
        .select('*')
        .eq('employee_email', email)
        .eq('is_claimed', false)
        .gte('expires_at', now)
        .order('created_at', { ascending: false })
        .limit(limit)

    const topicIds = Array.from(new Set((cacheRows || []).map((row: any) => row.topic_queue_id).filter(Boolean)))
    if (!topicIds.length) return []

    const { data: liveTopics } = await supabaseAdmin
        .from('topics_queue')
        .select('*, categories(*)')
        .in('id', topicIds)
        .eq('status', 'pending')
        .is('assigned_at', null)
        .is('assigned_employee_email', null)
        .not('generated_title', 'is', null)

    const preferredCategories = filters.ignore_category ? new Set<string>() : preferredCategorySet(profile)
    const liveById = new Map((liveTopics || [])
        .filter(isPreparedStdTopic)
        .filter((topic: any) => filters.ignore_category || topicMatchesPreferredCategory(topic, preferredCategories))
        .map((topic: any) => [String(topic.id), topic])
    )
    return (cacheRows || []).map((row: any) => liveById.get(String(row.topic_queue_id))).filter(Boolean)
}

async function saveRecommendationCache(email: string, topics: any[], policy: Record<string, any>, boosts: Map<string, number>) {
    await supabaseAdmin
        .from('user_topic_recommendations')
        .delete()
        .eq('employee_email', email)
        .eq('is_claimed', false)

    if (!topics.length) return
    const expiresAt = new Date(Date.now() + 7 * 86_400_000).toISOString()
    const rows = topics.map((topic: any) => {
        const payoutMultiplier = boosts.get(String(topic.category_id)) || 1
        const normalized = normalizeTopicForStd(topic, policy, payoutMultiplier)
        return {
            user_id: null,
            employee_email: email,
            topic_queue_id: topic.id,
            topic: normalized.topic,
            language: normalized.language,
            recommended_duration_minutes: normalized.recommended_duration_minutes,
            estimated_payout: normalized.estimated_payout,
            script_style: normalized.script_style,
            image_style: normalized.image_style,
            category_id: normalized.category_id,
            category_name: normalized.category_name,
            payout_multiplier: payoutMultiplier,
            is_claimed: false,
            expires_at: expiresAt,
        }
    })
    await supabaseAdmin.from('user_topic_recommendations').insert(rows)
}

function extractTopicKeywords(text: string): Set<string> {
    const cleaned = text.replace(/["'“”‘’`「」『』\[\]()<>,.?!~|/\\:;]/g, ' ')
    const tokens = cleaned.split(/\s+/).filter(Boolean)
    const particles = ['은', '는', '이', '가', '을', '를', '의', '에', '에서', '로', '으로', '와', '과', '도', '만', '차', '앞둔', '위한', '통해', '대해', '대', '년', '월', '원']
    const roots = new Set<string>()

    for (const t of tokens) {
        const lower = t.toLowerCase()
        roots.add(lower)
        for (const p of particles) {
            if (lower.endsWith(p) && lower.length > p.length) {
                const stem = lower.slice(0, -p.length)
                if (stem.length >= 1) roots.add(stem)
                break
            }
        }
    }
    return roots
}

function calculateTopicSimilarity(a: string, b: string): number {
    const cleanA = a.replace(/[\s\W_]+/g, '').toLowerCase()
    const cleanB = b.replace(/[\s\W_]+/g, '').toLowerCase()
    if (!cleanA || !cleanB) return 0.0
    if (cleanA === cleanB) return 1.0

    // 1. Shingle overlap (4-char sliding window)
    const shinglesA = new Set<string>()
    const shinglesB = new Set<string>()
    for (let i = 0; i < cleanA.length - 3; i++) shinglesA.add(cleanA.slice(i, i + 4))
    for (let i = 0; i < cleanB.length - 3; i++) shinglesB.add(cleanB.slice(i, i + 4))
    
    let shingleOverlap = 0
    if (shinglesA.size > 0 && shinglesB.size > 0) {
        let inter = 0
        for (const s of shinglesA) {
            if (shinglesB.has(s)) inter++
        }
        shingleOverlap = inter / Math.min(shinglesA.size, shinglesB.size)
    }

    // 2. Keyword roots overlap
    const rootsA = extractTopicKeywords(a)
    const rootsB = extractTopicKeywords(b)
    let rootOverlap = 0
    if (rootsA.size > 0 && rootsB.size > 0) {
        let inter = 0
        for (const r of rootsA) {
            if (rootsB.has(r)) inter++
        }
        rootOverlap = inter / Math.min(rootsA.size, rootsB.size)
    }

    // 3. Numbers overlap bonus (e.g. 30년, 80만원)
    const numsA = a.match(/\d+/g) || []
    const numsB = b.match(/\d+/g) || []
    const numsSetB = new Set(numsB)
    const numMatches = numsA.filter(n => numsSetB.has(n)).length
    const numBonus = (numMatches >= 2 && (shingleOverlap > 0.12 || rootOverlap > 0.20)) ? 0.25 : 0

    return Math.min(1.0, Math.max(shingleOverlap, rootOverlap) + numBonus)
}

function deduplicateTopics(topics: any[]): any[] {
    const seenTitles = new Set<string>()
    const seenIds = new Set<string>()
    const unique: any[] = []

    for (const t of topics) {
        if (!t) continue
        const id = String(t.id || '')
        const rawTitle = String(t.generated_title || t.topic || '').trim()
        if (!rawTitle) continue
        if (id && seenIds.has(id)) continue
        const titleKey = rawTitle.toLowerCase().replace(/\s+/g, '')
        if (seenTitles.has(titleKey)) continue

        if (id) seenIds.add(id)
        seenTitles.add(titleKey)
        unique.push(t)
    }

    return unique
}

export async function getStdRecommendedTopics(options: {
    email: string
    profile: any
    limit: number
    refresh: boolean
    filters: Record<string, boolean>
}) {
    const [policy, boosts] = await Promise.all([loadPolicy(), loadBoosts()])

    if (!options.refresh) {
        const cached = await cachedRecommendationTopics(options.email, options.limit, options.profile, options.filters)
        const dedupedCached = deduplicateTopics(cached)
        if (dedupedCached.length >= options.limit) {
            return {
                topics: dedupedCached
                    .slice(0, options.limit)
                    .map((topic: any) => normalizeTopicForStd(topic, policy, boosts.get(String(topic.category_id)) || 1)),
                cached: true,
            }
        }
    }

    const { data, error } = await supabaseAdmin
        .from('topics_queue')
        .select('*, categories(*)')
        .eq('status', 'pending')
        .is('assigned_at', null)
        .is('assigned_employee_email', null)
        .not('generated_title', 'is', null)
        .order('created_at', { ascending: false })
        .limit(300)
    if (error) throw error

    // 1. 중복 제거된 준비된 주제 목록
    const preparedTopics = deduplicateTopics((data || []).filter(isPreparedStdTopic))
    const preferredCategories = options.filters.ignore_category ? new Set<string>() : preferredCategorySet(options.profile)
    const candidateTopics = preparedTopics.filter((topic: any) =>
        options.filters.ignore_category || topicMatchesPreferredCategory(topic, preferredCategories)
    )
    
    let selectedTopics = candidateTopics
        .map((topic: any) => ({
            topic,
            score: calculateTopicScore(topic, options.profile, options.email, options.filters),
        }))
        .filter((row: any) => row.score > 0)
        .sort((a: any, b: any) => b.score - a.score)
        .slice(0, options.limit)
        .map((row: any) => row.topic)

    // Fallback: If filtered score produced not enough topics, fill from prepared topics
    if (selectedTopics.length < options.limit) {
        const existingIds = new Set(selectedTopics.map((t: any) => String(t.id)))
        const existingTitles = new Set(selectedTopics.map((t: any) => String(t.generated_title || t.topic || '').trim().toLowerCase().replace(/\s+/g, '')))
        
        const remaining = candidateTopics.filter((t: any) => {
            const id = String(t.id || '')
            const titleKey = String(t.generated_title || t.topic || '').trim().toLowerCase().replace(/\s+/g, '')
            return !existingIds.has(id) && !existingTitles.has(titleKey)
        }).slice(0, options.limit - selectedTopics.length)
        
        selectedTopics = [...selectedTopics, ...remaining]
    }

    const finalDeduped = deduplicateTopics(selectedTopics)
    await saveRecommendationCache(options.email, finalDeduped, policy, boosts)

    return {
        topics: finalDeduped.map((topic: any) => normalizeTopicForStd(topic, policy, boosts.get(String(topic.category_id)) || 1)),
        cached: false,
    }
}
