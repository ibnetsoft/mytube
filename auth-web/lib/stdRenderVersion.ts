export function stdRenderVersionOf(row: any): number {
    const value = Number(row?.metadata?.render_version ?? row?.render_version)
    return Number.isFinite(value) && value > 0 ? Math.floor(value) : 0
}

export function normalizeStdRenderHistory(rows: any[]) {
    const newestFirst = Array.isArray(rows) ? rows : []
    const chronological = [...newestFirst].reverse()
    const fallbackVersionById = new Map(chronological.map((row: any, index: number) => [row.id, index + 1]))
    return newestFirst.map((row: any) => ({
        ...row,
        render_version: stdRenderVersionOf(row) || fallbackVersionById.get(row.id) || 1,
    }))
}

export function nextStdRenderVersion(rows: any[]): number {
    return Math.max(0, ...normalizeStdRenderHistory(rows).map(stdRenderVersionOf)) + 1
}
