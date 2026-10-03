/** Serialize subtitle snapshots so an older request cannot overwrite a newer edit. */
export function createSubtitleSaveQueue(request: typeof fetch = fetch) {
    const pending = new Map<string, Promise<any>>()
    return (projectId: string, body: any, headers: Record<string, string>, signal?: AbortSignal): Promise<any> => {
        // Capture the snapshot before waiting for an earlier save.
        const serialized = JSON.stringify(body)
        const save = async () => {
            for (let attempt = 0; attempt < 3; attempt++) {
                signal?.throwIfAborted()
                const response = await request(`/api/std/projects/${encodeURIComponent(projectId)}`, {
                    method: 'PATCH', headers, body: serialized,
                    signal: signal || AbortSignal.timeout(30000),
                })
                const result = await response.json()
                // A concurrent media/translation update can win the server's row lock.
                // Each retry reads the current project before merging this scoped patch.
                if (response.status === 409 && result.error === 'Project changed while saving; reload and retry' && attempt < 2) continue
                if (!response.ok || result.success === false || result.project?.id !== projectId) {
                    throw new Error(result.error || `Subtitle save failed (${response.status})`)
                }
                return result.project
            }
        }
        const previous = pending.get(projectId) || Promise.resolve()
        const task = previous.catch(() => {}).then(save)
        pending.set(projectId, task)
        return task.finally(() => { if (pending.get(projectId) === task) pending.delete(projectId) })
    }
}
