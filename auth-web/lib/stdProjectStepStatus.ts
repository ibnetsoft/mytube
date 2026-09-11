import { isStdRequiredVideoScene } from './stdPolicy'

// List rows and editor rows must not infer completion from absent projection fields.
export function summarizeStdProject(project: any, assets: any[] = []) {
 const payload = project.project_payload || {}
 const progress = project.progress_payload || {}
 const scenes = payload.scenes || payload.structure?.scenes || []
 const active = assets.filter(a => ['uploaded', 'assigned'].includes(a.status) && a.drive_file_id)
 const isTopicDone = Boolean(project.title)
 const isPlanningDone = Boolean(payload.structure || payload.pregenerated_structure || scenes.length)
 const isScriptDone = Boolean(payload.script || payload.pregenerated_script || scenes.some((s: any) => s.scene_text || s.narration))
 const uploadedAssetsCount = scenes.filter((s: any, i: number) => {
   const n = Number(s.scene_number || s.scene_order || i + 1)
   const media = active.filter(a => Number(a.scene_number) === n)
   return isStdRequiredVideoScene(n) ? Boolean(s.video_url || media.some(a => a.asset_type === 'video'))
     : Boolean(s.image_url || s.video_url || media.some(a => ['image', 'video'].includes(a.asset_type)))
 }).length
 const isImageDone = scenes.length > 0 && uploadedAssetsCount === scenes.length
 const isTtsDone = !progress.script_changed_requires_audio_regeneration && Boolean(payload.audio_url || payload.tts_url || progress.tts_completed || active.some(a => a.asset_type === 'audio'))
 const isSubtitlesDone = Boolean(progress.subtitles_saved || progress.subtitles_completed || payload.subtitles_saved)
 const isThumbnailDone = Boolean(payload.thumbnail_url || progress.thumbnail_url || progress.thumbnail_completed || active.some(a => a.asset_type === 'thumbnail'))
 return { isTopicDone, isPlanningDone, isScriptDone, isImageDone, isTtsDone, isSubtitlesDone, isThumbnailDone,
  allDone: isTopicDone && isPlanningDone && isScriptDone && isImageDone && isTtsDone && isSubtitlesDone && isThumbnailDone,
  uploadedAssetsCount, totalScenesCount: scenes.length }
}
