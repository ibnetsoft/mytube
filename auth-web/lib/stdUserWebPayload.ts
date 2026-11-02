// Direction plans are production inputs, not editor state. Keep their canonical
// copies on the server for the worker and never include them in user-web payloads.
const postworkKeys = new Set([
    'scene_direction_plan', 'scene_direction_plans', 'ae_directorial_plan',
    'ae_motion_plan', 'ae_motion_plans', 'ae_effect_plan', 'ae_effect_plans',
    'psd_layer_plan', 'psd_layer_prompts', 'local_layer_plan',
    'image_generation_policy', 'video_keyframe_plan', 'shot_design', 'joint_motion_plan',
])

export function stripPostworkDirection(value: any): any {
    if (Array.isArray(value)) return value.filter(item => item?.metadata?.kind !== 'content_revision').map(stripPostworkDirection)
    if (!value || typeof value !== 'object') return value
    return Object.fromEntries(Object.entries(value).flatMap(([key, item]) =>
        postworkKeys.has(key) ? [] : [[key, stripPostworkDirection(item)]]))
}
