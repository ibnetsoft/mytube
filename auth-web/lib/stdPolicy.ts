import { isComicProject } from './stdComic'

// Scenes 1-12 are supplied by the user; scenes 13-18 are generated locally by ComfyUI.
export const STD_VIDEO_REQUIRED_UNTIL_SEC = 60
export const STD_VIDEO_REQUIRED_SCENE_SECONDS = 5
export const STD_REQUIRED_VIDEO_SCENE_COUNT = Math.ceil(
    STD_VIDEO_REQUIRED_UNTIL_SEC / STD_VIDEO_REQUIRED_SCENE_SECONDS
)
export const STD_COMFY_VIDEO_SCENE_START = STD_REQUIRED_VIDEO_SCENE_COUNT + 1
export const STD_COMFY_VIDEO_SCENE_END = 18

export function isStdComfyVideoScene(sceneNumber: any, project?: any): boolean {
    if (isComicProject(project)) return false
    const parsed = Number(sceneNumber)
    return Number.isFinite(parsed) && parsed >= STD_COMFY_VIDEO_SCENE_START && parsed <= STD_COMFY_VIDEO_SCENE_END
}

export function isStdVideoPromptScene(sceneNumber: any, project?: any): boolean {
    return isStdRequiredVideoScene(sceneNumber, project) || isStdComfyVideoScene(sceneNumber, project)
}

export function isStdRequiredVideoScene(sceneNumber: any, project?: any): boolean {
    if (isComicProject(project)) return false
    const parsed = Number(sceneNumber)
    return Number.isFinite(parsed) && parsed >= 1 && parsed <= STD_REQUIRED_VIDEO_SCENE_COUNT
}
