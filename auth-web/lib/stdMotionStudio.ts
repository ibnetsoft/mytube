import {normalizeDirectionCues,type DirectionCue} from './stdWebtoonDirection'
import {normalizeFinanceMotion,type FinanceMotion} from './stdFinanceMotion'
import {normalizeWebTimeline,type MotionClip} from './stdMotionTimeline'
import { AE_SCENE_EFFECTS } from './stdAeSceneEffects'
import {normalizeLayerAdvanced,normalizeNativeScene,type LayerAdvanced,type NativeScene} from './stdMotionRig'

export type MotionKey = { t: number; x: number; y: number; scale: number; rotation: number; opacity: number }
export type MotionEffect = { type: string; start: number; end: number; intensity: number; center: [number, number]; radius: number; color: [number, number, number] }
export type MotionLayer = { depth:number; keys:MotionKey[]; advanced?:LayerAdvanced }
export type MotionScene = { finance?:FinanceMotion; cues?:DirectionCue[]; source: 'auto' | 'image' | 'video' | 'psd'; fit: 'contain' | 'cover'; direction: string; keys: MotionKey[]; effects: MotionEffect[]; transition: 'cut' | 'fade' | 'flash'; layers?:Record<string,MotionLayer>;native?:NativeScene }
export type MotionAutomation = { mode: 'ae_only' | 'hybrid'; max_ai_clips: number; max_ai_seconds: number }
export type WebMotionInsert = { job_id:string; start:number; duration:number }
export type ProductionMethod = 'ae'|'motion_studio'|'effectcraft'|'filmcraft'
type MotionConfig = { version: 1; enabled: boolean; aspect: '16:9' | '9:16'; fps: 24 | 30; scenes: Record<string, MotionScene>; automation?: MotionAutomation; web?:{timeline?:MotionClip[];mode:'web'|'hybrid';inserts:Record<string,WebMotionInsert>} }
export type FinalRenderer = 'python'|'filmcraft'
export type MotionDraft = MotionConfig & {final_renderer?:FinalRenderer; edit_mode?:'horizontal_webtoon'; webtoon_baseline?:MotionDraft; production_method?:ProductionMethod; alternatives?:Partial<Record<ProductionMethod,MotionConfig>>}

export function switchHorizontalWebtoon(previous:MotionDraft,enabled:boolean):MotionDraft {
    if(!enabled)return normalizeMotionDraft(previous.webtoon_baseline?{...previous.webtoon_baseline,alternatives:previous.alternatives}:{...previous,edit_mode:undefined})
    const {alternatives:_,webtoon_baseline:__,edit_mode:___,...baseline}=previous
    const active=switchMotionProduction(previous,'ae')
    return normalizeMotionDraft({...active,edit_mode:'horizontal_webtoon',webtoon_baseline:previous.webtoon_baseline||baseline,enabled:true,production_method:'ae',aspect:'16:9',automation:{mode:'ae_only',max_ai_clips:1,max_ai_seconds:5}})
}

export function motionProductionMethod(project:any):ProductionMethod {
    const raw=project?.project_payload?.render_settings?.motion
    return raw?.production_method==='filmcraft'?'filmcraft':raw?.production_method==='effectcraft'?'effectcraft':raw?.production_method==='ae'?'ae':raw?.production_method==='motion_studio'||raw?.web?'motion_studio':'ae'
}
export function finalRenderMethod(project:any):FinalRenderer {
    return project?.project_payload?.render_settings?.motion?.final_renderer==='filmcraft'?'filmcraft':'python'
}
export function defaultMotionDraft(raw:any,aspect:'16:9'|'9:16'='16:9'):MotionDraft {
    return raw?normalizeMotionDraft(raw):{version:1,enabled:false,aspect,fps:24,scenes:{}}
}
export function switchMotionProduction(draft:MotionDraft,method:ProductionMethod):MotionDraft {
    draft=defaultMotionDraft(draft)
    const current=motionProductionMethod({project_payload:{render_settings:{motion:draft}}})
    if(current===method)return normalizeMotionDraft({...draft,production_method:method})
    const {production_method:_,alternatives:previous,final_renderer,...active}=draft
    const alternatives={...previous,[current]:active}
    const target=alternatives[method]||{version:1,enabled:method!=='ae',aspect:draft.aspect,fps:draft.fps,scenes:{},...(method==='motion_studio'?{web:{mode:'web',inserts:{}}}:(method==='effectcraft'||method==='filmcraft')?{automation:{mode:'ae_only',max_ai_clips:1,max_ai_seconds:5}}:{})}
    return normalizeMotionDraft({...target,...(method==='ae'&&draft.edit_mode?{edit_mode:draft.edit_mode}:{}),production_method:method,alternatives,...(method==='ae'?{final_renderer:'python'}:final_renderer?{final_renderer}:{})})
}
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
            if(e.type==='fireflies')throw new Error('반딧불은 제출 영상의 대본·실제 화면을 확인한 후작업에서 적용합니다.')
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
                layers[id]={depth:finite(layer.depth,0,1,'레이어 깊이'),keys:layerKeys,...(layer.advanced!==undefined?{advanced:normalizeLayerAdvanced(layer.advanced)}:{})}
            }
        }
        scenes[number]={...(s.cues!==undefined?{cues:normalizeDirectionCues(s.cues)}:{}),...(s.finance!==undefined?{finance:normalizeFinanceMotion(s.finance)}:{}),source:s.source,fit:s.fit,direction:s.direction,transition:s.transition,keys,effects,...(s.layers!==undefined?{layers}:{}),...(s.native!==undefined?{native:normalizeNativeScene(s.native)}:{})}
    }
    let automation: MotionAutomation | undefined
    if (raw.automation != null) {
        const a=raw.automation
        if (!['ae_only','hybrid'].includes(a.mode) || !Number.isInteger(a.max_ai_clips) || a.max_ai_clips<1 || a.max_ai_clips>3 || ![3,4,5].includes(a.max_ai_seconds)) throw new Error('자동 제작 모드와 AI 구간 한도를 확인해 주세요.')
        automation={mode:a.mode,max_ai_clips:a.max_ai_clips,max_ai_seconds:a.max_ai_seconds}
    }
    let web:MotionDraft['web']
    if(raw.web!==undefined){
        if(!raw.web||!['web','hybrid'].includes(raw.web.mode)||!raw.web.inserts||typeof raw.web.inserts!=='object'||Array.isArray(raw.web.inserts)||Object.keys(raw.web.inserts).length>1000)throw new Error('웹 모션 혼합 설정을 확인해 주세요.')
        const inserts:Record<string,WebMotionInsert>={}
        for(const [number,value] of Object.entries(raw.web.inserts)){const insert=value as any
            if(!/^[1-9]\d*$/.test(number)||!insert||typeof insert.job_id!=='string'||!/^[a-f0-9-]{36}$/.test(insert.job_id)||![3,4,5].includes(insert.duration))throw new Error('AI 혼합 구간을 확인해 주세요.')
            inserts[number]={job_id:insert.job_id,start:finite(insert.start,0,86400,'AI 시작'),duration:insert.duration}
        }
        web={mode:raw.web.mode,inserts,...(raw.web.timeline!==undefined?{timeline:normalizeWebTimeline(raw.web.timeline)}:{})}
    }
    if(raw.final_renderer!==undefined&&!['python','filmcraft'].includes(raw.final_renderer))throw new Error('최종 렌더러를 확인해 주세요.')
    if(raw.production_method!==undefined&&!['ae','motion_studio','effectcraft','filmcraft'].includes(raw.production_method))throw new Error('제작 방식을 확인해 주세요.')
    let alternatives:MotionDraft['alternatives']
    if(raw.alternatives!==undefined){
        if(!raw.alternatives||typeof raw.alternatives!=='object'||Array.isArray(raw.alternatives)||Object.keys(raw.alternatives).some(k=>!['ae','motion_studio','effectcraft','filmcraft'].includes(k)))throw new Error('제작 방식별 설정을 확인해 주세요.')
        alternatives={}
        for(const method of ['ae','motion_studio','effectcraft','filmcraft'] as const){const config=raw.alternatives[method];if(config===undefined)continue
            if(config.alternatives!==undefined||config.production_method!==undefined||config.final_renderer!==undefined)throw new Error('제작 설정을 중첩할 수 없습니다.')
            alternatives[method]=normalizeMotionDraft(config)
        }
    }
    if(raw.edit_mode!==undefined && raw.edit_mode!=='horizontal_webtoon')throw new Error('연출 모드를 확인해 주세요.')
    let webtoon_baseline:MotionDraft|undefined
    if(raw.webtoon_baseline!==undefined){
        if(!raw.webtoon_baseline||raw.webtoon_baseline.webtoon_baseline!==undefined||raw.webtoon_baseline.alternatives!==undefined||raw.webtoon_baseline.edit_mode!==undefined)throw new Error('웹툰 이전 제작 설정을 확인해 주세요.')
        webtoon_baseline=normalizeMotionDraft(raw.webtoon_baseline)
    }
    if(raw.edit_mode && (raw.aspect!=='16:9'||raw.web||raw.production_method==='effectcraft'||raw.production_method==='motion_studio'||!automation||automation.mode!=='ae_only'))throw new Error('가로 웹툰 컷 모드는 가로 16:9·AE·영상 생성 미사용으로 저장해 주세요.')
    return {...(raw.final_renderer?{final_renderer:raw.final_renderer}:{}),version:1,enabled:raw.enabled,aspect:raw.aspect,fps:raw.fps,scenes,...(raw.edit_mode?{edit_mode:raw.edit_mode}:{}),...(webtoon_baseline?{webtoon_baseline}:{}),...(automation?{automation}:{}),...(web?{web}:{}),...(raw.production_method?{production_method:raw.production_method}:{}),...(alternatives?{alternatives}:{})}
}
export function motionForProject(project: any): MotionDraft | null {
    const raw=project?.project_payload?.render_settings?.motion
    return raw==null?null:normalizeMotionDraft(raw)
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
