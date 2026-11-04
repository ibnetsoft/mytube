/** Server-only status projection: the database removes prompts and large receipts
 * before data crosses the network. Never fall back to downloading full projects. */
export async function loadStdProjectStatusContext(db: any, projectIds: string[]) {
    if (!projectIds.length) return []
    const { data, error } = await db.rpc('std_project_status_context', { p_project_ids: projectIds })
    if (error) throw error
    if (!Array.isArray(data)) throw new Error('Invalid project status context')
    return data
}

/** List-only projection omits subtitles, character geometry and full prompts. */
export async function loadStdProjectListStatusContext(db: any, projectIds: string[]) {
    if (!projectIds.length) return []
    const { data, error } = await db.rpc('std_project_list_context', { p_project_ids: projectIds })
    if (error) {
        // During a rolling deployment, the database schema cache can briefly lag.
        if (error.code === 'PGRST202') return loadStdProjectStatusContext(db, projectIds)
        throw error
    }
    if (!Array.isArray(data)) throw new Error('Invalid project list status context')
    return data
}
