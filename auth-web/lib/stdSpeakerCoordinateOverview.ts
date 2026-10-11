import { isWorkerSceneVideo, sceneVideoAssets } from './stdSceneVideo'
import { coordinateCast, coordinateScenes, savedSpeakerGeometry, savedSpeakerDraft } from './stdSpeakerGeometry'
import { mapDialogueAnnotations } from './stdDialogueAnnotations'
import { subtitleSpeaker } from './stdSpeakerAssignment'
import { charactersFromPayload } from './stdCharacterProtection'
import { subtitleSpeakerProgress } from './stdSubtitleSpeakerProgress'

export function speakerCoordinateOverview(project: any, assets: any[]) {
    const cast = coordinateCast(project),
        scenes = coordinateScenes(project, assets)
    const jobs = assets.filter((a) => a.metadata?.kind === 'ae_speaker_coordinates')
    const items = scenes.map((scene) => {
        const result = savedSpeakerGeometry(assets, cast, scene)
        const job = jobs.find(
            (a) =>
                a.metadata.input?.cast_key === JSON.stringify(cast) &&
                a.metadata.input?.scenes?.some(
                    (s: any) => s.number === scene.number && s.image?.id === scene.image?.id,
                ),
        )
        const meta = job?.metadata || {}
        const failure = meta.failures?.find((f: any) => f.number === scene.number)
        return {
            ...scene,
            result,
            draft: savedSpeakerDraft(assets, scene),
            error: result ? null : failure?.error || (Number(meta.current_scene) === scene.number ? meta.error : null),
            analysisState: meta.state,
            currentScene: meta.current_scene,
            heartbeatAt: meta.heartbeat_at || job?.updated_at,
        }
    })
    // Use the same latest-video selection and AIR badge rule as the subtitle scene list.
    const videos = sceneVideoAssets(assets, project.id)
    const workerCompleted = items.filter(scene => isWorkerSceneVideo(videos.get(scene.number))).length
    const results = items.flatMap((s) => (s.result ? [s.result] : []))
    return {
        count: items.length,
        workerCompleted,
        completed: results.length,
        failed: items.filter((s) => !s.result && s.error).length,
        pending: items.filter((s) => !s.result && !s.error).length,
        confirmed: items.filter((s) => s.result?.origin === 'user').length,
        scenes: items,
        state: results.length === items.length ? 'ready' : 'needs_review',
        results,
        error: '웹에서 화자 위치를 직접 확정할 수 있습니다. 새로고침 후 위치 지정 버튼을 눌러 주세요.',
    }
}

export function speakerWorkInfo(project: any, assets: any[]) {
    const { count, completed, confirmed, failed, pending, workerCompleted } = speakerCoordinateOverview(project, assets)
    const subtitles = Array.isArray(project.project_payload?.subtitles) ? project.project_payload.subtitles : []
    const parts = mapDialogueAnnotations(subtitles, project.project_payload?.structure?.dialogue_annotations)
    const characters = charactersFromPayload(project.project_payload)
    const speakers = subtitles.map((row: any, index: number) => row.dialogue_override === false ? null : subtitleSpeaker(row, parts.get(index), characters))
    return { projectId: project.id, count, completed, confirmed, failed, pending, workerCompleted,
        speakerProgress: subtitleSpeakerProgress(subtitles, parts, speakers) }
}
