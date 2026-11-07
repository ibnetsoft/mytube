import { createHash } from 'crypto'
import type { SupabaseClient } from '@supabase/supabase-js'

export const PROJECT_TITLE_TRANSLATIONS_TABLE = 'std_project_title_translations'
export const titleSourceHash = (source: string) => createHash('sha256').update(source).digest('hex')
export function titleTranslationMap(value: unknown): Record<string, string> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
    return Object.fromEntries(Object.entries(value).filter(([locale, title]) =>
        ['ko', 'en', 'vi', 'th'].includes(locale) && typeof title === 'string' && title.trim())) as Record<string, string>
}

export type ProjectTitleTranslation = { id: string; source: string; title: string }

// Call only with projects already scoped to the authorized owner. Never load payloads here.
export async function loadSavedProjectTitleTranslations(db: SupabaseClient, projects: any[]) {
    const byId = new Map(projects.map(project => [project.id, project.title]))
    const saved = new Map<string, Record<string, string>>()
    const ids = [...byId.keys()]
    for (let offset = 0; offset < ids.length; offset += 100) {
        const { data, error } = await db.from(PROJECT_TITLE_TRANSLATIONS_TABLE)
            .select('project_id,source_hash,source_title,locale,translated_title')
            .in('project_id', ids.slice(offset, offset + 100))
            .in('source_hash', ids.slice(offset, offset + 100).map(id => titleSourceHash(byId.get(id))))
        if (error) throw error
        for (const row of data || []) {
            const source = byId.get(row.project_id)
            if (typeof source !== 'string' || row.source_title !== source || row.source_hash !== titleSourceHash(source)) continue
            saved.set(row.project_id, { ...saved.get(row.project_id), [row.locale]: row.translated_title })
        }
    }
    return saved
}

export async function saveProjectTitleTranslations(db: SupabaseClient, locale: string, translations: ProjectTitleTranslation[]) {
    if (!translations.length) return
    const { error } = await db.from(PROJECT_TITLE_TRANSLATIONS_TABLE).upsert(translations.map(item => ({
        project_id: item.id, source_hash: titleSourceHash(item.source), source_title: item.source,
        locale, translated_title: item.title,
    })), { onConflict: 'project_id,source_hash,locale', ignoreDuplicates: true })
    if (error) throw error
}
