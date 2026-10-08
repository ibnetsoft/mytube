import { savedStdOutputStepStatus } from './stdOutputStepStatus'

// List rows and editor rows must not infer completion from absent projection fields.
export function summarizeStdProject(project: any, assets: any[] = []) {
 const payload = project.project_payload || {}
 const scenes = payload.scenes || payload.structure?.scenes || []
 const isTopicDone = Boolean(project.title)
 const isPlanningDone = Boolean(payload.structure || payload.pregenerated_structure || scenes.length)
 const isScriptDone = Boolean(payload.script || payload.pregenerated_script || scenes.some((s: any) => s.scene_text || s.narration))
 const { isImageDone, uploadedAssetsCount, totalScenesCount, isTtsDone, isSubtitlesDone, isThumbnailDone } = savedStdOutputStepStatus(project, assets)
 return { isTopicDone, isPlanningDone, isScriptDone, isImageDone, isTtsDone, isSubtitlesDone, isThumbnailDone,
  allDone: isTopicDone && isPlanningDone && isScriptDone && isImageDone && isTtsDone && isSubtitlesDone && isThumbnailDone,
  uploadedAssetsCount, totalScenesCount }
}
