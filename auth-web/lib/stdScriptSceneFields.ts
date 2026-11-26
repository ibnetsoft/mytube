/** Canonical saved project fields; silent cuts must stay silent. */
export function scriptSceneSpeech(scene:any):string {
    return String(scene?.scene_text ?? scene?.narration_text ?? scene?.metadata?.scene_text ?? '')
}
export function scriptSceneVisual(scene:any):string {
    return String(scene?.image_prompt ?? scene?.visual_prompt ?? scene?.metadata?.image_prompt ?? '')
}
