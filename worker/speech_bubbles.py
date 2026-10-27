"""Script-selected bubble presets; final pixels determine safe, voice-bound placement."""
import copy
import math

CONTRACT = 'speech_bubble_presets/v1'
PRESETS = ('dialogue','rounded','shout','whisper','thought','reaction','narration','electronic')
TASK = '''For every confirmed dialogue span return speech_bubble_plan:{contract:'speech_bubble_presets/v1',cues:[{text,speaker,style,reason}]}. Copy exact dialogue text and speaker. Select style by meaning and delivery, never punctuation alone: dialogue=ordinary oval, rounded=gentle rounded box, shout=raised voice jagged, whisper=quiet dashed oval, thought=cloud inner monologue, reaction=short surprised burst, narration=rectangular caption, electronic=chamfered communication. Confirmed spoken lines cannot use thought/narration. Do not invent thoughts or narration captions. One cue per confirmed span; empty cues for no confirmed dialogue. All placement and timing are provisional until actual footage and finalized recorded subtitles are inspected. Preserve original baked bubbles; do not duplicate them. Offscreen/uncertain speaker or no safe space requires repair, never an arbitrary tail.'''

def validate_script(raw, scene):
    spans=[s for s in scene.get('dialogue_spans',[]) if s['status']=='confirmed']
    value=raw.get('speech_bubble_plan')
    if value is None and not spans:return None
    if not isinstance(value,dict) or value.get('contract')!=CONTRACT or not isinstance(value.get('cues'),list):raise ValueError('Missing script bubble preset decisions')
    cues=value['cues']
    if len(cues)!=len(spans):raise ValueError('Bubble decisions must cover each confirmed dialogue span')
    result=[]
    for cue,span in zip(cues,spans):
        if cue.get('text')!=span['text'] or cue.get('speaker')!=span['speaker'] or cue.get('style') not in PRESETS or cue['style'] in ('thought','narration') or not str(cue.get('reason') or '').strip():raise ValueError('Bubble decision changed dialogue/speaker or has unsupported delivery')
        result.append({k:cue[k] for k in ('text','speaker','style','reason')})
    return {'contract':CONTRACT,'cues':result}

def bind(spec, rows, start, end):
    """Bind exact recorded subtitle text; ambiguous/changed wording stops execution."""
    result=copy.deepcopy(spec);text=''.join(str(r.get('text') or '') for r in rows)
    cursor=0
    for cue in result['cues']:
        quote=cue['text'];at=text.find(quote,cursor)
        if at<0:raise ValueError('Bubble dialogue differs from finalized recorded subtitles')
        offset=0;selected=[]
        for row in rows:
            left=offset;offset+=len(str(row.get('text') or ''))
            if left<at+len(quote) and offset>at:selected.append(row)
        if not selected or any(r.get('dialogue_kind')!='dialogue' for r in selected):raise ValueError('Bubble overlaps unconfirmed/non-dialogue recording')
        for row in selected:
            manual=row.get('editor_speaker') or {}
            speaker=(manual.get('name') if manual.get('text')==row.get('text') else None) or row.get('dialogue_speaker') or (row.get('speaker') or {}).get('name')
            if str(speaker or '').strip()!=cue['speaker']:raise ValueError('Bubble speaker differs from finalized recorded speaker')
        a=max(0,float(selected[0]['start'])-start);b=min(end-start,float(selected[-1]['end'])-start)
        if b-a<.3:raise ValueError('Recorded bubble interval too short')
        cue.update(start_seconds=a,end_seconds=b);cursor=at+len(quote)
    return result

def _nums(values,count):
    return isinstance(values,list) and len(values)==count and all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=1 for v in values)

def validate_layout(response,spec):
    if response.get('status')!='ready' or not str(response.get('evidence') or '').strip():raise ValueError('Bubble source layout needs repair')
    items=response.get('bubbles')
    if not isinstance(items,list) or len(items)!=len(spec['cues']):raise ValueError('Bubble layout lost dialogue')
    result=[]
    for item,cue in zip(items,spec['cues']):
        if any(item.get(k)!=cue[k] for k in ('text','speaker','style','start_seconds','end_seconds')):raise ValueError('Bubble layout changed frozen dialogue')
        box=item.get('box');target=item.get('speaker_anchor');protected=item.get('protected_boxes')
        if not _nums(box,4) or not _nums(target,2) or not isinstance(protected,list) or not protected or not all(_nums(p,4) and p[0]<p[2] and p[1]<p[3] for p in protected):raise ValueError('Bubble requires observed face/object protection and speaker anchor')
        x,y,r,b=box
        if not .04<=x<r<=.96 or not .04<=y<b<=.78 or r-x<.12 or b-y<.07:raise ValueError('Bubble outside safe area')
        # Include outline margin; reject overlap, not just the box center.
        if any(x-.015<p[2] and r+.015>p[0] and y-.015<p[3] and b+.015>p[1] for p in protected):raise ValueError('Bubble obscures protected face/object')
        if x<=target[0]<=r and y<=target[1]<=b:raise ValueError('Speaker anchor cannot lie inside bubble')
        if not str(item.get('speaker_evidence') or '').strip():raise ValueError('Speaker identity evidence missing')
        # First boundary intersection from the center toward the observed speaker.
        cx=(x+r)/2;cy=(y+b)/2;dx=target[0]-cx;dy=target[1]-cy
        t=min((r-x)/2/abs(dx) if dx else float('inf'),(b-y)/2/abs(dy) if dy else float('inf'))
        root=[cx+dx*t,cy+dy*t]
        # The tail corridor must not cross another face or an important object.
        for p in protected:
            if p[0]<=target[0]<=p[2] and p[1]<=target[1]<=p[3]:continue
            for n in range(21):
                q=[root[j]+(target[j]-root[j])*n/20 for j in (0,1)]
                if p[0]-.015<q[0]<p[2]+.015 and p[1]-.015<q[1]<p[3]+.015:raise ValueError('Bubble tail crosses important content')
        result.append({**cue,'box':box,'speaker_anchor':target,'tail_root':root,'protected_boxes':protected,'speaker_evidence':item['speaker_evidence']})
    for i,c in enumerate(result):
        for d in result[:i]:
            if max(c['start_seconds'],d['start_seconds'])<min(c['end_seconds'],d['end_seconds']):
                a,b=c['box'],d['box']
                if a[0]<b[2] and a[2]>b[0] and a[1]<b[3] and a[3]>b[1]:raise ValueError('Simultaneous bubbles overlap')
    return {'contract':CONTRACT,'bubbles':result,'evidence':response['evidence']}

LAYOUT_TASK = '''Inspect attached ACTUAL rendered footage at each cue start/middle/end. Return {status:'ready'|'needs_repair',evidence:string,bubbles:[{text,speaker,style,start_seconds,end_seconds,box:[left,top,right,bottom],speaker_anchor:[x,y],protected_boxes:[[left,top,right,bottom]],speaker_evidence:string}]}. Copy frozen cue fields exactly. Wrap text with no wording changes in AE. Choose negative space and protect ALL faces, essential props, existing text and focal objects across the ENTIRE interval. Coordinates normalized in final output canvas. Anchor tail to visible named speaker cheek boundary (not inside eyes/mouth). Never guess speaker identity, duplicate baked source bubbles or cover faces/objects/subtitles. Union protected regions over all supplied frames. If speaker moves so a fixed tail cannot stay connected, or no safe readable placement, return needs_repair. Do not omit a cue to force approval.'''

def apply(runner,snapshot,scene,visual,directory,fresh):
    spec=scene.get('speech_bubble_plan')
    if not spec or not spec.get('cues'):return visual
    from pathlib import Path
    from ae_media_utils import ffmpeg,run
    from ae_scene_production import _render_native
    from ae_flat_scene import prepare
    from moviepy import VideoFileClip
    from PIL import Image
    work=directory/'speech-bubbles';work.mkdir(exist_ok=True)
    rows=[r for r in snapshot['subtitles'] if int(r.get('scene_number') or 0)==scene['number']]
    frozen=bind(spec,rows,scene['start'],scene['end'])
    paths=[]
    with VideoFileClip(str(visual),audio=False) as clip:
        for i,c in enumerate(frozen['cues']):
            for n,t in enumerate((c['start_seconds'],(c['start_seconds']+c['end_seconds'])/2,c['end_seconds']-1/snapshot['motion']['fps'])):
                p=work/f'cue-{i}-{n}.png';Image.fromarray(clip.get_frame(max(0,min(t,clip.duration-1/clip.fps)))).save(p);paths.append(str(p.resolve()))
    feedback=None
    for attempt in range(3):
        fresh()
        response=runner._stage('bubble-'+str(scene['number'])+'-'+Path(directory).name,f'bubble_layout_{attempt}',{'_local_image_paths':paths,'scene':scene['text'],'frame_order':'For each frozen cue: start, middle, last displayed frame; final output coordinates','frozen_bubbles':frozen,'feedback':feedback},LAYOUT_TASK)
        try:layout=validate_layout(response,frozen);break
        except ValueError as error:
            feedback=str(error)
            if attempt==2:raise
    identity={'fit':'contain','keys':[{'t':t,'x':.5,'y':.5,'scale':1,'rotation':0,'opacity':100} for t in (0,1)],'effects':[]}
    prepared=prepare(visual,{**scene,'source_kind':'video'},snapshot['motion'],identity)
    prepared['plan']['speech_bubbles']=layout
    native=_render_native(prepared,work,scene['end']-scene['start'])
    output=work/'bubbles.mp4'
    run([ffmpeg(),'-v','error','-y','-i',str(native),'-an','-t',str(scene['end']-scene['start']),'-r',str(snapshot['motion']['fps']),'-c:v','libx264','-pix_fmt','yuv420p',str(output)])
    scene['_bubble_layout']=layout
    return output
