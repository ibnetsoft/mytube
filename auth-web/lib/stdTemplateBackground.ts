type TemplateBackground = { bgUrl?: unknown; bgColor?: unknown; bgTransparent?: unknown }

export function isTemplateBackgroundTransparent(settings: TemplateBackground): boolean {
    if (typeof settings.bgTransparent === 'boolean') return settings.bgTransparent
    const color = String(settings.bgColor || '').trim().toLowerCase()
    // Older text-only presets saved the editor's default black even with no background.
    return color === 'transparent' || (!settings.bgUrl && (!color || color === '#000000' || color === '#000'))
}
