"""Durable native-image work queue. Never calls a model or rewrites refused prompts.

The calling agent records tool outcomes and visual reviews. Safety/unknown failures
require an explicit, independently reviewed alternative, not a bypass retry.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
import re
import time
from pathlib import Path
from PIL import Image

POLICY = 'native-image-recovery/v1'
MAX_ATTEMPTS = 3

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def initialize(manifest):
    jobs = []
    if manifest.get('schema') == 'cowork_scene_assets/v1':
        for g in manifest['grids']:
            jobs.append({'id':f"grid-{g['grid_number']:03d}", 'kind':'scene', 'layout':'grid',
                'scene_numbers':g['scene_numbers'], 'prompt':g['prompt'],
                'references':manifest.get('character_references',[]),
                'scene_specs':[s for s in manifest.get('scene_specs',[]) if s['scene_number'] in g['scene_numbers']]})
    elif manifest.get('schema') == 'cowork_thumbnail_asset/v1':
        jobs = [{'id':'thumbnail','kind':'thumbnail','layout':'single','scene_numbers':[],
                 'prompt':manifest['prompt'],'references':manifest.get('character_references',[])}]
    else:
        jobs = copy.deepcopy(manifest['jobs'])
    ids = [j['id'] for j in jobs]
    if not ids or len(set(ids)) != len(ids): raise ValueError('Unique jobs required')
    for j in jobs:
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', j['id']): raise ValueError('Invalid job ID')
        if j['kind'] not in ('scene','character','thumbnail'): raise ValueError('Invalid image kind')
        if not str(j.get('prompt','')).strip(): raise ValueError('Prompt required')
        if j['layout'] not in ('grid','single'): raise ValueError('Invalid layout')
        if j['kind']=='scene' and len(j['scene_numbers']) != (4 if j['layout']=='grid' else 1):
            raise ValueError('Invalid scene mapping')
        j.update(status='pending', attempts=0, alternative_depth=0, next_after=0, history=[])
    return {'schema':POLICY,'source_hash':digest(manifest),'jobs':jobs}

def get_job(state, job_id):
    return next(j for j in state['jobs'] if j['id']==job_id)

def summary(state, now=None):
    now = time.time() if now is None else now
    jobs = [j for j in state['jobs'] if j['status']!='superseded']
    return {'complete':all(j['status']=='ready' for j in jobs),
        'ready':[j['id'] for j in jobs if j['status']=='ready'],
        'runnable':[j for j in jobs if j['status'] in ('pending','retry_wait') and j['next_after']<=now],
        'attention':[{'id':j['id'],'status':j['status'],'scene_numbers':j['scene_numbers']}
                     for j in jobs if j['status'] not in ('ready','pending','retry_wait')]}

def verify_file(job):
    path=Path(job['image_file'])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=job['sha256']: raise ValueError('Image changed after review')
    with Image.open(path) as im:
        im.verify()
    return path

def transition(state, event, now=None):
    state=copy.deepcopy(state); now=time.time() if now is None else now
    j=get_job(state,event['job_id']); action=event['action']
    if action=='start':
        if j['status'] not in ('pending','retry_wait') or now<j['next_after'] or j['attempts']>=MAX_ATTEMPTS:
            raise ValueError('Job is not runnable; review or wait required')
        j.update(status='running',attempts=j['attempts']+1)
    elif action=='result':
        if j['status']!='running': raise ValueError('No running attempt')
        outcome=event['outcome']
        if outcome=='generated':
            path=Path(event['image_file']).resolve()
            with Image.open(path) as im:
                im.load()
                if min(im.size)<320: raise ValueError('Generated bitmap is too small')
            j.update(status='quality_review', image_file=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        else:
            if outcome not in ('safety','transient','quota','unavailable','quality','unknown'):
                raise ValueError('Unknown outcome; use unknown, never guess transient')
            # A safety signal always wins over an accidentally supplied transient label.
            signal=str(event.get('code',''))+' '+str(event.get('reason',''))
            if re.search(r'safety|moderation|policy|content.filter|안전|정책',signal,re.I): outcome='safety'
            status={'safety':'safety_review','unknown':'needs_review','quota':'quota_wait',
                    'unavailable':'unavailable','quality':'quality_failed','transient':'retry_wait'}[outcome]
            if j['attempts']>=MAX_ATTEMPTS: status='exhausted'
            if outcome=='safety': status='safety_review'
            j.update(status=status, failure_kind=outcome,
                     next_after=now+([30,120][min(j['attempts']-1,1)] if status=='retry_wait' else 0))
    elif action=='accept':
        if j['status']!='quality_review' or not event.get('visual_review'): raise ValueError('Visual review required')
        verify_file(j); j['status']='ready'
    elif action=='reject_quality':
        if j['status']!='quality_review': raise ValueError('No generated image to review')
        j['status']='quality_failed'
    elif action=='split_quality':
        if j['status']!='quality_failed' or j['layout']!='grid' or j.get('failure_kind') in ('safety','unknown'):
            raise ValueError('Only a non-safety grid quality failure may split automatically')
        specs={s['scene_number']:s for s in j.get('scene_specs',[])}
        if any(not specs.get(n,{}).get('image_prompt') for n in j['scene_numbers']):
            raise ValueError('Original per-scene prompts required; do not invent them')
        return transition(state,{'action':'review','job_id':j['id'],'decision':'alternative',
            'review':{'reviewer':'original-scene-spec','reason':'grid layout quality failure',
                'source_fidelity':'original per-scene prompt unchanged','character_age_style_preserved':'original references retained'},
            'proposals':[{'scene_numbers':[n],'prompt':'One single 16:9 scene image, not a grid.\n'+specs[n]['image_prompt']}
                         for n in j['scene_numbers']]},now)
    elif action=='review':
        if j['status'] not in ('safety_review','needs_review','quality_failed','quota_wait','unavailable','exhausted'):
            raise ValueError('Review not applicable')
        decision=event['decision']
        if decision=='stop': j['status']='blocked'
        elif decision=='resume':
            if j['status'] not in ('quota_wait','unavailable') or not event.get('resolved_evidence'):
                raise ValueError('Only resolved availability/quota may resume')
            if j['attempts']>=MAX_ATTEMPTS: raise ValueError('Attempt budget exhausted')
            j.update(status='pending',next_after=0)
        elif decision=='alternative':
            if j['alternative_depth'] or j['attempts']>=MAX_ATTEMPTS: raise ValueError('Alternative budget exhausted')
            review=event.get('review',{})
            for key in ('reviewer','reason','source_fidelity','character_age_style_preserved'):
                if not review.get(key): raise ValueError('Missing review: '+key)
            if j.get('failure_kind') in ('safety','unknown'):
                if review.get('safety_assessment')!='allowed_alternative' or not review.get('user_approval'):
                    raise ValueError('Safety/unknown requires reviewed safe alternative and explicit user approval')
            proposals=event['proposals']
            expected=sorted(j['scene_numbers'])
            actual=sorted(n for p in proposals for n in p['scene_numbers'])
            if actual!=expected or not proposals: raise ValueError('Alternative must cover exact original scene IDs')
            if j['kind']!='scene' and len(proposals)!=1: raise ValueError('One replacement per asset')
            for i,p in enumerate(proposals,1):
                if len(p['scene_numbers'])!=(1 if j['kind']=='scene' else 0): raise ValueError('Alternatives are single images')
                if not p.get('prompt','').strip() or p['prompt']==j['prompt']: raise ValueError('Distinct alternative prompt required')
                state['jobs'].append({**copy.deepcopy(j), 'id':j['id']+f'-alt-{i}',
                    'parent_id':j['id'],'layout':'single','scene_numbers':p['scene_numbers'],
                    'prompt':p['prompt'],'status':'pending','next_after':0,'alternative_depth':1,
                    'history':[]})
            j['status']='superseded'
        else: raise ValueError('Invalid review decision')
    else: raise ValueError('Unknown action')
    j['history'].append({**event,'at':now})
    return state

def recipes(state, manifest):
    if state['source_hash']!=digest(manifest): raise ValueError('Manifest changed; do not reuse old images')
    if not summary(state)['complete']: raise ValueError('Incomplete images; cannot crop/publish as complete')
    result=[]
    for j in state['jobs']:
        if j['status']=='ready' and j['kind']=='scene':
            result.append({**j,'image_file':str(verify_file(j))})
    expected={n for g in manifest['grids'] for n in g['scene_numbers']}
    if {n for j in result for n in j['scene_numbers']}!=expected: raise ValueError('Missing scene mapping')
    return result

def state_path(manifest_path): return manifest_path.with_suffix('.recovery.json')

def update_file(path, operation):
    """Single-writer lock + atomic replace; interruptions never silently start another attempt."""
    path=Path(path); lock=path.with_suffix(path.suffix+'.lock')
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:
        current=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
        value=operation(current)
        temp=path.with_suffix(path.suffix+'.tmp')
        temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temp,path)
        return value
    finally:
        os.close(fd); lock.unlink()

def ensure_state(manifest_path):
    manifest_path=Path(manifest_path);manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    def ensure(old):
        if old is not None and old['source_hash']!=digest(manifest): raise ValueError('Use a new manifest path for a new revision')
        return old if old is not None else initialize(manifest)
    return update_file(state_path(manifest_path),ensure)

def main():
    parser=argparse.ArgumentParser(description='Native image recovery; no model/API calls')
    parser.add_argument('command',choices=['init','status','event'])
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--event',type=Path)
    args=parser.parse_args()
    if args.command=='init':state=ensure_state(args.manifest)
    elif args.command=='event':
        if not args.event:parser.error('--event required')
        event=json.loads(args.event.read_text(encoding='utf-8'))
        state=update_file(state_path(args.manifest),lambda s:transition(s,event))
    else:state=json.loads(state_path(args.manifest).read_text(encoding='utf-8'))
    print(json.dumps(summary(state),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
