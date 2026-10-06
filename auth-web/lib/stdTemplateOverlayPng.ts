import sharp from 'sharp'

export async function templateOverlayPng(settings: Record<string, any>): Promise<Buffer | null> {
    if (!settings.std_image_template_enabled || !settings.std_template_text_layers?.length) return null
    const url = String(settings.std_template_overlay_png_data_url || '')
    if (!url.startsWith('data:image/png;base64,') || JSON.stringify(settings.std_template_overlay_layers) !== JSON.stringify(settings.std_template_text_layers)) {
        throw new Error('자막 페이지에서 현재 텍스트 템플릿을 저장한 뒤 렌더링해 주세요.')
    }
    const png = Buffer.from(url.slice('data:image/png;base64,'.length), 'base64')
    const image = sharp(png)
    const [metadata, stats] = await Promise.all([image.metadata(), image.stats()])
    if (metadata.format !== 'png' || metadata.channels !== 4 || stats.channels[3]?.min !== 0) {
        throw new Error('템플릿 배경은 투명해야 합니다.')
    }
    return png
}
