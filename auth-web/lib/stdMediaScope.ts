export type MediaScope = { session: string; projectId: string; generation: number }

// Generation also rejects A -> B -> A transitions and logout/login with the same identity.
export function isCurrentMediaScope(request: MediaScope, current: MediaScope): boolean {
    return Boolean(request.session && request.projectId)
        && request.session === current.session
        && request.projectId === current.projectId
        && request.generation === current.generation
}

export function assetBelongsToProject(asset: any, projectId: string): boolean {
    return Boolean(asset && projectId && asset.project_id === projectId)
}
