import { persistentThumbnailUrl } from './stdThumbnailUrl'

export const THUMBNAIL_CONTRACT = 'editable-background-v1'
export type ThumbnailLayer = { id: string; text: string; fontSize: number; fontFamily: string;
    color: string; strokeColor: string; strokeWidth: number; x: number; y: number }

/** A flattened final is never an editable background, even on legacy records. */
export function thumbnailEditorBackground(project: any = {}, progress: any = {}): string {
    const design = project.thumbnail_design || progress.thumbnail_design || {}
    const finals = new Set([design.thumbnail_url, project.thumbnail_url, progress.thumbnail_url].filter(Boolean))
    return persistentThumbnailUrl(...[design.editor_bg_url, design.bg_url, project.thumbnail_bg_url, progress.thumbnail_bg_url]
        .filter(url => !finals.has(url)))
}

export function editableThumbnailError(design: any, finalUrl: unknown, completed: unknown): string {
    if (design?.contract !== THUMBNAIL_CONTRACT) return '' // Legacy records remain readable.
    const raw = persistentThumbnailUrl(design.editor_bg_url, design.bg_url)
    if (!completed && design.render_status === 'awaiting_background' && !design.editor_bg_url && !design.bg_url) return ''
    if (!raw || !Array.isArray(design.text_layers)) return '편집 배경과 문구 레이어를 먼저 저장해 주세요.'
    if (completed && (design.render_status !== 'completed' || !persistentThumbnailUrl(finalUrl)
        || finalUrl !== design.thumbnail_url || finalUrl === raw)) {
        return '배경과 문구를 합성한 최종 썸네일을 저장해 주세요.'
    }
    return ''
}

export async function loadThumbnailBackground(url: string, headers?: HeadersInit): Promise<HTMLImageElement> {
    if (!url) throw new Error('글자 없는 썸네일 배경 이미지를 먼저 준비해 주세요.')
    const response = await fetch(url, { headers })
    if (!response.ok) throw new Error(`썸네일 배경을 불러오지 못했습니다. (${response.status})`)
    const blob = await response.blob()
    if (!blob.type.startsWith('image/')) throw new Error('썸네일 배경이 이미지 파일이 아닙니다.')
    const objectUrl = URL.createObjectURL(blob)
    try {
        return await new Promise((resolve, reject) => {
            const image = new Image()
            image.onload = () => resolve(image)
            image.onerror = () => reject(new Error('썸네일 배경 이미지를 읽지 못했습니다.'))
            image.src = objectUrl
        })
    } finally { URL.revokeObjectURL(objectUrl) }
}

export function thumbnailLines(context: Pick<CanvasRenderingContext2D, 'measureText'>, text: string, maxWidth = 456): string[] {
    const lines: string[] = []
    for (const paragraph of text.split('\n')) {
        let line = ''
        for (const char of Array.from(paragraph)) {
            if (line && context.measureText(line + char).width > maxWidth) { lines.push(line); line = '' }
            line += char
        }
        lines.push(line)
    }
    return lines
}

/** Shared by preview and Save: 480-wide editor units -> 1280x720 PNG. */
export async function drawThumbnail(canvas: HTMLCanvasElement, image: HTMLImageElement, layers: ThumbnailLayer[]) {
    await Promise.all(layers.map(layer => document.fonts.load(`900 ${layer.fontSize}px "${layer.fontFamily}"`, layer.text)))
    await document.fonts.ready
    canvas.width = 1280; canvas.height = 720
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('썸네일 캔버스를 만들지 못했습니다.')
    const scale = Math.max(1280 / image.naturalWidth, 720 / image.naturalHeight)
    const w = image.naturalWidth * scale, h = image.naturalHeight * scale
    ctx.drawImage(image, (1280 - w) / 2, (720 - h) / 2, w, h)
    ctx.save(); ctx.scale(1280 / 480, 1280 / 480)
    for (const layer of layers) {
        const size = Math.max(6, Number(layer.fontSize) || 28)
        ctx.font = `900 ${size}px "${layer.fontFamily || 'sans-serif'}"`
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.lineJoin = 'round'
        ctx.fillStyle = layer.color || '#fff'; ctx.strokeStyle = layer.strokeColor || '#000'
        ctx.lineWidth = Math.max(0, Number(layer.strokeWidth) || 0) * 2
        const lines = thumbnailLines(ctx, layer.text)
        const x = (Number.isFinite(layer.x) ? layer.x : 50) * 4.8
        const y = (Number.isFinite(layer.y) ? layer.y : 50) * 2.7
        lines.forEach((line, i) => {
            const lineY = y + (i - (lines.length - 1) / 2) * size * 1.15
            if (ctx.lineWidth > 0) ctx.strokeText(line, x, lineY)
            ctx.fillText(line, x, lineY)
        })
    }
    ctx.restore()
}

export async function renderThumbnailFile(url: string, layers: ThumbnailLayer[], headers?: HeadersInit): Promise<File> {
    const image = await loadThumbnailBackground(url, headers)
    const canvas = document.createElement('canvas')
    await drawThumbnail(canvas, image, layers)
    const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/png'))
    if (!blob) throw new Error('최종 썸네일 PNG 생성에 실패했습니다.')
    return new File([blob], `std_thumbnail_${Date.now()}.png`, { type: 'image/png' })
}
