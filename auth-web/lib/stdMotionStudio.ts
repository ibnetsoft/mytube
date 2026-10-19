import { AE_SCENE_EFFECTS } from './stdAeSceneEffects'

export type MotionKey = { t: number; x: number; y: number; scale: number; rotation: number; opacity: number }
export type MotionEffect = { type: string; start: number; end: number; intensity: number; center: [number, number]; radius: number; color: [number, number, number] }
export type MotionLayer = { depth:number; keys:MotionKey[] }
export type MotionScene = { source: 'auto' | 'image' | 'video' | 'psd'; fit: 'contain' | 'cover'; direction: string; keys: MotionKey[]; effects: MotionEffect[]; transition: 'cut' | 'fade' | 'flash'; layers?:Record<string,MotionLayer> }
export type MotionDraft = { version: 1; enabled: boolean; aspect: '16:9' | '9:16'; fps: 24 | 30; scenes: Record<string, MotionScene> }
export const MOTION_PRESETS = [
    { id: 'still', label: '원본 유지', effects: [] },
    { id: 'push', label: '카메라 접근', effects: [] },
    { id: 'impact', label: '전투 타격', effects: ['impact_shake', 'impact_flash', 'shock_ring', 'speedline_burst'] },
    { id: 'aura', label: '검기·오라', effects: ['focus_glow', 'energy_trail', 'particle_burst'] },
    { id: 'debris', label: '충돌·파편', effects: ['impact_flash', 'debris_burst', 'shock_ring'] },
    { id: 'light', label: '분위기·빛', effects: ['atmospheric_haze', 'warm_dust_motes', 'light_sweep', 'subtle_vignette'] },
] as const
function finite(value: unknown, lo: number, hi: number, label: string) {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < lo || value > hi) throw new Error(`Motion Studio ${label}: ${lo}~${hi} 범위를 확인해 주세요.`)
    return value
}
export const motionKey = (t: number): MotionKey => ({ t, x: .5, y: .5, scale: 1, rotation: 0, opacity: 100 })
export const motionScene = (): MotionScene => ({ source: 'auto', fit: 'contain', direction: '', keys: [motionKey(0), motionKey(1)], effects: [], transition: 'cut' })
export function motionPreset(id: string, previous = motionScene()): MotionScene {
    const preset = MOTION_PRESETS.find(p => p.id === id) || MOTION_PRESETS[0]
    return { ...previous, keys: [motionKey(0), { ...motionKey(1), scale: id === 'still' ? 1 : 1.08 }],
        effects: preset.effects.map(type => ({ type, start: id === 'light' ? 0 : .35, end: id === 'light' ? 1 : .7, intensity: .45, center: [.5, .5], radius: .35, color: [1, .8, .4] })) }
}
export function normalizeMotionDraft(raw: any): MotionDraft {
    if (!raw || raw.version !== 1 || typeof raw.enabled !== 'boolean' || !['16:9', '9:16'].includes(raw.aspect) || ![24, 30].includes(raw.fps)) throw new Error('Motion Studio 프로젝트 설정을 확인해 주세요.')
    if (!raw.scenes || typeof raw.scenes !== 'object' || Array.isArray(raw.scenes) || Object.keys(raw.scenes).length > 1000) throw new Error('Motion Studio 씬 목록을 확인해 주세요.')
    const scenes: MotionDraft['scenes'] = {}
    for (const [number, value] of Object.entries(raw.scenes)) {
        const s = value as any
        if (!/^[1-9]\d*$/.test(number) || !s || !['auto','image','video','psd'].includes(s.source) || !['cover','contain'].includes(s.fit) || !['cut','fade','flash'].includes(s.transition)) throw new Error('Motion Studio 씬의 소스·전환을 확인해 주세요.')
        if (typeof s.direction !== 'string' || s.direction.length > 4000 || !Array.isArray(s.keys) || s.keys.length < 2 || s.keys.length > 64) throw new Error('씬 연출과 키프레임을 확인해 주세요.')
        const keys: MotionKey[] = s.keys.map((k: any) => ({ t: finite(k.t,0,1,'시간'), x: finite(k.x,0,1,'X'), y: finite(k.y,0,1,'Y'), scale: finite(k.scale,1,2,'확대'), rotation: finite(k.rotation,-8,8,'회전'), opacity: finite(k.opacity,0,100,'불투명도') }))
        if (keys[0].t !== 0 || keys[keys.length-1].t !== 1 || keys.some((k,i) => i > 0 && k.t <= keys[i-1].t)) throw new Error('키프레임은 0~100%를 순서대로 포함해야 합니다.')
        if (!Array.isArray(s.effects) || s.effects.length > AE_SCENE_EFFECTS.length) throw new Error('씬 효과 목록을 확인해 주세요.')
        const effects: MotionEffect[] = s.effects.map((e: any) => {
            if (!AE_SCENE_EFFECTS.some(item => item.id === e.type) || e.type === 'heat_distortion') throw new Error('열 왜곡은 분리된 PSD의 AE 준비 화면에서 선택해 주세요.')
            const start=finite(e.start,0,1,'효과 시작'), end=finite(e.end,0,1,'효과 종료')
            if (end <= start || !Array.isArray(e.center) || e.center.length !== 2 || !Array.isArray(e.color) || e.color.length !== 3) throw new Error('효과 위치·시간·색상을 확인해 주세요.')
            return { type:e.type, start,end,intensity:finite(e.intensity,.05,1,'효과 강도'),center:e.center.map((v:number)=>finite(v,0,1,'효과 위치')) as [number,number],radius:finite(e.radius,.02,1,'효과 반경'),color:e.color.map((v:number)=>finite(v,0,1,'색상')) as [number,number,number] }
        })
        if (new Set(effects.map(e=>e.type)).size !== effects.length) throw new Error('같은 효과를 중복 선택할 수 없습니다.')
        const layers:Record<string,MotionLayer>={}
        if(s.layers!==undefined){
            if(!s.layers||typeof s.layers!=='object'||Array.isArray(s.layers)||Object.keys(s.layers).length>80||s.source!=='psd')throw new Error('레이어 키프레임은 PSD 씬에서만 사용할 수 있습니다.')
            for(const [id,value] of Object.entries(s.layers)){
                const layer=value as any
                if(!/^[A-Za-z0-9_-]{1,80}$/.test(id)||!layer||!Array.isArray(layer.keys)||layer.keys.length<2||layer.keys.length>64)throw new Error('PSD 레이어 설정을 확인해 주세요.')
                const layerKeys:MotionKey[]=layer.keys.map((k:any)=>({t:finite(k.t,0,1,'레이어 시간'),x:finite(k.x,.45,.55,'레이어 X'),y:finite(k.y,.45,.55,'레이어 Y'),scale:finite(k.scale,.9,1.1,'레이어 확대'),rotation:finite(k.rotation,-8,8,'레이어 회전'),opacity:finite(k.opacity,0,100,'레이어 불투명도')}))
                if(layerKeys[0].t!==0||layerKeys[layerKeys.length-1].t!==1||layerKeys.some((k,i)=>i>0&&k.t<=layerKeys[i-1].t))throw new Error('PSD 레이어 키프레임 시간을 확인해 주세요.')
                layers[id]={depth:finite(layer.depth,0,1,'레이어 깊이'),keys:layerKeys}
            }
        }
        scenes[number]={source:s.source,fit:s.fit,direction:s.direction,transition:s.transition,keys,effects,...(s.layers!==undefined?{layers}:{})}
    }
    return {version:1,enabled:raw.enabled,aspect:raw.aspect,fps:raw.fps,scenes}
}
export function motionForProject(project: any): MotionDraft | null {
    const raw=project?.project_payload?.render_settings?.motion
    return raw == null ? null : normalizeMotionDraft(raw)
}
export function motionOutputAspect(project: any, fallback: '16:9'|'9:16' = '16:9') {
    const motion=motionForProject(project)
    return motion?.enabled ? motion.aspect : fallback
}
export function interpolateMotion(keys: MotionKey[], t: number): MotionKey {
    const right=keys.findIndex(k=>k.t >= t), b=keys[Math.max(0,right)], a=keys[Math.max(0,right-1)]
    if (right < 0) return keys[keys.length-1]
    const f=b.t===a.t ? 0 : (t-a.t)/(b.t-a.t)
    return Object.fromEntries(Object.keys(a).map(k=>[k,a[k as keyof MotionKey]+(b[k as keyof MotionKey]-a[k as keyof MotionKey])*f])) as MotionKey
}
