export const TOPIC_DELETE_LIMIT = 500
const DELETABLE_STATUSES = ['pending', 'excluded']
const TERMINAL_JOB_STATUSES = '(completed,failed,canceled,cancelled)'

export class TopicDeletionInputError extends Error {}

export function topicDeletionLanguage(value: unknown) {
    if (typeof value !== 'string' || !['ko', 'ja', 'en'].includes(value)) {
        throw new TopicDeletionInputError('국가를 한국, 일본, 미국 중에서 선택해 주세요.')
    }
    return value
}

export function topicDeletionIds(value: unknown): string[] {
    if (!Array.isArray(value) || !value.length || value.length > TOPIC_DELETE_LIMIT) {
        throw new TopicDeletionInputError(`한 번에 1~${TOPIC_DELETE_LIMIT}개의 주제를 선택해 주세요.`)
    }
    const ids = value.map(item => {
        if (typeof item !== 'string' && !(typeof item === 'number' && Number.isSafeInteger(item))) {
            throw new TopicDeletionInputError('올바르지 않은 주제 ID입니다.')
        }
        const id = String(item)
        if (!/^[1-9]\d{0,18}$/.test(id) || BigInt(id) > BigInt('9223372036854775807')) {
            throw new TopicDeletionInputError('올바르지 않은 주제 ID입니다.')
        }
        return id
    })
    return [...new Set(ids)]
}

function categoryLanguage(value: unknown) {
    const language = String(value || '').trim().toLowerCase()
    return ['ko', 'ja', 'en'].includes(language) ? language : 'ko'
}

async function categoriesForLanguage(db: any, language: string) {
    // Older category schemas do not contain video_type; keep the same fallback
    // as the dashboard instead of requiring a new database column.
    const { data, error } = await db.from('categories').select('*')
    if (error) throw error
    return (data || []).filter((category: any) => categoryLanguage(category.language) === language)
}

async function protectionReasons(db: any, topics: any[]) {
    const reasons = new Map<string, string>()
    for (const topic of topics) {
        if (!DELETABLE_STATUSES.includes(topic.status) || topic.assigned_at) {
            reasons.set(String(topic.id), '작업이 시작된 주제는 삭제할 수 없습니다.')
        }
    }
    const ids = topics.map(topic => String(topic.id))
    for (let offset = 0; offset < ids.length; offset += 100) {
        const batch = ids.slice(offset, offset + 100)
        for (let from = 0; ; from += 1000) {
            const { data: projects, error: projectError } = await db.from('std_projects')
                .select('id,topic_queue_id').in('topic_queue_id', batch)
                .order('id', { ascending: true }).range(from, from + 999)
            if (projectError) throw projectError
            for (const project of projects || []) {
                reasons.set(String(project.topic_queue_id), '연결된 프로젝트가 있어 삭제할 수 없습니다.')
            }
            if ((projects || []).length < 1000) break
        }
        // Include pending, leased and running jobs, while preserving completed
        // job history. IDs are validated numeric strings before entering filters.
        for (let from = 0; ; from += 1000) {
            const { data: jobs, error: jobError } = await db.from('remote_hermes_queue')
                .select('id,topic_queue_id:payload->>topic_queue_id,topic_id:payload->>topic_id')
                .not('status', 'in', TERMINAL_JOB_STATUSES)
                .or(`payload->>topic_queue_id.in.(${batch.join(',')}),payload->>topic_id.in.(${batch.join(',')})`)
                .order('id', { ascending: true }).range(from, from + 999)
            if (jobError) throw jobError
            for (const job of jobs || []) {
                for (const id of [job.topic_queue_id, job.topic_id]) {
                    if (id != null && batch.includes(String(id))) {
                        reasons.set(String(id), '주제 생성 작업이 진행 중입니다. 완료 후 다시 시도해 주세요.')
                    }
                }
            }
            if ((jobs || []).length < 1000) break
        }
        // The current local Codex worker stores repair targets here, rather than
        // in the older Hermes queue. Approval/application-pending work also
        // needs its source topic preserved. web_topic_id refers to a separate
        // UUID submission table, so the topic link is kind + source_id.
        for (let from = 0; ; from += 1000) {
            const { data: jobs, error: jobError } = await db.from('script_worker_jobs')
                .select('id,source_id:request_data->>source_id')
                .eq('request_data->>kind', 'topic').in('request_data->>source_id', batch)
                .not('status', 'in', '(completed,failed,interrupted,canceled,cancelled)')
                .order('id', { ascending: true }).range(from, from + 999)
            if (jobError) throw jobError
            for (const job of jobs || []) {
                reasons.set(String(job.source_id), '대본 생성·검토 작업이 진행 중입니다. 완료 후 다시 시도해 주세요.')
            }
            if ((jobs || []).length < 1000) break
        }
    }
    return reasons
}

export async function listTopicsForDeletion(db: any, language: string, page: number, perPage: number) {
    const categories = await categoriesForLanguage(db, language)
    if (!categories.length) return { success: true, topics: [], page, perPage, total: 0, hasMore: false }
    const from = (page - 1) * perPage
    const { data, error, count } = await db.from('topics_queue')
        .select('id,topic,category_id,status,assigned_at', { count: 'exact' })
        .in('category_id', categories.map((category: any) => category.id))
        .in('status', DELETABLE_STATUSES)
        .order('id', { ascending: false }).range(from, from + perPage - 1)
    if (error) throw error
    const topics = data || []
    const reasons = await protectionReasons(db, topics)
    const byId = new Map<string, any>(categories.map((category: any) => [String(category.id), category]))
    return {
        success: true,
        topics: topics.map((topic: any) => {
            const category = byId.get(String(topic.category_id))
            const reason = reasons.get(String(topic.id))
            return {
                id: String(topic.id), topic: topic.topic, category_id: String(topic.category_id),
                category_name: category?.name || '', video_type: category?.video_type || 'longform',
                status: topic.status, ...(reason ? { delete_block_reason: reason } : {}),
            }
        }),
        page, perPage, total: count ?? topics.length,
        hasMore: count != null ? from + perPage < count : topics.length === perPage,
    }
}

export async function deleteSelectedTopics(db: any, ids: string[], language: string) {
    const categories = await categoriesForLanguage(db, language)
    const categoryIds = categories.map((category: any) => String(category.id))
    const deletedIds: string[] = []
    const skipped: { id: string; reason: string }[] = []
    // Complete all reads before deleting so a failed protection lookup fails
    // closed and cannot result in an unchecked deletion.
    const topics: any[] = []
    for (let offset = 0; offset < ids.length; offset += 100) {
        const { data, error } = await db.from('topics_queue')
            .select('id,category_id,status,assigned_at').in('id', ids.slice(offset, offset + 100))
        if (error) throw error
        topics.push(...(data || []))
    }
    const reasons = await protectionReasons(db, topics)
    const byId = new Map(topics.map(topic => [String(topic.id), topic]))
    const eligible: string[] = []
    for (const id of ids) {
        const topic = byId.get(id)
        const reason = !topic ? '이미 삭제되었거나 찾을 수 없는 주제입니다.'
            : !categoryIds.includes(String(topic.category_id)) ? '선택한 국가의 주제가 아닙니다.'
            : reasons.get(id)
        if (reason) skipped.push({ id, reason })
        else eligible.push(id)
    }
    for (let offset = 0; offset < eligible.length; offset += 100) {
        const batch = eligible.slice(offset, offset + 100)
        const { data, error } = await db.from('topics_queue').delete()
            .in('id', batch).in('category_id', categoryIds)
            .in('status', DELETABLE_STATUSES).is('assigned_at', null).select('id')
        if (error) {
            console.error('Selected topic deletion batch failed:', error)
            for (const id of eligible.slice(offset)) {
                skipped.push({ id, reason: '삭제하지 못했습니다. 잠시 후 다시 시도해 주세요.' })
            }
            break
        }
        const actual = new Set<string>((data || []).map((topic: any) => String(topic.id)))
        for (const id of batch) {
            if (actual.has(id)) deletedIds.push(id)
            else skipped.push({ id, reason: '주제 상태가 변경되어 삭제하지 않았습니다. 목록을 새로 불러와 주세요.' })
        }
    }
    return { success: true, deletedIds, deletedCount: deletedIds.length, skipped }
}
