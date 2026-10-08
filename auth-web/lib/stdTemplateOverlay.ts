export const TEMPLATE_OVERLAY_CONTRACT = 'transparent-text-v1'
export const TEMPLATE_REFERENCE_WIDTH = 440

export function templateFontFamily(family: string) {
    return family === 'Pretendard' ? 'Pretendard-Bold' : family || 'sans-serif'
}

/** The preview and saved render input use the same transparent bitmap. */
export async function drawTemplateOverlay(canvas: HTMLCanvasElement, layers: any[]) {
    await Promise.all(layers.map(layer => document.fonts.load(
        `700 ${Number(layer.fontSize) || 28}px "${templateFontFamily(layer.fontFamily)}"`, String(layer.text || ''))))
    await document.fonts.ready
    canvas.width = 1920; canvas.height = 1080
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('템플릿 캔버스를 만들지 못했습니다.')
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.save(); ctx.scale(1920 / TEMPLATE_REFERENCE_WIDTH, 1920 / TEMPLATE_REFERENCE_WIDTH)
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.lineJoin = 'round'
    for (const layer of layers) {
        const size = Math.max(1, Number(layer.fontSize) || 28)
        ctx.font = `700 ${size}px "${templateFontFamily(layer.fontFamily)}"`
        ctx.fillStyle = layer.color || '#fff'; ctx.strokeStyle = layer.strokeColor || '#000'
        const strokeWidth = Math.max(0, Number(layer.strokeWidth) || 0)
        ctx.lineWidth = strokeWidth > 0 ? strokeWidth * 2 : 1
        const x = (Number.isFinite(Number(layer.x)) ? Number(layer.x) : 50) * TEMPLATE_REFERENCE_WIDTH / 100
        const y = (Number.isFinite(Number(layer.y)) ? Number(layer.y) : 50) * TEMPLATE_REFERENCE_WIDTH * 9 / 1600
        const lines = String(layer.text || '').split('\n')
        lines.forEach((line, i) => {
            const lineY = y + (i - (lines.length - 1) / 2) * size * 1.1
            const halfWidth = ctx.measureText(line).width / 2 + strokeWidth
            const safeX = halfWidth < TEMPLATE_REFERENCE_WIDTH / 2
                ? Math.min(TEMPLATE_REFERENCE_WIDTH - halfWidth, Math.max(halfWidth, x)) : x
            if (strokeWidth > 0) ctx.strokeText(line, safeX, lineY)
            ctx.fillText(line, safeX, lineY)
        })
    }
    ctx.restore()
}

export async function templateOverlaySettings(settings: Record<string, any>) {
    if (settings.std_image_template_enabled === undefined) return settings
    const layers = settings.std_template_text_layers || []
    const clean = { ...settings, std_image_template_bg_url: null, std_image_template_bg_color: 'transparent',
        std_template_shape_layers: [], std_template_contract: TEMPLATE_OVERLAY_CONTRACT,
        std_template_reference_width: TEMPLATE_REFERENCE_WIDTH, std_template_overlay_png_data_url: null,
        std_template_overlay_layers: layers }
    // Preserve explicit background choices from the current editor; legacy text-only
    // presets still discard their old default background and shape settings.
    if (typeof settings.std_image_template_bg_transparent === 'boolean') {
        clean.std_image_template_bg_url = settings.std_image_template_bg_url || null
        clean.std_image_template_bg_color = settings.std_image_template_bg_color
        clean.std_template_shape_layers = settings.std_template_shape_layers || []
    }
    if (!settings.std_image_template_enabled || !layers.length) return clean
    const canvas = document.createElement('canvas')
    await drawTemplateOverlay(canvas, layers)
    return { ...clean, std_template_overlay_png_data_url: canvas.toDataURL('image/png') }
}
