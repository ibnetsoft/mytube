/** Saved boxes are drafts until actual face/lip landmarks pass annotated crop QA. */
export function verifiedMouthGeometry(speaker: any, sourceSha: string): boolean {
    if (speaker?.status === 'offscreen') return true
    const g = speaker?.mouth_geometry
    if (g?.version !== 2 || g.source_sha256 !== sourceSha
        || g.review?.passed !== true || g.review?.proof !== 'annotated-face-crop-v4'
        || !g.review?.reason || !g.evidence) return false
    if (!['frontal','three_quarter_left','three_quarter_right','profile_left','profile_right'].includes(g.orientation)
        || !['level','up','down'].includes(g.pitch)) return false
    if (['partial','hidden'].includes(g.mouth_visibility)) return g.render_policy === 'preserve_original'
    if (g.mouth_visibility !== 'clear' || g.render_policy !== 'animate') return false
    const f = speaker.face_box, m = speaker.mouth_box, lm = g.landmarks
    const point = (p: any) => Array.isArray(p) && p.length === 2 && p.every((v: any) => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1)
    const inside = (p: number[], b: number[]) => p[0] >= b[0] && p[0] <= b[2] && p[1] >= b[1] && p[1] <= b[3]
    if (!Array.isArray(f) || f.length !== 4 || !Array.isArray(m) || m.length !== 4
        || !Array.isArray(g.face_outline) || g.face_outline.length < 5 || !g.face_outline.every(point)) return false
    for (const key of ['nose_tip','chin','lip_left','lip_right','lip_center']) if (!point(lm?.[key]) || !inside(lm[key],f)) return false
    for (const key of ['lip_left','lip_right','lip_center']) if (!inside(lm[key],m)) return false
    const [nx,ny] = lm.nose_tip, [cx,cy] = lm.chin, [x,y] = lm.lip_center
    const dx = cx-nx, dy = cy-ny, denominator = dx*dx+dy*dy
    if (denominator < .000025) return false
    const along = ((x-nx)*dx+(y-ny)*dy)/denominator
    return along >= .1 && along <= .95 && Math.abs((x-nx)*dy-(y-ny)*dx) <= denominator*.45
}
