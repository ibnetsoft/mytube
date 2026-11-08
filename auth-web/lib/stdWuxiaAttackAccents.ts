/** Reviewed action accents, sampled once by the editor and consumed verbatim by AE. */
export const ATTACK_ACCENT_CONTRACT = 'wuxia_attack_accent/v1'
export const ATTACK_ACCENT_TYPES = new Set(['electric_discharge', 'attack_speedline', 'contact_flash'])
const number = (v: any) => typeof v === 'number' && Number.isFinite(v)
const point = (p: any) => Array.isArray(p) && p.length === 2 && p.every(v => number(v) && v >= 0 && v <= 1)
const box = (b: any) => Array.isArray(b) && b.length === 4 && b.every(v => number(v) && v >= 0 && v <= 1) && b[0] < b[2] && b[1] < b[3]
export function attackAccentReviewError(e: any, state: any): string | null {
    const r = e.action_review
    if (!r || r.contract !== ATTACK_ACCENT_CONTRACT || r.source_sha256 !== state.sha256 || !/^[a-f0-9]{64}$/.test(state.sha256 || '') || r.source_reviewed !== true) return 'source_review'
    if (['event','materials','reason','motion_evidence'].some(k => typeof r[k] !== 'string' || !r[k].trim())) return 'event_review'
    if (!Array.isArray(state.face_exclusion_boxes) || state.face_exclusion_boxes.length>32 || !state.face_exclusion_boxes.every(box)) return 'head_review'
    if (!Array.isArray(r.protected_boxes) || r.protected_boxes.length > 16 || !r.protected_boxes.every(box)) return 'protection_review'
    if (!Array.isArray(e.attack_path) || e.attack_path.length < 2 || e.attack_path.length > 4 || !e.attack_path.every(point)) return 'attack_path'
    const p = e.attack_path
    if (Math.hypot((p[p.length-1][0]-p[0][0])*1920,(p[p.length-1][1]-p[0][1])*1080)<8) return 'attack_path'
    if (p.slice(1).some((q: number[], i: number) => Math.hypot((q[0]-p[i][0])*1920,(q[1]-p[i][1])*1080) < 8)) return 'attack_path'
    if (Math.hypot(p[p.length-1][0]-e.center[0],p[p.length-1][1]-e.center[1]) > .02) return 'contact_point'
    if (r.timing_basis === 'voice_anchor') {
        if (!e.voice_binding?.exact_anchor || !e.quote || e.contact_at_seconds != null) return 'contact_timing'
    } else if (r.timing_basis !== 'scene_local' || !number(e.contact_at_seconds) || e.contact_at_seconds < 0 || e.voice_binding) return 'contact_timing'
    if (e.type === 'electric_discharge' && r.electricity_motivated !== true) return 'electricity_review'
    const max = e.type === 'contact_flash' ? .125 : e.type === 'attack_speedline' ? .35 : .6
    if (e.duration_seconds > max || (e.type === 'contact_flash' && e.flash_scope !== 'local' && e.flash_scope !== 'screen')) return 'duration_or_scope'
    if (e.flash_scope === 'screen' && r.screen_flash_reviewed !== true) return 'screen_flash_review'
    if (e.type === 'attack_speedline' && e.delay_seconds) return 'speedline_after_contact'
    return null
}

export function attackAccentShapes(e: any, t: number, elapsedFrame: number, fps: number, protectedBoxes: number[][]): any[] {
    const result: any[] = [], strength = e.intensity, cx = e.center[0]*1920, cy = e.center[1]*1080
    const excluded = [...protectedBoxes, ...e.action_review.protected_boxes].map(b => [b[0]*1920,b[1]*1080,b[2]*1920,b[3]*1080])
    const intersects = (a: number[], b: number[]) => a[0] < b[2] && a[2] > b[0] && a[1] < b[3] && a[3] > b[1]
    const add = (points: number[][], color: string, opacity: number) => {
        const bounds = [Math.min(...points.map(p=>p[0]))-2,Math.min(...points.map(p=>p[1]))-2,Math.max(...points.map(p=>p[0]))+2,Math.max(...points.map(p=>p[1]))+2]
        if (points.some(p=>p[0]<0||p[0]>1920||p[1]<0||p[1]>1080) || excluded.some(b=>intersects(bounds,b))) return
        result.push({kind:'polygon',points,color,opacity:Math.min(1,Math.max(0,opacity)),stroke:0})
    }
    const ribbon = (a: number[], b: number[], width: number, color: string, opacity: number) => {
        const len=Math.hypot(b[0]-a[0],b[1]-a[1]); if(len<.01)return
        const nx=-(b[1]-a[1])/len*width/2,ny=(b[0]-a[0])/len*width/2
        add([[a[0]+nx,a[1]+ny],[b[0]+nx,b[1]+ny],[b[0]-nx,b[1]-ny],[a[0]-nx,a[1]-ny]],color,opacity)
    }
    if(e.type==='contact_flash') {
        // One brief pulse, never a repeating full-screen strobe. Faces/text are cut out.
        if(e.flash_scope==='screen') {
            let rects=[[0,0,1920,1080]]
            for(const b of excluded) {
                const cut=[Math.max(0,b[0]-3),Math.max(0,b[1]-3),Math.min(1920,b[2]+3),Math.min(1080,b[3]+3)]
                rects=rects.flatMap(a=>{
                    if(!intersects(a,cut))return[a]
                    const x0=Math.max(a[0],cut[0]),y0=Math.max(a[1],cut[1]),x1=Math.min(a[2],cut[2]),y1=Math.min(a[3],cut[3])
                    return [[a[0],a[1],a[2],y0],[a[0],y1,a[2],a[3]],[a[0],y0,x0,y1],[x1,y0,a[2],y1]].filter(r=>r[2]>r[0]&&r[3]>r[1])
                })
                if(rects.length>64)return[]
            }
            for(const a of rects)result.push({kind:'polygon',points:[[a[0],a[1]],[a[2],a[1]],[a[2],a[3]],[a[0],a[3]]],color:'#fff000',opacity:(1-t)*strength*.95,stroke:0})
        } else {
            for(let i=0;i<8;i++) {
                const a=i*Math.PI/4,extent=e.radius*1080*(1-t*.4),w=14+30*strength
                ribbon([cx,cy],[cx+Math.cos(a)*extent,cy+Math.sin(a)*extent],w,'#fff000',(1-t)*strength)
                ribbon([cx,cy],[cx+Math.cos(a)*extent*.7,cy+Math.sin(a)*extent*.7],w*.35,'#ffffff',(1-t)*strength)
            }
        }
        return result
    }
    const path=e.attack_path.map((p:number[])=>[p[0]*1920,p[1]*1080])
    if(e.type==='attack_speedline') {
        const lengths=path.slice(1).map((p:number[],i:number)=>Math.hypot(p[0]-path[i][0],p[1]-path[i][1])),total=lengths.reduce((a:number,b:number)=>a+b,0)
        const at=(progress:number)=>{
            let distance=Math.max(0,Math.min(1,progress))*total
            for(let i=0;i<lengths.length;i++){if(distance<=lengths[i]||i===lengths.length-1){const u=distance/lengths[i];return[path[i][0]+(path[i+1][0]-path[i][0])*u,path[i][1]+(path[i+1][1]-path[i][1])*u]}distance-=lengths[i]}
            return path[path.length-1]
        }
        const tangent=[path[path.length-1][0]-path[0][0],path[path.length-1][1]-path[0][1]],len=Math.hypot(...tangent),normal=[-tangent[1]/len,tangent[0]/len]
        if(!Number.isFinite(len)||len<8)return[]
        for(let lane=0;lane<5;lane++) {
            const offset=(lane-2)*15,head=Math.min(1,t*1.25),tail=Math.max(0,head-.38)
            for(let i=0;i<4;i++) {
                const a=at(tail+(head-tail)*i/4),b=at(tail+(head-tail)*(i+1)/4)
                const shift=(p:number[])=>[p[0]+normal[0]*offset,p[1]+normal[1]*offset]
                ribbon(shift(a),shift(b),lane===2?16:3,lane===2?'#ffffff':'#fff000',strength*(1-t*.5))
            }
        }
        return result
    }
    // Seeded, frame-stepped branching. Growth originates at the reviewed contact point.
    const phase=Math.floor(elapsedFrame/Math.max(1,Math.round(fps/12)))
    const noise=(i:number)=>{const n=Math.sin((i+1)*127.1+phase*311.7)*43758.5453;return(n-Math.floor(n))*2-1}
    const growth=Math.min(1,(elapsedFrame+1)/Math.max(1,fps*.08)),fade=(1-t*.65)*strength
    const heading=Math.atan2(cy-path[path.length-2][1],cx-path[path.length-2][0])
    for(let bolt=0;bolt<5;bolt++) {
        const angle=heading+(bolt-2)*1.05+noise(bolt)*.24,reach=e.radius*1080*growth*(.7+.3*Math.abs(noise(bolt+5)))
        let previous=[cx,cy]
        for(let segment=1;segment<=5;segment++) {
            const u=segment/5,jitter=(noise(bolt*7+segment)*.22+(segment%2?.09:-.09))*reach*u
            const next=[cx+Math.cos(angle)*reach*u-Math.sin(angle)*jitter,cy+Math.sin(angle)*reach*u+Math.cos(angle)*jitter]
            ribbon(previous,next,96*strength*(1-u*.5),'#fff000',fade*.18)
            ribbon(previous,next,44*strength*(1-u*.5),'#fff000',fade*.95)
            ribbon(previous,next,12*strength*(1-u*.5),'#ffffff',fade)
            if(segment===3){const fork=[next[0]+Math.cos(angle+.9)*reach*.22,next[1]+Math.sin(angle+.9)*reach*.22];ribbon(next,fork,3,'#ffffff',fade*.9)}
            previous=next
        }
    }
    return result
}
