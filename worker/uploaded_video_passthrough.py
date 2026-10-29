"""Keep uploaded video pixels out of AE when no native visual work is requested."""
import math
VERSION='uploaded_video_passthrough/v1'
def eligible(scene,plan,*,runtime_resolved=False):
    if scene.get('source_kind')!='video' or scene.get('webtoon') or plan.get('ai'):
        return False
    direction=plan.get('scene') or {}
    if direction.get('effects') or scene.get('reviewed_depth_effects'):
        return False
    if scene.get('speech_bubble_plan',{}).get('cues') or scene.get('parallax_mouth'):
        return False
    if (scene.get('_mouth_runtime') or {}).get('enabled') or (not runtime_resolved and any((scene.get(k) or {}).get('mouth_required') for k in ('postwork','still_mouth'))):
        return False
    keys=direction.get('keys')
    if not isinstance(keys,list) or len(keys)<2 or keys[0].get('t')!=0 or keys[-1].get('t')!=1:
        return False
    expected={'x':.5,'y':.5,'scale':1,'rotation':0,'opacity':100}
    return all(isinstance(k,dict) and all(isinstance(k.get(name),(int,float)) and not isinstance(k[name],bool) and math.isfinite(k[name]) and abs(k[name]-value)<1e-8 for name,value in expected.items()) for k in keys)
