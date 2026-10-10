import { savedStdVisualStepStatus } from './stdVisualStepStatus'
// Canonical saved output status for the user editor, project list, and admin queue.
// Local previews and stale topics_queue.steps do not override saved project state.
export function savedStdOutputStepStatus(project: any, assets: any[] = []) {
 const payload = project.project_payload || {}
 const progress = project.progress_payload || {}
 const active = assets.filter(a => ['uploaded', 'assigned'].includes(a.status) && a.id && (
  a.metadata?.gcs_path || a.metadata?.storage_path || a.metadata?.gcs_signed_url || a.metadata?.gcs_public_url
 ))
 const isTtsDone = !progress.script_changed_requires_audio_regeneration && Boolean(payload.audio_url || payload.tts_url || progress.tts_completed || active.some(a => a.asset_type === 'audio'))
 // The subtitle step is complete only after the combined Save + TTS flow
 // durably saves both the subtitles and the final narration.
 const isSubtitlesDone = isTtsDone && progress.subtitle_tts_completed === true
 const isThumbnailDone = Boolean(payload.thumbnail_url || progress.thumbnail_url || progress.thumbnail_completed || active.some(a => a.asset_type === 'thumbnail'))
 return { ...savedStdVisualStepStatus(project, assets), isTtsDone, isSubtitlesDone, isThumbnailDone }
}

export function topicOutputStepDone(key: string, saved: ReturnType<typeof savedStdOutputStepStatus> | undefined, legacy: Record<string, boolean> = {}) {
 if (saved) {
  if (key === 'image') return saved.isImageDone
  if (key === 'tts') return saved.isTtsDone
  if (key === 'subtitle') return saved.isSubtitlesDone
  if (key === 'template') return saved.isThumbnailDone
 }
 return Boolean(legacy[key])
}
