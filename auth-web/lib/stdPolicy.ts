import { isComicProject } from './stdComic'

// Legacy projects were authored with 18 required video scenes. New script-worker
// packages persist the requested count so every web execution path shares it.
export const STD_REQUIRED_CLIP_SCENE_END = 18

function positiveInteger(value: unknown): number | null {
    if (value == null || value === '') return null
    const parsed = Number(value)
    return Number.isInteger(parsed) && parsed >= 0 ? parsed : null
}

function structureFrom(value: any): any {
    return value?.pregenerated_structure
        || value?.structure
        || value?.project_payload?.structure
        || {}
}

export function stdRequiredVideoSceneCount(projectOrTopic?: any): number {
    if (isComicProject(projectOrTopic)) return 0
    const projectPayload = projectOrTopic?.project_payload || {}
    const sourcePayload = projectOrTopic?.source_payload || {}
    const progressPayload = projectOrTopic?.progress_payload || {}
    const structures = [
        structureFrom(projectOrTopic),
        structureFrom(projectPayload),
        structureFrom(sourcePayload),
        structureFrom(sourcePayload?.progress_payload),
    ]
    const candidates = [
        projectOrTopic?.required_video_scene_count,
        projectOrTopic?.video_scene_count,
        projectPayload?.required_video_scene_count,
        projectPayload?.video_scene_count,
        progressPayload?.required_video_scene_count,
        progressPayload?.video_scene_count,
        sourcePayload?.required_video_scene_count,
        sourcePayload?.video_scene_count,
        ...structures.flatMap(structure => [
            structure?.required_video_scene_count,
            structure?.video_scene_count,
            structure?.video_scenes,
        ]),
        projectOrTopic?.video_scenes,
        projectPayload?.video_scenes,
        progressPayload?.video_scenes,
        sourcePayload?.video_scenes,
    ]
    for (const candidate of candidates) {
        const parsed = positiveInteger(candidate)
        if (parsed != null) return parsed
    }

    for (const structure of structures) {
        const scenes = Array.isArray(structure?.scenes) ? structure.scenes : []
        const required = scenes
            .filter((scene: any) => scene?.video_prompt_required === true || scene?.video_generation_mode === 'user_upload')
            .map((scene: any, index: number) => Number(scene?.scene_number || scene?.scene_order || index + 1))
            .filter((sceneNumber: number) => Number.isInteger(sceneNumber) && sceneNumber > 0)
        if (required.length > 0) return Math.max(...required)
    }
    return STD_REQUIRED_CLIP_SCENE_END
}

export function isStdMiddleVideoScene(sceneNumber: any, project?: any): boolean {
    return isStdRequiredClipScene(sceneNumber, project)
}

export function isStdVideoPromptScene(sceneNumber: any, project?: any): boolean {
    return isStdRequiredClipScene(sceneNumber, project)
}

export function isStdRequiredVideoScene(sceneNumber: any, project?: any): boolean {
    return isStdRequiredClipScene(sceneNumber, project)
}

export function isStdRequiredClipScene(sceneNumber: any, project?: any): boolean {
    if (isComicProject(project)) return false
    const parsed = Number(sceneNumber)
    return Number.isFinite(parsed) && parsed >= 1 && parsed <= stdRequiredVideoSceneCount(project)
}
