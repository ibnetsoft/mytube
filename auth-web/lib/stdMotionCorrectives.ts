import type {Matrix,MotionRig,Point,SkinInfluence} from './stdMotionRig'

/** Authored bind-space pose driven by the solved local joint angle, including IK. */
export type JointCorrective = {bone:number;angle:number;center:Point;radius:Point;scale:Point;offset:Point;strength:number}
export type SkinRegion = {bone:number;min:Point;max:Point;feather:number}

/** Later regions override earlier ones. Bind (-1) protects other characters;
 * a head-bone region preserves the face while following the torso hierarchy. */
export function regionInfluences(influences:SkinInfluence[],regions:SkinRegion[]|undefined,x:number,y:number):SkinInfluence[]{
    if(!regions?.length)return influences
    const weights=new Map(influences.map(v=>[v.bone,v.weight]))
    for(const region of regions){
        const d=Math.min(x-region.min[0],region.max[0]-x,y-region.min[1],region.max[1]-y)
        if(d<0)continue
        const u=region.feather?Math.min(1,d/region.feather):1,k=u*u*(3-2*u)
        for(const [bone,weight] of weights)weights.set(bone,weight*(1-k))
        weights.set(region.bone,(weights.get(region.bone)||0)+k)
    }
    return [...weights].filter(([,weight])=>weight>1e-12).map(([bone,weight])=>({bone,weight}))
}

export function correctiveActivation(pose:JointCorrective,rig:MotionRig,matrices:Matrix[]):number {
    const m=matrices[pose.bone],parent=rig.bones[pose.bone].parent
    const parentAngle=parent<0?0:Math.atan2(matrices[parent][1],matrices[parent][0])
    const angle=Math.atan2(Math.sin(Math.atan2(m[1],m[0])-parentAngle),Math.cos(Math.atan2(m[1],m[0])-parentAngle))*180/Math.PI
    const u=Math.max(0,Math.min(1,angle/pose.angle))
    return u*u*(3-2*u)*pose.strength
}

export function correctJointPoint(p:Point,rig:MotionRig,matrices:Matrix[],influences:SkinInfluence[],w:number,h:number):Point {
    let x=p[0],y=p[1]
    for(const pose of rig.correctives||[]){
        const dx=p[0]/w-pose.center[0],dy=p[1]/h-pose.center[1],r2=(dx/pose.radius[0])**2+(dy/pose.radius[1])**2
        if(r2>=1)continue
        const parent=rig.bones[pose.bone].parent
        const ownership=influences.reduce((sum,v)=>sum+(v.bone===pose.bone||(parent>=0&&v.bone===parent)?v.weight:0),0)
        const k=(1-r2)**2*ownership*correctiveActivation(pose,rig,matrices)
        x+=(dx*(pose.scale[0]-1)+pose.offset[0])*w*k
        y+=(dy*(pose.scale[1]-1)+pose.offset[1])*h*k
    }
    return [x,y]
}
