import { createHash } from 'crypto'
import { dialogueSceneIndex, subtitleDialogueSpeakerName } from './stdDialogueSceneIndex'

export function coordinateCast(project: any) {
    const p = project.project_payload || {},
        s = p.structure || {}
    return {
        main: s.main_character || p.main_character || {},
        supporting: s.supporting_characters || p.supporting_characters || [],
        scene_cast: s.scene_cast || [],
    }
}
export function coordinateSource(image: any) {
    const m = image?.metadata || {}
    return { bucket: m.gcs_bucket || m.storage_bucket || 'air-studio-prod', path: m.gcs_path || m.storage_path || '' }
}
export function coordinateKey(cast: any, scene: any) {
    return createHash('sha256')
        .update(
            JSON.stringify({
                cast,
                number: scene.number,
                image: scene.image?.id,
                source: coordinateSource(scene.image),
                speakers: [...new Set(scene.rows.map((r: any) => r.speaker))].sort(),
            }),
        )
        .digest('hex')
}
export function coordinateVideo(assets: any[], number: number) {
    return assets.find(a => ['uploaded', 'assigned'].includes(a.status) && a.asset_type === 'video'
        && Number(a.scene_number) === number && !a.metadata?.ae_mouth_fingerprint
        && !a.metadata?.lipsync_fingerprint && !a.metadata?.region_motion_plan_id
        && !['after_effects', 'region_motion'].includes(a.metadata?.postprocess_mode))
}
export function coordinateImage(assets: any[], number: number) {
    const video = coordinateVideo(assets, number)
    const reference = video && assets.find(a => ['uploaded', 'assigned'].includes(a.status)
        && Number(a.scene_number) === number && a.metadata?.kind === 'speaker_video_reference'
        && a.metadata.source_video_id === video.id
        && a.metadata.source_video_path === coordinateSource(video).path)
    return reference || assets.find(a => ['uploaded', 'assigned'].includes(a.status)
        && a.asset_type === 'image' && Number(a.scene_number) === number)
}
export function coordinateScenes(project: any, assets: any[]) {
    const p = project.project_payload || {},
        subtitles = p.subtitles || [],
        cast = coordinateCast(project)
    return dialogueSceneIndex(subtitles)
        .scenes.filter((s) => s.scene_number >= 19 || coordinateVideo(assets, s.scene_number))
        .map((s) => {
            const image = coordinateImage(assets, s.scene_number)
            const video = coordinateVideo(assets, s.scene_number)
            const rows = s.subtitle_indices.map((i) => ({
                kind: 'dialogue',
                speaker: subtitleDialogueSpeakerName(subtitles[i]),
                text: subtitles[i].text,
            }))
            const scene = {
                number: s.scene_number,
                video: video ? { id: video.id, metadata: video.metadata } : null,
                image: image ? { id: image.id, metadata: image.metadata } : null,
                rows,
                text: rows.map((r) => r.text).join(' '),
            }
            return { ...scene, castKey: JSON.stringify(cast), key: coordinateKey(cast, scene) }
        })
}
export function validateSpeakerGeometry(rows: any, names: string[]) {
    if (
        !Array.isArray(rows) ||
        rows.length !== names.length ||
        !names.length ||
        names.some((n) => typeof n !== 'string' || !n.trim())
    )
        throw new Error('모든 화자의 위치 또는 화면 밖 여부를 확인해 주세요.')
    const box = (b: any) =>
        Array.isArray(b) &&
        b.length === 4 &&
        b.every((n) => typeof n === 'number' && Number.isFinite(n)) &&
        0 <= b[0] &&
        b[0] < b[2] &&
        b[2] <= 1 &&
        0 <= b[1] &&
        b[1] < b[3] &&
        b[3] <= 1
    return names.map((name, index) => {
        const r = rows[index]
        if (r?.speaker !== name || !['visible', 'offscreen'].includes(r.status))
            throw new Error('화자마다 얼굴·입 위치를 지정하거나 화면 밖을 선택해 주세요.')
        if (r.status === 'offscreen')
            return {
                speaker: name,
                status: 'offscreen',
                confidence: 1,
                reason: '사용자가 원본 이미지를 확인하고 화면 밖 화자로 확정함',
            }
        const f = r.face_box,
            m = r.mouth_box
        if (!box(f) || !box(m) || m[0] < f[0] || m[1] < f[1] || m[2] > f[2] || m[3] > f[3])
            throw new Error('입 영역은 얼굴 영역 안에 있어야 합니다.')
        if (m[2] - m[0] < 0.005 || m[2] - m[0] > 0.2 || m[3] - m[1] < 0.005 || m[3] - m[1] > 0.12)
            throw new Error(
                '입술과 주변 피부만 작게 지정해 주세요. 입이 가려졌다면 화면 밖으로 확정하지 말고 이미지를 수정해 주세요.',
            )
        if (
            rows
                .slice(0, index)
                .some(
                    (o: any) =>
                        o.status === 'visible' &&
                        box(o.mouth_box) &&
                        m[0] < o.mouth_box[2] &&
                        m[2] > o.mouth_box[0] &&
                        m[1] < o.mouth_box[3] &&
                        m[3] > o.mouth_box[1],
                )
        )
            throw new Error('다른 화자의 입 영역과 겹칠 수 없습니다.')
        return {
            speaker: name,
            status: 'visible',
            confidence: 1,
            face_box: [...f],
            mouth_box: [...m],
            reason: '사용자가 원본 이미지의 화자와 얼굴·입 영역을 직접 확인함',
        }
    })
}
export function savedSpeakerGeometry(assets: any[], cast: any, scene: any) {
    if (!scene.image) return null
    const names: string[] = [...new Set<string>(scene.rows.map((r: any) => r.speaker))]
    const candidates = assets
        .filter((a) => ['uploaded', 'assigned'].includes(a.status))
        .sort((a, b) =>
            String(b.updated_at || b.created_at || '').localeCompare(String(a.updated_at || a.created_at || '')),
        )
    // Explicit user confirmation wins even if the optional AI later publishes a result.
    for (const kind of ['speaker_coordinate_confirmation', 'ae_speaker_coordinates']) {
        for (const a of candidates) {
            const m = a.metadata || {}
            if (
                m.kind !== kind ||
                (kind === 'speaker_coordinate_confirmation'
                    ? m.scene_key !== coordinateKey(cast, scene)
                    : m.input?.cast_key !== JSON.stringify(cast))
            )
                continue
            const r = m.results?.find(
                (v: any) =>
                    v.number === scene.number &&
                    v.image_id === scene.image.id &&
                    v.source_path === coordinateSource(scene.image).path,
            )
            if (!r || !/^[a-f0-9]{64}$/.test(r.source_sha256 || '')) continue
            try {
                const speakers = names.map((name) => r.speakers?.find((s: any) => s.speaker === name))
                if (
                    kind === 'ae_speaker_coordinates' &&
                    speakers.some(
                        (s) =>
                            !s ||
                            typeof s.confidence !== 'number' ||
                            !Number.isFinite(s.confidence) ||
                            s.confidence < 0.9,
                    )
                )
                    continue
                validateSpeakerGeometry(speakers, names)
                return { ...r, speakers, origin: kind === 'speaker_coordinate_confirmation' ? 'user' : 'ai' }
            } catch {
                /* Invalid or stale results must be reviewed again. */
            }
        }
    }
    return null
}

// Drafts preserve completed manual work but never count as AE-ready confirmation.
export function savedSpeakerDraft(assets: any[], scene: any) {
    const names = [...new Set<string>(scene.rows.map((row: any) => row.speaker))]
    const key = scene.key
    const latest = assets.filter(a => ['uploaded', 'assigned'].includes(a.status)
        && ['speaker_coordinate_draft', 'speaker_coordinate_confirmation'].includes(a.metadata?.kind)
        && a.metadata.scene_key === key)
        .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))[0]
    if (latest?.metadata?.kind !== 'speaker_coordinate_draft') return null
    const result = latest.metadata.results?.find((r: any) => r.number === scene.number
        && r.image_id === scene.image?.id && r.source_path === coordinateSource(scene.image).path)
    if (!result || !/^[a-f0-9]{64}$/.test(result.source_sha256 || '')) return null
    try {
        const selected = names.filter(name => result.speakers?.some((s: any) => s.speaker === name))
        const speakers = validateSpeakerGeometry(selected.map(name => result.speakers.find((s: any) => s.speaker === name)), selected)
        return { ...result, speakers }
    } catch { return null }
}
