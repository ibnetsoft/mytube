import { createHash } from 'node:crypto'

// This is content identity, not an authorization token. It must be captured
// before generation, never relabelled using the project at completion time.
export function speechText(value: any): string {
    return String(value ?? '').normalize('NFKC').replace(/\s+/gu, '')
}
export function contentHash(value: any): string {
    return createHash('sha256').update(typeof value === 'string' ? value : JSON.stringify(value)).digest('hex')
}
export function fileContentHash(bytes: Uint8Array): string {
    return createHash('sha256').update(bytes).digest('hex')
}
export function timelineRows(rows: any[]): any[] {
    return (rows || []).map(row => ({
        text: speechText(row.text),
        start: Number(row.start_num ?? row.start_time ?? row.start),
        end: Number(row.end_num ?? row.end_time ?? row.end),
        voice_id: String(row.voice_id || row.voiceId || ''),
    }))
}
export function projectContentIdentity(project: any) {
    const payload = project.project_payload || {}
    const rows = Array.isArray(payload.subtitles) ? payload.subtitles : []
    const script = speechText(payload.script || rows.map((r: any) => r.text || '').join('')
        || (payload.structure?.scenes || []).map((s: any) => s.scene_text || s.narration || s.text || '').join(''))
    const scriptHash = contentHash(script)
    return {
        schema_version: 1, project_id: String(project.id), topic_queue_id: Number(project.topic_queue_id),
        script_revision: `sha256:${scriptHash}`, script_sha256: scriptHash,
        subtitle_text_sha256: contentHash(rows.map((r: any) => speechText(r.text)).join('')),
    }
}
export function sceneVisualHash(scene: any, type: string): string {
    return contentHash({ image_prompt: String(scene?.image_prompt || scene?.prompt || ''),
        video_prompt: type === 'video' ? String(scene?.video_prompt || '') : '' })
}
export function assetContentIdentity(project: any, options: {
    type: string; scene?: any; audioId?: string; timeline?: any[]; parents?: string[]; jobId?: string
}) {
    return { ...projectContentIdentity(project), asset_type: options.type,
        scene_id: options.scene?.id || null, scene_number: options.scene?.scene_number ?? null,
        scene_key: options.scene ? `${project.id}:${options.scene.scene_number}` : null,
        visual_sha256: options.scene ? sceneVisualHash(options.scene, options.type) : null,
        audio_asset_id: options.audioId || null,
        timeline_sha256: options.timeline ? contentHash(timelineRows(options.timeline)) : null,
        parent_asset_ids: options.parents || [], generation_job_id: options.jobId || null,
    }
}
function mismatch(message: string): never {
    throw Object.assign(new Error(`콘텐츠 식별정보 불일치: ${message}`), { code: 'CONTENT_IDENTITY_MISMATCH' })
}
export function assertAssetScope(project: any, asset: any, scene?: any) {
    if (!asset) mismatch('자산이 없습니다.')
    if (asset.project_id && String(asset.project_id) !== String(project.id)) mismatch('다른 프로젝트의 자산입니다.')
    const identity = asset.metadata?.content_identity
    if (identity && (String(identity.project_id) !== String(project.id)
        || Number(identity.topic_queue_id) !== Number(project.topic_queue_id))) mismatch('토픽 또는 프로젝트가 다릅니다.')
    if (scene && ((asset.scene_number != null && Number(asset.scene_number) !== Number(scene.scene_number))
        || (identity?.scene_number != null && Number(identity.scene_number) !== Number(scene.scene_number))
        || (asset.scene_id && scene.id && asset.scene_id !== scene.id)
        || (identity?.scene_id && scene.id && identity.scene_id !== scene.id))) mismatch(`${scene.scene_number}번 씬 자산 연결이 다릅니다.`)
    // Legacy storage provenance is checked too; a database row must not point
    // at another topic/project's file. Shared library paths have no topic scope.
    const metadata = asset.metadata || {}
    const path = String(metadata.gcs_path || metadata.storage_path || metadata.object_path || '')
    const topic = path.match(/^topics\/(\d+)\//)
    const owner = path.match(/^std(?:-projects)?\/([^/]+)\//)
    if (topic && Number(topic[1]) !== Number(project.topic_queue_id)) mismatch('저장 파일의 토픽 번호가 다릅니다.')
    const sharedLibrary = (metadata.audio_role === 'sfx' && metadata.sfx_library_id)
        || (metadata.audio_role === 'bgm' && (metadata.bgm_library_id || metadata.bgm_source_asset_id))
    if (owner && owner[1] !== String(project.id) && !sharedLibrary) mismatch('저장 파일의 프로젝트 번호가 다릅니다.')
}
export function selectNarrationAsset(project: any, assets: any[]) {
    const active = assets.filter(a => a.asset_type === 'audio' && ['uploaded', 'assigned'].includes(a.status)
        && !['bgm', 'sfx', 'background'].includes(a.metadata?.audio_role))
    const payload = project.project_payload || {}, progress = project.progress_payload || {}
    const url = String(payload.audio_url || payload.tts_url || '')
    const urlId = url.match(/[?&]assetId=([^&]+)/)?.[1]
    const ids = [progress.tts_asset_id, urlId && decodeURIComponent(urlId)].filter(Boolean).map(String)
    if (new Set(ids).size > 1) mismatch('확정 음성 ID와 음성 URL이 서로 다릅니다.')
    const asset = ids.length ? active.find(a => String(a.id) === ids[0]) : active.length === 1 ? active[0] : null
    if (!asset) mismatch('확정 음성을 하나로 지정해야 합니다. 여러 음성 중 첫 파일을 자동 선택하지 않습니다.')
    assertAssetScope(project, asset)
    return asset
}
export function assertNarrationIdentity(project: any, audio: any, subtitles: any[]) {
    assertAssetScope(project, audio)
    const identity = projectContentIdentity(project), stored = audio.metadata?.content_identity
    if (project.project_payload?.subtitle_source_audio_id && project.project_payload.subtitle_source_audio_id !== audio.id)
        mismatch('자막이 다른 음성 파일에 연결돼 있습니다.')
    const script = speechText(project.project_payload?.script)
    const spoken = subtitles.map(row => speechText(row.text)).join('')
    if (script && script !== spoken) mismatch('현재 대본과 자막의 내용이 다릅니다. 확장 대본과 이전 녹음을 섞을 수 없습니다.')
    if (stored?.script_sha256 && stored.script_sha256 !== identity.script_sha256) mismatch('음성이 다른 대본 버전에서 생성됐습니다.')
    const timeline = audio.metadata?.subtitle_timeline
    if (!Array.isArray(timeline) || !timeline.length) {
        // Imported recordings need a reviewed transcript receipt; a filename or
        // matching duration is not evidence of which words were recorded.
        if (stored?.subtitle_text_sha256 !== identity.subtitle_text_sha256
            || audio.metadata?.transcript_review?.decision !== 'approved'
            || audio.metadata?.transcript_review?.source_sha256 !== audio.metadata?.sha256
            || !audio.metadata?.sha256)
            mismatch('음성의 대본·자막 연결 기록이 없습니다. 녹음 원본의 내용을 확인해야 합니다.')
        return null
    }
    const actual = timelineRows(subtitles), recorded = timelineRows(timeline)
    if (actual.length !== recorded.length) mismatch(`음성 자막 ${recorded.length}개와 현재 자막 ${actual.length}개가 다릅니다.`)
    for (let i = 0; i < actual.length; i++) {
        const a = actual[i], b = recorded[i]
        if (a.text !== b.text || a.voice_id !== b.voice_id) mismatch(`${i + 1}번 자막 내용·성우가 확정 음성(TTS)과 다릅니다.`)
        if (![a.start, a.end, b.start, b.end].every(Number.isFinite) || b.end <= b.start
            || Math.abs(a.start - b.start) > .12 || Math.abs(a.end - b.end) > .12)
            mismatch(`${i + 1}번 자막 시간이 확정 음성과 다릅니다.`)
        if (i && b.start < recorded[i - 1].end - .01) mismatch('녹음 시간표가 겹칩니다.')
    }
    if (stored?.timeline_sha256 && stored.timeline_sha256 !== contentHash(recorded)) mismatch('음성 시간표가 생성 후 변경됐습니다.')
    const duration = recorded[recorded.length - 1].end
    if (audio.metadata?.duration_seconds && Math.abs(Number(audio.metadata.duration_seconds) - duration) > .15)
        mismatch('음성 파일 길이와 녹음 시간표의 끝이 다릅니다.')
    return { audio_asset_id: audio.id, timeline_sha256: contentHash(recorded), duration_seconds: duration,
        verification: stored && !stored.basis ? 'generation_identity_and_recorded_timeline' : 'legacy_recorded_timeline' }
}
export function renderAssetIdentity(project: any, scene: any, asset: any, audioId?: string) {
    assertAssetScope(project, asset, scene)
    const identity = asset.metadata?.content_identity
    const derived = Boolean(asset.metadata?.ae_mouth_fingerprint || asset.metadata?.lipsync_fingerprint || asset.metadata?.timing_locked)
    if (derived && asset.metadata?.source_audio_id && asset.metadata.source_audio_id !== audioId)
        mismatch(`${scene.scene_number}번 영상이 다른 확정 음성을 사용했습니다.`)
    if (identity) {
        if (derived && (identity.script_sha256 !== projectContentIdentity(project).script_sha256
            || identity.audio_asset_id !== audioId)) mismatch(`${scene.scene_number}번 영상의 대본·음성 버전이 다릅니다.`)
        if (!derived && identity.visual_sha256 && identity.visual_sha256 !== sceneVisualHash(scene, asset.asset_type))
            mismatch(`${scene.scene_number}번 이미지·영상의 생성 프롬프트가 바뀌었습니다.`)
    }
    return { asset_id: asset.id || null, scene_id: scene.id || null, scene_number: Number(scene.scene_number),
        source_content_identity: identity || null,
        // Do not manufacture a birth revision for old assets. This distinction
        // remains in the final manifest for later evidence-based migration.
        verification: identity?.basis === 'legacy_database_scope' || !identity ? 'legacy_project_scene_scope' : 'generation_identity',
        source_sha256: asset.metadata?.render_sha256 || asset.metadata?.sha256 || null,
    }
}
export function bindProjectContent(project: any, payload: any) {
    const identity = projectContentIdentity({ ...project, project_payload: payload })
    const old = project.project_payload?.content_identity
    return { ...payload, content_identity: identity,
        content_revision_history: [...(project.project_payload?.content_revision_history || []),
            ...(old && old.script_sha256 !== identity.script_sha256 ? [{ ...old, superseded_at: new Date().toISOString() }] : [])].slice(-100),
    }
}

/** Append-only snapshots: keep old scripts recoverable without a new SQL table. */
export async function persistContentRevision(db: any, project: any) {
    const identity = projectContentIdentity(project), payload = project.project_payload || {}
    if (!speechText(payload.script) && !(payload.subtitles || []).length) return
    const hex = contentHash(`${project.id}:${identity.script_sha256}`)
    const id = `${hex.slice(0,8)}-${hex.slice(8,12)}-5${hex.slice(13,16)}-a${hex.slice(17,20)}-${hex.slice(20,32)}`
    const result = await db.from('std_project_assets').insert({ id, project_id: project.id,
        asset_type: 'other', status: 'uploaded', file_name: `script-${identity.script_sha256}.json`, mime_type: 'application/json',
        metadata: { kind: 'content_revision', content_identity: identity,
            snapshot: { script: payload.script || '', subtitles: payload.subtitles || [],
                structure: payload.structure || {}, source_audio_id: payload.subtitle_source_audio_id || project.progress_payload?.tts_asset_id || null },
            captured_at: new Date().toISOString() },
    })
    if (result.error && result.error.code !== '23505') throw result.error
}

export function finalizeRecordedRenderConfig(config: any) {
    const starts = config.image_timing_starts, duration = Number(config.audio_duration)
    if (!Array.isArray(starts) || !Number.isFinite(duration) || duration <= 0) mismatch('확정 녹음 길이가 없습니다.')
    if (starts.length !== config.images.length || starts.some((v: any, i: number) =>
        !Number.isFinite(v) || v < 0 || v > duration || (i && v < starts[i - 1])))
        mismatch('씬 시작 시간이 순서대로 증가하지 않습니다. 시작 시간을 길이로 재해석할 수 없습니다.')
    const indices = starts.flatMap((start: number, i: number) => ((starts[i + 1] ?? duration) - start) > .001 ? [i] : [])
    const result = { ...config }
    for (const field of ['images', 'image_timing_starts', 'scene_numbers', 'image_effects', 'transition_effects', 'focal_point_ys'])
        if (Array.isArray(config[field])) result[field] = indices.map((i: number) => config[field][i])
    result.render_settings = { ...config.render_settings,
        scene_motion_speeds: indices.map((i: number) => config.render_settings?.scene_motion_speeds?.[i] ?? 1),
        timing_locked_indices: indices.flatMap((old: number, i: number) => config.render_settings?.timing_locked_indices?.includes(old) ? [i] : []),
    }
    const retained = new Set(result.scene_numbers)
    result.asset_manifest = { ...config.asset_manifest, files: config.asset_manifest.files.filter((f: any) =>
        !['image', 'video'].includes(f.asset_type) || retained.has(f.scene_number)) }
    return result
}
