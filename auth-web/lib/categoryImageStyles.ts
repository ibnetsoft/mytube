const LEGACY_AUTOMATIC_IMAGE_STYLES = new Set(['', 'realistic', 'cinematic'])

// Restored from the existing AIR Worker category-image-style screen.
// Supabase category.default_image_style still wins when it contains a
// deliberate non-legacy value, so admins can change future generations.
export const CATEGORY_IMAGE_STYLE_DEFAULTS: Record<string, string> = {
    '탈북사연': 'shadowed investigation',
    '해외감동': 'watercolor',
    '황혼19금': 'rainy neon metropolis',
    '옛날이야기': 'watercolor forest story',
    '한국사연': 'he moonlit hanok palace',
    '무협': 'classic vintage cinema',
    'English Folktales': 'realistic',
    '日本昔話': 'realistic',
}

export function resolveCategoryImageStyle(categoryName: unknown, configuredStyle: unknown): string {
    const configured = String(configuredStyle || '').trim()
    const restoredDefault = CATEGORY_IMAGE_STYLE_DEFAULTS[String(categoryName || '').trim()]
    if (configured && (!restoredDefault || !LEGACY_AUTOMATIC_IMAGE_STYLES.has(configured.toLowerCase()))) {
        return configured
    }
    return restoredDefault || configured || 'realistic'
}

export function imageStyleLabelForPrompt(styleKey: unknown): string {
    const style = String(styleKey || '').trim() || 'realistic'
    return `Selected image style: ${style}.`
}
