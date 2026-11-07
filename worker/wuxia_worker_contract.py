"""Bind native timeline support to this particular worker lease."""
SUPPORTED = {'wuxia_native_timeline/v1', 'wuxia_native_timeline/v2', 'wuxia_native_timeline/v3', 'wuxia_native_timeline/v4'}

def claim_acknowledgement(snapshot, metadata, token):
    required = metadata.get('required_worker_contract') or (metadata.get('input') or {}).get('required_worker_contract')
    timelines = [s['wuxia_timeline'] for s in snapshot.get('scenes', []) if s.get('wuxia_timeline')]
    if any(t.get('contract') not in SUPPORTED for t in timelines):
        raise ValueError('Unsupported frozen wuxia native timeline')
    if required:
        if required not in SUPPORTED or not timelines:
            raise ValueError('Unsupported required wuxia worker contract')
        return {'worker_contract_ack': {'contract': required, 'lease_token': token}}
    return {}
