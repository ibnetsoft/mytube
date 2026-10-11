import sharp from 'sharp'

export async function templateOverlayPng(settings: Record<string, any>): Promise<Buffer | null> {
    if (!settings.std_image_template_enabled || !settings.std_template_text_layers?.length) return null
    const url = String(settings.std_template_overlay_png_data_url || '')
    if ((!url.startsWith('data:image/png;base64,') && !settings.std_template_overlay_gcs?.path) || JSON.stringify(settings.std_template_overlay_layers) !== JSON.stringify(settings.std_template_text_layers)) {
        throw new Error('자막 페이지에서 현재 텍스트 템플릿을 저장한 뒤 렌더링해 주세요.')
    }
    const ref = settings.std_template_overlay_gcs
    const png = url.startsWith('data:image/png;base64,')
        ? Buffer.from(url.slice('data:image/png;base64,'.length), 'base64')
        : await (await import('./gcsStorage')).downloadGcsObject({ bucket: ref.bucket, objectPath: ref.path })
    const image = sharp(png)
    const [metadata, stats] = await Promise.all([image.metadata(), image.stats()])
    if (metadata.format !== 'png' || metadata.channels !== 4 || stats.channels[3]?.min !== 0) {
        throw new Error('템플릿 배경은 투명해야 합니다.')
    }
    return png
}

/** Persist only a GCS reference in Supabase, never a base64 image. */
export async function persistTemplateOverlay(projectId: string, settings: Record<string, any>) {
    if (!String(settings.std_template_overlay_png_data_url || '').startsWith('data:image/png;base64,')) {
        const ref = settings.std_template_overlay_gcs
        if (ref) {
            const { gcsBucketName, isGcsConfiguredAsync } = await import('./gcsStorage')
            if (!(await isGcsConfiguredAsync()) || ref.bucket !== gcsBucketName()
                || !String(ref.path || '').startsWith(`std-projects/${projectId}/template-overlay/`)
                || !/\/[a-f0-9]{64}\.png$/.test(ref.path)) throw new Error('Invalid template overlay reference')
        }
        return settings
    }
    const png = await templateOverlayPng(settings)
    if (!png) return { ...settings, std_template_overlay_png_data_url: null, std_template_overlay_gcs: null }
    const { createHash } = await import('crypto')
    const { uploadGcsBuffer } = await import('./gcsStorage')
    const hash = createHash('sha256').update(png).digest('hex')
    const ref = await uploadGcsBuffer({ objectPath: `std-projects/${projectId}/template-overlay/${hash}.png`, data: png, contentType: 'image/png' })
    return { ...settings, std_template_overlay_png_data_url: null, std_template_overlay_gcs: { bucket: ref.bucket, path: ref.path } }
}
