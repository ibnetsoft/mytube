export function charactersFromPayload(payload: any): any[] {
    const structure = payload?.structure || {}
    const anchors = structure?.character_anchors || payload?.character_anchors || {}
    const main = anchors?.main_character || payload?.main_character || structure?.main_character
    const supporting = anchors?.supporting_characters || payload?.supporting_characters || structure?.supporting_characters || []
    return [main, ...(Array.isArray(supporting) ? supporting : [])].filter(Boolean)
}

export function protectCharacterReferenceUrls(value: any, projectId: string): any {
    const clone = value && typeof value === 'object' ? JSON.parse(JSON.stringify(value)) : value
    const canonicalCharacters = charactersFromPayload(clone)
    const slotFor = (character: any) => canonicalCharacters.findIndex(candidate => {
        const candidateKey = String(candidate?.character_key || '').trim()
        const characterKey = String(character?.character_key || '').trim()
        if (candidateKey && characterKey) return candidateKey === characterKey
        return String(candidate?.name || '').trim() === String(character?.name || '').trim()
    })
    const visit = (node: any, characterContext = false, parentSlot = -1) => {
        if (!node || typeof node !== 'object') return
        if (Array.isArray(node)) {
            node.forEach(item => visit(item, characterContext, parentSlot))
            return
        }
        if (characterContext && typeof node.image_url === 'string' && node.image_url.trim()) {
            const ownSlot = slotFor(node)
            const slot = ownSlot >= 0 ? ownSlot : parentSlot
            if (slot >= 0) {
                node.image_url = `/api/std/projects/${encodeURIComponent(projectId)}/character-thumbnail?slot=${slot}`
                if (ownSlot < 0 && typeof node.type === 'string') {
                    const query = new URLSearchParams({ sheet: node.type })
                    if (node.fingerprint || node.sha256) query.set('v', String(node.fingerprint || node.sha256).slice(0, 24))
                    node.image_url += `&${query}`
                    delete node.gcs_bucket
                    delete node.gcs_path
                }
            } else {
                delete node.image_url
            }
            delete node.reference_image_url
            delete node.storage_object_path
            delete node.storage_bucket
        }
        for (const [key, child] of Object.entries(node)) {
            const nextContext = characterContext
                || key === 'character_anchors'
                || key === 'main_character'
                || key === 'supporting_characters'
            const ownSlot = slotFor(node)
            visit(child, nextContext, ownSlot >= 0 ? ownSlot : parentSlot)
        }
    }
    visit(clone)
    return clone
}
