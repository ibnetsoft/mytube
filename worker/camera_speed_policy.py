"""User preference: never add slow zooms; keep a static scale instead."""
import copy
VERSION='no_slow_zoom/v1'
TASK=' Never use slow, subtle or whole-scene zooms. Prefer a fixed camera. When a zoom is motivated, use a clearly visible medium-speed zoom over about 2..4 seconds, with holds before/after. Never stretch a small zoom across a long scene.'
def constrain(keys,duration):
    result=copy.deepcopy(keys)
    if not isinstance(result,list) or len(result)<2:return result,False
    moving=[(a,b) for a,b in zip(result,result[1:]) if abs(float(b.get('scale',1))-float(a.get('scale',1)))>1e-7]
    if not moving:return result,False
    seconds=sum(max(0,float(b['t'])-float(a['t']))*float(duration) for a,b in moving)
    travel=sum(abs(float(b.get('scale',1))-float(a.get('scale',1))) for a,b in moving)
    if seconds<=4.0001 and seconds>0 and travel/seconds>=.01:return result,False
    for key in result:key['scale']=result[0].get('scale',1)
    return result,True
