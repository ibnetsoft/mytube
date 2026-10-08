import { savedStdOutputStepStatus } from './stdOutputStepStatus'
import { isStdRequiredClipScene } from './stdPolicy'

// List rows and editor rows must not infer completion from absent projection fields.
export function summarizeStdProject(project: any, assets: any[] = []) {
 const payload = project.project_payload || {}
 const scenes = payload.scenes || payload.structure?.scenes || []
 const active = assets.filter(a => {
   if (!['uploaded', 'assigned'].includes(a.status)) return false
   const metadata = a.metadata || {}
   return Boolean(a.id && (metadata.gcs_path || metadata.storage_path || metadata.gcs_signed_url || metadata.gcs_public_url))
 })
 const isTopicDone = Boolean(project.title)
 const isPlanningDone = Boolean(payload.structure || payload.pregenerated_structure || scenes.length)
 const isScriptDone = Boolean(payload.script || payload.pregenerated_script || scenes.some((s: any) => s.scene_text || s.narration))
 const uploadedAssetsCount = scenes.filter((s: any, i: number) => {
   const n = Number(s.scene_number || s.scene_order || i + 1)
   const media = active.filter(a => Number(a.scene_number) === n)
   return isStdRequiredClipScene(n, project) ? Boolean(s.video_url || media.some(a => a.asset_type === 'video'))
     : Boolean(s.image_url || s.video_url || media.some(a => ['image', 'video'].includes(a.asset_type)))
 }).length
 const isImageDone = scenes.length > 0 && uploadedAssetsCount === scenes.length
 const { isTtsDone, isSubtitlesDone, isThumbnailDone } = savedStdOutputStepStatus(project, assets)
 return { isTopicDone, isPlanningDone, isScriptDone, isImageDone, isTtsDone, isSubtitlesDone, isThumbnailDone,
  allDone: isTopicDone && isPlanningDone && isScriptDone && isImageDone && isTtsDone && isSubtitlesDone && isThumbnailDone,
  uploadedAssetsCount, totalScenesCount: scenes.length }
}
