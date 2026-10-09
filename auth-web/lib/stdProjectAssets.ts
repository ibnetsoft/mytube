import { appendGeneratedSpeakerAssets } from './stdGeneratedSpeakerGeometry'
/** Read every active asset, including original clips older than the REST row limit. */
export async function loadStdProjectAssets(db: any, projectId: string, columns: string) {
    const assets: any[] = []
    const pageSize = 500
    for (let start = 0; ; start += pageSize) {
        const { data, error } = await db.from('std_project_assets')
            .select(columns)
            .eq('project_id', projectId)
            .in('status', ['uploaded', 'assigned'])
            .order('created_at', { ascending: false })
            .order('id', { ascending: false })
            .range(start, start + pageSize - 1)
        if (error) return { data: null, error }
        assets.push(...(data || []))
        if ((data || []).length < pageSize) {
            try { return { data: await appendGeneratedSpeakerAssets(db, [projectId], assets), error: null } }
            catch (error) { return { data: null, error } }
        }
    }
}
