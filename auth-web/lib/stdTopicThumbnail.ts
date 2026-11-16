import { editableThumbnailError, thumbnailEditorBackground } from './stdThumbnailRender'
import { persistentThumbnailUrl } from './stdThumbnailUrl'

const object = (value: any) => value && typeof value === 'object' && !Array.isArray(value) ? value : {}

/** Transfer the complete editable package, never just its background. */
export function topicThumbnailPayloads(topic: any) {
    const progress = object(topic?.progress_payload)
    const structure = object(topic?.pregenerated_structure)
    const design = object(progress.thumbnail_design || structure.thumbnail_design)
    const url = persistentThumbnailUrl(progress.thumbnail_url, design.thumbnail_url)
    const bg = thumbnailEditorBackground({ ...progress, thumbnail_design: design })
    const completed = progress.thumbnail_completed === true && Boolean(url && bg)
        && !editableThumbnailError(design, url, true)
    return {
        project_payload: {
            ...(bg ? { thumbnail_bg_url: bg } : {}),
            ...(url ? { thumbnail_url: url } : {}),
            ...(Object.keys(design).length ? { thumbnail_design: design } : {}),
        },
        progress_payload: {
            ...(url ? { thumbnail_url: url } : {}),
            ...(completed ? { thumbnail_completed: true, thumbnail_render_status: 'completed' } : {}),
        },
    }
}

/** A saved draft/final belongs to the user. Never replace it with a topic package. */
export function canRestoreTopicThumbnail(project: any) {
    const payload = object(project?.project_payload), progress = object(project?.progress_payload)
    return ![payload.thumbnail_design, progress.thumbnail_design].some(value => Object.keys(object(value)).length)
        && !persistentThumbnailUrl(payload.thumbnail_url, progress.thumbnail_url)
        && !progress.thumbnail_confirmed_at && progress.thumbnail_completed !== true
        && payload.strict_content_identity !== true
}

/** Read-time recovery is non-destructive; the normal thumbnail save persists edits. */
export function restoreTopicThumbnail(project: any, topic = project?.source_payload) {
    if (!canRestoreTopicThumbnail(project)) return project
    if (topic?.id && project.topic_queue_id && String(topic.id) !== String(project.topic_queue_id)) return project
    const inherited = topicThumbnailPayloads(topic)
    if (!inherited.project_payload.thumbnail_design) return project
    const payload = object(project.project_payload), progress = object(project.progress_payload)
    const currentBg = persistentThumbnailUrl(payload.thumbnail_bg_url, progress.thumbnail_bg_url)
    if (currentBg && currentBg !== inherited.project_payload.thumbnail_bg_url) return project
    return {
        ...project,
        project_payload: { ...payload, ...inherited.project_payload },
        progress_payload: { ...progress, ...inherited.progress_payload },
    }
}
