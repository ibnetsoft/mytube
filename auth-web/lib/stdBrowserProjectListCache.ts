// A small, scoped snapshot lets the list render while the server refreshes it.
// Never persist bearer tokens, full project payloads, subtitles or asset metadata.
const VERSION = 1
const MAX_AGE_MS = 24 * 60 * 60 * 1000
const PREFIX = 'std-project-list:v1:'
const FIELDS = ['id','title','status','language','category_id','category_name','topic_queue_id',
    'assigned_duration_minutes','created_at','updated_at','submitted_at',
    'latest_render_version','step_status','shared_submission','title_localization','title_translations'] as const

type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>
export function projectListScope(email: unknown, impersonateEmail: unknown = ''): string {
    const owner = String(email || '').trim().toLowerCase()
    if (!owner) return ''
    return JSON.stringify([owner, String(impersonateEmail || '').trim().toLowerCase()])
}
const keyFor = (scope: string) => PREFIX + encodeURIComponent(scope)
export function readProjectListSnapshot(storage: StorageLike, scope: string, now = Date.now()): any[] | null {
    if (!scope) return null
    try {
        const raw = storage.getItem(keyFor(scope))
        if (!raw) return null
        const value = JSON.parse(raw)
        if (value?.version !== VERSION || value.scope !== scope || !Number.isFinite(value.savedAt)
            || value.savedAt > now || now - value.savedAt > MAX_AGE_MS || !Array.isArray(value.projects)
            || value.projects.some((item: any) => !item || typeof item.id !== 'string' || typeof item.title !== 'string')) return null
        return value.projects
    } catch { return null }
}
export function writeProjectListSnapshot(storage: StorageLike, scope: string, projects: any[], now = Date.now()): void {
    if (!scope || !Array.isArray(projects)) return
    try {
        const previous = new Map((readProjectListSnapshot(storage, scope, now) || []).map(project => [project.id, project]))
        const safe = projects.map(project => Object.fromEntries(FIELDS.filter(field => project?.[field] !== undefined).map(field => [field, project[field]])))
        for (const project of safe) {
            const old: any = previous.get(project.id)
            if (old?.title !== project.title || !old?.title_localization?.title_translations) continue
            project.title_localization = { ...project.title_localization, title_translations: {
                ...old.title_localization.title_translations, ...project.title_localization?.title_translations,
            } }
        }
        storage.setItem(keyFor(scope), JSON.stringify({ version: VERSION, scope, savedAt: now, projects: safe }))
    } catch { /* Storage can be disabled or full; the live request remains authoritative. */ }
}
export function clearProjectListSnapshot(storage: StorageLike, scope: string): void {
    if (!scope) return
    try { storage.removeItem(keyFor(scope)) } catch { /* ignored */ }
}
export function saveProjectListTitleTranslations(storage: StorageLike, scope: string, locale: string, translations: any[], now = Date.now()): void {
    if (!scope || !['ko','en','vi','th'].includes(locale) || !Array.isArray(translations)) return
    try {
        const projects = readProjectListSnapshot(storage, scope, now)
        if (!projects) return
        const raw = JSON.parse(storage.getItem(keyFor(scope)) || 'null')
        const byId = new Map(translations.filter(item => typeof item?.id === 'string' && typeof item?.source === 'string'
            && typeof item?.title === 'string' && item.title.trim()).map(item => [item.id, item]))
        for (const project of projects) {
            const item: any = byId.get(project.id)
            if (!item || item.source !== project.title || item.title === item.source) continue
            project.title_localization = { ...project.title_localization, title_translations: {
                ...project.title_localization?.title_translations, [locale]: item.title.trim(),
            } }
        }
        storage.setItem(keyFor(scope), JSON.stringify({ ...raw, projects }))
    } catch { /* Preserve the live result even if storage is unavailable. */ }
}

// Concurrent startup and modal reads use one authorized request per scope.
const pending = new Map<string, Promise<Response>>()
export async function fetchSharedProjectList(url: string, headers: Record<string, string>, force = false): Promise<Response> {
    const scope = JSON.stringify([headers.Authorization || '', headers['x-impersonate-email'] || '', force])
    let request = pending.get(scope)
    if (!request) {
        const requestHeaders = force ? { ...headers, 'x-std-list-refresh': '1' } : headers
        request = fetch(url, { headers: requestHeaders, cache: 'no-store', signal: AbortSignal.timeout(20000) })
        pending.set(scope, request)
        void request.finally(() => { if (pending.get(scope) === request) pending.delete(scope) }).catch(() => {})
    }
    return (await request).clone()
}
