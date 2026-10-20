import type {Point,Matrix,SkinInfluence} from './stdMotionRig'
/** Planar dual-quaternion blend: normalized rotation avoids LBS joint collapse.
 * Bone transforms are rigid (rotation/translation), so this preserves local
 * thickness for equal weights. It cannot prevent all skin folds/occlusions. */
export function blendRigidPoint(p:Point,matrices:Matrix[],influences:SkinInfluence[]):Point {
 if(!influences.length)return [...p]
 const strongest=influences.reduce((a,b)=>a.weight>=b.weight?a:b),reference=strongest.bone<0?[1,0,0,1,0,0]:matrices[strongest.bone],angle=Math.atan2(reference[1],reference[0])/2,rw=Math.cos(angle),rz=Math.sin(angle)
 let w=0,z=0,dx=0,dy=0
 for(const item of influences){if(item.weight<=0)continue;const m=item.bone<0?[1,0,0,1,0,0]:matrices[item.bone],half=Math.atan2(m[1],m[0])/2,qw=Math.cos(half),qz=Math.sin(half),sign=qw*rw+qz*rz<0?-1:1,k=item.weight*sign;w+=qw*k;z+=qz*k;dx+=(m[4]*qw+m[5]*qz)*.5*k;dy+=(m[5]*qw-m[4]*qz)*.5*k}
 const length=Math.hypot(w,z);if(length<1e-10)return [reference[0]*p[0]+reference[2]*p[1]+reference[4],reference[1]*p[0]+reference[3]*p[1]+reference[5]]
 w/=length;z/=length;dx/=length;dy/=length;const c=w*w-z*z,s=2*w*z
 return [c*p[0]-s*p[1]+2*(dx*w-dy*z),s*p[0]+c*p[1]+2*(dy*w+dx*z)]
}
