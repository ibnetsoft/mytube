import { coordinateSource } from './stdSpeakerGeometry'

/** Adapt topic-generation receipts to the existing web/AE geometry contract.
 * Image asset records stay unchanged: workers compare their original metadata.
 */
export function generatedSpeakerAssets(project: any, structure: any, assets: any[]) {
    return (structure?.scenes || []).flatMap((scene: any, index: number) => {
        const number = Number(scene.scene_number || scene.scene_order || index + 1)
        const receipt = scene.metadata?.cowork_image_asset?.speaker_geometry
        if (number < 19 || receipt?.source !== 'local-codex-image-publish' || receipt.number !== number) return []
        const image = assets.find(a => a.project_id === project.id && a.asset_type === 'image'
            && Number(a.scene_number) === number && ['uploaded', 'assigned'].includes(a.status))
        if (!image) return []
        const ref = coordinateSource(image)
        if (ref.path !== receipt.source_path || ref.bucket !== receipt.source_bucket
            || !/^[a-f0-9]{64}$/.test(receipt.source_sha256 || '')) return []
        // The consumer also validates current cast, speakers, bounds and confidence.
        const result = { number, image_id: image.id, source_path: ref.path,
            source_sha256: receipt.source_sha256, speakers: receipt.speakers }
        return [{ id: `generated-speakers:${image.id}:${receipt.fingerprint}`, project_id: project.id,
            asset_type: 'other', status: 'uploaded', scene_number: number,
            created_at: receipt.updated_at, updated_at: receipt.updated_at,
            metadata: { kind: 'ae_speaker_coordinates', state: receipt.state,
                fingerprint: receipt.fingerprint, source: receipt.source,
                input: { cast_key: JSON.stringify({ main: receipt.cast?.main || {}, supporting: receipt.cast?.supporting || [], scene_cast: receipt.cast?.scene_cast || [] }), scenes: [{ number, image: { id: image.id } }] },
                results: receipt.state === 'ready' ? [result] : [],
                failures: receipt.state === 'needs_review' ? [{ number, error: receipt.error || 'Speaker coordinates need review' }] : [] } }]
    })
}

export async function appendGeneratedSpeakerAssets(db: any, projectIds: string[], assets: any[]) {
    // No applicable stills means there is no generation receipt to look up.
    const ids = projectIds.filter(id => assets.some(a => a.project_id === id && a.asset_type === 'image' && Number(a.scene_number) >= 19))
    if (!ids.length) return assets
    const projects = await db.from('std_projects').select('id,topic_queue_id,project_payload,source_payload').in('id', ids)
    if (projects.error) throw projects.error
    const topicId = (p: any) => p.topic_queue_id || p.source_payload?.topic_queue_id || p.project_payload?.topic_queue_id
    const topicIds = [...new Set((projects.data || []).map(topicId).filter(Boolean))]
    const topics = topicIds.length
        ? await db.from('topics_queue').select('id,pregenerated_structure').in('id', topicIds)
        : { data: [], error: null }
    if (topics.error) throw topics.error
    return [...assets, ...(projects.data || []).flatMap((project: any) => {
        const latest = topics.data?.find((t: any) => String(t.id) === String(topicId(project)))
        const structure = latest?.pregenerated_structure || project.project_payload?.structure || project.source_payload?.pregenerated_structure
        return generatedSpeakerAssets(project, structure, assets)
    })]
}
