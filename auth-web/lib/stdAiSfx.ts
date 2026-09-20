import { sfxNeedsReview } from './stdSfxCues'
import { createHash } from 'crypto'
import { supabaseAdmin } from './supabaseAdmin'
import { sfxDescriptionKo } from './stdSfxDescriptions'

export const AI_SFX_SOURCE = 'codex-sfx-v1'
export function sfxSnapshot(subtitles: any[]) {
    return createHash('sha256').update(JSON.stringify(subtitles.map(s => [s.id ?? null, s.scene_number, s.text]))).digest('hex')
}
export async function sharedSfxCatalog(): Promise<any[]> {
    const { data, error } = await supabaseAdmin.storage.from('content-assets').download('sfx-library/catalog.json')
    if (error || !data) throw new Error('공용 효과음 목록을 불러오지 못했습니다.')
    const parsed = JSON.parse(await data.text())
    return (parsed.items || []).filter((a: any) => a.id && a.metadata?.storage_path)
}
export async function projectSfxCatalog(projectId: string) {
    const { data, error } = await supabaseAdmin.from('std_project_assets').select('*')
        .eq('project_id', projectId).in('status', ['uploaded', 'assigned'])
        .or('asset_type.eq.sfx,metadata->>audio_role.eq.sfx')
    if (error) throw error
    const shared = await sharedSfxCatalog()
    const local = (data || []).filter(a => a.metadata?.storage_path || a.drive_file_id)
    const paths = new Set(local.map(a => a.metadata?.storage_path).filter(Boolean))
    return [...local, ...shared.filter(a => !paths.has(a.metadata?.storage_path))]
        .map(a => ({ ...a, description_ko: sfxDescriptionKo(a) }))
}
export async function attachSfxAssets(projectId: string, cues: any[], catalog: any[]) {
    const out = []
    for (const cue of cues) {
        const source = catalog.find(a => a.id === cue.asset_id)
        if (!source) continue
        let asset = source
        if (source.project_id !== projectId) {
            const found = await supabaseAdmin.from('std_project_assets').select('*').eq('project_id', projectId)
                .eq('metadata->>sfx_library_id', source.id).in('status', ['uploaded','assigned']).limit(1).maybeSingle()
            if (found.error) throw found.error
            asset = found.data
            if (!asset) {
                const saved = await supabaseAdmin.from('std_project_assets').insert({
                    project_id: projectId, asset_type: 'other', status: 'uploaded',
                    file_name: source.file_name, mime_type: source.mime_type || 'audio/mpeg', file_size: source.file_size,
                    metadata: { ...source.metadata, audio_role: 'sfx', sfx_library_id: source.id },
                }).select('*').single()
                if (saved.error) throw saved.error
                asset = saved.data
            }
        }
        out.push({ ...cue, asset_id: asset.id, file_name: asset.file_name })
    }
    return out
}

export function preserveSfxForAnalysis(existing: any[], subtitles: any[]) {
    return existing.map(c => ({ ...c, keep_ai: c.source === AI_SFX_SOURCE && !sfxNeedsReview(c, subtitles) }))
}

export function mergeAiSfx(existing: any[], proposed: any[], subtitles?: any[]) {
    const manual = existing.filter(c => c.source !== AI_SFX_SOURCE || c.user_override)
    const retainedAi = subtitles ? existing.filter(c => c.source === AI_SFX_SOURCE && !c.user_override) : []
    const protectedScenes = new Set([...manual, ...retainedAi.filter(c => !sfxNeedsReview(c, subtitles!))].map(c => String(c.scene_number)))
    return [...manual, ...retainedAi, ...proposed.filter(c => !protectedScenes.has(String(c.scene_number)))]
}
