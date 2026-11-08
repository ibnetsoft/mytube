"""Bind native timeline support to this particular worker lease."""
SUPPORTED = {'wuxia_cinematic/v1', 'wuxia_native_timeline/v6', 'wuxia_native_timeline/v1', 'wuxia_native_timeline/v2', 'wuxia_native_timeline/v3', 'wuxia_native_timeline/v4', 'wuxia_native_timeline/v5', 'wuxia_motion_auto/v1', 'wuxia_sword_aura/v1'}

def claim_acknowledgement(snapshot, metadata, token):
    required = metadata.get('required_worker_contract') or (metadata.get('input') or {}).get('required_worker_contract')
    timelines = [s['wuxia_timeline'] for s in snapshot.get('scenes', []) if s.get('wuxia_timeline')]
    if any(t.get('contract') not in SUPPORTED for t in timelines):
        raise ValueError('Unsupported frozen wuxia native timeline')
    if required:
        if required not in SUPPORTED or not timelines:
            raise ValueError('Unsupported required wuxia worker contract')
        if required=='wuxia_cinematic/v1' and not any(t.get('contract')=='wuxia_native_timeline/v6' and t.get('cinematic_plan') for t in timelines):raise ValueError('Cinematic contract lacks its frozen plan')
        if required=='wuxia_motion_auto/v1' and not any(t.get('auto_motion_policy',{}).get('actual_output_review_required') is True for t in timelines):
            raise ValueError('Automatic motion review contract has no matching scene policy')
        if required=='wuxia_sword_aura/v1' and not any(t.get('auto_motion_policy',{}).get('actual_output_review_required') is True and any(l.get('sword_aura') for s in t.get('states',[]) for l in s.get('ambient_loops',[])) for t in timelines):
            raise ValueError('Sword aura output review has no matching source-bound patches')
        return {'worker_contract_ack': {'contract': required, 'lease_token': token}}
    return {}
