export function audioAssetRole(asset: any): string {
    const type = String(asset?.asset_type || '')
    const role = String(asset?.metadata?.audio_role || '')
    return type === 'other' && ['bgm', 'sfx'].includes(role) ? role : type
}

// Older production schemas support `other`, but not dedicated BGM/SFX types.
export function audioAssetStorageFields(role: string) {
    return ['bgm', 'sfx'].includes(role)
        ? { asset_type: 'other', metadata: { audio_role: role } }
        : { asset_type: role, metadata: {} }
}

export function backgroundVolume(value: unknown): number {
    const volume = value == null ? 0.08 : Number(value)
    return Number.isFinite(volume) ? Math.max(0, Math.min(1, volume)) : 0.08
}
