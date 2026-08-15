export const STD_VIDEO_REQUIRED_UNTIL_SEC = 60
export const STD_VIDEO_REQUIRED_SCENE_SECONDS = 5
export const STD_REQUIRED_VIDEO_SCENE_COUNT = Math.ceil(
    STD_VIDEO_REQUIRED_UNTIL_SEC / STD_VIDEO_REQUIRED_SCENE_SECONDS
)

export function isStdRequiredVideoScene(sceneNumber: any): boolean {
    const parsed = Number(sceneNumber)
    return Number.isFinite(parsed) && parsed >= 1 && parsed <= STD_REQUIRED_VIDEO_SCENE_COUNT
}
