import { createHash } from 'crypto'
import { isGcsConfiguredAsync, uploadGcsBuffer } from '@/lib/gcsStorage'

export function segmentAudioKey(identity: Record<string, any>): string {
    // Hash the complete Unicode text/settings. Never strip Korean text or truncate it.
    return createHash('sha256').update(JSON.stringify(identity)).digest('hex')
}

export function legacySegmentMatches(metadata: any, identity: Record<string, any>): boolean {
    return Boolean(metadata
        && metadata.text === identity.text
        && metadata.voice_id === identity.voiceId
        && metadata.model_id === identity.modelId
        && Number(metadata.tts_speed) === identity.speed
        && Number(metadata.stability) === Number(identity.stability)
        && Number(metadata.style) === Number(identity.style)
        && String(metadata.direction || '') === identity.direction)
}

export async function persistSegmentAudio(db: any, args: {
    projectId: string; cacheKey: string; identity: Record<string, any>;
    audioBuffer: Buffer; fileName: string; segmentIndex: number; generatedBy: string;
}) {
    const path = `std/${args.projectId}/tts/${args.cacheKey}.mp3`
    const gcsMeta = await persistTtsAudio(path, args.audioBuffer)

    const identity = args.identity
    const { data, error } = await db.from('std_project_assets').insert({
        project_id: args.projectId, scene_id: null,
        scene_number: Number.isFinite(args.segmentIndex) ? args.segmentIndex + 1 : null,
        asset_type: 'other', file_name: args.fileName, mime_type: 'audio/mpeg',
        file_size: args.audioBuffer.length, status: 'uploaded',
        metadata: {
            kind: 'vrew_segment_tts', cache_key: args.cacheKey,
            segment_index: args.segmentIndex, provider: identity.provider,
            voice_id: identity.voiceId, model_id: identity.modelId,
            tts_speed: identity.speed, stability: identity.stability, style: identity.style,
            direction: identity.direction, language: identity.language, text: identity.text,
            text_hash: createHash('sha1').update(identity.text).digest('hex'),
            generated_by: args.generatedBy,
            ...gcsMeta,
        },
    }).select('*').single()
    if (error) throw new Error(`음성 저장 정보 기록 실패: ${error.message}`)
    return data
}

export async function persistTtsAudio(path: string, buffer: Buffer) {
    if (!(await isGcsConfiguredAsync())) throw new Error('GCS 음성 저장 설정이 필요합니다.')
    const ref = await uploadGcsBuffer({objectPath: path, buffer, contentType: 'audio/mpeg'})
    return {storage_provider: 'gcs', storage_bucket: ref.bucket, storage_path: ref.path,
        gcs_bucket: ref.bucket, gcs_path: ref.path}
}
