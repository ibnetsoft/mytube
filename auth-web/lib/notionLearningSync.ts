const NOTION_VERSION = '2022-06-28'

function notionToken(): string {
    return String(process.env.NOTION_API_KEY || process.env.NOTION_TOKEN || '').trim()
}

function notionLearningDatabaseId(): string {
    return String(process.env.NOTION_LEARNING_DATABASE_ID || '').trim()
}

function richText(text: any) {
    const content = String(text ?? '').slice(0, 1900)
    return { rich_text: [{ type: 'text', text: { content } }] }
}

function titleText(text: any) {
    const content = String(text ?? 'Untitled learning row').slice(0, 1900)
    return { title: [{ type: 'text', text: { content } }] }
}

function selectName(value: any, fallback = 'unknown') {
    const name = String(value || fallback).slice(0, 100)
    return { select: { name } }
}

function numberValue(value: any) {
    const n = Number(value)
    return Number.isFinite(n) ? { number: n } : { number: null }
}

function dateValue(value: any) {
    return { date: { start: value || new Date().toISOString() } }
}

async function notionDatabaseProperties(token: string, databaseId: string): Promise<Record<string, any>> {
    const response = await fetch(`https://api.notion.com/v1/databases/${databaseId}`, {
        headers: {
            Authorization: `Bearer ${token}`,
            'Notion-Version': NOTION_VERSION,
        },
    })
    if (!response.ok) return {}
    const data = await response.json().catch(() => ({}))
    return data?.properties && typeof data.properties === 'object' ? data.properties : {}
}

function titlePropertyName(properties: Record<string, any>): string {
    return Object.entries(properties).find(([, meta]: any) => meta?.type === 'title')?.[0] || 'Name'
}

function propertyValue(type: string | undefined, value: any) {
    if (type === 'title') return titleText(value)
    if (type === 'rich_text') return richText(value)
    if (type === 'select') return selectName(value)
    if (type === 'number') return numberValue(value)
    if (type === 'date') return dateValue(value)
    return null
}

function putProperty(target: Record<string, any>, properties: Record<string, any>, name: string, value: any) {
    const meta = properties[name]
    if (!meta) return
    const converted = propertyValue(meta.type, value)
    if (converted) target[name] = converted
}

function jsonBlock(label: string, value: any) {
    return {
        object: 'block',
        type: 'code',
        code: {
            language: 'json',
            rich_text: [{
                type: 'text',
                text: { content: JSON.stringify({ [label]: value ?? null }, null, 2).slice(0, 1900) },
            }],
        },
    }
}

function compactTitleCandidates(titleGeneration: any, limit = 6) {
    const data = titleGeneration && typeof titleGeneration === 'object' ? titleGeneration : {}
    const candidates = Array.isArray(data.title_candidates) ? data.title_candidates : []
    return {
        generated_title: String(data.generated_title || data.final_title || '').slice(0, 180),
        selected_score: data.selected_score ?? null,
        title_candidates: candidates.slice(0, limit).map((candidate: any) => ({
            title: String(candidate?.title || '').slice(0, 180),
            angle: String(candidate?.angle || '').slice(0, 220),
            score: candidate?.final_score ?? candidate?.score ?? null,
        })).filter((candidate: any) => candidate.title),
    }
}

export async function syncContentFeedbackToNotion(row: any): Promise<void> {
    const token = notionToken()
    const databaseId = notionLearningDatabaseId()
    if (!token || !databaseId || !row) return
    const databaseProperties = await notionDatabaseProperties(token, databaseId)
    const titleProp = titlePropertyName(databaseProperties)

    const title = row.generated_title || row.production_topic || row.topic_queue_id || 'AIR learning row'
    const bodyText = [
        row.source_job_id ? `Source ID: ${row.source_job_id}` : '',
        `Category: ${row.category_name || row.category_id || '-'}`,
        `Quality: ${row.outcome_quality || 'unknown'}`,
        `Title score: ${row.title_score ?? '-'}`,
        `Script score: ${row.script_score ?? '-'}`,
        `Topic: ${row.production_topic || '-'}`,
        `Generated title: ${row.generated_title || '-'}`,
        row.reviewer_note ? `Reviewer note: ${row.reviewer_note}` : '',
    ].filter(Boolean).join('\n')

    const properties: Record<string, any> = {
        [titleProp]: titleText(title),
    }
    putProperty(properties, databaseProperties, 'Category', row.category_name || '')
    putProperty(properties, databaseProperties, 'Category ID', row.category_id || '')
    putProperty(properties, databaseProperties, 'Quality', row.outcome_quality)
    putProperty(properties, databaseProperties, 'Source', row.feedback_source)
    putProperty(properties, databaseProperties, 'Topic Queue ID', row.topic_queue_id || '')
    putProperty(properties, databaseProperties, 'Source Job ID', row.source_job_id || '')
    putProperty(properties, databaseProperties, 'Title Score', row.title_score)
    putProperty(properties, databaseProperties, 'Script Score', row.script_score)
    putProperty(properties, databaseProperties, 'Created At', row.created_at || row.updated_at || new Date().toISOString())
    putProperty(properties, databaseProperties, 'Learning Text', bodyText)

    const payload = {
        parent: { database_id: databaseId },
        properties,
        children: [
            {
                object: 'block',
                type: 'paragraph',
                paragraph: { rich_text: [{ type: 'text', text: { content: bodyText.slice(0, 1900) } }] },
            },
            jsonBlock('metrics', row.metrics || {}),
            jsonBlock('title_generation', row.title_generation || {}),
            jsonBlock('title_candidates_compact', compactTitleCandidates(row.title_generation || {})),
            jsonBlock('benchmark_summary', row.benchmark_summary || {}),
            jsonBlock('evaluation', row.evaluation || {}),
        ],
    }

    const response = await fetch('https://api.notion.com/v1/pages', {
        method: 'POST',
        headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
            'Notion-Version': NOTION_VERSION,
        },
        body: JSON.stringify(payload),
    })

    if (!response.ok) {
        const text = await response.text().catch(() => '')
        console.warn('[notionLearningSync] Notion sync failed:', response.status, text.slice(0, 300))
    }
}

export async function syncMusicLearningToNotion(row: any): Promise<void> {
    const token = notionToken()
    const databaseId = notionLearningDatabaseId()
    if (!token || !databaseId || !row) return
    const databaseProperties = await notionDatabaseProperties(token, databaseId)
    const titleProp = titlePropertyName(databaseProperties)
    const title = row.title || row.task_title || row.prompt_title || row.source_id || 'AIR music learning row'
    const source = row.feedback_source || row.source || 'music_submission'
    const category = row.category || [
        'music',
        String(row.target_market || row.market || 'global').trim().toLowerCase(),
        String(row.genre || '').trim().toLowerCase(),
    ].filter(Boolean).join(':')
    const bodyText = [
        `Source ID: ${row.source_id || row.submission_id || row.task_id || '-'}`,
        `Market: ${row.target_market || row.market || '-'}`,
        `Genre: ${row.genre || '-'}`,
        `Mood: ${row.mood || '-'}`,
        `Tool: ${row.tool_name || '-'}`,
        `Prompt: ${row.prompt_used || row.prompt || '-'}`,
        row.lyrics ? `Lyrics: ${row.lyrics}` : '',
        Array.isArray(row.negative_rules) && row.negative_rules.length ? `Negative rules: ${row.negative_rules.join(', ')}` : '',
        row.quality_note ? `Quality note: ${row.quality_note}` : '',
    ].filter(Boolean).join('\n')

    const properties: Record<string, any> = {
        [titleProp]: titleText(title),
    }
    putProperty(properties, databaseProperties, 'Category', category)
    putProperty(properties, databaseProperties, 'Category ID', category)
    putProperty(properties, databaseProperties, 'Quality', row.outcome_quality || 'music_memory')
    putProperty(properties, databaseProperties, 'Source', source)
    putProperty(properties, databaseProperties, 'Source Job ID', row.source_id || row.submission_id || row.task_id || '')
    putProperty(properties, databaseProperties, 'Title Score', row.title_score ?? '')
    putProperty(properties, databaseProperties, 'Script Score', row.script_score ?? '')
    putProperty(properties, databaseProperties, 'Created At', row.created_at || row.submitted_at || new Date().toISOString())
    putProperty(properties, databaseProperties, 'Learning Text', bodyText)

    const response = await fetch('https://api.notion.com/v1/pages', {
        method: 'POST',
        headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
            'Notion-Version': NOTION_VERSION,
        },
        body: JSON.stringify({
            parent: { database_id: databaseId },
            properties,
            children: [
                {
                    object: 'block',
                    type: 'paragraph',
                    paragraph: { rich_text: [{ type: 'text', text: { content: bodyText.slice(0, 1900) } }] },
                },
                jsonBlock('music_metadata', row.metadata || {}),
            ],
        }),
    })
    if (!response.ok) {
        const text = await response.text().catch(() => '')
        console.warn('[notionLearningSync] Music Notion sync failed:', response.status, text.slice(0, 300))
    }
}
