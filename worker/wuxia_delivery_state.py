"""Derive the authorized episode endpoint from evidence, never preview flags."""
import hashlib
import json
from pathlib import Path

def delivery_state(directory):
    root=Path(directory)
    receipt_path=root/'packaging/registration-receipt.json'
    if not receipt_path.is_file():
        return {'complete':False,'next_stage':'continue_package_then_register'}
    receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
    saved_path=root/'packaging/registered-topic-readback.json'
    if not saved_path.is_file():
        return {'complete':False,'next_stage':'verify_registered_topic_readback'}
    saved=json.loads(saved_path.read_text(encoding='utf-8'))
    digest=hashlib.sha256(str(saved.get('pregenerated_script','')).encode()).hexdigest()
    scenes=(saved.get('pregenerated_structure') or {}).get('scenes',[])
    checks={
      'topic_id':bool(receipt.get('topic_id')) and receipt['topic_id']==saved.get('id'),
      'source_hash':bool(saved.get('pregenerated_script')) and receipt.get('script_sha256')==digest,
      'scenes':bool(scenes) and receipt.get('scene_count')==len(scenes),
      'readback':receipt.get('database_readback')=='exact_match',
      'web_ready':receipt.get('web_readiness',{}).get('ready') is True,
      'thumbnail':receipt.get('thumbnail_completed') is True,
    }
    complete=all(checks.values())
    return {'complete':complete,'topic_id':receipt.get('topic_id'),'checks':checks,
            'next_stage':'episode_delivery_complete' if complete else 'repair_delivery_evidence'}
