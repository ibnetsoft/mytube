import { createHash } from 'crypto'

export function lipSyncEnabled(project: any) {
    return project.project_payload?.lipsync?.enabled === true
}

export function lipSyncPlan(project: any, scenes: any[], assets: any[]) {
    const subtitles = (project.project_payload?.subtitles || []).map((s: any) => ({ ...s, start: Number(s.start ?? s.start_num ?? s.start_time), end: Number(s.end ?? s.end_num ?? s.end_time), scene_number: Number(s.scene_number ?? s.scene ?? s.sceneNumber) }))
    const audio = assets.find(a => a.asset_type === 'audio' && ['uploaded', 'assigned'].includes(a.status))
    const timeline = audio?.metadata?.subtitle_timeline
    if (!audio || !Array.isArray(timeline) || timeline.length !== subtitles.length) {
        throw new Error('자막의 저장+TTS를 먼저 완료해 대사별 실제 음성 시간을 확정해 주세요.')
    }
    const speed = project.project_payload?.tts_speed ?? project.progress_payload?.tts_speed
    if (speed != null && Math.abs(Number(speed) - Number(audio.metadata.tts_speed)) > .001) {
        throw new Error('음성 속도가 바뀌었습니다. 저장+TTS로 다시 확정해 주세요.')
    }
    subtitles.forEach((s: any, i: number) => {
        const t = timeline[i]
        if (s.text?.trim() !== t.text?.trim() || String(s.voice_id || s.voiceId || '') !== String(t.voice_id || '')
            || Math.abs(Number(s.start) - Number(t.start)) > .12 || Math.abs(Number(s.end) - Number(t.end)) > .12) {
            throw new Error('자막·성우·시간이 저장된 TTS와 다릅니다. 저장+TTS로 다시 확정해 주세요.')
        }
        if (!Number.isFinite(Number(s.start)) || !Number.isFinite(Number(s.end)) || !Number.isFinite(t.start) || !Number.isFinite(t.end) || t.end <= t.start) throw new Error('실제 음성 시간이 유효하지 않습니다.')
        const recorded = audio.metadata.voice_segments?.[i]
        if (recorded && String(s.direction || '') !== String(recorded.direction || '')) throw new Error('음성 연출이 바뀌었습니다. 저장+TTS로 다시 확정해 주세요.')
        if (i > 0 && t.start < timeline[i - 1].end - .01) throw new Error('음성 시간이 겹칩니다. 저장+TTS로 다시 확정해 주세요.')
    })
    const total = timeline[timeline.length - 1]?.end || 0
    const starts = lipSyncSceneStarts(project, scenes, audio)
    if (starts.some((s, i) => !Number.isFinite(s) || (i > 0 && s < starts[i - 1]))) throw new Error('씬 순서와 음성 시간이 일치하지 않습니다.')
    return scenes.map((scene, index) => {
        const shots = subtitles.flatMap((s: any, i: number) => s.dialogue_kind === 'dialogue' && Number(s.scene_number) === Number(scene.scene_number)
            ? [{ text: s.text, speaker: s.dialogue_speaker || s.voice_id, voice_id: timeline[i].voice_id, start: timeline[i].start, end: timeline[i].end }] : [])
        const image = assets.find(a => a.asset_type === 'image' && Number(a.scene_number) === Number(scene.scene_number) && ['uploaded', 'assigned'].includes(a.status))
        const start = starts[index]!, end = starts[index + 1] ?? total
        if (shots.some((s: any) => s.start < start - .001 || s.end > end + .001)) throw new Error(`${scene.scene_number}번 씬의 대사가 씬 구간을 벗어납니다.`)
        const identity = { scene_number: Number(scene.scene_number), start, end, shots, audio_id: audio.id, audio: audio.metadata, image_id: image?.id, image: image?.metadata }
        const fingerprint = createHash('sha256').update(JSON.stringify(identity)).digest('hex')
        return { ...identity, fingerprint, audio, image }
    }).filter(s => s.shots.length)
}

export function reviewedLipSyncAssets(project: any, scenes: any[], assets: any[]) {
    if (!lipSyncEnabled(project)) return new Map<number, any>()
    const plan = lipSyncPlan(project, scenes, assets)
    const result = new Map<number, any>()
    for (const item of plan) {
        const ready = assets.find(a => a.asset_type === 'video' && ['uploaded', 'assigned'].includes(a.status)
            && a.metadata?.lipsync_fingerprint === item.fingerprint && a.metadata?.lipsync_reviewed === true
            && a.metadata?.ae_reviewed === true && a.metadata?.timing_locked === true)
        if (!ready) throw new Error(`${item.scene_number}번 씬의 현재 음성에 맞는 립싱크·AE 검수가 필요합니다.`)
        result.set(item.scene_number, ready)
    }
    return result
}

export function lipSyncSceneStarts(project: any, scenes: any[], audio: any): number[] {
    const subtitles = (project.project_payload?.subtitles || []).map((s: any) => ({ ...s, start: Number(s.start ?? s.start_num ?? s.start_time), end: Number(s.end ?? s.end_num ?? s.end_time), scene_number: Number(s.scene_number ?? s.scene ?? s.sceneNumber) }))
    const timeline = audio?.metadata?.subtitle_timeline || []
    const total = timeline[timeline.length - 1]?.end || 0
    // Allocate silent scenes only after the preceding recorded speech has ended.
    const starts: (number | null)[] = scenes.map(s => {
        const indices = subtitles.map((t: any, i: number) => Number(t.scene_number) === Number(s.scene_number) ? i : -1).filter((i: number) => i >= 0)
        return indices.length ? timeline[indices[0]].start : null
    })
    if (starts.length && starts[0] == null) starts[0] = 0
    for (let i = 0; i < starts.length; i++) {
        if (starts[i] != null) continue
        const left = i - 1
        let right = i
        while (right < starts.length && starts[right] == null) right++
        const end = right < starts.length ? starts[right]! : total
        const previousEnds = subtitles.flatMap((t: any, k: number) => Number(t.scene_number) === Number(scenes[left].scene_number) ? [Number(timeline[k]?.end)] : [])
        const speechEnd = Math.max(starts[left]!, ...previousEnds.filter(Number.isFinite))
        if (speechEnd > end + .001) throw new Error('Recorded speech overlaps the next scene')
        const gapStart = Math.min(end, speechEnd)
        for (let j = i; j < right; j++) starts[j] = gapStart + (end - gapStart) * (j - i) / (right - i)
        i = right - 1
    }
    return starts as number[]
}
