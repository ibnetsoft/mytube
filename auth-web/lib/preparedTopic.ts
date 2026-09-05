export type PreparedTopicLike = {
    status?: string | null
    assigned_at?: string | null
    generated_title?: string | null
    category_id?: string | number | null
    categories?: unknown
    pregenerated_structure?: any
    pregenerated_structure_status?: string | null
    pregenerated_script?: string | null
    pregenerated_script_status?: string | null
    publish_metadata?: any
    progress_payload?: any
}

export function hasReadySceneMediaPrompts(topic: PreparedTopicLike): boolean {
    const structure = topic?.pregenerated_structure
    const scenes = Array.isArray(structure?.scenes) ? structure.scenes : []
    if (topic?.pregenerated_structure_status !== 'ready' || !structure || scenes.length === 0) return false
    if (String(structure.image_grid_prompt_status || '') !== 'ready') return false

    const grids = Array.isArray(structure.image_grid_prompts) ? structure.image_grid_prompts : []
    const expectedGridCount = Math.floor(scenes.length / 4) + (scenes.length % 4 ? 1 : 0)
    if (grids.length !== expectedGridCount) return false
    const seenGridPrompts = new Set<string>()
    const coveredSceneNumbers = new Set<string>()
    const fallbackMarkers = [
        'visualize the final narration beat',
        'distinct story beat with consistent characters and setting',
    ]
    for (const grid of grids) {
        const prompt = String(grid?.prompt || grid?.grid_prompt || '').trim()
        const sceneNumbers = Array.isArray(grid?.scene_numbers) ? grid.scene_numbers : []
        if (!prompt || sceneNumbers.length !== 4) return false
        const template = String(grid?.template || '')
        if (template && !['strict_2x2_v1', 'strict_2x2_compact_v1'].includes(template)) return false
        if (template === 'strict_2x2_compact_v1') {
            const panels = Array.isArray(grid?.panels) ? grid.panels : []
            if (panels.length !== 4) return false
            for (let index = 0; index < panels.length; index += 1) {
                const panelPrompt = String(panels[index]?.panel_prompt || panels[index]?.brief || '').trim()
                if (panelPrompt.length < 80 || fallbackMarkers.some(marker => panelPrompt.toLowerCase().includes(marker))) return false
                if (String(panels[index]?.scene_number || '') !== String(sceneNumbers[index] || '')) return false
            }
        }
        if (prompt.length < 420) return false
        for (const position of ['Top-Left', 'Top-Right', 'Bottom-Left', 'Bottom-Right']) {
            if (!prompt.includes(`Position: ${position}`)) return false
        }
        if (seenGridPrompts.has(prompt)) return false
        seenGridPrompts.add(prompt)
        for (const sceneNumber of sceneNumbers) coveredSceneNumbers.add(String(sceneNumber))
    }
    const seenImagePrompts = new Set<string>()
    return scenes.every((scene: any, index: number) => {
        const sceneNumber = Number(scene?.scene_order || scene?.scene_number || index + 1)
        const imagePrompt = String(scene?.image_prompt || '').trim()
        if (scene?.media_prompt_status !== 'ready' || imagePrompt.length < 120) return false
        if (fallbackMarkers.some(marker => imagePrompt.toLowerCase().includes(marker))) return false
        if (seenImagePrompts.has(imagePrompt)) return false
        seenImagePrompts.add(imagePrompt)
        const requiresVideo = scene?.video_prompt_required !== false && sceneNumber <= 12
        if (requiresVideo && !String(scene?.video_prompt || '').trim()) return false
        return coveredSceneNumbers.has(String(Number.isFinite(sceneNumber) ? sceneNumber : index + 1))
    })
}

export function hasPublishDescription(topic: PreparedTopicLike): boolean {
    const metadata = topic?.publish_metadata || topic?.progress_payload?.publish_metadata || {}
    return String(metadata?.description || '').trim().length > 0
}

export function isPreparedUserTopic(topic: PreparedTopicLike): boolean {
    const scriptReady = topic?.pregenerated_script_status === 'ready'
        && String(topic?.pregenerated_script || '').trim().length > 0
    const structureReady = topic?.pregenerated_structure_status === 'ready'
        && Boolean(topic?.pregenerated_structure)

    return topic?.status === 'pending'
        && !String(topic?.assigned_at || '').trim()
        && String(topic?.generated_title || '').trim().length > 0
        && topic?.category_id !== null
        && topic?.category_id !== undefined
        && scriptReady
        && structureReady
        && hasReadySceneMediaPrompts(topic)
        && hasPublishDescription(topic)
}

export function preparedTopicStatus(topic: PreparedTopicLike): 'ready' | 'not_ready' | 'claimed' {
    if (topic?.status === 'assigned' || String(topic?.assigned_at || '').trim()) return 'claimed'
    return isPreparedUserTopic(topic) ? 'ready' : 'not_ready'
}
