export type FinalSceneTransition = {
    to: number
    effect: string
    ae_direction: string
    boundary_ms: number
    start_ms: number
    end_ms: number
}

export type FinalSceneEffect = {
    number: number
    title: string
    start_ms: number
    end_ms: number
    effects: string[]
    ae_directions: string[]
    notes: string[]
    outgoing: FinalSceneTransition | null
}

export type FinalSceneDelivery = {
    schema: 'std_final_scene_delivery/v1'
    master: { asset_id: string; sha256: string; render_version: number; duration_ms: number }
    scenes: FinalSceneEffect[]
}

export type FinalScenePlayback = { label: string; start_ms: number; end_ms: number }

const milliseconds = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) >= 0
const texts = (value: unknown): value is string[] => Array.isArray(value) && value.every(entry => typeof entry === 'string' && entry.trim())

export function readStdFinalSceneDelivery(assets: any[], renderHistory: any[]): FinalSceneDelivery | null {
    const completed = renderHistory.filter(render => render.status === 'completed')
        .sort((a, b) => Number(b.render_version) - Number(a.render_version))[0]
    if (!completed?.playback_asset_id) return null
    for (const asset of assets) {
        const delivery = asset.metadata?.delivery as FinalSceneDelivery | undefined
        const master = delivery?.master
        if (asset.asset_type !== 'other' || asset.status !== 'uploaded' || asset.metadata?.kind !== 'final_scene_delivery'
            || delivery?.schema !== 'std_final_scene_delivery/v1' || !master
            || master.asset_id !== completed.playback_asset_id || master.sha256 !== completed.metadata?.sha256
            || master.render_version !== Number(completed.render_version) || !milliseconds(master.duration_ms)
            || !Array.isArray(delivery.scenes) || !delivery.scenes.length) continue
        const valid = delivery.scenes.every((scene, index, scenes) => {
            const next = scenes[index + 1]
            const transition = scene.outgoing
            if (scene.number !== index + 1 || typeof scene.title !== 'string'
                || !milliseconds(scene.start_ms) || !milliseconds(scene.end_ms)
                || scene.end_ms <= scene.start_ms || scene.end_ms !== (next?.start_ms ?? master.duration_ms)
                || !texts(scene.effects) || !texts(scene.ae_directions) || !texts(scene.notes)) return false
            return next ? transition && transition.to === next.number && typeof transition.effect === 'string'
                && typeof transition.ae_direction === 'string' && milliseconds(transition.boundary_ms)
                && milliseconds(transition.start_ms) && milliseconds(transition.end_ms)
                && transition.boundary_ms === scene.end_ms && transition.start_ms >= scene.start_ms
                && transition.start_ms < transition.boundary_ms && transition.end_ms > transition.boundary_ms
                && transition.end_ms <= next.end_ms : transition === null
        })
        if (valid && delivery.scenes[0].start_ms === 0) return delivery
    }
    return null
}
