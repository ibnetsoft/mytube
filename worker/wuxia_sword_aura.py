"""Source-bound sword energy patches; never displace the person or steel blade.

The generated clean plate is used ONLY through a reviewed energy matte. Original
art outside that matte and all protected polygons stays untouched. Prepared PNGs
use the existing editor/native ambient frame clock, below authored lettering.
"""
import json, math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageChops

CONTRACT='wuxia_sword_aura/v1'

def protection_mask(size,polygons,guard=3):
    mask=Image.new('L',size);draw=ImageDraw.Draw(mask)
    for polygon in polygons:
        if not isinstance(polygon,list) or len(polygon)<3 or any(not isinstance(p,list) or len(p)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in p) for p in polygon):
            raise ValueError('Invalid sword aura protection polygon')
        draw.polygon([(round(x*(size[0]-1)),round(y*(size[1]-1))) for x,y in polygon],fill=255)
    return mask.filter(ImageFilter.MaxFilter(guard*2+1))

def validate_contract(loop):
    a=loop.get('sword_aura')
    if a is None:return
    if (a.get('contract')!=CONTRACT or a.get('source_reviewed') is not True
        or a.get('source_sha256')!=loop['source_sha256'] or not a.get('protected_polygons')
        or not str(a.get('reason','')).strip() or not 0<a.get('amplitude_px',0)<=16
        or len(a.get('clean_plate_sha256',''))!=64):raise ValueError('Invalid reviewed sword aura contract')
    protection_mask((loop['width'],loop['height']),a['protected_polygons'])

def validate_alpha(loop,alpha):
    validate_contract(loop)
    if loop.get('sword_aura'):
        from worker.ambient_loop import pixel_box
        b=alpha.getbbox();r=pixel_box(loop['region'],alpha.size)
        if b and (b[0]<r[0] or b[1]<r[1] or b[2]>r[2] or b[3]>r[3]):raise ValueError('Sword aura escaped reviewed pixel envelope')
    if loop.get('sword_aura') and ImageChops.multiply(alpha,protection_mask(alpha.size,loop['sword_aura']['protected_polygons'])).getbbox():
        raise ValueError('Sword aura overlaps protected person/blade pixels')

def prepare(source,clean_plate,spec,directory):
    from worker.ambient_loop import digest,validate,pixel_box
    source=Path(source);clean_plate=Path(clean_plate);directory=Path(directory)
    if spec.get('source_reviewed') is not True or spec.get('source_sha256')!=digest(source):raise ValueError('Review exact source before aura preparation')
    base=Image.open(source).convert('RGB');plate=Image.open(clean_plate).convert('RGB')
    if plate.size!=base.size:raise ValueError('Clean plate alignment/canvas mismatch')
    size=base.size;w,h=size;directory.mkdir(parents=True,exist_ok=True)
    protected=protection_mask(size,spec['protected_polygons']);allowed=Image.new('L',size)
    left,top,right,bottom=pixel_box(spec['region'],size)
    ImageDraw.Draw(allowed).rectangle((left,top,right-1,bottom-1),fill=255)
    allowed=ImageChops.subtract(allowed,protected)
    rgb=np.asarray(base).astype(float);red,green,blue=rgb[:,:,0],rgb[:,:,1],rgb[:,:,2]
    # Color selection is confined to a source-reviewed ROI, never global blue clothing.
    strength=np.minimum.reduce((np.clip((blue-red-55)/55,0,1),np.clip((green-red-15)/40,0,1),np.clip((blue-160)/40,0,1)))
    if spec.get('energy_polygons'):
        islands=protection_mask(size,spec['energy_polygons'],guard=0)
        emission_islands=islands
        if spec.get('kind') in ('body','sword'):
            margin=math.ceil(spec['amplitude_px'])+8
            islands=islands.filter(ImageFilter.MaxFilter(2*margin+1)).filter(ImageFilter.GaussianBlur(2))
        allowed=ImageChops.multiply(allowed,islands)
        hi=rgb.max(axis=2);lo=rgb.min(axis=2)
        strength=np.maximum(np.minimum(np.clip((hi-150)/65,0,1),np.clip((hi-lo-25)/65,0,1)),np.clip((lo-220)/35,0,1))
    if spec.get('energy_polygons') and spec.get('kind')=='sword':
        # Extract only traced source energy. The wider envelope permits travel,
        # but must never turn bright background objects into moving emission.
        strength=strength*np.asarray(emission_islands)/255
    matte=Image.fromarray(np.uint8(strength*255)).filter(ImageFilter.GaussianBlur(1.1))
    matte=ImageChops.multiply(matte,allowed)
    if not matte.getbbox():raise ValueError('No luminous energy in the reviewed region')
    removal=matte.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(1.2))
    removal=ImageChops.multiply(removal,allowed)
    # Only luminous color islands are cleaned; generated anatomy never enters output.
    cleaned=Image.composite(plate,base,removal)
    energy=np.asarray(base.convert('RGBA')).copy();energy[:,:,3]=np.asarray(matte)
    dummy=dict(media_url='https://prepared.invalid/aura.png',gcs_bucket='pending',gcs_path='pending',duration_ms=60,sha256='0'*64)
    aura=dict(contract=CONTRACT,source_reviewed=True,source_sha256=digest(source),clean_plate_sha256=digest(clean_plate),
        protected_polygons=spec['protected_polygons'],reason=spec['reason'],amplitude_px=spec['amplitude_px'],
        method='isolated_energy_turbulence_and_traveling_emission',stationary_original=True)
    loop=dict(contract='ambient_loop/v1',enabled=True,source_sha256=digest(source),role='environment',width=w,height=h,
        region=spec['region'],protected_regions=spec['protected_regions'],start_ms=0,end_ms=spec['end_ms'],phase_ms=0,repeat=True,sword_aura=aura,frames=[dummy,dummy])
    validate(loop);validate_contract(loop)
    yy,xx=np.mgrid[0:h,0:w];amplitude=spec['amplitude_px']
    isolated_sword=bool(spec.get('energy_polygons') and spec.get('kind')=='sword')
    if isolated_sword:
        # Signed emission replacement moves light, never sampled background RGB.
        # Keep the original as the static plate and remove/add only positive glow.
        emission=np.maximum(rgb-np.asarray(plate).astype(float),0)*(np.asarray(matte)[:,:,None]/255)
    # Periodic, spatially varying refraction: no camera/body transform and no seam.
    frames=[]
    for i in range(16):
        phase=2*math.pi*i/16
        dx=amplitude*(.65*np.sin(yy/28+phase)+.35*np.sin(xx/48+2*phase))
        dy=amplitude*(.65*np.sin(xx/36-phase)+.35*np.sin(yy/57+2*phase))
        sx=np.clip(np.rint(xx+dx).astype(int),0,w-1);sy=np.clip(np.rint(yy+dy).astype(int),0,h-1)
        warped=energy[sy,sx].copy();wave=.8+.2*np.sin(xx/55+yy/71-2*phase)
        warped[:,:,3]=np.uint8(warped[:,:,3]*wave*np.asarray(allowed)/255)
        if isolated_sword:
            delta=(emission[sy,sx]*wave[:,:,None]-emission)*(np.asarray(allowed)[:,:,None]/255)
            value=np.uint8(np.clip(rgb+delta,0,255))
            alpha=np.uint8(np.any(value!=np.uint8(rgb),axis=2))*255
            patch=Image.fromarray(np.dstack((value,alpha)))
            validate_alpha(loop,patch.getchannel('A'))
            path=directory/f'aura-{i:02d}.png';patch.save(path)
            frames.append({**dummy,'sha256':digest(path),'local_path':str(path.resolve())})
            continue
        moving=Image.fromarray(warped)
        composite=cleaned.convert('RGBA');composite.alpha_composite(moving)
        alpha=ImageChops.lighter(removal,moving.getchannel('A'));alpha=ImageChops.multiply(alpha,allowed)
        # Frame contains a local clean-plate replacement + moving energy only.
        patch=composite.copy();patch.putalpha(alpha)
        validate_alpha(loop,patch.getchannel('A'))
        path=directory/f'aura-{i:02d}.png';patch.save(path)
        frames.append({**dummy,'sha256':digest(path),'local_path':str(path.resolve())})
    loop['frames']=frames;validate(loop)
    (directory/'manifest.local.json').write_text(json.dumps(loop,ensure_ascii=False,indent=2))
    return loop
