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
        if (points.some(p=>p[0]<0||p[0]>1920||p[1]<0||p[1]>1080) || excluded.some(b=>intersects(bounds,b))) return false
        result.push({kind:'polygon',points,color,opacity:Math.min(1,Math.max(0,opacity)),stroke:0})
        return true
    }
    const ribbon = (a: number[], b: number[], width: number, color: string, opacity: number) => {
        const len=Math.hypot(b[0]-a[0],b[1]-a[1]); if(len<.01)return false
        const nx=-(b[1]-a[1])/len*width/2,ny=(b[0]-a[0])/len*width/2
        return add([[a[0]+nx,a[1]+ny],[b[0]+nx,b[1]+ny],[b[0]-nx,b[1]-ny],[a[0]-nx,a[1]-ny]],color,opacity)
    }
    if(e.type==='contact_flash') {
        // A brief exposure wash must never cut rectangular holes around faces.
        // Keep the entire picture readable; opaque electrical cores stay excluded.
        if(e.flash_scope==='screen') {
            result.push({kind:'polygon',points:[[0,0],[1920,0],[1920,1080],[0,1080]],color:'#fff7cf',opacity:(1-t)*strength*.22,stroke:0})
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
    // Continuous tapered silhouettes, rather than disconnected constant-width bars.
    // Several low-opacity contours approximate a soft bloom identically in SVG/AE.
    const phase=Math.floor(elapsedFrame/Math.max(1,Math.round(fps/16)))
    const noise=(i:number)=>{const n=Math.sin((i+1)*127.1+phase*311.7)*43758.5453;return(n-Math.floor(n))*2-1}
    const growth=Math.min(1,(elapsedFrame+1)/Math.max(1,fps*.09)),fade=Math.pow(1-t, .7)*strength
    const heading=Math.atan2(cy-path[path.length-2][1],cx-path[path.length-2][0])
    const silhouette=(points:number[][],widths:number[],expand:number)=>{
        const left:number[][]=[],right:number[][]=[]
        for(let i=0;i<points.length;i++){
            const before=points[Math.max(0,i-1)],after=points[Math.min(points.length-1,i+1)]
            const len=Math.hypot(after[0]-before[0],after[1]-before[1])||1
            const nx=-(after[1]-before[1])/len,ny=(after[0]-before[0])/len
            const w=widths[i]+expand*Math.pow(1-i/(points.length-1),.35)
            left.push([points[i][0]+nx*w,points[i][1]+ny*w]);right.push([points[i][0]-nx*w,points[i][1]-ny*w])
        }
        return [...left,...right.reverse()]
    }
    const draw=(points:number[][],widths:number[],opacity:number)=>{
        if(points.length<3)return
        // Bloom has no opaque yellow outer band. The pale hot core carries the shape.
        for(const [spread,alpha] of [[17,.025],[11,.045],[7,.075],[3.5,.13],[1,.38],[0,.94]])
            add(silhouette(points,widths,spread),spread===0?'#ffffff':'#fff000',opacity*alpha)
    }
    for(let bolt=0;bolt<6;bolt++) {
        const angle=heading+(bolt-2.5)*.91+noise(bolt)*.36
        const reach=e.radius*1080*growth*(.48+.48*Math.abs(noise(bolt+8)))
        const points:number[][]=[[cx,cy]],widths=[(2.5+Math.abs(noise(bolt+2))*2.5)*strength]
        let distance=0
        for(let segment=1;segment<=11;segment++){
            distance+=.055+.055*(noise(bolt*19+segment)+1)/2
            const u=Math.min(1,distance),side=noise(bolt*31+segment)*reach*(.015+.10*u)
            const next=[cx+Math.cos(angle)*reach*u-Math.sin(angle)*side,cy+Math.sin(angle)*reach*u+Math.cos(angle)*side]
            const previous=points[points.length-1]
            const bounds=[Math.min(previous[0],next[0])-20,Math.min(previous[1],next[1])-20,Math.max(previous[0],next[0])+20,Math.max(previous[1],next[1])+20]
            if(next[0]<22||next[0]>1898||next[1]<22||next[1]>1058||excluded.some(b=>intersects(bounds,b)))break
            points.push(next);widths.push(Math.max(.12,(1-u)*(.55+Math.abs(noise(segment+bolt*13))*3.4))*strength)
            if(u===1)break
        }
        if(points.length<3)continue
        widths[widths.length-1]=0
        draw(points,widths,fade)
        // Fine curving offshoot, distinct from the main jagged discharge.
        const k=Math.min(points.length-2,3+bolt%3),origin=points[k],twig:number[][]=[origin],tw:number[]=[.9*strength]
        for(let j=1;j<=5;j++){
            const u=j/5,turn=angle+(bolt%2?1:-1)*(.6+u*.6),len=reach*.27*u
            twig.push([origin[0]+Math.cos(turn)*len,origin[1]+Math.sin(turn)*len]);tw.push((1-u)*.75*strength)
        }
        draw(twig,tw,fade*.65)
    }
    return result
}
