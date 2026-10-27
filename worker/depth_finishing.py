"""Script intent for restrained depth-plane finishing; actual PSD pixels must be reviewed."""
TYPES={'depth_background_blur','depth_foreground_blur','depth_background_haze'}
TASK="""Optionally return depth_effects:[{type:'depth_background_blur'|'depth_foreground_blur'|'depth_background_haze',intensity:.05.. .35,blur_pixels:1..12 (blur only),reason:'script and composition evidence'}]. Use [] when depth finishing adds nothing. This is optional, even in all-scene parallax mode. Request only real separated planes in required_layers. Background blur keeps the middle-plane subject sharp, foreground blur defocuses only near-plane objects, and haze reduces distant contrast only behind the subject. Preserve original foreground occlusion with foreground above characters above background. Never blur a character/face, captions or readable art text. Do not apply these effects to uploaded moving video; absence of separated planes requires repair rather than a full-frame filter. Avoid excessive fog or an effect on every scene."""

def normalize(raw,scene,layers):
    effects=raw.get('depth_effects',[])
    if not isinstance(effects,list) or len(effects)>3:raise ValueError('Depth finishing must be a bounded list')
    known={l['role'] for l in layers};seen=set();clean=[]
    for effect in effects:
        if not isinstance(effect,dict) or effect.get('type') not in TYPES or effect['type'] in seen:raise ValueError('Invalid or duplicate depth effect')
        if scene.get('visual_type')=='video' or scene.get('video_generation_mode')=='user_upload':raise ValueError('Depth finishing requires separated still layers')
        role='foreground' if effect['type']=='depth_foreground_blur' else 'background'
        if role not in known:raise ValueError('Depth finishing requested without its separated plane')
        intensity=effect.get('intensity');blur=effect.get('blur_pixels')
        valid=lambda v,lo,hi:type(v) in (int,float) and lo<=v<=hi
        if not valid(intensity,.05,.35) or not str(effect.get('reason') or '').strip():raise ValueError('Depth effect needs restrained intensity and scene evidence')
        if effect['type'].endswith('_blur') and not valid(blur,1,12):raise ValueError('Depth blur needs 1..12 source pixels')
        clean.append(dict(effect));seen.add(effect['type'])
    return clean
