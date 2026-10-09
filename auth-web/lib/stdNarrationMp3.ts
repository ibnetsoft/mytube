import { execFile } from 'child_process'
import { mkdtemp, writeFile, readFile, rm } from 'fs/promises'
import { tmpdir } from 'os'
import path from 'path'
import { promisify } from 'util'
import { createHash } from 'crypto'
import ffmpeg from 'ffmpeg-static'
import { joinMp3Segments, mp3FrameDuration } from './stdJoinMp3'

const run = promisify(execFile)

// MP3 frames with different sample rates/channel layouts cannot safely share a
// media-element timeline. Keep compatible recordings encoded; normalize only
// incompatible clips, then write one accurate seek/duration header for the join.
export async function finalizeNarrationMp3(clips: Buffer[]) {
    if (!ffmpeg) throw new Error('Narration audio encoder is unavailable')
    const directory = await mkdtemp(path.join(tmpdir(), 'air-narration-'))
    try {
        const frames: Buffer[] = []
        const normalized = new Map<string, Buffer>()
        for (let index = 0; index < clips.length; index++) {
            let clip = joinMp3Segments([clips[index]])
            mp3FrameDuration(clip) // reject truncated/invalid inputs before replacing any saved narration
            const version = (clip[1] >> 3) & 3
            const rate = (clip[2] >> 2) & 3
            const mono = (clip[3] >> 6) === 3
            if (version !== 3 || rate !== 0 || !mono) {
                const key = createHash('sha256').update(clip).digest('hex')
                let converted = normalized.get(key)
                if (!converted) {
                    const source = path.join(directory, 'source.mp3'), output = path.join(directory, 'normalized.mp3')
                    await writeFile(source, clip)
                    await run(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-y', '-i', source,
                        '-map', '0:a:0', '-ar', '44100', '-ac', '1', '-c:a', 'libmp3lame', '-b:a', '128k', output], { timeout: 30000 })
                    converted = joinMp3Segments([await readFile(output)])
                    normalized.set(key, converted)
                }
                clip = converted
            }
            frames.push(clip)
        }
        const source = path.join(directory, 'joined.mp3'), output = path.join(directory, 'narration.mp3')
        await writeFile(source, Buffer.concat(frames))
        await run(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-y', '-i', source,
            '-map', '0:a:0', '-c:a', 'copy', '-write_xing', '1', output], { timeout: 60000 })
        return { audioBuffer: await readFile(output), durations: frames.map(mp3FrameDuration) }
    } finally {
        await rm(directory, { recursive: true, force: true })
    }
}
