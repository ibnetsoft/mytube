// One provider wave per request, below the server's 300-second execution limit.
export const NARRATION_BATCH_SIZE = 4

type Reply = { res: { ok: boolean; status: number; statusText?: string }; payload: any }
export async function generateNarrationInBatches(
    body: Record<string, any>,
    send: (body: Record<string, any>) => Promise<Reply>,
    progress: (ready: number, total: number) => void,
): Promise<Reply> {
    const segments = body.voice_segments
    if (!Array.isArray(segments) || !segments.length) return send(body)
    let generated = 0, reused = 0
    for (let offset = 0; offset < segments.length; offset += NARRATION_BATCH_SIZE) {
        const batch = segments.slice(offset, offset + NARRATION_BATCH_SIZE)
        const { res, payload } = await send({ ...body, text: batch.map(s => s.text).join('\n'),
            voice_segments: batch, mode: 'prepare_narration_segments', segment_offset: offset })
        if (!res.ok || payload?.success !== true || payload?.prepared !== batch.length) {
            throw new Error(`TTS generation failed (prepare_saved_segments): ${String(payload?.error || payload?.raw || res.status).slice(0, 600)}`)
        }
        generated += Number(payload.segment_reuse?.generated || 0)
        reused += Number(payload.segment_reuse?.reused || 0)
        progress(offset + batch.length, segments.length)
    }
    const result = await send({ ...body, mode: 'assemble_narration_segments' })
    if (result.res.ok && result.payload?.success) result.payload.segment_reuse = { generated, reused }
    return result
}
