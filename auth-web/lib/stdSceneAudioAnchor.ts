// Character positions survive subtitle splitting without retaining old seconds/indices.
const compact = (text: any) => Array.from(String(text ?? '').replace(/\s+/gu, ''))
const text = (row: any) => row.anchor_text ?? row.text ?? ''

function position(row: any, index: number, offset: number) {
    const chars = compact(text(row)).length
    const start = Number(row.start_num ?? row.start ?? row.start_time), end = Number(row.end_num ?? row.end ?? row.end_time)
    if (!Number.isFinite(start) || !Number.isFinite(end) || end < start || offset < 0 || offset > chars) return null
    const words = String(text(row)).match(/\S+/gu) || []
    let consumed = 0, boundary = 0
    while (boundary < words.length && consumed < offset) consumed += compact(words[boundary++]).length
    const fraction = consumed === offset ? boundary / Math.max(1, words.length) : offset / Math.max(1, chars)
    return { index, start: start + (end - start) * fraction }
}

export function sceneAudioAnchor(rows: any[], index: number, boundary = 0) {
    const row = rows[index]
    if (!row || row.scene_number == null) return undefined
    const scene = rows.flatMap((r, i) => String(r.scene_number) === String(row.scene_number) ? [{ r, i }] : [])
    const before = scene.filter(item => item.i < index).reduce((n, item) => n + compact(text(item.r)).length, 0)
    const words = String(text(row)).match(/\S+/gu) || []
    const within = words.slice(0, Math.max(0, boundary)).reduce((n, word) => n + compact(word).length, 0)
    return { scene_number: row.scene_number, source_text: scene.map(item => compact(text(item.r)).join('')).join(''), offset: before + within, subtitle_id: row.id, subtitle_text: text(row), subtitle_offset: within }
}
export function resolveSceneAudioAnchor(anchor: any, rows: any[]) {
    if (!anchor || !Number.isInteger(anchor.offset) || anchor.offset < 0) return null
    const direct = rows.flatMap((r, index) => anchor.subtitle_id != null && String(r.id) === String(anchor.subtitle_id) && String(r.scene_number) === String(anchor.scene_number) && text(r) === anchor.subtitle_text ? [{ r, index }] : [])
    if (direct.length === 1 && Number.isInteger(anchor.subtitle_offset)) {
        const { r, index } = direct[0]
        return position(r, index, anchor.subtitle_offset)
    }
    const scene = rows.flatMap((r, index) => String(r.scene_number) === String(anchor.scene_number) ? [{ r, index }] : [])
    if (!scene.length || scene.map(({ r }) => compact(text(r)).join('')).join('') !== compact(anchor.source_text).join('')) return null
    let offset = anchor.offset
    for (const [rowPosition, { r, index }] of scene.entries()) {
        const length = compact(text(r)).length
        if (offset < length || rowPosition === scene.length - 1) {
            if (offset > length) return null
            return position(r, index, offset)
        }
        offset -= length
    }
    return null
}
