import { deleteGcsObject } from './gcsStorage'
import { supabaseAdmin } from './supabaseAdmin'

/** Delete only replaced, project-owned clips after their successor is saved. */
export async function cleanupReplacedSceneVideos(projectId: string, oldAssets: any[], newAsset: any) {
    const newMetadata = newAsset?.metadata || {}
    const newPath = String(newMetadata.gcs_path || newMetadata.storage_path || '')
    if (!newAsset?.id || !newPath || !['uploaded', 'assigned'].includes(newAsset.status)) {
        throw new Error('The replacement video was not saved')
    }
    for (const old of oldAssets) {
        if (old.id === newAsset.id) continue
        const metadata = old.metadata || {}
        const bucket = String(metadata.gcs_bucket || metadata.storage_bucket || '')
        const path = String(metadata.gcs_path || metadata.storage_path || '')
        if (!bucket || !path || path === newPath || !path.startsWith(`std-projects/${projectId}/scenes/`)) continue
        const current = await supabaseAdmin.from('std_project_assets').select('status').eq('id', old.id).single()
        if (current.error) throw current.error
        if (current.data?.status !== 'replaced') continue
        const [byGcs, byStorage] = await Promise.all([
            supabaseAdmin.from('std_project_assets').select('id').eq('project_id', projectId)
                .in('status', ['uploaded', 'assigned']).eq('metadata->>gcs_path', path).limit(1),
            supabaseAdmin.from('std_project_assets').select('id').eq('project_id', projectId)
                .in('status', ['uploaded', 'assigned']).eq('metadata->>storage_path', path).limit(1),
        ])
        if (byGcs.error || byStorage.error) throw byGcs.error || byStorage.error
        if ((byGcs.data || []).length || (byStorage.data || []).length) continue
        await deleteGcsObject({ bucket, objectPath: path })
    }
}
