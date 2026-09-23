"""Deterministic 3-D leaf mesh, hinged at the centre of a two-page spread.

Front: current right page. Back: next left page, with physical UV orientation.
The next right page is underneath. No AI generation or physics engine required.
"""
import math
import numpy as np


def leaf_mesh(progress, width, height, columns=36, rows=18):
    p=progress*progress*(3-2*progress)
    u,v=np.meshgrid(np.linspace(0,1,columns+1),np.linspace(0,1,rows+1))
    # Tip and bottom corner lead the turn; the spine (u=0) never moves.
    bend=math.sin(math.pi*p)
    angle=math.pi*p + .95*bend*u**1.6*(.35+.65*v)
    step=(width/2)/columns
    x=np.zeros_like(u);z=np.zeros_like(u)
    x[:,1:]=np.cumsum(np.cos((angle[:,1:]+angle[:,:-1])/2)*step,axis=1)
    z[:,1:]=np.cumsum(np.sin((angle[:,1:]+angle[:,:-1])/2)*step,axis=1)
    # Orthographic oblique view: height creates visible lift without cropping corners.
    vertices=np.stack((width/2+x, v*(height-1)-z*.12*np.sin(math.pi*v), z),axis=-1)
    return vertices,np.stack((u,v),axis=-1),angle


def page_curl(previous, following, progress):
    if progress<=0:return previous.copy()
    if progress>=1:return following.copy()
    if previous.shape!=following.shape:raise ValueError('Page dimensions must match')
    h,w=previous.shape[:2];mid=w//2
    output=following.astype(float).copy();output[:,:mid]=previous[:,:mid]
    vertices,uv,angles=leaf_mesh(progress,w,h)
    # Soft cast shadow follows the elevated leaf, vanishing at both endpoints.
    yy,xx=np.mgrid[:h,:w]
    edge=np.interp(np.arange(h),np.linspace(0,h-1,vertices.shape[0]),vertices[:,-1,0])[:,None]
    shadow=np.exp(-((xx-edge)/(w*.025+1))**2)*.19*math.sin(math.pi*progress)
    output*=1-shadow[:,:,None]
    depth=np.full((h,w),-np.inf)
    for row in range(vertices.shape[0]-1):
        for col in range(vertices.shape[1]-1):
            for ids in (((row,col),(row,col+1),(row+1,col+1)),((row,col),(row+1,col+1),(row+1,col))):
                pts=np.array([vertices[i] for i in ids]);tex=np.array([uv[i] for i in ids])
                xmin=max(0,int(np.floor(pts[:,0].min())));xmax=min(w-1,int(np.ceil(pts[:,0].max())))
                ymin=max(0,int(np.floor(pts[:,1].min())));ymax=min(h-1,int(np.ceil(pts[:,1].max())))
                if xmin>xmax or ymin>ymax:continue
                a,b,c=pts;den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
                if abs(den)<1e-8:continue
                gy,gx=np.mgrid[ymin:ymax+1,xmin:xmax+1]
                wa=((b[1]-c[1])*(gx-c[0])+(c[0]-b[0])*(gy-c[1]))/den
                wb=((c[1]-a[1])*(gx-c[0])+(a[0]-c[0])*(gy-c[1]))/den
                wc=1-wa-wb;z=wa*a[2]+wb*b[2]+wc*c[2]
                old_depth=depth[ymin:ymax+1,xmin:xmax+1]
                visible=(wa>=-1e-6)&(wb>=-1e-6)&(wc>=-1e-6)&(z>=old_depth)
                if not visible.any():continue
                tu=wa*tex[0,0]+wb*tex[1,0]+wc*tex[2,0]
                tv=wa*tex[0,1]+wb*tex[1,1]+wc*tex[2,1]
                theta=float(np.mean([angles[i] for i in ids]));front=math.cos(theta)>=0
                sx=mid+tu*(w-mid-1) if front else (1-tu)*(mid-1)
                sy=np.clip(np.rint(tv*(h-1)).astype(int),0,h-1)
                sx=np.clip(np.rint(sx).astype(int),0,w-1)
                texture=previous if front else following
                light=.76+.24*abs(math.cos(theta))
                patch=output[ymin:ymax+1,xmin:xmax+1]
                patch[visible]=(texture[sy,sx]*light)[visible]
                old_depth[visible]=z[visible]
    return np.clip(output,0,255).astype(np.uint8)
