/** Display-only source. Never write the short pose cycle into scene.video_url. */
export function subtitleMouthPreview(scene: any, originalVideoUrl?: string | null) {
    const preview = scene?.mouth_preview || scene?.metadata?.cowork_image_asset?.speaker_geometry?.mouth_preview
    const url = originalVideoUrl || (preview?.state && preview.state !== 'ready' ? '' :
        scene?.mouth_preview_url || preview?.url) || ''
    const isMouthPreview = Boolean(url && !originalVideoUrl)
    const preserveOriginal = isMouthPreview && preview?.preserve_original === true
    return { url: String(url), isMouthPreview, preserveOriginal,
        label: isMouthPreview ? (preserveOriginal
            ? '3초 미리보기 · 가려진 입 원본 유지'
            : '3초 입모양 미리보기 · 음성 싱크 전') : '' }
}
