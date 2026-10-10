const sceneNumber = (scene: any) => Number(scene?.scene_number ?? scene?.scene_order ?? scene?.number)

/** Return only an explicitly enabled script-worker eye-blink direction for this scene. */
export function directedEyeBlinkPlan(scenes: any[], number: number) {
    for (const scene of scenes || []) {
        if (!scene || sceneNumber(scene) !== Number(number)) continue
        const direction = scene.scene_direction_plan || scene.ae_directorial_plan
            || scene.metadata?.scene_direction_plan || scene.metadata?.ae_directorial_plan
        const plan = direction?.eye_blink_plan
        if (plan?.enabled === true && Array.isArray(plan.cues) && plan.cues.length > 0) return plan
    }
    return null
}
