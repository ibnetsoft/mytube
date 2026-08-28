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

export async function syncContentFeedbackToNotion(row: any): Promise<void> {
    const token = notionToken()
    const databaseId = notionLearningDatabaseId()
    if (!token || !databaseId || !row) return

    const title = row.generated_title || row.production_topic || row.topic_queue_id || 'AIR learning row'
    const bodyText = [
        `Category: ${row.category_name || row.category_id || '-'}`,
        `Quality: ${row.outcome_quality || 'unknown'}`,
        `Title score: ${row.title_score ?? '-'}`,
        `Script score: ${row.script_score ?? '-'}`,
        `Topic: ${row.production_topic || '-'}`,
        `Generated title: ${row.generated_title || '-'}`,
        row.reviewer_note ? `Reviewer note: ${row.reviewer_note}` : '',
    ].filter(Boolean).join('\n')

    const payload = {
        parent: { database_id: databaseId },
        properties: {
            Name: titleText(title),
            Category: richText(row.category_name || ''),
            'Category ID': richText(row.category_id || ''),
            Quality: selectName(row.outcome_quality),
            Source: selectName(row.feedback_source),
            'Topic Queue ID': richText(row.topic_queue_id || ''),
            'Source Job ID': richText(row.source_job_id || ''),
            'Title Score': numberValue(row.title_score),
            'Script Score': numberValue(row.script_score),
            'Created At': { date: { start: row.created_at || row.updated_at || new Date().toISOString() } },
            'Learning Text': richText(bodyText),
        },
        children: [
            {
                object: 'block',
                type: 'paragraph',
                paragraph: { rich_text: [{ type: 'text', text: { content: bodyText.slice(0, 1900) } }] },
            },
            jsonBlock('metrics', row.metrics || {}),
            jsonBlock('title_generation', row.title_generation || {}),
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
