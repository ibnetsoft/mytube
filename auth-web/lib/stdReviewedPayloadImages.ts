/** Expose only source-bound, anatomy-reviewed payload images to motion editors. */
export function withReviewedPayloadImages(project: any, assets: any[]) {
    const scenes = project?.project_payload?.structure?.scenes
    if (!Array.isArray(scenes)) return assets
    const excluded = new Set(project.project_payload.structure.excluded_image_cut_ids || [])
    const existing = new Set(assets.filter(a => a.asset_type === 'image').map(a => Number(a.scene_number)))
    const images = scenes.flatMap((scene: any) => {
        const number = Number(scene.scene_number ?? scene.scene_order)
        const sha = String(scene.source_image_sha256 || '').toLowerCase()
        const review = scene.anatomy_review
        if (!Number.isInteger(number) || number < 1 || existing.has(number) || excluded.has(scene.cut_id)
            || scene.image_use_status !== 'approved' || review?.contract !== 'wuxia_anatomy_review/v1'
            || review.verdict !== 'pass' || String(review.source_sha256 || '').toLowerCase() !== sha
            || (review.cut_id && review.cut_id !== scene.cut_id)
            || !/^[a-f0-9]{64}$/.test(sha) || !scene.gcs_bucket || !scene.gcs_path) return []
        return [{ id: `reviewed-payload:${number}:${sha}`, project_id: project.id, asset_type: 'image',
            status: 'assigned', scene_number: number, mime_type: 'image/png',
            metadata: { storage_provider: 'gcs', gcs_bucket: scene.gcs_bucket, gcs_path: scene.gcs_path, reviewed_source_sha256: sha } }]
    })
    return [...assets, ...images]
}
