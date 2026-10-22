import { hasReadyNonverbalPlan } from './stdNonverbal'
import { savedStdOutputStepStatus } from './stdOutputStepStatus'

// List rows and editor rows must not infer completion from absent projection fields.
export function summarizeStdProject(project: any, assets: any[] = []) {
 const payload = project.project_payload || {}
 const scenes = Array.isArray(payload.scenes) && payload.scenes.length ? payload.scenes
  : (Array.isArray(payload.structure?.scenes) ? payload.structure.scenes
   : (Array.isArray(payload.pregenerated_structure?.scenes) ? payload.pregenerated_structure.scenes : []))
 const isTopicDone = Boolean(String(project.title || '').trim())
 const isPlanningDone = Boolean(payload.structure || payload.pregenerated_structure || scenes.length)
 const isScriptDone = hasReadyNonverbalPlan(project) || Boolean(payload.script || payload.pregenerated_script || scenes.some((s: any) => s.scene_text || s.narration))
 const { isImageDone, uploadedAssetsCount, totalScenesCount, isTtsDone, isSubtitlesDone, isThumbnailDone } = savedStdOutputStepStatus(project, assets)
 return { isTopicDone, isPlanningDone, isScriptDone, isImageDone, isTtsDone, isSubtitlesDone, isThumbnailDone,
  allDone: isTopicDone && isPlanningDone && isScriptDone && isImageDone && isTtsDone && isSubtitlesDone && isThumbnailDone,
  uploadedAssetsCount, totalScenesCount }
}
