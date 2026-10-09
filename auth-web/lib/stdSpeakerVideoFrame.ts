import { execFile } from 'child_process'
import { promisify } from 'util'
import { mkdtemp, writeFile, readFile, rm } from 'fs/promises'
import { tmpdir } from 'os'
import path from 'path'
import { createHash } from 'crypto'
import ffmpeg from 'ffmpeg-static'
import sharp from 'sharp'
import { coordinateImage, coordinateSource } from './stdSpeakerGeometry'
import { downloadGcsObject, uploadGcsBuffer } from './gcsStorage'

const run = promisify(execFile)
export async function firstVideoFrame(video: Buffer) {
    if (!ffmpeg) throw new Error('Video frame decoder is unavailable')
    const directory = await mkdtemp(path.join(tmpdir(), 'air-speaker-frame-'))
    try {
        const input = path.join(directory, 'source.mp4'), output = path.join(directory, 'frame.png')
        await writeFile(input, video)
        await run(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-y', '-i', input,
            '-map', '0:v:0', '-frames:v', '1', '-an', output], { timeout: 90000, maxBuffer: 1024 * 1024 })
        const buffer = await readFile(output)
        const { width, height } = await sharp(buffer).metadata()
        if (!width || !height) throw new Error('Video first frame is invalid')
        return { buffer, width, height }
    } finally { await rm(directory, { recursive: true, force: true }) }
}

/** Persist a reference separately; never replace the user's image or original video. */
export async function prepareSpeakerVideoFrame(db: any, projectId: string, scene: any, assets: any[]) {
    const existing = coordinateImage(assets, scene.number)
    if (existing?.metadata?.kind === 'speaker_video_reference') return existing
    const source = coordinateSource(scene.video)
    if (!source.path) throw new Error('Original video storage path is missing')
    const video = await downloadGcsObject({ bucket: source.bucket, objectPath: source.path })
    const frame = await firstVideoFrame(video)
    const hash = createHash('sha256').update(frame.buffer).digest('hex')
    const stored = await uploadGcsBuffer({ objectPath: `std-projects/${projectId}/speaker-reference/${scene.video.id}/${hash}.png`,
        data: frame.buffer, contentType: 'image/png' })
    const saved = await db.from('std_project_assets').insert({ project_id: projectId, scene_number: scene.number,
        asset_type: 'other', status: 'uploaded', file_name: `scene-${scene.number}-speaker-reference.png`,
        mime_type: 'image/png', file_size: frame.buffer.length,
        metadata: { kind: 'speaker_video_reference', storage_provider: 'gcs', gcs_bucket: stored.bucket, gcs_path: stored.path,
            source_video_id: scene.video.id, source_video_path: source.path, source_video_sha256: createHash('sha256').update(video).digest('hex'),
            frame_seconds: 0, source_sha256: hash, width: frame.width, height: frame.height },
    }).select('*').single()
    if (saved.error) throw saved.error
    return saved.data
}
