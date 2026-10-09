import { loadStdProjectAssets } from './stdProjectAssets'
import { supabaseAdmin } from './supabaseAdmin'
import { aeMouthApplicable } from './stdAeMouth'
import { ensureAeMouthJob } from './stdAeMouthQueue'

/** A replacement source needs a fresh AE input before automatic final rendering. */
export async function queueSubmittedVideoReplacement(project: any, projectPayload: any) {
    if (project.status !== 'review_requested' || !project.submitted_at) return
    const [scenes, assets] = await Promise.all([
        supabaseAdmin.from('std_project_scenes').select('*').eq('project_id', project.id).order('scene_number'),
        loadStdProjectAssets(supabaseAdmin, project.id, '*'),
    ])
    if (scenes.error || assets.error) throw scenes.error || assets.error
    const current = { ...project, project_payload: projectPayload }
    if (aeMouthApplicable(current, scenes.data || [])) {
        await ensureAeMouthJob(current, scenes.data || [], assets.data || [])
    }
}
