"""Source-reviewed electrical PNG keys on the existing editor/native image clock."""
import math
CONTRACT='wuxia_attack_sprite/v1'

def validate(loop):
 r=loop.get('attack_sprite')
 if (not isinstance(r,dict) or r.get('contract')!=CONTRACT or r.get('source_reviewed') is not True
     or r.get('source_sha256')!=loop.get('source_sha256') or r.get('frames_reviewed') is not True
     or any(not isinstance(r.get(k),str) or not r[k].strip() for k in ('event','reason'))
     or type(r.get('contact_ms')) not in (int,float) or not math.isfinite(r['contact_ms'])
     or not 0<=r['contact_ms']<=loop['start_ms'] or loop['end_ms']-loop['start_ms']>600
     or loop.get('repeat') is not False):raise ValueError('Invalid reviewed attack sprite')
 boxes=r.get('protected_boxes')
 if not isinstance(boxes,list) or len(boxes)>100:raise ValueError('Invalid sprite protection')
 for b in boxes:
  if (not isinstance(b,list) or len(b)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in b)
      or b[0]>=b[2] or b[1]>=b[3]):raise ValueError('Invalid sprite protection')
 return r

def validate_alpha(loop,alpha):
 r=validate(loop);w,h=alpha.size
 for b in r['protected_boxes']:
  # Include every pixel touching the protected rectangle.
  box=(math.floor(b[0]*w),math.floor(b[1]*h),math.ceil(b[2]*w),math.ceil(b[3]*h))
  if alpha.crop(box).getbbox():raise ValueError('Electrical sprite covers protected artwork')
