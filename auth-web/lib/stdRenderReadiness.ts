import { isNonverbalProject } from './stdNonverbal'

export function needsFreshNarration(project: any) {
    return !isNonverbalProject(project) && Boolean(project.progress_payload?.script_changed_requires_audio_regeneration)
}

export async function activeStdRenderJobs(db: any, ids: string[]) {
    if (!ids.length) return new Map<string, string>()
    const { data, error } = await db.from('std_project_assets')
        .select('id,project_id,state:metadata->>state')
        .in('project_id', ids).eq('asset_type', 'other')
        .in('metadata->>kind', ['motion_automation', 'effectcraft_automation', 'filmcraft_automation', 'horizontal_webtoon_automation', 'ae_mouth_job'])
        .in('metadata->>state', ['queued', 'processing'])
        .order('id')
    if (error) throw error
    return new Map<string, string>((data || []).map((job: any) => [job.project_id, job.id]))
}

export async function activeStdRenderQueueRows(db: any, ids: string[]) {
    if (!ids.length) return new Map<string, string>()
    const { data, error } = await db.from('remote_render_queue')
        .select('id,project_id:metadata->>std_web_project_id')
        .in('metadata->>std_web_project_id', ids)
        .in('status', ['pending', 'rendering'])
        .order('id')
    if (error) throw error
    return new Map<string, string>((data || []).map((row: any) => [row.project_id, row.id]))
}
