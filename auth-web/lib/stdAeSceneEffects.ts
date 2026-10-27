/** Effects supported by the reviewed PSD renderer; IDs match ae_scene_effects.py. */
export const AE_SCENE_EFFECTS = [
    { id: 'depth_background_blur', label: '깊이 · 먼 배경 흐림' },
    { id: 'depth_foreground_blur', label: '깊이 · 가까운 전경 흐림' },
    { id: 'depth_background_haze', label: '깊이 · 먼 배경 안개' },
    { id: 'impact_shake', label: '타격 카메라 흔들림' },
    { id: 'atmospheric_haze', label: '안개' },
    { id: 'warm_dust_motes', label: '떠다니는 먼지' },
    { id: 'particle_burst', label: '파티클 분출' },
    { id: 'debris_burst', label: '파편 분출' },
    { id: 'focus_glow', label: '부분 발광' },
    { id: 'light_sweep', label: '빛줄기 이동' },
    { id: 'impact_flash', label: '충격 섬광' },
    { id: 'shock_ring', label: '충격파 링' },
    { id: 'energy_trail', label: '에너지 궤적' },
    { id: 'heat_distortion', label: '국소 열 왜곡' },
    { id: 'subtle_vignette', label: '비네트' },
    { id: 'speedline_burst', label: '집중선' },
    { id: 'fireflies', label: '반딧불 · 제출 영상 대본 연동' },
] as const
export function aeSceneEffectSelection(value: unknown): string[] | undefined {
    if (value === undefined) return undefined // Keep existing preparation fingerprints valid.
    if (!Array.isArray(value) || value.length > AE_SCENE_EFFECTS.length
        || value.some(id => id==='fireflies' || !AE_SCENE_EFFECTS.some(effect => effect.id === id))
        || new Set(value).size !== value.length) throw new Error('지원하는 AE 효과를 중복 없이 선택해 주세요.')
    return [...value].sort()
}
export function aeSceneEffectsMatch(requested: unknown, plan: any): boolean {
    const selected = aeSceneEffectSelection(requested)
    if (selected === undefined) return true
    const actual = plan?.effects ?? []
    return Array.isArray(actual) && actual.length === selected.length
        && JSON.stringify(actual.map((e: any) => e?.type).sort()) === JSON.stringify(selected)
}
