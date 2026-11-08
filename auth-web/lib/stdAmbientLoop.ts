/** Optional, prepared PNG patches. Never play a GIF with a wall-clock <img>. */
export const AMBIENT_LOOP_CONTRACT = 'ambient_loop/v1'
export type AmbientLoop = {
    contract: typeof AMBIENT_LOOP_CONTRACT; enabled: boolean; source_sha256: string;
    role: 'background' | 'hair' | 'cloth' | 'environment';
    width: number; height: number;
    region: number[]; protected_regions: number[][];
    start_ms: number; end_ms: number; phase_ms: number; repeat: boolean;
    frames: { media_url: string; sha256: string; duration_ms: number; gcs_bucket: string; gcs_path: string }[];
    attack_sprite?: {contract:'wuxia_attack_sprite/v1';source_sha256:string;source_reviewed:boolean;frames_reviewed:boolean;event:string;reason:string;contact_ms:number;protected_boxes:number[][]};
    sword_aura?: {contract:'wuxia_sword_aura/v1';source_sha256:string;source_reviewed:boolean;clean_plate_sha256:string;reason:string;amplitude_px:number;protected_polygons:number[][][]};
}
const sha = (v: any) => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v)
const number = (v: any, min: number, max: number) => typeof v === 'number' && Number.isFinite(v) && v >= min && v <= max
const rect = (r: any): r is number[] => Array.isArray(r) && r.length === 4 && r.every(v => number(v, 0, 1)) && r[0] < r[2] && r[1] < r[3]
export function validAmbientLoop(v: any): v is AmbientLoop {
    if (!v || v.contract !== AMBIENT_LOOP_CONTRACT || typeof v.enabled !== 'boolean' || !sha(v.source_sha256)
        || !Number.isInteger(v.width) || !Number.isInteger(v.height) || !number(v.width,1,8192) || !number(v.height,1,8192) || v.width*v.height>16000000
        || !['background', 'hair', 'cloth', 'environment'].includes(v.role) || !rect(v.region)
        || (v.region[2]-v.region[0])*(v.region[3]-v.region[1]) > .35
        || !Array.isArray(v.protected_regions) || v.protected_regions.length > 100
        || !v.protected_regions.every((r: any) => rect(r) && !(v.region[0]<r[2] && v.region[2]>r[0] && v.region[1]<r[3] && v.region[3]>r[1]))
        || !number(v.start_ms, 0, 3600000) || !number(v.end_ms, v.start_ms+1, 3600000)
        || !number(v.phase_ms, 0, 3600000) || typeof v.repeat !== 'boolean'
        || !Array.isArray(v.frames) || v.frames.length < 2 || v.frames.length > 16) return false
    const sprite=v.attack_sprite
    if(sprite&&(sprite.contract!=='wuxia_attack_sprite/v1'||sprite.source_sha256!==v.source_sha256||sprite.source_reviewed!==true||sprite.frames_reviewed!==true
        ||!['event','reason'].every(k=>typeof sprite[k]==='string'&&sprite[k].trim())||!number(sprite.contact_ms,0,v.start_ms)
        ||v.end_ms-v.start_ms>600||v.repeat!==false||!Array.isArray(sprite.protected_boxes)||sprite.protected_boxes.length>100||!sprite.protected_boxes.every(rect)))return false
    const a=v.sword_aura
    if(a && (a.contract!=='wuxia_sword_aura/v1'||a.source_reviewed!==true||a.source_sha256!==v.source_sha256||!sha(a.clean_plate_sha256)
        ||typeof a.reason!=='string'||!a.reason.trim()||!number(a.amplitude_px,.001,16)||!Array.isArray(a.protected_polygons)||!a.protected_polygons.length
        ||!a.protected_polygons.every((p:any)=>Array.isArray(p)&&p.length>=3&&p.every((xy:any)=>Array.isArray(xy)&&xy.length===2&&xy.every((x:any)=>number(x,0,1))))))return false
    return v.frames.every((f: any) => sha(f.sha256) && Number.isInteger(f.duration_ms) && number(f.duration_ms, 20, 2000)
        && typeof f.media_url === 'string' && /^(https:\/\/|\/api\/std\/)/.test(f.media_url)
        && typeof f.gcs_bucket === 'string' && !!f.gcs_bucket && typeof f.gcs_path === 'string' && !!f.gcs_path)
}
/** Half-open windows, integer milliseconds; identical to the native worker. */
export function ambientFrameIndex(loop: AmbientLoop, localMs: number): number | null {
    if (!validAmbientLoop(loop) || !loop.enabled || !Number.isFinite(localMs)) return null
    const ms = Math.floor(localMs + 1e-6)
    if (ms < loop.start_ms || ms >= loop.end_ms) return null
    const total = loop.frames.reduce((sum, f) => sum + f.duration_ms, 0)
    let at = ms - loop.start_ms + loop.phase_ms
    at = loop.repeat ? at % total : Math.min(at, total - 1)
    for (let i=0; i<loop.frames.length; i++) { if (at < loop.frames[i].duration_ms) return i; at -= loop.frames[i].duration_ms }
    return null
}
export function ambientLoopsForState(state: any): AmbientLoop[] {
    return (Array.isArray(state?.ambient_loops) ? state.ambient_loops : []).filter((v: any) => validAmbientLoop(v) && v.source_sha256 === state.sha256)
}
export function hasAmbientLoops(project: any): boolean {
    return Boolean(project.project_payload?.structure?.wuxia_ae_package?.scenes?.some((s: any) =>
        s.states?.some((state: any) => state.ambient_loops?.some((loop: any) => loop.enabled !== false))))
}
/** Freeze against the chosen actual source. Unsupported renderers must never silently discard motion. */
export function freezeAmbientLoops(project: any, sceneNumber: number, source: any): AmbientLoop[] {
    const pkg = project.project_payload?.structure?.wuxia_ae_package
    const scene = pkg?.scenes?.find((s: any) => Number(String(s.scene_id).match(/S(\d+)$/)?.[1]) === sceneNumber)
    const hash = source.metadata?.sha256
    const states = (scene?.states || []).filter((s: any) => s.ambient_loops?.some((l: any) => l.enabled !== false))
    if (states.some((s: any) => s.sha256 !== hash)) throw Error(`${sceneNumber}번 씬의 보조 움직임 원화와 제출 원화가 다릅니다. 상태별 원화를 먼저 일치시켜 주세요.`)
    const raw = states.length ? states.flatMap((s: any) => s.ambient_loops || []) : source.metadata?.ambient_loops || []
    if (!Array.isArray(raw) || raw.length > 4 || raw.some((v: any) => !validAmbientLoop(v) || v.source_sha256 !== hash)) throw Error(`${sceneNumber}번 씬의 보조 움직임 패키지·원화 체크섬을 확인해 주세요.`)
    return raw.filter((v: AmbientLoop) => v.enabled)
}
