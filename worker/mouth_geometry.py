"""Evidence-bound mouth placement. Boxes alone never authorize a mouth overlay."""
import hashlib
import json
import math

VERSION = 2
POSES = {'frontal', 'three_quarter_left', 'three_quarter_right', 'profile_left', 'profile_right'}

def point(value):
    return (isinstance(value, list) and len(value) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    and math.isfinite(v) and 0 <= v <= 1 for v in value))

def inside(p, box):
    return box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]

def polygon_contains(p, polygon):
    x, y = p; hit = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        cross = (b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0])
        if abs(cross) < 1e-9 and min(a[0],b[0]) <= x <= max(a[0],b[0]) and min(a[1],b[1]) <= y <= max(a[1],b[1]):
            return True
        if (a[1] > y) != (b[1] > y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            hit = not hit
    return hit

def validate(speaker, source_sha256=None, require_review=True):
    g = speaker.get('mouth_geometry') or {}
    if g.get('version') != VERSION:
        raise ValueError('Mouth geometry v2 required; legacy boxes cannot authorize animation')
    if source_sha256 and g.get('source_sha256') != source_sha256:
        raise ValueError('Mouth geometry belongs to a different source image')
    if g.get('orientation') not in POSES or g.get('pitch') not in {'level', 'up', 'down'}:
        raise ValueError('Face orientation and pitch are required')
    if g.get('mouth_visibility') not in {'clear', 'partial', 'hidden'}:
        raise ValueError('Mouth occlusion assessment required')
    if not str(g.get('evidence') or '').strip():
        raise ValueError('Mouth geometry needs visual evidence')
    if require_review and (g.get('review', {}).get('proof') != 'annotated-face-crop-v4'
                           or g.get('review', {}).get('passed') is not True
                           or not g.get('review', {}).get('reason')):
        raise ValueError('Original face crop must pass independent geometry review')
    if g['mouth_visibility'] != 'clear':
        if g.get('render_policy') != 'preserve_original':
            raise ValueError('Occluded mouth must preserve original pixels')
        return g
    if g.get('render_policy') != 'animate':
        raise ValueError('Clear mouth needs an explicit render policy')
    face, mouth = speaker.get('face_box'), speaker.get('mouth_box')
    if not face or not mouth or len(face) != 4 or len(mouth) != 4:
        raise ValueError('Verified face and mouth bounds required')
    outline = g.get('face_outline')
    if not isinstance(outline, list) or len(outline) < 5 or not all(point(p) for p in outline):
        raise ValueError('Visible face contour required')
    landmarks = g.get('landmarks') or {}
    for key in ('nose_tip', 'chin', 'lip_left', 'lip_right', 'lip_center'):
        if not point(landmarks.get(key)) or not inside(landmarks[key], face):
            raise ValueError('Missing or out-of-face landmark: ' + key)
    for key in ('lip_left', 'lip_right', 'lip_center'):
        if not inside(landmarks[key], mouth) or not polygon_contains(landmarks[key], outline):
            raise ValueError('Lip landmarks must lie inside actual face contour and mouth patch')
    a,b,c = (landmarks[k] for k in ('lip_left','lip_right','lip_center'))
    if a[0] >= b[0] or math.dist(a,b) < .004:
        raise ValueError('Lip endpoints must describe a visible mouth')
    if math.dist(c,[(a[0]+b[0])/2,(a[1]+b[1])/2]) > math.dist(a,b)*.25:
        raise ValueError('Lip center disagrees with lip endpoints')
    # Compare along nose-to-chin axis, so a tilted/downward face is not judged
    # by a screen-y heuristic. The cheek is not a valid mouth location.
    n,ch = landmarks['nose_tip'],landmarks['chin']
    dx,dy=ch[0]-n[0],ch[1]-n[1];den=dx*dx+dy*dy
    if den < .000025:raise ValueError('Nose/chin geometry degenerate')
    along=((c[0]-n[0])*dx+(c[1]-n[1])*dy)/den
    lateral=abs((c[0]-n[0])*dy-(c[1]-n[1])*dx)/math.sqrt(den)
    if not .1 <= along <= .95 or lateral > math.sqrt(den)*.45:
        raise ValueError('Mouth must lie anatomically between nose and chin, not on cheek')
    return g

def animatable(speaker, source_sha256=None):
    if speaker.get('status') != 'visible':return False
    return validate(speaker,source_sha256).get('render_policy') == 'animate'

def fingerprint(speaker):
    return hashlib.sha256(json.dumps(speaker.get('mouth_geometry'),sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def validate_image_evidence(speaker, image):
    """Reject lip points on blank cheek skin before any model approval/generation."""
    import numpy as np
    pixels=np.asarray(image.convert('L'),dtype=float)
    h,w=pixels.shape
    landmarks=speaker['mouth_geometry']['landmarks']
    box=speaker['mouth_box']
    l,t,r,b=[round(v*(w if i%2==0 else h)) for i,v in enumerate(box)]
    pad=max(4,round((b-t)*.35));region=pixels[max(0,t-pad):min(h,b+pad),max(0,l-pad):min(w,r+pad)]
    skin=float(np.percentile(region,65))
    def ink(key):
        x,y=round(landmarks[key][0]*w),round(landmarks[key][1]*h)
        area=pixels[max(0,y-3):min(h,y+4),max(0,x-3):min(w,x+4)]
        return area.size>0 and skin-float(area.min()) >= 18
    if not ink('lip_center') or not (ink('lip_left') or ink('lip_right')):
        raise ValueError('Proposed lip points lack visible lip-line pixels; possible cheek placement')
