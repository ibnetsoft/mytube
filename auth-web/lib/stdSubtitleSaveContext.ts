// Only retry this read-only operation. A failed write response can be ambiguous
// and must never be replayed here without checking whether it already committed.
import { isDeepStrictEqual } from 'node:util'

const temporaryStatuses = [502, 503, 504, 520, 521, 522, 523, 524]

export async function readSubtitleSaveContext<T extends { error: unknown; status: number }>(
    read: () => PromiseLike<T>,
    wait: (ms: number) => Promise<void> = ms => new Promise(resolve => setTimeout(resolve, ms)),
): Promise<T> {
    for (let attempt = 0; ; attempt++) {
        const result = await read()
        if (!result.error || !temporaryStatuses.includes(result.status) || attempt >= 2) return result
        await wait(attempt === 0 ? 500 : 1500)
    }
}

/** Reuse the original CAS version; a committed or concurrent write cannot be overwritten. */
export async function saveSubtitlePatchWithVerification<T extends { data: any; error: any; status: number }>(
    write: () => PromiseLike<T>,
    read: () => PromiseLike<T>,
    payload: Record<string, any>, progress: Record<string, any>,
    wait: (ms: number) => Promise<void> = ms => new Promise(resolve => setTimeout(resolve, ms)),
): Promise<T> {
    const first = await write()
    if (!first.error || !temporaryStatuses.includes(first.status)) return first
    await wait(500)
    const second = await write()
    if (!second.error && second.data) return second
    const verification = await readSubtitleSaveContext(read, wait)
    const current = verification.data
    const matches = !verification.error && current
        && Object.entries(payload).every(([key, value]) => isDeepStrictEqual(current.project_payload?.[key], value))
        && Object.entries(progress).every(([key, value]) => isDeepStrictEqual(current.progress_payload?.[key], value))
    if (matches) return { ...second, data: current, error: null, status: 200 }
    // Do not return a normal CAS conflict here: the client would replay an
    // older snapshot after a newer concurrent edit. Keep the draft unsaved.
    return { ...second, data: null, error: second.error || { message: 'Could not confirm subtitle save' }, status: 503 }
}
