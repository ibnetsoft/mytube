import { isComicProject } from './stdComic'

// Scenes 1-18 require video clips; scenes after 18 use still images.
export const STD_VIDEO_REQUIRED_UNTIL_SEC = 60
export const STD_VIDEO_REQUIRED_SCENE_SECONDS = 5
export const STD_REQUIRED_VIDEO_SCENE_COUNT = Math.ceil(
    STD_VIDEO_REQUIRED_UNTIL_SEC / STD_VIDEO_REQUIRED_SCENE_SECONDS
)
export const STD_MIDDLE_VIDEO_SCENE_START = STD_REQUIRED_VIDEO_SCENE_COUNT + 1
export const STD_REQUIRED_CLIP_SCENE_END = 18

export function isStdMiddleVideoScene(sceneNumber: any, project?: any): boolean {
    if (isComicProject(project)) return false
    const parsed = Number(sceneNumber)
    return Number.isFinite(parsed) && parsed >= STD_MIDDLE_VIDEO_SCENE_START && parsed <= STD_REQUIRED_CLIP_SCENE_END
}

export function isStdVideoPromptScene(sceneNumber: any, project?: any): boolean {
    return isStdRequiredClipScene(sceneNumber, project)
}

export function isStdRequiredVideoScene(sceneNumber: any, project?: any): boolean {
    if (isComicProject(project)) return false
    const parsed = Number(sceneNumber)
    return Number.isFinite(parsed) && parsed >= 1 && parsed <= STD_REQUIRED_VIDEO_SCENE_COUNT
}

export function isStdRequiredClipScene(sceneNumber: any, project?: any): boolean {
    if (isComicProject(project)) return false
    const parsed = Number(sceneNumber)
    return Number.isFinite(parsed) && parsed >= 1 && parsed <= STD_REQUIRED_CLIP_SCENE_END
}
